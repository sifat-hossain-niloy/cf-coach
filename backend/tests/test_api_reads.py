from app import jobs
from app.analytics.service import refresh_analytics
from app.sync import run_sync
from tests.conftest import FakeCF, load_fixture
from tests.test_sync import sub


async def _synced(session_factory, user, subs, ratings=()):
    cf = FakeCF(users={user["handle"].lower(): user}, submissions={user["handle"].lower(): subs},
                ratings={user["handle"].lower(): list(ratings)},
                problemset=load_fixture("problemset_sample.json")["result"])
    with session_factory() as db:
        job, _ = jobs.enqueue_sync(db, user["handle"].lower())
    await run_sync(cf, session_factory, job.id, user["handle"], after_sync=refresh_analytics)


async def test_read_endpoints_for_rated_user(api, session_factory):
    user = load_fixture("user_info_tourist.json")["result"][0]
    subs = [sub(i, cid=2270 + i % 6, idx="ABCDEF"[i % 6], rating=2000 + 100 * (i % 6),
                tags=("dp", "math") if i % 2 else ("graphs",),
                verdict="OK" if i % 3 else "WRONG_ANSWER") for i in range(60, 0, -1)]
    ratings = load_fixture("user_rating_tourist_last15.json")["result"]
    await _synced(session_factory, user, subs, ratings)

    s = api.get("/api/handles/TOURIST/summary").json()
    assert s["handle"] == "tourist" and s["rating"] == user["rating"]
    assert s["rank"]["name"] == "Legendary Grandmaster" and s["target"] is None and s["gap"] is None
    assert s["counts"]["rated_contests"] == 15 and len(s["top_weak"]) <= 3

    s2 = api.get("/api/handles/tourist/summary?target=4000").json()
    assert s2["target"] == 4000 and s2["gap"] == 4000 - user["rating"]

    t = api.get("/api/handles/tourist/tags").json()
    assert t["enough_data"] and {x["tag"] for x in t["tags"]} >= {"dp", "graphs"}

    b = api.get("/api/handles/tourist/bands").json()
    assert b["enough_data"] and all(x["bucket"] % 100 == 0 for x in b["bands"])

    w = api.get("/api/handles/tourist/weak").json()
    assert w["band_lo"] == user["rating"] + 100 and w["band_hi"] == user["rating"] + 400
    w2 = api.get("/api/handles/tourist/weak?band_lo=1900&band_hi=2300").json()
    assert (w2["band_lo"], w2["band_hi"]) == (1900, 2300) and w2["tags"]
    for x in w2["tags"]:
        assert 0 <= x["importance"] <= 1 and 0 <= x["success"] <= 1 and 0 <= x["coverage"] <= 1

    p = api.get("/api/handles/tourist/progress").json()
    assert p["enough_data"] and len(p["history"]) == 15 and p["recent_contests"] == 10
    assert p["practice_history"]


async def test_new_user_gets_not_enough_data(api, session_factory):
    user = {"handle": "Fresh_Coder", "rank": None}
    await _synced(session_factory, user, [sub(1, cid=2270, idx="A", rating=800)])
    s = api.get("/api/handles/fresh_coder/summary").json()
    assert s["handle"] == "Fresh_Coder" and s["rating"] is None and s["rank"] is None
    assert s["level"]["source"] == "default" and s["level"]["value"] == 1000
    assert s["target"] == 1200 and s["gap"] == 200
    assert api.get("/api/handles/fresh_coder/tags").json()["enough_data"] is False
    assert api.get("/api/handles/fresh_coder/bands").json()["enough_data"] is False
    p = api.get("/api/handles/fresh_coder/progress").json()
    assert p["enough_data"] is False and p["contests_needed"] is None and p["practice_message"]


def test_unsynced_handle_is_404_not_synced(api):
    r = api.get("/api/handles/someone/summary")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_synced"


async def test_queue_endpoint_deterministic_and_validated(api, session_factory):
    user = {"handle": "Mid_User", "rating": 1500, "maxRating": 1550, "rank": "specialist"}
    subs = [sub(i, cid=2270 + i % 6, idx="ABCDEF"[i % 6], rating=1200 + 100 * (i % 6),
                tags=("dp",), verdict="OK" if i % 4 else "WRONG_ANSWER", ptype="CONTESTANT")
            for i in range(40, 0, -1)]
    ratings = [{"contestId": 2270 + k, "contestName": f"R{k}", "rank": 100, "ratingUpdateTimeSeconds": 1_600_000_000 + k,
                "oldRating": 1400 + 20 * k, "newRating": 1420 + 20 * k} for k in range(5)]
    await _synced(session_factory, user, subs, ratings)
    q1 = api.get("/api/handles/mid_user/queue?date=2026-10-23").json()
    q2 = api.get("/api/handles/MID_USER/queue?date=2026-10-23").json()
    assert q1["items"] and q1["items"] == q2["items"] and q1["date"] == "2026-10-23"
    assert len(api.get("/api/handles/mid_user/queue?date=2026-10-23&n=2").json()["items"]) <= 2
    first = q1["items"][0]
    q3 = api.get(f"/api/handles/mid_user/queue?date=2026-10-23&exclude={first['contest_id']}-{first['index']}").json()
    assert all((i["contest_id"], i["index"]) != (first["contest_id"], first["index"]) for i in q3["items"])
    assert api.get("/api/handles/mid_user/queue?date=2026-13-45").status_code == 422
    assert api.get("/api/handles/mid_user/queue?n=99").status_code == 422
