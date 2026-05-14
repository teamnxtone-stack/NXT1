"""Tests for persisted agent conversations (Phase B.12).

Exercises the create → fetch → list → delete path against an in-memory
mock Mongo collection. No real LLM calls.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeCursor:
    """Minimal async cursor for our tests — supports .sort().limit().to_list()."""
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, length=None):
        return self._docs[:length] if length else self._docs


class _FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    def find(self, query, projection=None):
        # Very small filter — match exact equality on top-level fields.
        out = []
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                out.append({k: v for k, v in d.items() if not projection or k in projection or projection.get(k, 1) != 0})
                if projection:
                    # Honour explicit excludes ({_id:0, messages:0})
                    excluded = {k for k, v in projection.items() if v == 0}
                    out[-1] = {k: v for k, v in out[-1].items() if k not in excluded}
        return _FakeCursor(out)

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                if projection:
                    excluded = {k for k, v in projection.items() if v == 0}
                    return {k: v for k, v in d.items() if k not in excluded}
                return d
        return None

    async def insert_one(self, doc):
        self.docs.append(doc)
        return type("R", (), {"inserted_id": "x"})()

    async def update_one(self, query, update):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                if "$push" in update:
                    for k, v in update["$push"].items():
                        d.setdefault(k, []).append(v)
                if "$set" in update:
                    d.update(update["$set"])
                return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in query.items()):
                self.docs.pop(i)
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()


@pytest.fixture
def client(monkeypatch):
    from routes import agents_catalog
    from routes._deps import verify_token

    fake = {}
    class _FakeDb:
        def __getitem__(self, k):
            return fake.setdefault(k, _FakeCollection())

    monkeypatch.setattr(agents_catalog, "db", _FakeDb())
    agents_catalog._CACHE = None

    app = FastAPI()
    app.include_router(agents_catalog.router)
    app.dependency_overrides[verify_token] = lambda: "test-user"
    return TestClient(app)


def test_create_and_fetch_conversation(client):
    item_id = "agent::backend-development::backend-architect"
    r = client.post("/api/agents/conversations", json={"item_id": item_id, "title": "tdd plan"})
    assert r.status_code == 200, r.text
    conv = r.json()
    assert conv["item_id"] == item_id
    assert conv["title"] == "tdd plan"
    assert conv["messages"] == []
    cid = conv["id"]

    # Fetch one
    r = client.get(f"/api/agents/conversations/{cid}")
    assert r.status_code == 200
    assert r.json()["id"] == cid

    # By-agent listing
    r = client.get(f"/api/agents/conversations/by-agent/{item_id}")
    assert r.status_code == 200
    listed = r.json()
    assert any(c["id"] == cid for c in listed)


def test_create_rejects_unknown_item(client):
    r = client.post("/api/agents/conversations", json={"item_id": "agent::nope::nope"})
    assert r.status_code == 404


def test_delete_conversation(client):
    item_id = "skill::github"
    cid = client.post("/api/agents/conversations", json={"item_id": item_id}).json()["id"]
    assert client.delete(f"/api/agents/conversations/{cid}").status_code == 200
    assert client.get(f"/api/agents/conversations/{cid}").status_code == 404
    assert client.delete(f"/api/agents/conversations/{cid}").status_code == 404


def test_user_scope_isolation(client, monkeypatch):
    """Conversations from one user must not be visible to another."""
    from routes import agents_catalog
    from routes._deps import verify_token

    # Create as the default test-user
    item_id = "skill::github"
    cid = client.post("/api/agents/conversations", json={"item_id": item_id}).json()["id"]

    # Re-route auth to a different user.
    client.app.dependency_overrides[verify_token] = lambda: "other-user"
    r = client.get(f"/api/agents/conversations/{cid}")
    assert r.status_code == 404
    r = client.get(f"/api/agents/conversations/by-agent/{item_id}")
    assert r.status_code == 200
    assert r.json() == []

    # Restore
    client.app.dependency_overrides[verify_token] = lambda: "test-user"
    _ = agents_catalog
