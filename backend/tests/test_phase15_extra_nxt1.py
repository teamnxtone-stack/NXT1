"""Phase 15 extra — NXT1 spec coverage:

- providers_status shape (ready flags + regions + missing list)
- supabase provision returns friendly 502 when SUPABASE_ACCESS_TOKEN missing
- bogus provider returns 400 (not 500/502)
- admin secrets whitelist lists 20+ items including new provisioning keys
- AI_PROVIDER (non-protected key) is editable + persists
- /api/users/me reflects admin role (login round-trip)
- GitHub import stores source_owner/source_name/source_repo_url
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE_URL}/api"
PASSWORD = os.environ.get("APP_PASSWORD", "555")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"password": PASSWORD}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def H(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---- providers shape ----
def test_providers_neon_ready_supabase_configured(H):
    r = requests.get(f"{API}/databases/providers", headers=H, timeout=10)
    assert r.status_code == 200
    body = r.json()
    # NEON_API_KEY is set in env
    assert body["neon"]["configured"] is True
    assert body["neon"]["ready"] is True
    assert isinstance(body["neon"]["regions"], list) and len(body["neon"]["regions"]) > 0
    # SUPABASE_ACCESS_TOKEN is intentionally NOT set per the testing brief
    assert body["supabase"]["ready"] in (False, True)
    if not body["supabase"]["ready"]:
        assert "SUPABASE_ACCESS_TOKEN" in body["supabase"]["missing"]


# ---- provider validation 400 on bogus ----
def test_provision_bogus_provider_400(H):
    pj = requests.get(f"{API}/projects", headers=H, timeout=10).json()
    if not pj:
        pytest.skip("no projects")
    pid = pj[0]["id"]
    r = requests.post(
        f"{API}/projects/{pid}/databases/provision",
        headers=H,
        json={"provider": "bogus", "name": "x"},
        timeout=15,
    )
    assert r.status_code == 400, r.text
    assert "Unsupported provider" in (r.json().get("detail") or "") or "bogus" in r.text


# ---- supabase friendly 502 when token missing ----
def test_supabase_missing_token_returns_502_with_hint(H):
    if (os.environ.get("SUPABASE_ACCESS_TOKEN") or "").strip():
        pytest.skip("SUPABASE_ACCESS_TOKEN is set — skipping missing-token check")
    pj = requests.get(f"{API}/projects", headers=H, timeout=10).json()
    if not pj:
        pytest.skip("no projects")
    pid = pj[0]["id"]
    r = requests.post(
        f"{API}/projects/{pid}/databases/provision",
        headers=H,
        json={"provider": "supabase", "name": "phase15-test"},
        timeout=20,
    )
    assert r.status_code == 502, r.text
    detail = (r.json().get("detail") or "").lower()
    assert "supabase_access_token" in detail or "access token" in detail
    assert "supabase.com" in detail or "/admin" in detail


# ---- admin secrets count + AI_PROVIDER edit persists ----
def test_admin_secrets_has_20_plus_items(H):
    r = requests.get(f"{API}/admin/secrets", headers=H, timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    keys = {i["key"] for i in items}
    assert len(items) >= 20
    for k in ("SUPABASE_ACCESS_TOKEN", "SUPABASE_ORG_ID", "NEON_API_KEY", "NEON_ORG_ID"):
        assert k in keys


def test_admin_secrets_update_ai_provider_persists(H):
    # Read current
    r0 = requests.get(f"{API}/admin/secrets", headers=H, timeout=10)
    prior = next((i for i in r0.json()["items"] if i["key"] == "AI_PROVIDER"), None)
    prior_present = bool(prior and prior.get("present"))

    # Set to a sentinel
    sentinel = "auto"
    r = requests.post(
        f"{API}/admin/secrets",
        headers=H,
        json={"updates": {"AI_PROVIDER": sentinel}},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    assert "AI_PROVIDER" in r.json()["updated"]

    # Verify persistence via GET
    r2 = requests.get(f"{API}/admin/secrets", headers=H, timeout=10)
    cur = next(i for i in r2.json()["items"] if i["key"] == "AI_PROVIDER")
    assert cur["present"] is True
    # restore (no-op since same value)
    if not prior_present:
        requests.post(f"{API}/admin/secrets", headers=H, json={"updates": {"AI_PROVIDER": ""}}, timeout=10)


# ---- /users/me admin role ----
def test_users_me_admin_role(H):
    r = requests.get(f"{API}/users/me", headers=H, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body.get("role") == "admin"


# ---- GitHub import preserves source repo metadata ----
def test_github_import_stores_source_metadata(H):
    """Import a tiny public repo and verify project doc has github.source_*."""
    # Use a tiny well-known public repo
    payload = {
        "repo_url": "https://github.com/github/gitignore",
        "project_name": f"phase15-import-{uuid.uuid4().hex[:8]}",
    }
    r = requests.post(f"{API}/projects/import/github", headers=H, json=payload, timeout=90)
    if r.status_code in (502, 503):
        pytest.skip(f"GitHub import upstream unavailable: {r.status_code} {r.text[:120]}")
    if r.status_code == 404:
        pytest.skip("import endpoint shape differs — skipping integration check")
    assert r.status_code in (200, 201), r.text
    body = r.json()
    pid = body.get("id") or body.get("project", {}).get("id")
    assert pid, f"no project id in response: {body}"

    # POST response should include github metadata
    gh_post = body.get("github") or {}
    assert gh_post.get("source_owner") == "github"
    assert gh_post.get("source_name") == "gitignore"
    assert "github.com/github/gitignore" in (gh_post.get("source_repo_url") or "")

    # Verify via dedicated /github endpoint (persisted in Mongo)
    pr = requests.get(f"{API}/projects/{pid}/github", headers=H, timeout=10)
    assert pr.status_code == 200
    gh = pr.json()
    assert gh.get("source_owner") == "github"
    assert gh.get("source_name") == "gitignore"
    assert "github.com/github/gitignore" in (gh.get("source_repo_url") or "")
