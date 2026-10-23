"""Single asyncio worker: claims sync jobs from the DB and runs them one at a time.

Only one worker may run. A Postgres advisory lock enforces that, so the in-process
RateLimiter is the one global limiter for every Codeforces request the server makes.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from sqlalchemy import text

from app import config, iplimit, jobs
from app.analytics.service import refresh_analytics
from app.cf.client import CFError, CFUnavailable, CodeforcesClient, make_http_client
from app.cf.ratelimit import RateLimiter
from app.config import get_settings
from app.db import get_engine, session_scope
from app.sync import SyncFailed, run_sync

log = logging.getLogger("cfcoach.worker")

ADVISORY_LOCK_ID = 0xCFC0AC4  # arbitrary, constant
IDLE_POLL_S = 1.0
PRUNE_EVERY = 300


async def process_one(client: CodeforcesClient) -> bool:
    """Run the next queued job, if any. Returns True when a job was processed."""
    with session_scope() as db:
        job = jobs.claim_next(db)
        if job is None:
            return False
        job_id, key = job.id, job.handle_key
    log.info("job %d: sync %s", job_id, key)
    try:
        await run_sync(client, session_scope, job_id, key, after_sync=refresh_analytics)
    except SyncFailed as exc:
        _fail(job_id, str(exc), exc.code)
    except CFUnavailable as exc:
        _fail(job_id, exc.comment, "cf_unavailable")
    except CFError as exc:
        _fail(job_id, f"Codeforces error: {exc.comment}", "cf_error")
    except Exception:  # noqa: BLE001 - a worker must survive any single job
        log.exception("job %d crashed", job_id)
        _fail(job_id, "Internal error while syncing. Please try again later.", "internal")
    else:
        with session_scope() as db:
            jobs.finish_job(db, job_id)
    return True


def _fail(job_id: int, message: str, code: str) -> None:
    log.warning("job %d failed: %s (%s)", job_id, message, code)
    with session_scope() as db:
        jobs.finish_job(db, job_id, error=message, error_code=code)


async def run_forever(stop: asyncio.Event) -> None:
    settings = get_settings()
    engine = get_engine()
    lock_conn = None
    if engine.dialect.name == "postgresql":
        lock_conn = engine.connect()
        got = lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_ID}).scalar()
        if not got:
            log.error("another worker holds the lock; exiting so only one worker talks to Codeforces")
            return
    with session_scope() as db:
        n = jobs.requeue_stale_running(db)
        if n:
            log.info("re-queued %d stale running jobs", n)

    limiter = RateLimiter(config.CF_MIN_INTERVAL_S)
    async with make_http_client(settings.user_agent) as http:
        client = CodeforcesClient(http, limiter, base_url=settings.cf_base_url)
        ticks = 0
        log.info("worker ready")
        while not stop.is_set():
            worked = await process_one(client)
            ticks += 1
            if ticks % PRUNE_EVERY == 0:
                with session_scope() as db:
                    jobs.prune_finished(db)
                    iplimit.prune(db)
            if not worked:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=IDLE_POLL_S)
                except TimeoutError:
                    pass
    if lock_conn is not None:
        lock_conn.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    loop = asyncio.new_event_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    loop.run_until_complete(run_forever(stop))


if __name__ == "__main__":
    main()
