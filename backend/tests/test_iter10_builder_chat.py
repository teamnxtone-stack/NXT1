"""Iter10 — Builder chat persistence + bolt-engine proxy regression.

Covers the new /api/v1/builder/chat/{project_id} GET/POST/PUT/DELETE endpoints
and re-verifies that /api/bolt-engine/ still serves COEP/COOP isolation
headers (both with and without ?headless=1).
"""
from __future__ import annotations

import os
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
TIMEOUT = 30


@pytest.fixture
def project_id():
    return f"TEST_proj_{uuid.uuid4().hex[:10]}"


# ---------- /api/v1/builder/chat/{project_id} ----------


class TestBuilderChat:
    def test_get_empty_history_for_unknown_project(self, project_id):
        r = requests.get(f"{BASE_URL}/api/v1/builder/chat/{project_id}", timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert data["project_id"] == project_id
        assert data["messages"] == []

    def test_post_user_message_returns_created_message(self, project_id):
        r = requests.post(
            f"{BASE_URL}/api/v1/builder/chat/{project_id}",
            json={"role": "user", "content": "hello"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text
        msg = r.json()
        for k in ("id", "role", "content", "ts"):
            assert k in msg, f"missing field {k} in {msg}"
        assert msg["role"] == "user"
        assert msg["content"] == "hello"
        assert isinstance(msg["ts"], (int, float))
        assert msg["id"].startswith("m_")

        # GET should now return the message
        g = requests.get(f"{BASE_URL}/api/v1/builder/chat/{project_id}", timeout=TIMEOUT)
        assert g.status_code == 200
        gd = g.json()
        assert len(gd["messages"]) == 1
        assert gd["messages"][0]["content"] == "hello"
        assert gd["messages"][0]["id"] == msg["id"]

        # cleanup
        requests.delete(f"{BASE_URL}/api/v1/builder/chat/{project_id}", timeout=TIMEOUT)

    def test_post_invalid_role_returns_400(self, project_id):
        r = requests.post(
            f"{BASE_URL}/api/v1/builder/chat/{project_id}",
            json={"role": "system", "content": "nope"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 400

    def test_put_replaces_full_history(self, project_id):
        # Seed two messages via POST
        for c in ("first", "second"):
            requests.post(
                f"{BASE_URL}/api/v1/builder/chat/{project_id}",
                json={"role": "user", "content": c},
                timeout=TIMEOUT,
            )

        # Replace with one assistant message
        new_msgs = [
            {"id": "m_replaced1", "role": "assistant", "content": "final answer", "ts": 1234567890.0}
        ]
        r = requests.put(
            f"{BASE_URL}/api/v1/builder/chat/{project_id}",
            json={"messages": new_msgs},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["project_id"] == project_id
        assert len(data["messages"]) == 1
        assert data["messages"][0]["role"] == "assistant"
        assert data["messages"][0]["content"] == "final answer"

        # Verify persisted
        g = requests.get(f"{BASE_URL}/api/v1/builder/chat/{project_id}", timeout=TIMEOUT)
        assert g.status_code == 200
        gd = g.json()
        assert len(gd["messages"]) == 1
        assert gd["messages"][0]["id"] == "m_replaced1"

        requests.delete(f"{BASE_URL}/api/v1/builder/chat/{project_id}", timeout=TIMEOUT)

    def test_delete_clears_history(self, project_id):
        requests.post(
            f"{BASE_URL}/api/v1/builder/chat/{project_id}",
            json={"role": "user", "content": "to be deleted"},
            timeout=TIMEOUT,
        )
        r = requests.delete(f"{BASE_URL}/api/v1/builder/chat/{project_id}", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("ok") is True

        g = requests.get(f"{BASE_URL}/api/v1/builder/chat/{project_id}", timeout=TIMEOUT)
        assert g.status_code == 200
        assert g.json()["messages"] == []


# ---------- /api/bolt-engine/ COEP+COOP regression ----------


class TestBoltProxyIsolation:
    def _assert_isolation_headers(self, resp):
        # Headers are case-insensitive in requests
        coep = resp.headers.get("cross-origin-embedder-policy", "").lower()
        coop = resp.headers.get("cross-origin-opener-policy", "").lower()
        assert coep == "credentialless", f"COEP wrong: {coep!r}"
        assert coop == "same-origin", f"COOP wrong: {coop!r}"

    def test_bolt_engine_root_returns_200_with_isolation(self):
        r = requests.get(f"{BASE_URL}/api/bolt-engine/", timeout=TIMEOUT)
        assert r.status_code == 200, r.status_code
        self._assert_isolation_headers(r)
        assert "html" in r.headers.get("content-type", "").lower()

    def test_bolt_engine_headless_query_returns_200_with_isolation(self):
        r = requests.get(f"{BASE_URL}/api/bolt-engine/?headless=1", timeout=TIMEOUT)
        assert r.status_code == 200, r.status_code
        self._assert_isolation_headers(r)
