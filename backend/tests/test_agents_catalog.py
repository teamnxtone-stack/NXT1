"""Backend tests for the unified agents+OpenClaw catalog.

Phase B.11 (2026-05-13). Exercises both the loader cache and the two
endpoints (catalog + stats). We don't spin up the full FastAPI app —
just the router itself with a TestClient — to keep the unit test fast
and dependency-free.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "agents_catalog.json"


@pytest.fixture(autouse=True)
def _reset_cache():
    from routes import agents_catalog
    agents_catalog._CACHE = None
    yield
    agents_catalog._CACHE = None


@pytest.fixture
def client(monkeypatch):
    """Build an isolated FastAPI app with only the catalog router and a
    bypassed auth dependency."""
    from routes import agents_catalog
    from routes._deps import verify_token

    app = FastAPI()
    app.include_router(agents_catalog.router)
    # Bypass auth for unit tests.
    app.dependency_overrides[verify_token] = lambda: "test-user"
    return TestClient(app)


def test_catalog_file_exists():
    assert CATALOG_PATH.exists(), (
        "Run `python3 backend/scripts/build_agents_catalog.py` to bake the catalog."
    )
    data = json.loads(CATALOG_PATH.read_text())
    assert data["version"] == 1
    assert data["agents_count"] >= 100, data["agents_count"]
    assert data["skills_count"] >= 30, data["skills_count"]


def test_catalog_endpoint_returns_full_payload(client):
    r = client.get("/api/agents/catalog")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data
    assert data["agents_count"] >= 100
    assert data["skills_count"] >= 30
    # Every item has the required machine-readable fields.
    for item in data["items"][:25]:
        assert {"id", "kind", "name", "category", "description"} <= set(item.keys())
        assert item["kind"] in {"agent", "skill"}


def test_stats_endpoint_aggregates_counts(client):
    r = client.get("/api/agents/catalog/stats")
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats["total"] == stats["agents_count"] + stats["skills_count"]
    assert stats["by_kind"].get("agent", 0) == stats["agents_count"]
    assert stats["by_kind"].get("skill", 0) == stats["skills_count"]
    # At least 30 distinct categories from the combined catalog.
    assert len(stats["by_category"]) >= 30


def test_catalog_cache_is_warm_on_second_call(client):
    """Calling the endpoint twice must hit the in-process cache —
    no second filesystem read."""
    from routes import agents_catalog
    assert agents_catalog._CACHE is None
    client.get("/api/agents/catalog")
    cached = agents_catalog._CACHE
    assert cached is not None
    client.get("/api/agents/catalog/stats")
    # Same object reference — i.e. NOT re-read.
    assert agents_catalog._CACHE is cached
