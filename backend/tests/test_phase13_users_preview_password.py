"""Phase 13 — User accounts (email + password) + preview password protection."""
import os
import time
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PASSWORD = os.environ.get("APP_PASSWORD", "555")


def _admin_token() -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _new_email() -> str:
    return f"phase13_{int(time.time()*1000)}@nxt1.test"


class TestUserAccounts:
    def test_signup_signin_me(self):
        email = _new_email()
        r = requests.post(f"{BASE_URL}/api/users/signup",
                          json={"email": email, "password": "test1234", "name": "Tester"},
                          timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        token = data["token"]
        assert data["user"]["email"] == email
        assert data["user"]["onboarded"] is False

        # Duplicate email -> 409
        r = requests.post(f"{BASE_URL}/api/users/signup",
                          json={"email": email, "password": "test1234"}, timeout=15)
        assert r.status_code == 409, r.text

        # Sign in -> 200
        r = requests.post(f"{BASE_URL}/api/users/signin",
                          json={"email": email, "password": "test1234"}, timeout=15)
        assert r.status_code == 200, r.text

        # Wrong password -> 401
        r = requests.post(f"{BASE_URL}/api/users/signin",
                          json={"email": email, "password": "nope"}, timeout=15)
        assert r.status_code == 401, r.text

        # /users/me (user)
        r = requests.get(f"{BASE_URL}/api/users/me",
                         headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["email"] == email

        # /users/me (admin)
        admin_token = _admin_token()
        r = requests.get(f"{BASE_URL}/api/users/me",
                         headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_signup_validation(self):
        r = requests.post(f"{BASE_URL}/api/users/signup",
                          json={"email": "not-an-email", "password": "test1234"}, timeout=10)
        assert r.status_code == 400
        r = requests.post(f"{BASE_URL}/api/users/signup",
                          json={"email": _new_email(), "password": "short"}, timeout=10)
        assert r.status_code == 400

    def test_onboarding(self):
        email = _new_email()
        r = requests.post(f"{BASE_URL}/api/users/signup",
                          json={"email": email, "password": "test1234"}, timeout=15)
        token = r.json()["token"]
        r = requests.post(f"{BASE_URL}/api/users/me/onboarding",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"company": "Acme", "use_case": "build_app",
                                "request": "Need a CRM.", "referral": "twitter"},
                          timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["onboarded"] is True


class TestPreviewPassword:
    def test_password_lock_unlock(self):
        admin = _admin_token()
        # Use any existing project (assumes at least one with files)
        r = requests.get(f"{BASE_URL}/api/projects",
                         headers={"Authorization": f"Bearer {admin}"}, timeout=10)
        projects = r.json()
        if not projects:
            return  # nothing to test against
        pid = projects[0]["id"]

        # Set a password
        r = requests.post(f"{BASE_URL}/api/projects/{pid}/preview",
                          headers={"Authorization": f"Bearer {admin}"},
                          json={"password": "letmein"}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        slug = body["slug"]
        assert body["password_protected"] is True
        # password value never echoed back
        assert "password" not in body or body.get("password") in (None, "")

        # Public load -> 401 (locked HTML)
        r = requests.get(f"{BASE_URL}/api/preview/{slug}", timeout=10)
        assert r.status_code == 401
        assert "Password required" in r.text or "<form" in r.text

        # Wrong password -> 401
        r = requests.post(f"{BASE_URL}/api/preview/{slug}/unlock",
                          json={"password": "wrong"}, timeout=10)
        assert r.status_code == 401

        # Correct password -> ok + cookie
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/preview/{slug}/unlock",
                   json={"password": "letmein"}, timeout=10)
        assert r.status_code == 200, r.text

        # Now public load should succeed (with cookie)
        r = s.get(f"{BASE_URL}/api/preview/{slug}", timeout=10)
        assert r.status_code == 200, r.text

        # Remove password
        r = requests.post(f"{BASE_URL}/api/projects/{pid}/preview",
                          headers={"Authorization": f"Bearer {admin}"},
                          json={"password": ""}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["password_protected"] is False
        # Public load works without unlock
        r = requests.get(f"{BASE_URL}/api/preview/{slug}", timeout=10)
        assert r.status_code == 200
