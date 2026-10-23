"""One sync job: Codeforces → DB → analytics cache. Runs only inside the worker."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app import config, jobs
from app.analytics.importance import bucket_tag_counts
from app.cf.client import CFNotFound, CodeforcesClient
from app.models import Handle, Meta, Problem, ProblemTagBucket, RatingChange, Submission, as_utc, utcnow

log = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractContextManager[Session]]
PROBLEMSET_META_KEY = "problemset_fetched_at"
PENDING_VERDICTS = (None, "TESTING")


class SyncFailed(Exception):
    """A sync failed in a way the user should see (`code` is machine-readable)."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


# --- parsing (pure) ----------------------------------------------------------------------------


def parse_submission(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Flatten a user.status item into a Submission row; None for gym or contest-less entries."""
    problem = raw.get("problem") or {}
    contest_id = problem.get("contestId", raw.get("contestId"))
    if contest_id is None or contest_id >= config.GYM_CONTEST_MIN_ID:
        return None
    return {
        "id": raw["id"],
        "contest_id": contest_id,
        "problem_index": problem.get("index", ""),
        "problem_name": problem.get("name", ""),
        "problem_rating": problem.get("rating"),
        "tags": list(problem.get("tags") or []),
        "verdict": raw.get("verdict"),
        "participant_type": (raw.get("author") or {}).get("participantType"),
        "creation_time": raw.get("creationTimeSeconds", 0),
    }


def parse_problemset(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge problems with their solvedCount; drop gym and contest-less problems."""
    solved = {
        (s.get("contestId"), s.get("index")): s.get("solvedCount", 0)
        for s in result.get("problemStatistics", [])
    }
    rows: dict[tuple[int, str], dict[str, Any]] = {}
    for p in result.get("problems", []):
        cid = p.get("contestId")
        if cid is None or cid >= config.GYM_CONTEST_MIN_ID:
            continue
        key = (cid, p["index"])
        rows[key] = {
            "contest_id": cid,
            "index": p["index"],
            "name": p.get("name", ""),
            "rating": p.get("rating"),
            "tags": list(p.get("tags") or []),
            "solved_count": solved.get(key, 0),
        }
    return list(rows.values())


def parse_rating_change(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "contest_id": raw["contestId"],
        "contest_name": raw.get("contestName", ""),
        "rank": raw.get("rank", 0),
        "old_rating": raw.get("oldRating", 0),
        "new_rating": raw.get("newRating", 0),
        "update_time": raw.get("ratingUpdateTimeSeconds", 0),
    }


# --- DB helpers ----------------------------------------------------------------------------------


def upsert(db: Session, model: type, rows: list[dict[str, Any]], keys: list[str]) -> None:
    """INSERT ... ON CONFLICT (keys) DO UPDATE for Postgres or SQLite."""
    if not rows:
        return
    dialect = db.get_bind().dialect.name
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    for i in range(0, len(rows), 1000):
        chunk = rows[i : i + 1000]
        stmt = insert(model).values(chunk)
        updates = {c: stmt.excluded[c] for c in chunk[0] if c not in keys}
        stmt = stmt.on_conflict_do_update(index_elements=keys, set_=updates) if updates else (
            stmt.on_conflict_do_nothing(index_elements=keys)
        )
        db.execute(stmt)


def problemset_is_stale(db: Session, now: datetime | None = None) -> bool:
    meta = db.get(Meta, PROBLEMSET_META_KEY)
    if meta is None:
        return True
    age = (now or utcnow()) - as_utc(meta.updated_at)
    return age > timedelta(hours=config.PROBLEMSET_MAX_AGE_HOURS)


def store_problemset(db: Session, rows: list[dict[str, Any]]) -> None:
    """Replace the problemset and recompute global (bucket, tag) counts."""
    db.execute(delete(Problem))
    upsert(db, Problem, rows, ["contest_id", "index"])
    db.execute(delete(ProblemTagBucket))
    counts = bucket_tag_counts((r["rating"], r["tags"]) for r in rows)
    db.add_all(ProblemTagBucket(bucket=b, tag=t, count=n) for (b, t), n in counts.items())
    meta = db.get(Meta, PROBLEMSET_META_KEY)
    if meta is None:
        db.add(Meta(key=PROBLEMSET_META_KEY, value=str(len(rows)), updated_at=utcnow()))
    else:
        meta.value, meta.updated_at = str(len(rows)), utcnow()


def mark_not_found(db: Session, key: str) -> None:
    handle = db.scalars(select(Handle).where(Handle.handle_key == key)).first()
    if handle is None:
        db.add(Handle(handle_key=key, display_handle=key, not_found_at=utcnow()))
    else:
        handle.not_found_at = utcnow()


def upsert_handle(db: Session, user: dict[str, Any], key: str) -> Handle:
    """Store under the key the user asked for (an old, renamed handle still resolves on Codeforces)."""
    handle = db.scalars(select(Handle).where(Handle.handle_key == key)).first()
    if handle is None:
        handle = Handle(handle_key=key, display_handle=user["handle"])
        db.add(handle)
    handle.display_handle = user["handle"]
    handle.rating = user.get("rating")
    handle.max_rating = user.get("maxRating")
    handle.rank = user.get("rank")
    handle.max_rank = user.get("maxRank")
    handle.avatar = user.get("titlePhoto") or user.get("avatar")
    handle.not_found_at = None
    db.flush()
    return handle


def resume_point(db: Session, handle: Handle) -> int | None:
    """Stop paging at submissions with id <= this. Pending (TESTING) submissions are re-fetched."""
    if handle.newest_submission_id is None:
        return None
    pending_min = db.scalar(
        select(func.min(Submission.id)).where(
            Submission.handle_id == handle.id,
            Submission.verdict.is_(None) | (Submission.verdict == "TESTING"),
        )
    )
    if pending_min is not None:
        return min(handle.newest_submission_id, pending_min - 1)
    return handle.newest_submission_id


# --- the sync ------------------------------------------------------------------------------------


async def fetch_new_submissions(
    client: CodeforcesClient,
    handle: str,
    stop_at: int | None,
    on_page: Callable[[int], None] = lambda page: None,
    page_size: int = config.CF_STATUS_PAGE_SIZE,
) -> tuple[list[dict[str, Any]], int | None]:
    """Page user.status newest-first until a known id (<= stop_at) or the end appears.

    Returns (raw submissions newer than stop_at, newest id seen).
    """
    collected: list[dict[str, Any]] = []
    newest: int | None = None
    start = 1
    page_no = 1
    while True:
        on_page(page_no)
        page = await client.user_status(handle, start, page_size)
        if page and newest is None:
            newest = page[0]["id"]
        fresh = [s for s in page if stop_at is None or s["id"] > stop_at]
        collected.extend(fresh)
        if len(fresh) < len(page) or len(page) < page_size:
            break
        start += page_size
        page_no += 1
    return collected, newest


async def run_sync(
    client: CodeforcesClient,
    session: SessionFactory,
    job_id: int,
    key: str,
    after_sync: Callable[[Session, int], None] | None = None,
) -> None:
    """Sync one handle end to end. Raises SyncFailed for user-facing failures."""

    def stage(text: str) -> None:
        with session() as db:
            jobs.set_stage(db, job_id, text)

    stage("Looking up handle")
    try:
        users = await client.user_info([key])
    except CFNotFound as exc:
        with session() as db:
            mark_not_found(db, key)
        raise SyncFailed(f"Handle '{key}' was not found on Codeforces", "not_found") from exc
    user = users[0]
    canonical = user["handle"]

    with session() as db:
        handle = upsert_handle(db, user, key.lower())
        handle_id = handle.id
        stop_at = resume_point(db, handle)
        prev_newest = handle.newest_submission_id

    stage("Fetching rating history")
    ratings = [parse_rating_change(r) for r in await client.user_rating(canonical)]
    with session() as db:
        db.execute(delete(RatingChange).where(RatingChange.handle_id == handle_id))
        db.add_all(RatingChange(handle_id=handle_id, **r) for r in ratings)

    raw, newest = await fetch_new_submissions(
        client, canonical, stop_at, on_page=lambda n: stage(f"Fetching submissions (page {n})")
    )
    rows = [r for r in (parse_submission(s) for s in raw) if r is not None]
    for r in rows:
        r["handle_id"] = handle_id
    with session() as db:
        upsert(db, Submission, rows, ["id"])
        h = db.get(Handle, handle_id)
        candidates = [x for x in (prev_newest, newest) if x is not None]
        h.newest_submission_id = max(candidates) if candidates else None

    with session() as db:
        stale = problemset_is_stale(db)
    if stale:
        stage("Refreshing the shared problemset")
        problems = parse_problemset(await client.problemset_problems())
        with session() as db:
            store_problemset(db, problems)

    stage("Crunching the numbers")
    with session() as db:
        if after_sync is not None:
            after_sync(db, handle_id)
        db.get(Handle, handle_id).last_synced_at = utcnow()
    log.info("synced %s: %d new submissions, %d rated contests", canonical, len(rows), len(ratings))
