"""Live integration tests for Phase B.14 AgentOS endpoints.

Hits the actual preview pod via REACT_APP_BACKEND_URL with the shared
APP password (`555`). Covers the 6 net-new endpoints plus regression
checks for the existing six.
"""
from __future__ import annotations

import os
import re
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://preserve-deploy-1.preview.emergentagent.com",
).rstrip("/")
PASSWORD = "555"
API = f"{BASE_URL}/api/v1/agentos"
TIMEOUT = 30


@pytest.fixture(scope="module")
def token() -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"password": PASSWORD}, timeout=TIMEOUT)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in {data}"
    return tok


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# --------- Regression: previously-shipped endpoints still respond ---------
def test_profile_get(H):
    r = requests.get(f"{API}/profile", headers=H, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "target_titles" in body


def test_jobs_list(H):
    r = requests.get(f"{API}/jobs", headers=H, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_leads_list(H):
    r = requests.get(f"{API}/leads", headers=H, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_approvals_list(H):
    r = requests.get(f"{API}/approvals", headers=H, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_system_keys(H):
    r = requests.get(f"{API}/system/keys", headers=H, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "llm" in body and "voice" in body and "platforms" in body


def test_resume_master(H):
    r = requests.get(f"{API}/resume/master", headers=H, timeout=TIMEOUT)
    # 200 or 404 are both acceptable depending on whether one exists
    assert r.status_code in (200, 404), r.text


# --------- NEW: Phase B.14 endpoints ---------
def test_social_status(H):
    r = requests.get(f"{API}/social/status", headers=H, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["service"] == "postiz"
    assert "reachable" in body
    assert isinstance(body["reachable"], bool)
    assert "url" in body and "boot_hint" in body
    # In the preview pod, postiz is not deployed → must be unreachable
    assert body["reachable"] is False


def test_builder_status(H):
    r = requests.get(f"{API}/builder/status", headers=H, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["service"] == "bolt.diy"
    assert isinstance(body["reachable"], bool)
    assert body["reachable"] is False
    assert "url" in body and "boot_hint" in body


def test_founders_config_defaults(H):
    r = requests.get(f"{API}/founders/config", headers=H, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("stages", "industries", "geographies", "keywords", "exclude_keywords"):
        assert k in body, f"missing {k} in {body}"


def test_founders_config_partial_put_preserves_defaults(H):
    # PUT only stages + keywords → industries should remain defaulted.
    new_stages = ["pre-seed"]
    new_keywords = ["YC W26", "indie hacker"]
    r = requests.put(f"{API}/founders/config",
                     headers=H,
                     json={"stages": new_stages, "keywords": new_keywords},
                     timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stages"] == new_stages
    assert body["keywords"] == new_keywords
    # Defaults preserved for un-touched fields.
    assert isinstance(body["industries"], list) and len(body["industries"]) > 0
    assert isinstance(body["geographies"], list) and len(body["geographies"]) > 0


def test_founders_stats_shape(H):
    r = requests.get(f"{API}/founders/stats", headers=H, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("drafted", "queued", "sent", "rejected", "total"):
        assert k in body
        assert isinstance(body[k], int)


def test_social_strategies_list(H):
    r = requests.get(f"{API}/social/strategies", headers=H, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_social_strategy_validation_422(H):
    # cadence_per_week bounded 1..21
    r = requests.post(f"{API}/social/strategy", headers=H,
                      json={"goals": "x", "cadence_per_week": 99},
                      timeout=TIMEOUT)
    assert r.status_code == 422, r.text


def test_social_strategy_generation(H):
    """Hits real LLM via ANTHROPIC_API_KEY — may take 10-30s.
    Accept any 2xx as success per the brief."""
    r = requests.post(
        f"{API}/social/strategy",
        headers=H,
        json={
            "goals": "Share my AgentOS build notes for a week",
            "platforms": ["linkedin"],
            "cadence_per_week": 3,
        },
        timeout=90,
    )
    assert 200 <= r.status_code < 300, f"{r.status_code} {r.text[:300]}"
    body = r.json()
    assert "posts" in body
    assert isinstance(body["posts"], list)


# --------- Auth negative ---------
def test_unauth_request_rejected():
    r = requests.get(f"{API}/profile", timeout=TIMEOUT)
    assert r.status_code in (401, 403), r.text
