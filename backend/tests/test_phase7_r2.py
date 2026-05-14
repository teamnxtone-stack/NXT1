"""Phase 7 R2 + Phase 8 routes refactor + Phase 9 foundation backend tests.

Covers:
- /api/agents (now from routes/agents.py)
- /api/agents/route heuristic router (no LLM call)
- /api/projects/{id}/readiness (success + 404)
- /api/projects/{id}/deploy/auto-fix no-deployments path (400) + success path (no LLM)
- /api/projects/{id}/runtime/auto-fix endpoint reachability (no LLM trigger)
- Regression: POST /api/projects/{id}/scaffold remains reachable
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PASSWORD = "555"
ZIP_PROJECT_ID = "ed2736da-9f17-4525-8e3b-e0f1ccfad4e2"
TEST_PROJECT_ID_FASTAPI = "0d888ce7"  # may not be the full id; resolve below


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=45)
    assert r.status_code == 200, r.text
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def session(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


# ----- Agents -----
class TestAgents:
    def test_list_agents(self, session):
        r = session.get(f"{BASE_URL}/api/agents", timeout=10)
        assert r.status_code == 200
        data = r.json()
        roles = {a["role"] for a in data}
        assert {"architecture", "frontend", "backend", "debug", "devops"}.issubset(roles)
        assert len(data) >= 5

    @pytest.mark.parametrize("prompt,expected", [
        ("the deploy keeps failing on vercel", "devops"),
        ("add a responsive landing page", "frontend"),
        ("my python server crashes with NameError", "debug"),
        ("build a CRM for contractors", "architecture"),
        ("hi", "frontend"),  # short ambiguous → frontend default
    ])
    def test_agents_route(self, session, prompt, expected):
        r = session.post(f"{BASE_URL}/api/agents/route", json={"prompt": prompt}, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["role"] == expected, f"prompt={prompt!r} got role={body['role']!r}"
        assert "label" in body


# ----- Readiness -----
class TestReadiness:
    def test_readiness_existing(self, session):
        r = session.get(f"{BASE_URL}/api/projects/{ZIP_PROJECT_ID}/readiness", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data["score"], int)
        assert 0 <= data["score"] <= 100
        assert isinstance(data["fail_count"], int)
        assert isinstance(data["warn_count"], int)
        check_ids = {c["id"] for c in data["checks"]}
        # Must contain core checks (some are conditional like runtime_alive)
        for required in ("has_files", "frontend_entry", "backend", "deployed", "domain", "readme"):
            assert required in check_ids, f"missing check {required}; got {check_ids}"
        for c in data["checks"]:
            assert "id" in c and "label" in c and "status" in c and "detail" in c

    def test_readiness_404(self, session):
        r = session.get(f"{BASE_URL}/api/projects/does-not-exist-xyz/readiness", timeout=10)
        assert r.status_code == 404


# ----- Deploy auto-fix -----
class TestDeployAutoFix:
    @pytest.fixture(scope="class")
    def fastapi_project_id(self, session):
        # Find a project starting with the prefix
        r = session.get(f"{BASE_URL}/api/projects", timeout=10)
        assert r.status_code == 200
        for p in r.json():
            if p["id"].startswith(TEST_PROJECT_ID_FASTAPI):
                return p["id"]
        pytest.skip(f"No project with prefix {TEST_PROJECT_ID_FASTAPI}")

    def test_no_deployments_returns_400(self, session, fastapi_project_id):
        # Create an empty test project to guarantee no deployments
        r = session.post(f"{BASE_URL}/api/projects",
                         json={"name": "TEST_phase7r2_nodeploy"}, timeout=10)
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]
        try:
            r = session.post(f"{BASE_URL}/api/projects/{pid}/deploy/auto-fix",
                             json={}, timeout=10)
            assert r.status_code == 400, r.text
            detail = r.json().get("detail", "")
            assert "No deployments" in detail or "no deployments" in detail.lower()
        finally:
            session.delete(f"{BASE_URL}/api/projects/{pid}", timeout=10)

    def test_success_path_no_llm(self, session, fastapi_project_id):
        """If the latest deployment is 'deployed' (success), endpoint short-circuits
        with has_errors=false and never calls the LLM."""
        r = session.get(f"{BASE_URL}/api/projects/{fastapi_project_id}", timeout=10)
        assert r.status_code == 200
        deps = r.json().get("deployments") or []
        if not deps:
            pytest.skip("No deployments on FastAPI project — covered by no-deploy test")
        if deps[-1].get("status") != "deployed":
            pytest.skip("Latest deployment is not successful — would invoke LLM")
        r = session.post(f"{BASE_URL}/api/projects/{fastapi_project_id}/deploy/auto-fix",
                         json={}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["has_errors"] is False
        assert body.get("deployment_status") == "deployed"
        assert body.get("fix_id") is None
        assert body.get("files") == []
        assert "diagnosis" in body


# ----- Runtime auto-fix reachability -----
class TestRuntimeAutoFixReachable:
    def test_runtime_autofix_no_errors_short_circuit(self, session):
        """When buffer is empty & no body error_text, the endpoint returns
        has_errors=false WITHOUT calling the LLM."""
        r = session.post(f"{BASE_URL}/api/projects",
                         json={"name": "TEST_phase7r2_runtime"}, timeout=10)
        assert r.status_code in (200, 201)
        pid = r.json()["id"]
        try:
            r = session.post(f"{BASE_URL}/api/projects/{pid}/runtime/auto-fix",
                             json={}, timeout=15)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ok"] is True
            assert body["has_errors"] is False
            assert body["files"] == []
            assert "fix_id" in body  # key exists (None when no errors)
        finally:
            session.delete(f"{BASE_URL}/api/projects/{pid}", timeout=10)

    def test_runtime_autofix_404_unknown_project(self, session):
        r = session.post(f"{BASE_URL}/api/projects/no-such-pid/runtime/auto-fix",
                         json={}, timeout=10)
        assert r.status_code == 404


# ----- Regression: scaffold and runtime/start endpoints reachable -----
class TestRegression:
    def test_scaffold_endpoint_reachable(self, session):
        r = session.post(f"{BASE_URL}/api/projects",
                         json={"name": "TEST_phase7r2_scaffold"}, timeout=10)
        assert r.status_code in (200, 201)
        pid = r.json()["id"]
        try:
            r = session.post(f"{BASE_URL}/api/projects/{pid}/scaffold",
                             json={"kind": "fastapi"}, timeout=20)
            assert r.status_code in (200, 201), r.text
            body = r.json()
            assert "files" in body or body.get("ok") is True
        finally:
            session.delete(f"{BASE_URL}/api/projects/{pid}", timeout=10)
