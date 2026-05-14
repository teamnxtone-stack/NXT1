"""Phase 14 — Admin user management + AI Site Editor."""
import os
import time
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PASSWORD = os.environ.get("APP_PASSWORD", "555")


def _admin_token() -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"password": PASSWORD}, timeout=15)
    return r.json()["token"]


def _hdr() -> dict:
    return {"Authorization": f"Bearer {_admin_token()}"}


class TestUserAccessAdmin:
    def test_list_users_admin_only(self):
        # Unauthed → 401
        r = requests.get(f"{BASE_URL}/api/users", timeout=10)
        assert r.status_code == 401

        # Regular user → 403
        email = f"phase14_{int(time.time()*1000)}@nxt1.test"
        rs = requests.post(f"{BASE_URL}/api/users/signup",
                           json={"email": email, "password": "test1234"}, timeout=15)
        utoken = rs.json()["token"]
        r = requests.get(f"{BASE_URL}/api/users",
                         headers={"Authorization": f"Bearer {utoken}"}, timeout=10)
        assert r.status_code == 403

        # Admin → 200
        r = requests.get(f"{BASE_URL}/api/users", headers=_hdr(), timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(u["email"] == email for u in items)

    def test_approve_then_deny(self):
        email = f"phase14_approve_{int(time.time()*1000)}@nxt1.test"
        r = requests.post(f"{BASE_URL}/api/users/signup",
                          json={"email": email, "password": "test1234"}, timeout=15)
        uid = r.json()["user"]["user_id"]
        assert r.json()["user"]["access_status"] == "pending"

        # Approve
        r = requests.post(f"{BASE_URL}/api/users/{uid}/access",
                          headers=_hdr(),
                          json={"access_status": "approved"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["access_status"] == "approved"

        # Deny
        r = requests.post(f"{BASE_URL}/api/users/{uid}/access",
                          headers=_hdr(),
                          json={"access_status": "denied"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["access_status"] == "denied"

        # Bad value
        r = requests.post(f"{BASE_URL}/api/users/{uid}/access",
                          headers=_hdr(),
                          json={"access_status": "garbage"}, timeout=10)
        assert r.status_code == 400


class TestSiteEditor:
    def test_admin_only(self):
        # Unauthed
        r = requests.get(f"{BASE_URL}/api/site-editor/files", timeout=10)
        assert r.status_code == 401

        # Regular user → 403
        email = f"phase14_se_{int(time.time()*1000)}@nxt1.test"
        rs = requests.post(f"{BASE_URL}/api/users/signup",
                           json={"email": email, "password": "test1234"}, timeout=15)
        utoken = rs.json()["token"]
        r = requests.get(f"{BASE_URL}/api/site-editor/files",
                         headers={"Authorization": f"Bearer {utoken}"}, timeout=10)
        assert r.status_code == 403

    def test_list_files(self):
        r = requests.get(f"{BASE_URL}/api/site-editor/files",
                         headers=_hdr(), timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        paths = {it["path"] for it in items}
        # The whitelist should always include these:
        assert "frontend/src/pages/LandingPage.jsx" in paths
        assert "frontend/src/components/Brand.jsx" in paths

    def test_propose_validation(self):
        r = requests.post(f"{BASE_URL}/api/site-editor/propose",
                          headers=_hdr(),
                          json={"prompt": ""}, timeout=10)
        assert r.status_code == 400
        # Non-whitelisted path → 400
        r = requests.post(f"{BASE_URL}/api/site-editor/propose",
                          headers=_hdr(),
                          json={"prompt": "x", "paths": ["backend/server.py"]}, timeout=10)
        assert r.status_code == 400

    def test_history_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/site-editor/history",
                         headers=_hdr(), timeout=10)
        assert r.status_code == 200
        assert "items" in r.json()
