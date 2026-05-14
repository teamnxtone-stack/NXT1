"""Phase 6 backend tests: Claude provider, saved requests, ZIP/GitHub import + analysis."""
import os
import io
import zipfile
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://nxt-studio.preview.emergentagent.com").rstrip("/")
PASSWORD = "555"
EXISTING_PROJECT_ID = "0d888ce7-0efd-4f08-bddf-a01f13d5ce4a"
ZIP_PROJECT_ID = "ed2736da-9f17-4525-8e3b-e0f1ccfad4e2"


@pytest.fixture(scope="module")
def auth_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def test_zip_path():
    p = "/tmp/testproj.zip"
    if not os.path.exists(p):
        # Recreate
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("backend/server.py",
                        "from fastapi import FastAPI\napp = FastAPI()\n"
                        "@app.get('/api/users')\ndef users(): return []\n"
                        "@app.post('/api/users')\ndef create_user(): return {}\n")
            zf.writestr("package.json",
                        '{"name":"x","dependencies":{"react":"^19.0.0","next":"^14.0.0","tailwindcss":"^3.0.0"}}')
            zf.writestr("src/App.jsx",
                        "import React from 'react';\n"
                        "const URL = process.env.REACT_APP_API_URL;\n"
                        "const KEY = process.env.STRIPE_KEY;\n"
                        "export default function App(){return null;}\n")
        with open(p, "wb") as f:
            f.write(bio.getvalue())
    return p


# ---------- Providers ----------
class TestProviders:
    def test_providers_includes_anthropic_and_openai(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/system/providers", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        ai = data.get("ai") or {}
        assert ai.get("anthropic") is True, f"anthropic not true: {ai}"
        assert ai.get("openai") is True, f"openai not true: {ai}"


# ---------- Saved requests ----------
class TestSavedRequests:
    def test_saved_request_crud(self, auth_headers):
        # Create
        r = requests.post(
            f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/requests",
            headers=auth_headers,
            json={"name": "health", "method": "GET", "path": "/api/health"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "id" in body
        assert body["name"] == "health"
        assert body["method"] == "GET"
        assert body["path"] == "/api/health"
        req_id = body["id"]

        # List
        r2 = requests.get(
            f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/requests",
            headers=auth_headers, timeout=15,
        )
        assert r2.status_code == 200
        items = r2.json()
        assert any(x["id"] == req_id for x in items)

        # Delete
        r3 = requests.delete(
            f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/requests/{req_id}",
            headers=auth_headers, timeout=15,
        )
        assert r3.status_code == 200
        assert r3.json().get("ok") is True

        # Verify removed
        r4 = requests.get(
            f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/requests",
            headers=auth_headers, timeout=15,
        )
        assert r4.status_code == 200
        assert not any(x["id"] == req_id for x in r4.json())


# ---------- ZIP import ----------
class TestZipImport:
    @pytest.fixture(scope="class")
    def imported(self, auth_headers, test_zip_path):
        with open(test_zip_path, "rb") as f:
            r = requests.post(
                f"{BASE_URL}/api/projects/import/zip",
                params={"project_name": "ZipE2E"},
                files={"file": ("testproj.zip", f, "application/zip")},
                headers=auth_headers,
                timeout=60,
            )
        assert r.status_code == 200, r.text
        return r.json()

    def test_zip_import_response(self, imported):
        assert imported.get("files_count") == 3, imported
        analysis = imported.get("analysis") or {}
        frameworks = set(analysis.get("frameworks") or [])
        for fw in ["fastapi", "next", "react", "tailwind"]:
            assert fw in frameworks, f"missing {fw} in {frameworks}"
        routes = analysis.get("routes") or []
        assert len(routes) == 2, f"expected 2 routes, got {routes}"
        methods = sorted(r["method"] for r in routes)
        assert methods == ["GET", "POST"]
        for r in routes:
            assert r["path"] == "/api/users"
        env_keys = analysis.get("env_keys") or []
        assert env_keys == ["REACT_APP_API_URL", "STRIPE_KEY"], env_keys
        split = analysis.get("split") or {}
        assert split.get("frontend") is True
        assert split.get("backend") is True

    def test_zip_get_analysis_cached(self, auth_headers, imported):
        new_id = imported["id"]
        r = requests.get(f"{BASE_URL}/api/projects/{new_id}/analysis",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200
        a = r.json()
        assert a.get("files_count") == imported["analysis"]["files_count"]
        assert a.get("frameworks") == imported["analysis"]["frameworks"]

    def test_zip_refresh_analysis(self, auth_headers, imported):
        new_id = imported["id"]
        r = requests.post(f"{BASE_URL}/api/projects/{new_id}/analysis/refresh",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200
        a = r.json()
        assert a.get("files_count") == 3
        assert "fastapi" in (a.get("frameworks") or [])

    def test_zip_env_seeded(self, auth_headers, imported):
        new_id = imported["id"]
        r = requests.get(f"{BASE_URL}/api/projects/{new_id}/env",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        rows = r.json()
        keys = {row.get("key") for row in rows}
        assert "REACT_APP_API_URL" in keys
        assert "STRIPE_KEY" in keys
        assert len(rows) == 2
        # Values must be empty/masked
        for row in rows:
            v = row.get("value", "")
            assert v in ("", None) or v == "", f"expected empty value, got {row}"


# ---------- Error paths ----------
class TestImportErrors:
    def test_zip_with_txt_returns_400(self, auth_headers):
        files = {"file": ("notazip.txt", io.BytesIO(b"hello"), "text/plain")}
        r = requests.post(
            f"{BASE_URL}/api/projects/import/zip",
            files=files, headers=auth_headers, timeout=15,
        )
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "zip" in detail.lower(), detail
        assert "Please upload a .zip archive" in detail

    def test_github_invalid_url_returns_400(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/import/github",
            json={"repo_url": "not-a-url"},
            headers=auth_headers, timeout=60,
        )
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert detail.startswith("Import failed:"), f"detail was: {detail!r}"
