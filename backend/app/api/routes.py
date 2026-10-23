"""HTTP routes. None of these call Codeforces; they read the DB and enqueue jobs."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, iplimit, jobs
from app.config import get_settings
from app.db import get_db
from app.handles import handle_key, is_valid_handle
from app.models import Handle, Job, Meta, as_utc, utcnow
from app.analytics import service
from app.analytics.progress import choose_target, contests_needed, recent_average_delta
from app.analytics.weakness import weakness_scores
from app.ranks import rank_for
from app.schemas import (
    BandsOut,
    CoreAnalytics,
    HealthOut,
    JobOut,
    ProgressOut,
    RankOut,
    SummaryOut,
    SyncOut,
    TagsOut,
    WeakOut,
)
from app.sync import PROBLEMSET_META_KEY

router = APIRouter(prefix="/api")


def client_ip(request: Request) -> str:
    """Caller IP; X-Real-IP is trusted only behind our own proxy (CFC_TRUST_PROXY)."""
    if get_settings().trust_proxy:
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()
    return request.client.host if request.client else "unknown"


def validated_key(handle: str) -> str:
    if not is_valid_handle(handle):
        raise HTTPException(
            422,
            "Invalid handle: use 3 to 24 letters, digits, underscores, dots or hyphens.",
        )
    return handle_key(handle)


def find_handle(db: Session, key: str) -> Handle | None:
    return db.scalars(select(Handle).where(Handle.handle_key == key)).first()


def recently_not_found(handle: Handle | None) -> bool:
    if handle is None or handle.not_found_at is None:
        return False
    age = utcnow() - as_utc(handle.not_found_at)
    return age < timedelta(minutes=config.NOT_FOUND_CACHE_MINUTES)


def is_fresh(handle: Handle | None) -> bool:
    if handle is None or handle.last_synced_at is None:
        return False
    age = utcnow() - as_utc(handle.last_synced_at)
    return age < timedelta(minutes=config.SYNC_FRESH_MINUTES)


def job_out(db: Session, job: Job) -> JobOut:
    handle = find_handle(db, job.handle_key)
    return JobOut(
        id=job.id,
        handle=handle.display_handle if handle else job.handle_key,
        status=job.status,  # type: ignore[arg-type]
        position=jobs.queue_position(db, job),
        stage=job.stage,
        error=job.error,
        error_code=job.error_code,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def not_found(handle: str) -> HTTPException:
    return HTTPException(
        404, {"code": "not_found", "message": f"Handle '{handle}' was not found on Codeforces."}
    )


def synced_handle(db: Session, handle: str) -> Handle:
    """The stored handle, or a 404 explaining whether it doesn't exist or isn't synced yet."""
    key = validated_key(handle)
    row = find_handle(db, key)
    if recently_not_found(row) and (row.last_synced_at is None):
        raise not_found(handle)
    if row is None or row.last_synced_at is None:
        raise HTTPException(
            404, {"code": "not_synced", "message": f"No data for '{handle}' yet. Start a sync first."}
        )
    return row


def rank_out(rating: int | None) -> RankOut | None:
    if rating is None:
        return None
    r = rank_for(rating)
    return RankOut(name=r.name, color=r.color, min_rating=max(r.min_rating, 0))


NOT_ENOUGH = "Not enough data yet. Solve a few more problems and sync again."
TargetQuery = Query(None, ge=0, le=5000, description="Override the target rating")


@router.post("/handles/{handle}/sync", response_model=SyncOut)
def sync_handle(handle: str, request: Request, db: Session = Depends(get_db)) -> SyncOut:
    """Enqueue a sync, or return the cached state if synced in the last 10 minutes."""
    key = validated_key(handle)
    row = find_handle(db, key)
    if recently_not_found(row):
        raise not_found(handle)
    display = row.display_handle if row and row.last_synced_at else handle
    if is_fresh(row):
        return SyncOut(handle=display, cached=True, last_synced_at=row.last_synced_at, job=None)

    active = jobs.find_active_job(db, key)
    if active is None and not iplimit.check_and_record(db, client_ip(request)):
        raise HTTPException(429, "Too many sync requests from your network. Try again later.")
    job, _created = jobs.enqueue_sync(db, key)
    return SyncOut(
        handle=display,
        cached=False,
        last_synced_at=row.last_synced_at if row else None,
        job=job_out(db, job),
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    return job_out(db, job)


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    queued = db.scalar(select(func.count()).select_from(Job).where(Job.status == "queued"))
    meta = db.get(Meta, PROBLEMSET_META_KEY)
    return HealthOut(
        status="ok",
        db=True,
        queued_jobs=int(queued or 0),
        problemset_fetched_at=meta.updated_at if meta else None,
    )


def _current(handle: Handle, core: CoreAnalytics) -> int:
    """The rating progress is measured from: contest rating, or the level for unrated users."""
    return handle.rating if handle.rating is not None and core.counts.rated_contests else core.level.value


@router.get("/handles/{handle}/summary", response_model=SummaryOut)
def summary(handle: str, target: int | None = TargetQuery, db: Session = Depends(get_db)) -> SummaryOut:
    """Profile, rank, target, gap, top 3 weak tags, last synced time."""
    row = synced_handle(db, handle)
    core = service.get_core(db, row)
    current = _current(row, core)
    tgt = choose_target(current, target)
    rated = row.rating if core.counts.rated_contests else None
    return SummaryOut(
        handle=row.display_handle,
        avatar=row.avatar,
        rating=rated,
        max_rating=row.max_rating if rated is not None else None,
        rank=rank_out(rated),
        level=core.level,
        practice_rating=core.practice_rating,
        target=tgt,
        target_rank=rank_out(tgt),
        gap=(tgt - current) if tgt is not None else None,
        top_weak=core.weak[:3],
        counts=core.counts,
        last_synced_at=row.last_synced_at,
    )


@router.get("/handles/{handle}/tags", response_model=TagsOut)
def tags(handle: str, db: Session = Depends(get_db)) -> TagsOut:
    row = synced_handle(db, handle)
    core = service.get_core(db, row)
    enough = core.counts.attempted >= config.MIN_SUBMISSIONS_FOR_DATA
    return TagsOut(handle=row.display_handle, enough_data=enough,
                   message=None if enough else NOT_ENOUGH, tags=core.tags)


@router.get("/handles/{handle}/bands", response_model=BandsOut)
def bands(handle: str, db: Session = Depends(get_db)) -> BandsOut:
    row = synced_handle(db, handle)
    core = service.get_core(db, row)
    enough = sum(b.attempted for b in core.bands) >= config.MIN_SUBMISSIONS_FOR_DATA
    return BandsOut(handle=row.display_handle, enough_data=enough,
                    message=None if enough else NOT_ENOUGH, level=core.level, bands=core.bands)


@router.get("/handles/{handle}/weak", response_model=WeakOut)
def weak(
    handle: str,
    band_lo: int | None = Query(None, ge=0, le=5000),
    band_hi: int | None = Query(None, ge=0, le=5000),
    db: Session = Depends(get_db),
) -> WeakOut:
    """Top weak tags with every score component. band_lo/band_hi override the default band."""
    row = synced_handle(db, handle)
    core = service.get_core(db, row)
    lo, hi, tags_, prior = core.band_lo, core.band_hi, core.weak, core.prior
    if band_lo is not None or band_hi is not None:
        lo = band_lo if band_lo is not None else core.band_lo
        hi = band_hi if band_hi is not None else max(core.band_hi, lo)
        if lo > hi:
            raise HTTPException(422, "band_lo must be <= band_hi")
        user = service.load_user(db, row.id, service.load_problems(db))
        tags_, prior = weakness_scores(user.aggs.values(), service.load_bucket_counts(db), lo, hi)
    enough = core.counts.attempted >= config.MIN_SUBMISSIONS_FOR_DATA and bool(tags_)
    return WeakOut(
        handle=row.display_handle, enough_data=enough, message=None if enough else NOT_ENOUGH,
        level=core.level, band_lo=lo, band_hi=hi, prior=prior,
        smoothing_a=config.WEAKNESS_SMOOTHING_A, coverage_full=config.WEAKNESS_COVERAGE_FULL,
        coverage_weight=config.WEAKNESS_COVERAGE_WEIGHT, tags=tags_,
    )


@router.get("/handles/{handle}/progress", response_model=ProgressOut)
def progress(handle: str, target: int | None = TargetQuery, db: Session = Depends(get_db)) -> ProgressOut:
    row = synced_handle(db, handle)
    core = service.get_core(db, row)
    current = _current(row, core)
    tgt = choose_target(current, target)
    gap = (tgt - current) if tgt is not None else None
    recent = core.history[-config.PROGRESS_RECENT_CONTESTS:]
    avg = recent_average_delta(core.history)
    needed, note = contests_needed(gap, avg)
    rated = core.counts.rated_contests > 0
    practice_msg = None
    if core.counts.rated_solves < config.MIN_RATED_SOLVES_FOR_LEVEL:
        practice_msg = (
            f"Practice rating needs more data: {core.counts.rated_solves} rated problems solved so far."
        )
    return ProgressOut(
        handle=row.display_handle,
        enough_data=rated,
        message=None if rated else "No rated contests yet. Your rating history will appear here.",
        rating=row.rating if rated else None,
        max_rating=row.max_rating if rated else None,
        rank=rank_out(row.rating) if rated else None,
        max_rank=rank_out(row.max_rating) if rated else None,
        level=core.level,
        target=tgt,
        target_rank=rank_out(tgt),
        gap=gap,
        history=core.history,
        avg_delta_recent=avg,
        recent_contests=len(recent),
        contests_needed=needed,
        estimate_note=note,
        practice_rating=core.practice_rating,
        practice_history=core.practice_history,
        practice_message=practice_msg,
    )
