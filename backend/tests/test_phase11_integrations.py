"""Phase 11 — GitHub Save integration + Developer Mode plumbing tests."""
import os
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PASSWORD = os.environ.get("APP_PASSWORD", "555")


def _token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"password": PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr() -> dict:
    return {"Authorization": f"Bearer {_token()}"}


class TestGithubIntegration:
    def test_github_save_route_exists(self):
        """Endpoint should exist; un-authenticated returns 401."""
        r = requests.post(
            f"{BASE_URL}/api/projects/no-such-project/github/save",
            json={},
            timeout=15,
        )
        assert r.status_code == 401, r.text

    def test_github_save_unknown_project(self):
        r = requests.post(
            f"{BASE_URL}/api/projects/no-such-project/github/save",
            headers=_hdr(),
            json={},
            timeout=15,
        )
        assert r.status_code == 404, r.text

    def test_github_status_unknown_project(self):
        r = requests.get(
            f"{BASE_URL}/api/projects/no-such-project/github",
            headers=_hdr(),
            timeout=15,
        )
        assert r.status_code == 404, r.text

    def test_github_save_existing_project_returns_actionable_error(self):
        """Token in this environment is read-only — we expect a 502 with the
        actionable hint pointing the user to upgrade the PAT scopes."""
        # Create a tiny project so we have something to push
        r = requests.post(
            f"{BASE_URL}/api/projects",
            headers=_hdr(),
            json={"name": "phase11_gh_test", "description": ""},
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]
        try:
            r = requests.post(
                f"{BASE_URL}/api/projects/{pid}/github/save",
                headers=_hdr(),
                json={"private": True},
                timeout=30,
            )
            # Either succeeds (if token is upgraded) or returns the friendly 502.
            assert r.status_code in (200, 502), r.text
            if r.status_code == 502:
                detail = r.json().get("detail", "")
                # Friendly hint should mention scopes / read & write so the user
                # knows what to fix.
                assert "read & write" in detail or "blocked" in detail.lower(), detail
        finally:
            requests.delete(
                f"{BASE_URL}/api/projects/{pid}",
                headers=_hdr(),
                timeout=10,
            )


class TestSecretsHasGithubEntries:
    def test_github_token_listed(self):
        r = requests.get(
            f"{BASE_URL}/api/system/secrets",
            headers=_hdr(),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        keys = {it["key"] for it in r.json().get("items", [])}
        assert "GITHUB_TOKEN" in keys
        assert "SUPABASE_SERVICE_ROLE_KEY" in keys
        assert "NEON_API_KEY" in keys
