"""Agent Memory — per-user persistent context shared across all NXT1 agents.

Distinct from `project_memory` (project-scoped, code-aware). This stores
*user-level* facts the social/studio/future agents need to keep continuity:

  • brand voice, hard rules ("never use the word 'synergy'")
  • past successful post topics + captions
  • style preferences ("I like one-line hooks")
  • user-uploaded reference images / brand assets
  • feedback ("regenerated this one — too corporate")

Collection: `agent_memory`
Shape:
  {
    id, user_id, scope (e.g. "social" | "studio" | "global"),
    kind: "fact" | "preference" | "example" | "feedback" | "image" | "system",
    summary: str (<=300 chars, used in prompts),
    payload: dict,
    pinned: bool,   # always inject if true
    created_at, updated_at
  }
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("nxt1.agent_memory")

VALID_KINDS = {"fact", "preference", "example", "feedback", "image", "system"}
VALID_SCOPES = {"global", "social", "studio", "agents"}

MAX_PROMPT_CHARS = 2200  # cap how much memory we inject per generation


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def remember(db, *, user_id: str, scope: str, kind: str, summary: str,
                   payload: Optional[dict] = None, pinned: bool = False) -> dict:
    if kind not in VALID_KINDS:
        raise ValueError(f"Unknown kind '{kind}'. Allowed: {sorted(VALID_KINDS)}")
    if scope not in VALID_SCOPES:
        raise ValueError(f"Unknown scope '{scope}'. Allowed: {sorted(VALID_SCOPES)}")
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "scope": scope,
        "kind": kind,
        "summary": (summary or "")[:300],
        "payload": payload or {},
        "pinned": bool(pinned),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.agent_memory.insert_one(dict(doc))
    return doc


async def recall(db, *, user_id: str, scope: Optional[str] = None,
                 kind: Optional[str] = None, limit: int = 50) -> list[dict]:
    q: dict = {"user_id": user_id}
    if scope:
        q["scope"] = {"$in": list({scope, "global"})}
    if kind:
        q["kind"] = kind
    # Pinned first, then newest
    cur = db.agent_memory.find(q, {"_id": 0}).sort([("pinned", -1), ("created_at", -1)]).limit(int(limit))
    return [d async for d in cur]


async def forget(db, *, user_id: str, memory_id: str) -> int:
    res = await db.agent_memory.delete_one({"user_id": user_id, "id": memory_id})
    return int(res.deleted_count)


async def pin(db, *, user_id: str, memory_id: str, pinned: bool = True) -> int:
    res = await db.agent_memory.update_one(
        {"user_id": user_id, "id": memory_id},
        {"$set": {"pinned": bool(pinned), "updated_at": _now()}},
    )
    return int(res.matched_count)


async def update_summary(db, *, user_id: str, memory_id: str, summary: str) -> int:
    res = await db.agent_memory.update_one(
        {"user_id": user_id, "id": memory_id},
        {"$set": {"summary": summary[:300], "updated_at": _now()}},
    )
    return int(res.matched_count)


async def build_context_block(db, *, user_id: str, scope: str = "global",
                              max_chars: int = MAX_PROMPT_CHARS) -> str:
    """Return a ready-to-inject prompt snippet of the user's memory.

    Pinned items first, then most recent. Stops cleanly under max_chars.
    """
    items = await recall(db, user_id=user_id, scope=scope, limit=60)
    if not items:
        return ""
    lines = ["=== USER MEMORY (auto-loaded) ==="]
    used = len(lines[0]) + 1
    for it in items:
        tag = "★" if it.get("pinned") else "•"
        kind = it.get("kind", "fact")
        line = f"{tag} [{kind}] {it.get('summary','').strip()}"
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    if len(lines) == 1:
        return ""
    lines.append("=== END MEMORY ===")
    return "\n".join(lines)
