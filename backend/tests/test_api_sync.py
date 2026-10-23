from datetime import timedelta

from app.handles import is_valid_handle
from app.models import Handle, Job, utcnow


def test_handle_validation():
    assert is_valid_handle("tourist") and is_valid_handle("a.b-c_d") and is_valid_handle("x" * 24)
    for bad in ("ab", "x" * 25, "bad handle", "semi;colon", "ünï", "a/b"):
        assert not is_valid_handle(bad)


def test_invalid_handle_is_422(api):
    assert api.post("/api/handles/a!/sync").status_code == 422


def test_sync_enqueues_then_dedups(api):
    r1 = api.post("/api/handles/Tourist/sync").json()
    r2 = api.post("/api/handles/TOURIST/sync").json()
    assert r1["cached"] is False and r1["job"]["status"] == "queued"
    assert r1["job"]["position"] == 1
    assert r2["job"]["id"] == r1["job"]["id"]
    job = api.get(f"/api/jobs/{r1['job']['id']}").json()
    assert job["status"] == "queued" and job["position"] == 1


def test_recently_synced_returns_cache(api, session_factory):
    with session_factory() as db:
        db.add(Handle(handle_key="tourist", display_handle="tourist", last_synced_at=utcnow()))
    r = api.post("/api/handles/TOURIST/sync").json()
    assert r["cached"] is True and r["job"] is None and r["handle"] == "tourist"


def test_stale_handle_enqueues(api, session_factory):
    with session_factory() as db:
        db.add(Handle(handle_key="tourist", display_handle="tourist",
                      last_synced_at=utcnow() - timedelta(minutes=11)))
    assert api.post("/api/handles/tourist/sync").json()["job"] is not None


def test_recent_not_found_is_clean_404(api, session_factory):
    with session_factory() as db:
        db.add(Handle(handle_key="ghost_user", display_handle="ghost_user", not_found_at=utcnow()))
    r = api.post("/api/handles/ghost_user/sync")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_failed_job_reports_error(api, session_factory):
    with session_factory() as db:
        db.add(Job(kind="sync", handle_key="ghost_user", status="failed",
                   error="Handle 'ghost_user' was not found on Codeforces", error_code="not_found"))
    j = api.get("/api/jobs/1").json()
    assert j["status"] == "failed" and j["error_code"] == "not_found" and j["position"] is None


def test_unknown_job_404(api):
    assert api.get("/api/jobs/999").status_code == 404


def test_per_ip_rate_limit(api):
    codes = [api.post(f"/api/handles/user_{i:02d}/sync").status_code for i in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_dedup_does_not_spend_rate_limit(api):
    for _ in range(15):
        assert api.post("/api/handles/same_user/sync").status_code == 200


def test_health(api):
    body = api.get("/api/health").json()
    assert body["status"] == "ok" and body["queued_jobs"] == 0
