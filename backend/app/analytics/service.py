"""Glue between the DB and the pure analytics functions: load, compute, cache."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.analytics.dedup import aggregate, build_canonical_map
from app.analytics.practice import practice_rating, practice_timeline, solved_rated_in_order
from app.analytics.progress import determine_level
from app.analytics.stats import band_stats, tag_stats
from app.analytics.types import ProblemAgg, ProblemKey, Prob, Sub
from app.analytics.weakness import weakness_scores
from app.models import AnalyticsCache, Handle, Meta, Problem, ProblemTagBucket, RatingChange, Submission, utcnow
from app.schemas import CoreAnalytics, Counts, RatingPoint

CORE = "core"
_problem_cache: dict[str, object] = {}


@dataclass
class UserData:
    """A user's raw data plus the deduplicated per-problem view."""

    subs: list[Sub]
    history: list[RatingPoint]
    aggs: dict[ProblemKey, ProblemAgg]
    canon: dict[ProblemKey, ProblemKey]


# --- loading -------------------------------------------------------------------------------------


def load_problems(db: Session) -> list[Prob]:
    """All problemset problems, memoised per problemset refresh."""
    meta = db.get(Meta, "problemset_fetched_at")
    stamp = meta.updated_at.isoformat() if meta else ""
    if _problem_cache.get("stamp") != stamp:
        rows = db.scalars(select(Problem)).all()
        _problem_cache["problems"] = [
            Prob(r.contest_id, r.index, r.name, r.rating, tuple(r.tags or ()), r.solved_count)
            for r in rows
        ]
        _problem_cache["stamp"] = stamp
    return _problem_cache["problems"]  # type: ignore[return-value]


def load_bucket_counts(db: Session) -> dict[tuple[int, str], int]:
    return {(r.bucket, r.tag): r.count for r in db.scalars(select(ProblemTagBucket))}


def load_user(db: Session, handle_id: int, problems: list[Prob]) -> UserData:
    subs = [
        Sub(r.id, r.contest_id, r.problem_index, r.problem_name, r.problem_rating,
            tuple(r.tags or ()), r.verdict, r.participant_type, r.creation_time)
        for r in db.scalars(select(Submission).where(Submission.handle_id == handle_id))
    ]
    changes = db.scalars(
        select(RatingChange).where(RatingChange.handle_id == handle_id).order_by(RatingChange.update_time)
    ).all()
    history = [
        RatingPoint(
            contest_id=c.contest_id, contest_name=c.contest_name, time=c.update_time,
            old_rating=c.old_rating, new_rating=c.new_rating,
            delta=c.new_rating - c.old_rating, rank=c.rank,
        )
        for c in changes
    ]
    refs = [(p.key, p.name, p.rating) for p in problems] + [(s.key, s.name, s.rating) for s in subs]
    canon = build_canonical_map(refs)
    return UserData(subs=subs, history=history, aggs=aggregate(subs, canon), canon=canon)


# --- computing -----------------------------------------------------------------------------------


def target_band(level: int) -> tuple[int, int]:
    return level + config.TARGET_BAND_LO_OFFSET, level + config.TARGET_BAND_HI_OFFSET


def compute_core(user: UserData, rating: int | None, bucket_counts: dict[tuple[int, str], int]) -> CoreAnalytics:
    """All cached analytics for one user (pure given its inputs)."""
    aggs = list(user.aggs.values())
    rated_solves = len(solved_rated_in_order(aggs))
    practice = practice_rating(aggs)
    level = determine_level(rating, len(user.history), practice, rated_solves)
    lo, hi = target_band(level.value)
    weak, prior = weakness_scores(aggs, bucket_counts, lo, hi)
    return CoreAnalytics(
        version=config.ANALYTICS_VERSION,
        counts=Counts(
            submissions=len(user.subs),
            attempted=sum(a.attempted for a in aggs),
            solved=sum(a.solved for a in aggs),
            rated_solves=rated_solves,
            rated_contests=len(user.history),
        ),
        level=level,
        practice_rating=practice,
        practice_history=practice_timeline(aggs),
        tags=tag_stats(aggs),
        bands=band_stats(aggs),
        band_lo=lo,
        band_hi=hi,
        prior=prior,
        weak=weak,
        history=user.history,
    )


# --- cache -----------------------------------------------------------------------------------------


def refresh_analytics(db: Session, handle_id: int) -> CoreAnalytics:
    """Recompute and cache a handle's analytics (called by the worker after each sync)."""
    handle = db.get(Handle, handle_id)
    user = load_user(db, handle_id, load_problems(db))
    core = compute_core(user, handle.rating, load_bucket_counts(db))
    row = db.get(AnalyticsCache, (handle_id, CORE))
    payload = core.model_dump(mode="json")
    if row is None:
        db.add(AnalyticsCache(handle_id=handle_id, kind=CORE, payload=payload, computed_at=utcnow()))
    else:
        row.payload, row.computed_at = payload, utcnow()
    db.flush()
    return core


def get_core(db: Session, handle: Handle) -> CoreAnalytics:
    """Cached analytics; recomputed from stored data if missing or from an older version."""
    row = db.get(AnalyticsCache, (handle.id, CORE))
    if row is not None and (row.payload or {}).get("version") == config.ANALYTICS_VERSION:
        return CoreAnalytics.model_validate(row.payload)
    return refresh_analytics(db, handle.id)
