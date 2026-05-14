"""Phase 18 — Persistent jobs + stream-interruption persistence."""
import asyncio
import os
import sys
import requests
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE_URL}/api"
PASSWORD = os.environ.get("APP_PASSWORD", "555")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"password": PASSWORD}, timeout=10)
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def project_id(auth_headers):
    pr = requests.get(f"{API}/projects", headers=auth_headers, timeout=10).json()
    if not pr:
        pytest.skip("No projects available")
    return pr[0]["id"]


def test_jobs_list_endpoint_exists(auth_headers, project_id):
    r = requests.get(f"{API}/projects/{project_id}/jobs?limit=5",
                     headers=auth_headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "count" in body
    assert isinstance(body["items"], list)


def test_active_jobs_endpoint(auth_headers, project_id):
    r = requests.get(f"{API}/projects/{project_id}/jobs/active",
                     headers=auth_headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    # Active jobs may legitimately be empty; only the shape matters.
    assert "items" in body and "count" in body


def test_get_job_404(auth_headers):
    r = requests.get(f"{API}/jobs/00000000-bogus-job", headers=auth_headers, timeout=10)
    assert r.status_code == 404


def test_jobs_require_auth(project_id):
    r = requests.get(f"{API}/projects/{project_id}/jobs", timeout=10)
    assert r.status_code in (401, 403)


# ---------- job_service unit ----------
def test_job_service_lifecycle():
    """Run start → log → complete in-process against the live Mongo."""
    from services import job_service
    from routes._deps import db

    async def go():
        job = await job_service.start(db, kind="test", project_id=None, actor="admin")
        assert job["status"] == "running"
        await job_service.append_log(db, job["id"], "info", "step 1", phase="step-1", progress=0.2)
        await job_service.append_log(db, job["id"], "info", "step 2", phase="step-2", progress=0.6)
        await job_service.complete(db, job["id"], status="completed", result={"out": "ok"})

        fetched = await job_service.get(db, job["id"])
        assert fetched["status"] == "completed"
        assert fetched["result"]["out"] == "ok"
        assert len(fetched["logs"]) >= 2
        assert fetched["phase"] == "completed"

        # Cleanup
        await db.jobs.delete_one({"id": job["id"]})

    asyncio.get_event_loop().run_until_complete(go())


def test_job_service_cancel():
    from services import job_service
    from routes._deps import db

    async def go():
        job = await job_service.start(db, kind="test-cancel", project_id=None)
        assert await job_service.cancel(db, job["id"]) is True
        # Second cancel is a no-op
        assert await job_service.cancel(db, job["id"]) is False
        fetched = await job_service.get(db, job["id"])
        assert fetched["status"] == "cancelled"
        await db.jobs.delete_one({"id": job["id"]})

    asyncio.get_event_loop().run_until_complete(go())


def test_job_service_log_bounded():
    """Logs should be capped at MAX_LOG_LINES (200)."""
    from services import job_service
    from routes._deps import db

    async def go():
        job = await job_service.start(db, kind="test-bounded", project_id=None)
        # Push 220 entries
        for i in range(220):
            await job_service.append_log(db, job["id"], "info", f"line {i}")
        fetched = await job_service.get(db, job["id"])
        assert len(fetched["logs"]) <= 200
        # And the LAST 200 should be present (oldest 20 trimmed)
        last_msg = fetched["logs"][-1]["msg"]
        assert last_msg == "line 219"
        await db.jobs.delete_one({"id": job["id"]})

    asyncio.get_event_loop().run_until_complete(go())
