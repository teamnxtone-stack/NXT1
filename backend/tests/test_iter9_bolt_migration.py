"""
Iter9 — Bolt.diy builder migration regression.

Covers:
  - Bolt reverse proxy (COEP/COOP headers, HTML payload, route forwarding)
  - Workspace pages' backend APIs still functional after the swap
    (notifications, social, memory, leads, public chat, system health).
No 5xx tolerance.
"""
import os
import re
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
TIMEOUT = 20

# ---------- fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s

@pytest.fixture(scope="module")
def user_token(session):
    r = session.post(f"{BASE}/api/users/signin",
                     json={"email": "test@nxt1.local", "password": "testpass123"},
                     timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    tok = r.json().get("token")
    assert tok
    return tok

@pytest.fixture(scope="module")
def admin_token(session):
    r = session.post(f"{BASE}/api/auth/login",
                     json={"password": "555"}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    return r.json()["token"]

@pytest.fixture
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}

@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ---------- Bolt proxy (CRITICAL) ----------
class TestBoltProxy:
    def test_root_returns_html_with_coep_coop(self, session):
        r = session.get(f"{BASE}/api/bolt-engine/", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct, f"unexpected content-type: {ct}"
        assert r.headers.get("cross-origin-embedder-policy") == "credentialless", \
            f"missing/wrong COEP: {r.headers.get('cross-origin-embedder-policy')}"
        assert r.headers.get("cross-origin-opener-policy") == "same-origin", \
            f"missing/wrong COOP: {r.headers.get('cross-origin-opener-policy')}"

    def test_html_payload_is_bolt_remix(self, session):
        r = session.get(f"{BASE}/api/bolt-engine/", timeout=TIMEOUT)
        html = r.text
        # Bolt is a remix app — should reference /api/bolt-engine prefix in assets
        assert "/api/bolt-engine/" in html, "expected asset paths rewritten with /api/bolt-engine/ base"
        # Default theme should be dark per /app/services/bolt-engine/app/lib/stores/theme.ts
        # Look for either data-theme="dark" or theme initialization snippet
        assert ("data-theme=\"dark\"" in html) or ("'dark'" in html) or ("\"dark\"" in html), \
            "expected dark theme reference in HTML"

    def test_query_string_preserved(self, session):
        r = session.get(f"{BASE}/api/bolt-engine/?project=abc123", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.headers.get("cross-origin-embedder-policy") == "credentialless"

    def test_logo_svg_served(self, session):
        r = session.get(f"{BASE}/api/bolt-engine/logo.svg", timeout=TIMEOUT)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "svg" in ct or "xml" in ct, f"unexpected ct: {ct}"
        assert "<svg" in r.text

    def test_favicon_served(self, session):
        r = session.get(f"{BASE}/api/bolt-engine/favicon.svg", timeout=TIMEOUT)
        assert r.status_code == 200


# ---------- Notifications ----------
class TestNotifications:
    def test_list_authed(self, session, user_headers):
        r = session.get(f"{BASE}/api/notifications/list", headers=user_headers, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        # accept either list or {notifications:[...]} shape
        assert isinstance(data, (list, dict))


# ---------- Social ----------
class TestSocial:
    def test_posts_list(self, session, user_headers):
        r = session.get(f"{BASE}/api/social/posts", headers=user_headers, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        # Should be a list or dict, never a 5xx
        body = r.json()
        assert isinstance(body, (list, dict))

    def test_oauth_status(self, session, user_headers):
        r = session.get(f"{BASE}/api/social/oauth/status", headers=user_headers, timeout=TIMEOUT)
        assert r.status_code == 200


# ---------- Memory ----------
class TestMemory:
    def test_list(self, session, user_headers):
        r = session.get(f"{BASE}/api/memory", headers=user_headers, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert isinstance(body, (list, dict))


# ---------- Leads (admin) ----------
class TestLeads:
    def test_leads_list_admin(self, session, admin_headers):
        # Actual route is /api/v1/agentos/leads (not /api/leads / /api/v1/leads).
        r = session.get(f"{BASE}/api/v1/agentos/leads", headers=admin_headers, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert isinstance(body, (list, dict))

    def test_leads_list_user(self, session, user_headers):
        # test@nxt1.local has role=admin per signin payload, so should succeed.
        r = session.get(f"{BASE}/api/v1/agentos/leads", headers=user_headers, timeout=TIMEOUT)
        assert r.status_code in (200, 403), r.text[:300]
        assert r.status_code != 500


# ---------- Public chat / landing ----------
class TestPublicChat:
    def test_landing_page(self, session):
        r = session.get(f"{BASE}/", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_chat_intake_endpoint_reachable(self, session):
        # The public chat bubble posts to some intake; probe common shapes
        # and make sure none of them 5xx.
        for path in ("/api/public/chat", "/api/chat/intake", "/api/v1/agentos/leads/intake"):
            r = session.options(f"{BASE}{path}", timeout=TIMEOUT)
            assert r.status_code < 500, f"{path} -> {r.status_code}"


# ---------- System health ----------
class TestHealth:
    def test_system_health(self, session):
        r = session.get(f"{BASE}/api/system/health", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_agentos_builder_status(self, session, admin_headers):
        r = session.get(f"{BASE}/api/v1/agentos/builder/status", headers=admin_headers, timeout=TIMEOUT)
        # 200 ok or 404 if removed; we only care it never 5xxs
        assert r.status_code < 500, r.text[:300]
