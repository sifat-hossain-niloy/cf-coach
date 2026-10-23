"""SQLAlchemy models. JSON columns (not ARRAY) keep the schema portable to SQLite for tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; treat naive datetimes as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class Handle(Base):
    __tablename__ = "handles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    handle_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_handle: Mapped[str] = mapped_column(String(32))
    rating: Mapped[int | None] = mapped_column(Integer)
    max_rating: Mapped[int | None] = mapped_column(Integer)
    rank: Mapped[str | None] = mapped_column(String(64))
    max_rank: Mapped[str | None] = mapped_column(String(64))
    avatar: Mapped[str | None] = mapped_column(Text)
    newest_submission_id: Mapped[int | None] = mapped_column(BigInteger)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    not_found_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    handle_id: Mapped[int] = mapped_column(ForeignKey("handles.id", ondelete="CASCADE"), index=True)
    contest_id: Mapped[int] = mapped_column(Integer)
    problem_index: Mapped[str] = mapped_column(String(16))
    problem_name: Mapped[str] = mapped_column(Text)
    problem_rating: Mapped[int | None] = mapped_column(Integer)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    verdict: Mapped[str | None] = mapped_column(String(48))
    participant_type: Mapped[str | None] = mapped_column(String(32))
    creation_time: Mapped[int] = mapped_column(BigInteger)


class RatingChange(Base):
    __tablename__ = "rating_changes"

    handle_id: Mapped[int] = mapped_column(
        ForeignKey("handles.id", ondelete="CASCADE"), primary_key=True
    )
    contest_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    contest_name: Mapped[str] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer)
    old_rating: Mapped[int] = mapped_column(Integer)
    new_rating: Mapped[int] = mapped_column(Integer)
    update_time: Mapped[int] = mapped_column(BigInteger)


class Problem(Base):
    __tablename__ = "problems"

    contest_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    index: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    solved_count: Mapped[int] = mapped_column(Integer, default=0)


class ProblemTagBucket(Base):
    """Global per-(rating bucket, tag) problem counts. tag '__total__' holds the bucket total."""

    __tablename__ = "problem_tag_buckets"

    bucket: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    tag: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


class Meta(Base):
    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalyticsCache(Base):
    __tablename__ = "analytics_cache"

    handle_id: Mapped[int] = mapped_column(
        ForeignKey("handles.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload: Mapped[Any] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


ACTIVE_JOB_STATUSES = ("queued", "running")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), default="sync")
    handle_key: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    stage: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # At most one active sync job per handle: the backstop for enqueue races.
        Index(
            "uq_jobs_active_handle",
            "kind",
            "handle_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )


class SyncRequest(Base):
    __tablename__ = "sync_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
