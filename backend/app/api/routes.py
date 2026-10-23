"""HTTP routes. None of these call Codeforces; they read the DB and enqueue jobs."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, iplimit, jobs
from app.config import get_settings
from app.db import get_db
from app.handles import handle_key, is_valid_handle
from app.models import Handle, Job, Meta, as_utc, utcnow
from app.schemas import HealthOut, JobOut, SyncOut
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
    return HTTPException(404, f"Handle '{handle}' was not found on Codeforces.")


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
