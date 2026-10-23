import pytest
from sqlalchemy import func, select

from app import jobs
from app.models import Handle, Problem, ProblemTagBucket, RatingChange, Submission
from app.sync import SyncFailed, fetch_new_submissions, parse_problemset, parse_submission, run_sync
from tests.conftest import FakeCF, load_fixture


def sub(id_, cid=1, idx="A", verdict="OK", rating=800, tags=("math",), ptype="PRACTICE", name=None):
    return {
        "id": id_,
        "contestId": cid,
        "creationTimeSeconds": 1_600_000_000 + id_,
        "problem": {"contestId": cid, "index": idx, "name": name or f"P{cid}{idx}",
                    "rating": rating, "tags": list(tags)},
        "author": {"participantType": ptype},
        "verdict": verdict,
    }


def test_parse_submission_skips_gym_and_keeps_fields():
    assert parse_submission(sub(1, cid=100500)) is None
    row = parse_submission(load_fixture("user_status_tourist_40.json")["result"][0])
    assert row["contest_id"] == 2261 and row["problem_index"] == "H"
    assert row["participant_type"] == "CONTESTANT" and row["verdict"] == "OK"
    assert "trees" in row["tags"]


def test_parse_problemset_joins_solved_count():
    rows = parse_problemset(load_fixture("problemset_sample.json")["result"])
    by_key = {(r["contest_id"], r["index"]): r for r in rows}
    assert by_key[(2276, "G")]["solved_count"] == 192
    assert by_key[(2214, "J")]["rating"] is None


async def test_paging_stops_at_known_submission():
    subs = [sub(i) for i in range(2500, 0, -1)]  # newest first
    cf = FakeCF(submissions={"x": subs})
    fresh, newest = await fetch_new_submissions(cf, "x", stop_at=2200, page_size=100)
    assert newest == 2500
    assert [s["id"] for s in fresh] == list(range(2500, 2200, -1))
    assert len([c for c in cf.calls if c[0] == "user.status"]) == 4  # pages 1..4; page 4 hits 2200


async def test_paging_fetches_full_history_in_chunks():
    subs = [sub(i) for i in range(2500, 0, -1)]
    cf = FakeCF(submissions={"x": subs})
    fresh, _ = await fetch_new_submissions(cf, "x", stop_at=None, page_size=1000)
    assert len(fresh) == 2500
    assert [c[1][1] for c in cf.calls] == [1, 1001, 2001]


def _cf_world():
    info = load_fixture("user_info_tourist.json")["result"][0]
    return FakeCF(
        users={"tourist": info},
        submissions={"tourist": [sub(5, cid=3, verdict="OK"), sub(4, cid=3, verdict="WRONG_ANSWER"),
                                 sub(3, cid=100001), sub(2, cid=2, idx="B", verdict="TESTING"),
                                 sub(1, cid=1)]},
        ratings={"tourist": load_fixture("user_rating_tourist_last15.json")["result"]},
        problemset=load_fixture("problemset_sample.json")["result"],
    )


async def test_full_sync_stores_everything(session_factory):
    cf = _cf_world()
    with session_factory() as db:
        job, _ = jobs.enqueue_sync(db, "tourist")
    await run_sync(cf, session_factory, job.id, "TOURIST")
    with session_factory() as db:
        h = db.scalars(select(Handle)).one()
        assert h.display_handle == "tourist" and h.handle_key == "tourist"
        assert h.newest_submission_id == 5 and h.last_synced_at is not None
        assert db.scalar(select(func.count()).select_from(Submission)) == 4  # gym dropped
        assert db.scalar(select(func.count()).select_from(RatingChange)) == 15
        assert db.scalar(select(func.count()).select_from(Problem)) > 400
        assert db.scalar(select(func.count()).select_from(ProblemTagBucket)) > 0


async def test_incremental_sync_refetches_pending_and_skips_problemset(session_factory):
    cf = _cf_world()
    with session_factory() as db:
        job, _ = jobs.enqueue_sync(db, "tourist")
    await run_sync(cf, session_factory, job.id, "tourist")
    # The TESTING submission (id 2) got judged and a new one arrived.
    cf.submissions["tourist"][3]["verdict"] = "OK"
    cf.submissions["tourist"].insert(0, sub(6, cid=4))
    cf.calls.clear()
    await run_sync(cf, session_factory, job.id, "tourist")
    with session_factory() as db:
        assert db.get(Submission, 2).verdict == "OK"
        assert db.get(Submission, 6) is not None
        assert db.scalars(select(Handle)).one().newest_submission_id == 6
    assert ("problemset.problems", None) not in cf.calls  # fetched < 24h ago


async def test_handle_not_found_fails_job_and_marks_handle(session_factory):
    cf = FakeCF()
    with session_factory() as db:
        job, _ = jobs.enqueue_sync(db, "ghost_user")
    with pytest.raises(SyncFailed) as err:
        await run_sync(cf, session_factory, job.id, "ghost_user")
    assert err.value.code == "not_found"
    with session_factory() as db:
        assert db.scalars(select(Handle)).one().not_found_at is not None
