"""Phase 12 — Shareable preview links + AI narration tests."""
import os
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PASSWORD = os.environ.get("APP_PASSWORD", "555")


def _token() -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr() -> dict:
    return {"Authorization": f"Bearer {_token()}"}


def _new_project_with_files(files=None) -> str:
    r = requests.post(f"{BASE_URL}/api/projects",
                      headers=_hdr(),
                      json={"name": "phase12_preview_test", "description": ""},
                      timeout=15)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    payload = files or [
        {"path": "index.html", "content": "<html><body><h1>Preview!</h1></body></html>"},
    ]
    for f in payload:
        rr = requests.put(f"{BASE_URL}/api/projects/{pid}/files/{f['path']}",
                          headers=_hdr(), json={"content": f["content"]},
                          timeout=15)
        assert rr.status_code in (200, 201), rr.text
    return pid


class TestPreviewLinks:
    def test_create_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/projects/x/preview",
                          json={}, timeout=10)
        assert r.status_code == 401

    def test_create_unknown_project(self):
        r = requests.post(f"{BASE_URL}/api/projects/no-such/preview",
                          headers=_hdr(), json={}, timeout=10)
        assert r.status_code == 404

    def test_create_then_get_then_serve_public(self):
        pid = _new_project_with_files()
        try:
            # 1st create
            r = requests.post(f"{BASE_URL}/api/projects/{pid}/preview",
                              headers=_hdr(), json={}, timeout=10)
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["slug"] and len(data["slug"]) >= 6
            assert "/p/" in data["url"]
            # URL must NOT expose the underlying preview host. PREVIEW_PUBLIC_ORIGIN
            # is configured to https://nxtone.tech in /app/backend/.env.
            assert "emergentagent" not in data["url"], data["url"]
            assert data["build_count"] == 1
            assert data["public"] is True
            slug = data["slug"]

            # GET
            r = requests.get(f"{BASE_URL}/api/projects/{pid}/preview",
                             headers=_hdr(), timeout=10)
            assert r.status_code == 200
            assert r.json()["slug"] == slug

            # 2nd POST refreshes — same slug, build_count bumps
            r = requests.post(f"{BASE_URL}/api/projects/{pid}/preview",
                              headers=_hdr(), json={}, timeout=10)
            assert r.status_code == 200, r.text
            assert r.json()["slug"] == slug
            assert r.json()["build_count"] == 2

            # Public serving (no auth)
            r = requests.get(f"{BASE_URL}/api/preview/{slug}", timeout=10)
            assert r.status_code == 200, r.text
            assert "Preview!" in r.text or "<h1>" in r.text

            # Private toggle
            r = requests.post(f"{BASE_URL}/api/projects/{pid}/preview",
                              headers=_hdr(), json={"public": False}, timeout=10)
            assert r.status_code == 200
            r = requests.get(f"{BASE_URL}/api/preview/{slug}", timeout=10)
            assert r.status_code == 403

            # Delete
            r = requests.delete(f"{BASE_URL}/api/projects/{pid}/preview",
                                headers=_hdr(), timeout=10)
            assert r.status_code == 200
            r = requests.get(f"{BASE_URL}/api/preview/{slug}", timeout=10)
            assert r.status_code == 404
        finally:
            requests.delete(f"{BASE_URL}/api/projects/{pid}",
                            headers=_hdr(), timeout=10)

    def test_unknown_slug_returns_404(self):
        r = requests.get(f"{BASE_URL}/api/preview/zzzzzzzz", timeout=10)
        assert r.status_code == 404
