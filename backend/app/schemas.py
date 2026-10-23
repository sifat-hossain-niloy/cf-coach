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


# --- analytics building blocks ------------------------------------------------------------------


class RankOut(BaseModel):
    name: str
    color: str
    min_rating: int


class Level(BaseModel):
    value: int
    source: Literal["contest", "practice", "default"]
    note: str | None


class VerdictCounts(BaseModel):
    wa: int = 0
    tle: int = 0
    mle: int = 0
    re: int = 0


class TagStat(BaseModel):
    tag: str
    attempted: int
    solved: int
    solve_rate: float | None
    first_try_rate: float | None
    avg_wrong_before_ac: float | None
    median_rating_solved: int | None
    max_rating_solved: int | None
    verdicts: VerdictCounts


class BandStat(BaseModel):
    bucket: int  # e.g. 1700 covers ratings 1700..1799
    attempted: int = 0
    solved: int = 0
    solve_rate: float | None = None
    contest_attempted: int = 0
    contest_solved: int = 0
    practice_attempted: int = 0
    practice_solved: int = 0


class WeakTag(BaseModel):
    tag: str
    weakness: float
    importance: float
    success: float
    coverage: float
    attempted_in_band: int
    solved_in_band: int


class PracticePoint(BaseModel):
    time: int
    rating: int
    window: int  # how many solves the percentile used (< 30 early on)


class RatingPoint(BaseModel):
    contest_id: int
    contest_name: str
    time: int
    old_rating: int
    new_rating: int
    delta: int
    rank: int


class Counts(BaseModel):
    submissions: int
    attempted: int
    solved: int
    rated_solves: int
    rated_contests: int


class CoreAnalytics(BaseModel):
    """Everything computed after a sync, stored in analytics_cache (kind='core')."""

    version: int
    counts: Counts
    level: Level
    practice_rating: int | None
    practice_history: list[PracticePoint]
    tags: list[TagStat]
    bands: list[BandStat]
    band_lo: int
    band_hi: int
    prior: float
    weak: list[WeakTag]
    history: list[RatingPoint]


# --- endpoint responses ---------------------------------------------------------------------------


class Section(BaseModel):
    handle: str
    enough_data: bool
    message: str | None = None


class TagsOut(Section):
    tags: list[TagStat]


class BandsOut(Section):
    level: Level
    bands: list[BandStat]


class WeakOut(Section):
    level: Level
    band_lo: int
    band_hi: int
    prior: float
    smoothing_a: float
    coverage_full: int
    coverage_weight: float
    tags: list[WeakTag]


class ProgressOut(Section):
    rating: int | None
    max_rating: int | None
    rank: RankOut | None
    max_rank: RankOut | None
    level: Level
    target: int | None
    target_rank: RankOut | None
    gap: int | None
    history: list[RatingPoint]
    avg_delta_recent: float | None
    recent_contests: int
    contests_needed: int | None
    estimate_note: str
    practice_rating: int | None
    practice_history: list[PracticePoint]
    practice_message: str | None


class SummaryOut(BaseModel):
    handle: str
    avatar: str | None
    rating: int | None
    max_rating: int | None
    rank: RankOut | None  # None when unrated
    level: Level
    practice_rating: int | None
    target: int | None
    target_rank: RankOut | None
    gap: int | None
    top_weak: list[WeakTag]
    counts: Counts
    last_synced_at: datetime | None


class QueueItem(BaseModel):
    contest_id: int
    index: str
    name: str
    rating: int | None
    tags: list[str]
    source: Literal["A", "B", "C"]
    reason: str
    url: str
    solved: bool


class QueueOut(Section):
    date: str
    level: Level
    band_lo: int
    band_hi: int
    items: list[QueueItem]
