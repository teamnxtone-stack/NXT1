"""Phase 9 backend tests — Access Requests PATCH + ProductAgent endpoints."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PASSWORD = "555"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login", json={"password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- ACCESS REQUESTS (PATCH/DELETE/PUBLIC POST) ----------
class TestAccessRequests:
    """Phase 9: PATCH lifecycle + DELETE 404 + public POST still works."""

    @pytest.fixture(scope="class")
    def created_request(self):
        # Public POST (no auth)
        body = {
            "name": f"TEST_phase9_{uuid.uuid4().hex[:6]}",
            "email": f"test_{uuid.uuid4().hex[:6]}@example.com",
            "company": "TestCo",
            "project_type": "app",
            "description": "Phase 9 access request test seed.",
            "budget": "$5k",
            "timeline": "2 weeks",
        }
        r = requests.post(f"{API}/access/request", json=body, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("id")
        rid = data["id"]
        yield rid
        # Cleanup using auth
        token_resp = requests.post(f"{API}/auth/login", json={"password": PASSWORD}).json()
        requests.delete(
            f"{API}/access/requests/{rid}",
            headers={"Authorization": f"Bearer {token_resp['token']}"},
            timeout=10,
        )

    def test_public_post_no_auth_works(self):
        body = {
            "name": "TEST_public",
            "email": "publicz@example.com",
            "description": "Public submission no auth.",
        }
        r = requests.post(f"{API}/access/request", json=body, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_public_post_invalid_email(self):
        body = {
            "name": "TEST_invalid",
            "email": "not-an-email",
            "description": "Missing @ symbol so should 400.",
        }
        r = requests.post(f"{API}/access/request", json=body, timeout=15)
        assert r.status_code == 400

    def test_patch_to_contacted_returns_ok_and_updated(self, auth, created_request):
        body = {"status": "contacted", "notes": "Reached out via email"}
        r = requests.patch(
            f"{API}/access/requests/{created_request}", headers=auth, json=body, timeout=10
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("status") == "contacted"
        assert data.get("notes") == "Reached out via email"
        assert "updated_at" in data

        # Verify persisted via GET list
        r2 = requests.get(f"{API}/access/requests", headers=auth, timeout=10)
        assert r2.status_code == 200
        items = r2.json()
        match = next((it for it in items if it.get("id") == created_request), None)
        assert match is not None
        assert match["status"] == "contacted"
        assert match["notes"] == "Reached out via email"

    def test_patch_invalid_status_400(self, auth, created_request):
        r = requests.patch(
            f"{API}/access/requests/{created_request}",
            headers=auth,
            json={"status": "wrong_status"},
            timeout=10,
        )
        assert r.status_code == 400

    def test_patch_no_fields_400(self, auth, created_request):
        r = requests.patch(
            f"{API}/access/requests/{created_request}", headers=auth, json={}, timeout=10
        )
        assert r.status_code == 400

    def test_patch_requires_auth(self, created_request):
        r = requests.patch(
            f"{API}/access/requests/{created_request}",
            json={"status": "closed"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_delete_nonexistent_404(self, auth):
        r = requests.delete(
            f"{API}/access/requests/does-not-exist-{uuid.uuid4().hex[:6]}",
            headers=auth,
            timeout=10,
        )
        assert r.status_code == 404


# ---------- PRODUCT / READINESS ----------
@pytest.fixture(scope="module")
def project(token):
    h = {"Authorization": f"Bearer {token}"}
    name = f"TEST_phase9_proj_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/projects", headers=h, json={"name": name}, timeout=15)
    assert r.status_code in (200, 201), r.text
    p = r.json()
    pid = p.get("id") or p.get("project_id")
    assert pid
    yield pid
    requests.delete(f"{API}/projects/{pid}", headers=h, timeout=10)


class TestReadiness:
    def test_readiness_returns_score_and_checks(self, auth, project):
        r = requests.get(f"{API}/projects/{project}/readiness", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "score" in data
        assert isinstance(data["score"], (int, float))
        assert "checks" in data and isinstance(data["checks"], list)
        assert len(data["checks"]) > 0
        assert "fail_count" in data
        assert "warn_count" in data
        # Each check has id/label/status/detail
        for c in data["checks"]:
            assert "id" in c
            assert "label" in c
            assert "status" in c
            assert "detail" in c
            assert c["status"] in ("pass", "warn", "fail", "skip")

    def test_readiness_404_for_missing_project(self, auth):
        r = requests.get(
            f"{API}/projects/does_not_exist_{uuid.uuid4().hex[:6]}/readiness",
            headers=auth,
            timeout=10,
        )
        assert r.status_code == 404

    def test_readiness_requires_auth(self, project):
        r = requests.get(f"{API}/projects/{project}/readiness", timeout=10)
        assert r.status_code == 401


class TestProductPlan:
    def test_product_plan_returns_plan(self, auth, project):
        body = {"brief": "Build a CRM for roofing contractors."}
        r = requests.post(
            f"{API}/projects/{project}/product-plan",
            headers=auth,
            json=body,
            timeout=120,  # AI call can be slow
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert "plan" in data
        plan = data["plan"]
        # Either parsed JSON has summary/mvp_features, or there's raw_text_preview.
        has_summary = bool(plan.get("summary"))
        has_features = bool(plan.get("mvp_features"))
        has_raw = bool(data.get("raw_text_preview"))
        assert has_summary or has_features or has_raw, f"Empty plan: {data}"
        assert data.get("provider")
        assert data.get("model")

    def test_product_plan_404_for_missing_project(self, auth):
        r = requests.post(
            f"{API}/projects/does_not_exist_xyz/product-plan",
            headers=auth,
            json={"brief": "x"},
            timeout=15,
        )
        assert r.status_code == 404
