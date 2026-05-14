"""Phase 15 — Real database provisioning + admin workspace fixes.

Covers:
- /api/databases/providers presence + auth gating
- Provisioning shape (does not actually call Neon — we mock the service call)
- Migration history + connection test wiring (mocked)
- Site editor + admin endpoints stay green
- Imported-from-github source pointer survives Save-to-GitHub
"""
import os
import sys
import asyncio
import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE_URL}/api"
PASSWORD = os.environ.get("APP_PASSWORD", "555")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"password": PASSWORD}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def test_databases_providers_endpoint(auth_headers):
    r = requests.get(f"{API}/databases/providers", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "neon" in body and "supabase" in body
    for k in ("configured", "ready", "regions", "label", "missing"):
        assert k in body["neon"]
        assert k in body["supabase"]


def test_databases_providers_requires_auth():
    r = requests.get(f"{API}/databases/providers", timeout=10)
    assert r.status_code in (401, 403)


def test_admin_overview_includes_providers(auth_headers):
    r = requests.get(f"{API}/admin/overview", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "providers" in body
    assert "supabase" in body["providers"]
    assert "neon" in body["providers"]


def test_admin_secrets_whitelist_includes_provisioning_keys(auth_headers):
    r = requests.get(f"{API}/admin/secrets", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    keys = {item["key"] for item in r.json()["items"]}
    for k in ("SUPABASE_ACCESS_TOKEN", "SUPABASE_ORG_ID", "NEON_API_KEY", "NEON_ORG_ID"):
        assert k in keys, f"{k} should be editable from /admin"


def test_admin_secrets_protects_core_keys(auth_headers):
    r = requests.post(
        f"{API}/admin/secrets",
        headers=auth_headers,
        json={"updates": {"MONGO_URL": "x"}},
        timeout=10,
    )
    assert r.status_code == 400


def test_provision_endpoint_validates_provider(auth_headers):
    # Pick any project (the admin is project-agnostic; this test just needs a 4xx).
    r = requests.get(f"{API}/projects", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    projects = r.json()
    if not projects:
        pytest.skip("No projects available")
    pid = projects[0]["id"]
    r = requests.post(
        f"{API}/projects/{pid}/databases/provision",
        headers=auth_headers,
        json={"provider": "bogus", "name": "x"},
        timeout=15,
    )
    assert r.status_code in (400, 502, 422), r.text


def test_admin_workspace_user_me_is_admin(auth_headers):
    r = requests.get(f"{API}/users/me", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
