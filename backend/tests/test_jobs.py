from sqlalchemy import select

from app import jobs
from app.models import Job


def test_enqueue_dedups_active_job(db):
    a, created_a = jobs.enqueue_sync(db, "tourist")
    b, created_b = jobs.enqueue_sync(db, "tourist")
    assert created_a and not created_b
    assert a.id == b.id
    assert len(db.scalars(select(Job)).all()) == 1


def test_running_job_is_reused(db):
    a, _ = jobs.enqueue_sync(db, "tourist")
    claimed = jobs.claim_next(db)
    assert claimed.id == a.id and claimed.status == "running"
    b, created = jobs.enqueue_sync(db, "tourist")
    assert not created and b.id == a.id


def test_finished_job_allows_new_one(db):
    a, _ = jobs.enqueue_sync(db, "tourist")
    jobs.claim_next(db)
    jobs.finish_job(db, a.id)
    db.expire_all()
    b, created = jobs.enqueue_sync(db, "tourist")
    assert created and b.id != a.id


def test_unique_index_backstops_a_race(db):
    """Simulate a racing insert that slipped past the first lookup."""
    db.add(Job(kind="sync", handle_key="petr", status="queued"))
    db.flush()
    original = jobs.find_active_job
    calls = {"n": 0}

    def blind_first(session, key, kind="sync"):
        calls["n"] += 1
        return None if calls["n"] == 1 else original(session, key, kind)

    jobs.find_active_job = blind_first
    try:
        job, created = jobs.enqueue_sync(db, "petr")
    finally:
        jobs.find_active_job = original
    assert not created and job.handle_key == "petr"
    assert len(db.scalars(select(Job)).all()) == 1


def test_queue_positions(db):
    a, _ = jobs.enqueue_sync(db, "a_user")
    b, _ = jobs.enqueue_sync(db, "b_user")
    c, _ = jobs.enqueue_sync(db, "c_user")
    assert [jobs.queue_position(db, j) for j in (a, b, c)] == [1, 2, 3]
    jobs.claim_next(db)
    db.refresh(a)
    assert jobs.queue_position(db, a) == 0
    assert jobs.queue_position(db, b) == 2  # running job is still ahead of b
    jobs.finish_job(db, a.id)
    db.refresh(a)
    assert jobs.queue_position(db, a) is None
    assert jobs.queue_position(db, b) == 1


def test_claim_order_is_fifo_and_stale_running_requeued(db):
    a, _ = jobs.enqueue_sync(db, "first")
    jobs.enqueue_sync(db, "second")
    assert jobs.claim_next(db).id == a.id
    assert jobs.requeue_stale_running(db) == 1
    db.expire_all()
    assert jobs.claim_next(db).id == a.id
