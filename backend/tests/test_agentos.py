"""Smoke tests for the AgentOS routes (Phase B.13)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Reuse the in-memory Mongo fake from the conversations tests.
from tests.test_agents_conversations import _FakeCollection


@pytest.fixture
def client(monkeypatch):
    from routes import agentos
    from routes._deps import verify_token

    fake_collections: dict = {}
    class _FakeDb:
        def __getitem__(self, k):
            return fake_collections.setdefault(k, _FakeCollection())

    monkeypatch.setattr(agentos, "db", _FakeDb())

    app = FastAPI()
    app.include_router(agentos.router)
    app.dependency_overrides[verify_token] = lambda: "test-user"
    return TestClient(app)


def test_profile_auto_creates_and_updates(client):
    r = client.get("/api/v1/agentos/profile")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"] == "test-user"
    assert body["target_titles"]  # default applied

    r = client.put("/api/v1/agentos/profile", json={"name": "Alice", "remote_only": False})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Alice"
    assert body["remote_only"] is False
    # Defaults preserved for un-touched fields.
    assert body["daily_application_limit"] == 20


def test_system_keys_reports_shape(client):
    r = client.get("/api/v1/agentos/system/keys")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "llm" in body
    assert "voice" in body
    assert "platforms" in body
    # Never leak the actual key values.
    for grp in body.values():
        if isinstance(grp, dict):
            for v in grp.values():
                assert isinstance(v, bool)


def test_approvals_round_trip(client):
    # Empty queue initially.
    r = client.get("/api/v1/agentos/approvals")
    assert r.json() == []
    # Decisions on non-existent ids should 404 (not crash).
    assert client.post("/api/v1/agentos/approvals/nope/approve").status_code == 404
    assert client.post("/api/v1/agentos/approvals/nope/reject").status_code == 404


def test_jobs_list_returns_empty(client):
    r = client.get("/api/v1/agentos/jobs")
    assert r.status_code == 200
    assert r.json() == []


def test_lead_draft_requires_real_payload(client):
    r = client.post("/api/v1/agentos/leads/draft", json={"platform": "linkedin"})
    assert r.status_code == 422   # missing name + snippet



# ---------- Phase B.14 — new endpoints (Social / Founders / Builder) -----------

def test_social_status_returns_shape(client, monkeypatch):
    # Don't actually hit localhost:5000 during the test.
    from routes import agentos
    async def _fake_probe(*a, **kw): return False
    monkeypatch.setattr(agentos, "_probe_url", _fake_probe)
    r = client.get("/api/v1/agentos/social/status")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "postiz"
    assert body["reachable"] is False
    assert "boot_hint" in body and "url" in body


def test_builder_status_returns_shape(client, monkeypatch):
    from routes import agentos
    async def _fake_probe(*a, **kw): return False
    monkeypatch.setattr(agentos, "_probe_url", _fake_probe)
    r = client.get("/api/v1/agentos/builder/status")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "bolt.diy"
    assert "url" in body and body["reachable"] is False


def test_founders_config_round_trip(client):
    # First GET auto-creates with defaults.
    r = client.get("/api/v1/agentos/founders/config")
    assert r.status_code == 200
    body = r.json()
    assert "stages" in body and "industries" in body
    assert "seed" in body["stages"]

    # PUT updates only the provided fields.
    r = client.put("/api/v1/agentos/founders/config", json={
        "stages": ["pre-seed"],
        "keywords": ["YC W26", "indie hacker"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["stages"] == ["pre-seed"]
    assert body["keywords"] == ["YC W26", "indie hacker"]
    # Defaults preserved for un-touched fields.
    assert "AI" in body["industries"]


def test_founders_stats_returns_zeroes(client):
    r = client.get("/api/v1/agentos/founders/stats")
    assert r.status_code == 200
    body = r.json()
    assert body == {"drafted": 0, "queued": 0, "sent": 0, "rejected": 0, "total": 0}


def test_social_strategy_requires_valid_cadence(client):
    # cadence_per_week is bounded 1..21.
    r = client.post("/api/v1/agentos/social/strategy",
                    json={"goals": "x", "cadence_per_week": 99})
    assert r.status_code == 422
