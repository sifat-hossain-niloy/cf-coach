"""Per-IP sync rate limit, stored in the DB so it holds across API processes."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import IP_SYNC_LIMIT_PER_HOUR
from app.models import SyncRequest, utcnow

WINDOW = timedelta(hours=1)


def check_and_record(db: Session, ip: str, limit: int = IP_SYNC_LIMIT_PER_HOUR) -> bool:
    """Record a sync request for `ip`. Returns False (and records nothing) when over the limit."""
    since = utcnow() - WINDOW
    used = db.scalar(
        select(func.count())
        .select_from(SyncRequest)
        .where(SyncRequest.ip == ip, SyncRequest.created_at >= since)
    )
    if (used or 0) >= limit:
        return False
    db.add(SyncRequest(ip=ip))
    db.flush()
    return True


def prune(db: Session) -> None:
    db.execute(delete(SyncRequest).where(SyncRequest.created_at < utcnow() - WINDOW))
