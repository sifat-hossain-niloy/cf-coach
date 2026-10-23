"""Pydantic response models (the OpenAPI schema the frontend types are generated from)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

JobStatus = Literal["queued", "running", "done", "failed"]


class JobOut(BaseModel):
    id: int
    handle: str
    status: JobStatus
    position: int | None  # 1-based place in line; 0 = running now; None = finished
    stage: str | None
    error: str | None
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None


class SyncOut(BaseModel):
    handle: str
    cached: bool  # True when synced < 10 minutes ago and no job was created
    last_synced_at: datetime | None
    job: JobOut | None


class HealthOut(BaseModel):
    status: Literal["ok"]
    db: bool
    queued_jobs: int
    problemset_fetched_at: datetime | None
