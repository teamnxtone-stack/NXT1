"""Phase 16 — Workers provider, R2 storage, domain auto-detect, audit log, Atlas provisioning."""
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
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- Workers / Atlas / R2 in providers status ----------
def test_provisioning_includes_atlas(auth_headers):
    r = requests.get(f"{API}/databases/providers", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert "atlas" in j
    assert j["atlas"]["label"] == "MongoDB Atlas"
    assert "MONGODB_ATLAS_PUBLIC_KEY" in j["atlas"]["missing"] or j["atlas"]["ready"]


def test_admin_overview_lists_atlas_and_r2(auth_headers):
    r = requests.get(f"{API}/admin/overview", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    p = r.json()["providers"]
    assert "atlas" in p
    assert "r2" in p


def test_admin_secrets_includes_atlas_and_r2_keys(auth_headers):
    r = requests.get(f"{API}/admin/secrets", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    keys = {item["key"] for item in r.json()["items"]}
    for k in (
        "MONGODB_ATLAS_PUBLIC_KEY", "MONGODB_ATLAS_PRIVATE_KEY", "MONGODB_ATLAS_ORG_ID",
        "R2_BUCKET", "R2_PUBLIC_BASE",
    ):
        assert k in keys, f"{k} should be editable from /admin"


def test_atlas_provision_friendly_error_when_missing_keys(auth_headers):
    pr = requests.get(f"{API}/projects", headers=auth_headers, timeout=10).json()
    if not pr:
        pytest.skip("No projects")
    pid = pr[0]["id"]
    r = requests.post(
        f"{API}/projects/{pid}/databases/provision",
        headers=auth_headers,
        json={"provider": "atlas", "name": "phase16-skip"},
        timeout=15,
    )
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert "ATLAS" in detail.upper() or "MONGODB" in detail.upper()


# ---------- Domain auto-detect ----------
def test_domain_detect_managed(auth_headers):
    r = requests.get(f"{API}/domains/detect", params={"host": "app.nxtone.tech"},
                     headers=auth_headers, timeout=15)
    # Not asserting True since this depends on the live CF account; the
    # endpoint must exist and return the correct shape regardless.
    assert r.status_code == 200
    body = r.json()
    for k in ("managed", "instructions"):
        assert k in body


def test_domain_detect_unknown_domain(auth_headers):
    r = requests.get(f"{API}/domains/detect", params={"host": "totally.nonexistent-zone-1234.test"},
                     headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["managed"] is False
    assert isinstance(body.get("instructions"), list) and len(body["instructions"]) >= 1


def test_domain_detect_invalid_host(auth_headers):
    r = requests.get(f"{API}/domains/detect", params={"host": "not a host"},
                     headers=auth_headers, timeout=10)
    assert r.status_code == 400


# ---------- Audit log ----------
def test_audit_endpoint_admin_only():
    r = requests.get(f"{API}/audit", timeout=10)
    assert r.status_code in (401, 403)


def test_audit_records_env_changes(auth_headers):
    pr = requests.get(f"{API}/projects", headers=auth_headers, timeout=10).json()
    if not pr:
        pytest.skip("No projects")
    pid = pr[0]["id"]
    # Trigger a fresh write
    key = f"AUDIT_TEST_{os.getpid()}"
    requests.post(f"{API}/projects/{pid}/env", headers=auth_headers,
                  json={"key": key, "value": "v"}, timeout=10).raise_for_status()
    requests.delete(f"{API}/projects/{pid}/env/{key}", headers=auth_headers, timeout=10).raise_for_status()
    r = requests.get(f"{API}/audit", params={"limit": 50, "tool": "env"}, headers=auth_headers, timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    targets = [i.get("target") for i in items]
    assert any(key in (t or "") for t in targets)


def test_audit_rollback_404(auth_headers):
    r = requests.post(f"{API}/audit/00000000-bogus-bogus/rollback",
                      headers=auth_headers, timeout=10)
    assert r.status_code == 404


# ---------- Cloudflare Workers provider ----------
def test_workers_provider_listed(auth_headers):
    pr = requests.get(f"{API}/projects", headers=auth_headers, timeout=10).json()
    if not pr:
        pytest.skip("No projects")
    # Provider list is exposed via /api/system/providers (existing) — sanity-check
    r = requests.get(f"{API}/system/providers", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    deploy_providers = body.get("deploy") or body.get("deploy_providers") or []
    names = [p.get("name") for p in deploy_providers]
    assert "cloudflare-workers" in names


def test_workers_deploy_friendly_error_when_no_entry(auth_headers):
    """Deploy a workers build for a project with no Worker entry → friendly fail."""
    pr = requests.get(f"{API}/projects", headers=auth_headers, timeout=10).json()
    if not pr:
        pytest.skip("No projects")
    pid = pr[0]["id"]
    # Fire the deploy. Workers go async — we just check the queued record.
    r = requests.post(
        f"{API}/projects/{pid}/deployments",
        headers=auth_headers,
        json={"provider": "cloudflare-workers"},
        timeout=15,
    )
    assert r.status_code == 200
    rec = r.json()
    assert rec["provider"] == "cloudflare-workers"
    assert rec["status"] in ("building", "failed", "pending")
