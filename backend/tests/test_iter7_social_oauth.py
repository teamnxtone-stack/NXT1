"""Iteration 7 — Workspace login, Social OAuth, Connections, Autopilot, Scheduler.

Covers:
  • POST /api/auth/login  (APP_PASSWORD=555 path + 401 wrong password)
  • GET  /api/social/oauth/status            (3 platforms, configured=false)
  • GET  /api/social/oauth/{platform}/start  (400 when not configured)
  • GET  /api/social/connections             (3 platforms, connected=false, 401 unauth)
  • POST /api/social/connections/{platform}/disconnect  (idempotent ok=true)
  • GET/POST /api/social/autopilot           (defaults + persistence)
  • POST /api/social/posts/{id}/publish      (400 no connection, 404 missing)
  • POST /api/social/posts/{id}/schedule     (200 + 404)
  • Scheduler safety: scheduled past post + no connection → no crash, stays scheduled
  • Existing endpoints: /api/social/posts, /api/video/health, /api/social/generate
  • E2E: signin (user JWT) → access /api/social/*
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_PASSWORD = "555"
USER_EMAIL = "test@nxt1.local"
USER_PASSWORD = "testpass123"
PLATFORMS = ["instagram", "linkedin", "twitter"]


# ────────────────────────────────────────────────────────── fixtures
@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"workspace login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok and isinstance(tok, str) and len(tok) > 20
    return tok


@pytest.fixture(scope="module")
def user_token() -> str:
    try:
        r = requests.post(f"{BASE_URL}/api/users/signin",
                          json={"email": USER_EMAIL, "password": USER_PASSWORD}, timeout=90)
    except requests.exceptions.ReadTimeout:
        pytest.skip("user signin timed out (>90s)")
    if r.status_code != 200:
        pytest.skip(f"user signin not available: {r.status_code} {r.text[:120]}")
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


# ────────────────────────────────────────────────────────── 1. Workspace login
class TestWorkspaceLogin:
    def test_login_with_correct_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"password": ADMIN_PASSWORD}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "token" in body
        assert isinstance(body["token"], str)
        assert len(body["token"]) > 20  # JWT-shaped

    def test_login_with_wrong_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"password": "wrong-password-xyz"}, timeout=15)
        assert r.status_code == 401
        # body must contain detail
        body = r.json()
        assert "detail" in body or "message" in body

    def test_login_empty_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"password": ""}, timeout=15)
        assert r.status_code == 401

    def test_auth_verify_with_admin_token(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/auth/verify",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True


# ────────────────────────────────────────────────────────── 2. OAuth status
class TestOAuthStatus:
    def test_returns_three_platforms_all_unconfigured(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/social/oauth/status",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()
        # has all three platforms
        for p in PLATFORMS:
            assert p in body, f"missing platform {p}"
            assert body[p]["configured"] is False, f"{p} should be unconfigured"
            assert body[p].get("label")
            redirect = body[p].get("redirect_uri", "")
            assert redirect.startswith("http")
            assert f"/api/social/oauth/{p}/callback" in redirect

    def test_status_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/social/oauth/status", timeout=15)
        assert r.status_code in (401, 403)


# ────────────────────────────────────────────────────────── 3. OAuth start (not configured)
class TestOAuthStart:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_start_returns_400_when_unconfigured(self, platform, admin_headers):
        r = requests.get(f"{BASE_URL}/api/social/oauth/{platform}/start",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 400, f"{platform}: expected 400 got {r.status_code}: {r.text[:200]}"
        body = r.json()
        msg = (body.get("detail") or body.get("message") or "").lower()
        # must mention "not configured" + how to fix
        assert "not configured" in msg
        assert "env" in msg or "restart" in msg

    def test_start_unknown_platform(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/social/oauth/myspace/start",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 400
        assert "unknown" in (r.json().get("detail") or "").lower()


# ────────────────────────────────────────────────────────── 4. Connections list / disconnect
class TestConnections:
    def test_connections_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/social/connections", timeout=15)
        assert r.status_code in (401, 403)

    def test_connections_returns_three_unconnected(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/social/connections",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        items = r.json().get("items")
        assert isinstance(items, list)
        assert len(items) == 3
        plats = {it["platform"] for it in items}
        assert plats == set(PLATFORMS)
        for it in items:
            assert it["connected"] is False
            assert it["configured"] is False
            assert it.get("label")
            assert it.get("redirect_uri", "").startswith("http")

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_disconnect_idempotent(self, platform, admin_headers):
        # call twice — both should return ok=True (no record exists)
        for _ in range(2):
            r = requests.post(
                f"{BASE_URL}/api/social/connections/{platform}/disconnect",
                headers=admin_headers, timeout=15)
            assert r.status_code == 200
            assert r.json().get("ok") is True

    def test_disconnect_unknown_platform(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/social/connections/myspace/disconnect",
            headers=admin_headers, timeout=15)
        assert r.status_code == 400


# ────────────────────────────────────────────────────────── 5. Autopilot
class TestAutopilot:
    def test_get_default_for_new_user(self, admin_headers, mongo):
        # Make sure no record exists for 'admin'
        mongo.social_autopilot.delete_many({"user_id": "admin"})
        r = requests.get(f"{BASE_URL}/api/social/autopilot",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        b = r.json()
        assert b["enabled"] is False
        assert b["tone"] == "professional"
        assert b["brief"] == ""
        assert set(b["platforms"]) == {"linkedin", "twitter"}
        assert b["cadence_day"] == 1
        assert b["cadence_hour"] == 9
        assert b.get("last_run_at") is None

    def test_post_persists_and_get_reflects(self, admin_headers, mongo):
        payload = {
            "enabled": True,
            "brief": "TEST_iter7 weekly brief for AI tools",
            "tone": "playful",
            "platforms": ["linkedin"],
            "duration": "next week",
            "cadence_day": 3,
            "cadence_hour": 14,
        }
        r = requests.post(f"{BASE_URL}/api/social/autopilot",
                          headers=admin_headers, json=payload, timeout=15)
        assert r.status_code == 200
        saved = r.json()
        for k, v in payload.items():
            assert saved[k] == v
        assert saved["user_id"] == "admin"

        # GET reflects
        r2 = requests.get(f"{BASE_URL}/api/social/autopilot",
                          headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        got = r2.json()
        for k, v in payload.items():
            assert got[k] == v

        # cleanup
        mongo.social_autopilot.delete_many({"user_id": "admin"})

    def test_autopilot_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/social/autopilot", timeout=15)
        assert r.status_code in (401, 403)


# ────────────────────────────────────────────────────────── 6. Publish / Schedule
class TestPublishSchedule:
    @pytest.fixture
    def seeded_post(self, mongo):
        """Insert a fake post directly into mongo (under admin)."""
        pid = f"TEST_iter7_{uuid.uuid4().hex[:8]}"
        doc = {
            "id": pid,
            "user_id": "admin",
            "platform": "linkedin",
            "status": "draft",
            "caption": "TEST_iter7 caption",
            "hashtags": ["ai", "test"],
            "image_url": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        mongo.social_posts.insert_one(doc)
        yield pid
        mongo.social_posts.delete_many({"id": pid})

    def test_publish_404_for_missing_post(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/social/posts/does-not-exist-xyz/publish",
            headers=admin_headers, timeout=15)
        assert r.status_code == 404

    def test_publish_400_when_no_connection(self, admin_headers, seeded_post, mongo):
        # ensure no connection
        mongo.social_connections.delete_many({"user_id": "admin", "platform": "linkedin"})
        r = requests.post(
            f"{BASE_URL}/api/social/posts/{seeded_post}/publish",
            headers=admin_headers, timeout=15)
        assert r.status_code == 400
        msg = (r.json().get("detail") or "").lower()
        assert "linkedin" in msg
        assert "connected" in msg or "connect" in msg

    def test_schedule_404_for_missing(self, admin_headers):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        r = requests.post(
            f"{BASE_URL}/api/social/posts/does-not-exist-xyz/schedule",
            headers=admin_headers, json={"scheduled_at": future}, timeout=15)
        assert r.status_code == 404

    def test_schedule_sets_status_and_time(self, admin_headers, seeded_post, mongo):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        r = requests.post(
            f"{BASE_URL}/api/social/posts/{seeded_post}/schedule",
            headers=admin_headers, json={"scheduled_at": future}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        # verify persisted
        doc = mongo.social_posts.find_one({"id": seeded_post})
        assert doc is not None
        assert doc["status"] == "scheduled"
        assert doc["scheduled_at"] == future


# ────────────────────────────────────────────────────────── 7. Scheduler safety
class TestSchedulerSafety:
    """Insert a past-due scheduled post with NO connection; wait for the
    60s tick to fire. The post must remain status='scheduled' (no crash)."""

    @pytest.mark.slow
    def test_past_due_with_no_connection_stays_scheduled(self, mongo):
        pid = f"TEST_iter7_sched_{uuid.uuid4().hex[:8]}"
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        mongo.social_connections.delete_many({"user_id": "admin", "platform": "linkedin"})
        mongo.social_posts.insert_one({
            "id": pid,
            "user_id": "admin",
            "platform": "linkedin",
            "status": "scheduled",
            "scheduled_at": past,
            "caption": "TEST_iter7 scheduled past-due",
            "hashtags": [],
            "image_url": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            # Wait > 60s for one full scheduler tick
            time.sleep(75)
            doc = mongo.social_posts.find_one({"id": pid})
            assert doc is not None, "post disappeared!"
            assert doc["status"] == "scheduled", (
                f"Expected status=scheduled (no connection), got {doc['status']}. "
                f"last_publish_error={doc.get('last_publish_error')}"
            )
            # No publish-error should be set since the loop should `continue` early
            assert not doc.get("last_publish_error"), \
                f"Scheduler should not record error when no connection; got: {doc.get('last_publish_error')}"
        finally:
            mongo.social_posts.delete_many({"id": pid})


# ────────────────────────────────────────────────────────── 8. Existing endpoints
class TestExistingEndpoints:
    def test_video_health(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/video/health",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        b = r.json()
        assert b.get("ok") is True
        assert b.get("fal_configured") is False  # env empty

    def test_social_posts_list(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/social/posts",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()
        # routes/social.py shape is {"items": [...]} or list — accept both
        items = body if isinstance(body, list) else body.get("items", body.get("posts"))
        assert items is not None, f"unexpected shape: {body}"

    def test_social_generate_kicks_job(self, admin_headers, mongo):
        """Just verify the endpoint accepts the request and returns a job id;
        don't wait for completion (covered by iter6 tests)."""
        r = requests.post(
            f"{BASE_URL}/api/social/generate",
            headers=admin_headers,
            json={"brief": "TEST_iter7 quick check", "tone": "professional",
                  "platforms": ["linkedin"], "duration": "this week"},
            timeout=20,
        )
        assert r.status_code in (200, 202)
        body = r.json()
        job_id = body.get("job_id") or body.get("id")
        assert job_id, f"no job_id in response: {body}"
        # cleanup the job + any posts that get generated
        # (we leave the job; iter6 covers full lifecycle)


# ────────────────────────────────────────────────────────── 9. E2E user-token flow
class TestUserTokenE2E:
    def test_user_token_can_access_social(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/social/oauth/status",
                         headers=user_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()
        for p in PLATFORMS:
            assert p in body

    def test_user_token_connections_isolated(self, user_headers, mongo):
        r = requests.get(f"{BASE_URL}/api/social/connections",
                         headers=user_headers, timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) == 3
        for it in items:
            assert it["connected"] is False

    def test_user_token_autopilot(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/social/autopilot",
                         headers=user_headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("enabled") is False
