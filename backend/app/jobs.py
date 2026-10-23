"""DB-backed job queue: enqueue with deduplication, queue position, claiming, completion."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ACTIVE_JOB_STATUSES, Job, utcnow

SYNC = "sync"


def find_active_job(db: Session, key: str, kind: str = SYNC) -> Job | None:
    """The queued or running job for this handle, if any."""
    stmt = select(Job).where(
        Job.kind == kind, Job.handle_key == key, Job.status.in_(ACTIVE_JOB_STATUSES)
    )
    return db.scalars(stmt).first()


def enqueue_sync(db: Session, key: str) -> tuple[Job, bool]:
    """Return (job, created). An existing queued/running job for the handle is reused.

    The partial unique index on active jobs makes concurrent enqueues safe: the loser of
    a race gets an IntegrityError and returns the winner's job instead.
    """
    existing = find_active_job(db, key)
    if existing is not None:
        return existing, False
    job = Job(kind=SYNC, handle_key=key, status="queued", stage="Waiting in line")
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        existing = find_active_job(db, key)
        if existing is None:
            raise
        return existing, False
    return job, True


def queue_position(db: Session, job: Job) -> int | None:
    """1-based place in line for a queued job (the running job counts as ahead).

    0 means the job is running now; None means it has finished.
    """
    if job.status == "running":
        return 0
    if job.status != "queued":
        return None
    ahead = db.scalar(
        select(func.count()).select_from(Job).where(
            (Job.status == "running") | ((Job.status == "queued") & (Job.id < job.id))
        )
    )
    return int(ahead or 0) + 1


def claim_next(db: Session) -> Job | None:
    """Atomically take the oldest queued job and mark it running."""
    stmt = (
        select(Job)
        .where(Job.status == "queued")
        .order_by(Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = db.scalars(stmt).first()
    if job is None:
        return None
    job.status = "running"
    job.started_at = utcnow()
    job.stage = "Starting"
    db.flush()
    return job


def set_stage(db: Session, job_id: int, stage: str) -> None:
    db.execute(update(Job).where(Job.id == job_id).values(stage=stage))


def finish_job(
    db: Session, job_id: int, error: str | None = None, error_code: str | None = None
) -> None:
    """Mark a job done, or failed when `error` is given."""
    db.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(
            status="failed" if error else "done",
            error=error,
            error_code=error_code,
            stage=None if error else "Done",
            finished_at=utcnow(),
        )
    )


def requeue_stale_running(db: Session) -> int:
    """On worker start, put jobs left 'running' by a crashed worker back in the queue."""
    result = db.execute(
        update(Job).where(Job.status == "running").values(status="queued", stage="Waiting in line")
    )
    return result.rowcount or 0


def prune_finished(db: Session, older_than: timedelta = timedelta(days=2)) -> None:
    """Delete finished jobs older than `older_than`."""
    db.execute(
        delete(Job).where(
            Job.status.in_(("done", "failed")), Job.finished_at < utcnow() - older_than
        )
    )
