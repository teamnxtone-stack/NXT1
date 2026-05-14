"""NXT1 — Project Memory (Phase 11 W2-E foundation).

Lightweight persistent project context layer. The orchestrator + builder
generators write structured notes here (decisions, file maps, framework
locks, integration receipts) so subsequent prompts on the same project can
be “code-aware.”

This is intentionally MINIMAL in shape — a single Mongo collection with a
thin service layer. We're laying foundation, not shipping autonomous
improvements yet.

Schema (collection: project_memory):
  {
    id:            str (uuid)
    project_id:    str
    kind:          str   # "decision" | "file-map" | "framework" | "integration" | "note"
    summary:       str
    payload:       dict   # free-form details
    created_at:    ISO datetime str (UTC)
    pinned:        bool   # pinned memories are always included in context
  }

Usage:
    from services.project_memory import remember, recall, recall_pinned
    await remember(project_id, kind="decision", summary="Chose Next.js + Tailwind", payload={...})
    notes = await recall(project_id, limit=20)
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger("nxt1.project_memory")

_VALID_KINDS = {"decision", "file-map", "framework", "integration", "note"}

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


def _get_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        url = os.environ.get("MONGO_URL")
        if not url:
            raise RuntimeError("MONGO_URL not configured")
        _client = AsyncIOMotorClient(url)
        db_name = os.environ.get("DB_NAME", "test_database")
        _db = _client[db_name]
    return _db


async def remember(project_id: str, *, kind: str, summary: str,
                    payload: Optional[Dict] = None, pinned: bool = False) -> Dict:
    """Persist a memory entry for a project. Returns the inserted document."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"Unknown kind '{kind}'. Allowed: {sorted(_VALID_KINDS)}")
    doc = {
        "id":         str(uuid.uuid4()),
        "project_id": project_id,
        "kind":       kind,
        "summary":    summary[:500],
        "payload":    payload or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pinned":     bool(pinned),
    }
    await _get_db().project_memory.insert_one({**doc})
    return doc


async def recall(project_id: str, *, kind: Optional[str] = None,
                  limit: int = 50) -> List[Dict]:
    q: Dict = {"project_id": project_id}
    if kind:
        q["kind"] = kind
    cursor = _get_db().project_memory.find(q, {"_id": 0}).sort("created_at", -1).limit(int(limit))
    return [d async for d in cursor]


async def recall_pinned(project_id: str) -> List[Dict]:
    cursor = _get_db().project_memory.find(
        {"project_id": project_id, "pinned": True}, {"_id": 0}
    ).sort("created_at", -1)
    return [d async for d in cursor]


async def forget(project_id: str, *, memory_id: str) -> int:
    res = await _get_db().project_memory.delete_one({"project_id": project_id, "id": memory_id})
    return int(res.deleted_count)


async def pin(project_id: str, *, memory_id: str, pinned: bool = True) -> int:
    res = await _get_db().project_memory.update_one(
        {"project_id": project_id, "id": memory_id},
        {"$set": {"pinned": bool(pinned)}},
    )
    return int(res.matched_count)
