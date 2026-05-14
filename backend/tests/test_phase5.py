"""NXT1 Phase 5 backend tests:
- POST /api/projects/{id}/scaffold (fastapi / express)
- POST /api/projects/{id}/runtime/start | stop | health | try
- GET  /api/projects/{id}/runtime endpoints_full
- Database registry CRUD (+ url masking + schema template)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PASSWORD = "555"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def project(auth_headers):
    r = requests.post(
        f"{BASE_URL}/api/projects",
        headers=auth_headers,
        json={"name": "TEST_phase5_fastapi", "description": "phase 5 fastapi"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    # try to stop runtime then cleanup
    try:
        requests.post(f"{BASE_URL}/api/projects/{pid}/runtime/stop", headers=auth_headers, timeout=15)
    except Exception:
        pass
    requests.delete(f"{BASE_URL}/api/projects/{pid}", headers=auth_headers, timeout=15)


@pytest.fixture(scope="module")
def express_project(auth_headers):
    r = requests.post(
        f"{BASE_URL}/api/projects",
        headers=auth_headers,
        json={"name": "TEST_phase5_express", "description": "phase 5 express"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    try:
        requests.post(f"{BASE_URL}/api/projects/{pid}/runtime/stop", headers=auth_headers, timeout=15)
    except Exception:
        pass
    requests.delete(f"{BASE_URL}/api/projects/{pid}", headers=auth_headers, timeout=15)


# ---------- FastAPI scaffold + runtime ----------
class TestFastAPIScaffold:
    def test_scaffold_fastapi(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/scaffold",
            headers=auth_headers,
            json={"kind": "fastapi", "auto_start": False},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        files_added = body.get("files_added") or body.get("files") or []
        # accept list of strings or list of dicts with 'path'
        names = [f if isinstance(f, str) else f.get("path") for f in files_added]
        # Should include backend/server.py + requirements.txt + README.md (any of these)
        joined = " ".join(names)
        assert "backend/server.py" in joined or "server.py" in joined, names
        assert "requirements.txt" in joined, names

    def test_runtime_start(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/runtime/start",
            headers=auth_headers, timeout=90,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("alive") is True, body
        assert body.get("port"), body

    def test_runtime_health(self, project, auth_headers):
        # give it a moment to settle
        time.sleep(1.0)
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/runtime/health",
            headers=auth_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True, body
        assert body.get("status_code") == 200, body

    def test_runtime_try_get_health(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/runtime/try",
            headers=auth_headers,
            json={"method": "GET", "path": "/api/health"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status_code") == 200, body
        bj = body.get("body_json") or {}
        assert bj.get("status") == "ok", body

    def test_runtime_endpoints_full(self, project, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/projects/{project}/runtime",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        eps = body.get("endpoints_full") or []
        assert isinstance(eps, list) and len(eps) >= 3, body
        sigs = {(e.get("method"), e.get("path")) for e in eps}
        assert ("GET", "/api/health") in sigs, sigs
        assert ("GET", "/api/hello") in sigs, sigs
        assert ("POST", "/api/echo") in sigs, sigs
        for e in eps:
            assert "file" in e and "line" in e, e

    def test_runtime_stop(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/runtime/stop",
            headers=auth_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True


# ---------- Express scaffold (don't auto-start; npm install can be slow) ----------
class TestExpressScaffold:
    def test_scaffold_express(self, express_project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{express_project}/scaffold",
            headers=auth_headers,
            json={"kind": "express", "auto_start": False},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        files_added = body.get("files_added") or body.get("files") or []
        names = [f if isinstance(f, str) else f.get("path") for f in files_added]
        joined = " ".join(names)
        assert "server.js" in joined, names
        assert "package.json" in joined, names


# ---------- Database registry ----------
class TestDatabases:
    db_id = None

    def test_list_empty(self, project, auth_headers):
        r = requests.get(f"{BASE_URL}/api/projects/{project}/databases",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_add_postgres(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/databases",
            headers=auth_headers,
            json={"kind": "postgres", "name": "main", "url": "postgres://u:p@h/d"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("name") == "main"
        assert d.get("kind") == "postgres"
        # password should be masked, host preserved
        assert d.get("url_masked") == "postgres://u:***@h/d", d
        assert d.get("id")
        TestDatabases.db_id = d["id"]

    def test_schema_template(self, project, auth_headers):
        assert TestDatabases.db_id, "add_postgres must run first"
        r = requests.get(
            f"{BASE_URL}/api/projects/{project}/databases/{TestDatabases.db_id}/schema-template",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # accept either {schema:str} or raw string field
        schema = body.get("schema") or body.get("template") or body.get("sql") or ""
        if isinstance(body, str):
            schema = body
        assert isinstance(schema, str) and len(schema) > 10, body

    def test_delete_db(self, project, auth_headers):
        assert TestDatabases.db_id, "add_postgres must run first"
        r = requests.delete(
            f"{BASE_URL}/api/projects/{project}/databases/{TestDatabases.db_id}",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True
