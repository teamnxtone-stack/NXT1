"""Agents + OpenClaw skills catalog endpoint + persisted conversations.

Reads catalog from `backend/data/agents_catalog.json` (regenerable via
`scripts/build_agents_catalog.py`). Persists user ↔ agent conversations
in MongoDB so they survive reloads and the user can return to any prior
thread.

Endpoints (all auth-required, scoped to the authed user):

  GET    /api/agents/catalog                       → light list
  GET    /api/agents/catalog/stats                 → counts breakdown
  GET    /api/agents/catalog/item/{id}             → full item incl. prompt

  GET    /api/agents/conversations                 → list all my threads
  GET    /api/agents/conversations/by-agent/{id}   → my threads for one agent
  POST   /api/agents/conversations                 → create a new thread
  GET    /api/agents/conversations/{cid}           → fetch thread + messages
  DELETE /api/agents/conversations/{cid}           → delete a thread
  POST   /api/agents/conversations/{cid}/invoke    → stream a reply,
                                                     persist both turns

NOTE: catalog data is static + tiny so an in-process cache is fine.
Conversations live in Mongo and are not cached — they're hot per turn.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.agents")

router = APIRouter(prefix="/api", tags=["agents-catalog"])

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "agents_catalog.json"
_CACHE: dict | None = None
_CACHE_LOCK = Lock()


def _load() -> dict:
    global _CACHE
    with _CACHE_LOCK:
        if _CACHE is not None:
            return _CACHE
        if not _CATALOG_PATH.exists():
            raise HTTPException(
                status_code=503,
                detail="Agents catalog not built. Run "
                       "`python3 scripts/build_agents_catalog.py` once.",
            )
        _CACHE = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        return _CACHE


def _light(item: dict) -> dict:
    """Strip the heavy `system_prompt` field for list views."""
    return {k: v for k, v in item.items() if k != "system_prompt"}


@router.get("/agents/catalog")
async def get_catalog(_: str = Depends(verify_token)):
    """Return the full agent + skill catalog WITHOUT system prompts —
    keeps the wire payload <200KB so it ships fast to mobile clients.
    Use `/agents/catalog/{id}` to fetch a single item with its prompt
    when the user actually wants to invoke it.
    """
    cat = _load()
    return {
        **{k: v for k, v in cat.items() if k != "items"},
        "items": [_light(i) for i in cat.get("items", [])],
    }


@router.get("/agents/catalog/stats")
async def get_stats(_: str = Depends(verify_token)):
    cat = _load()
    by_category: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for item in cat.get("items", []):
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1
        by_kind[item["kind"]]         = by_kind.get(item["kind"], 0) + 1
        by_source[item["source"]]     = by_source.get(item["source"], 0) + 1
    return {
        "agents_count": cat.get("agents_count", 0),
        "skills_count": cat.get("skills_count", 0),
        "total":        len(cat.get("items", [])),
        "by_category":  by_category,
        "by_kind":      by_kind,
        "by_source":    by_source,
    }


@router.get("/agents/catalog/item/{item_id:path}")
async def get_item(item_id: str, _: str = Depends(verify_token)):
    """Return one catalog item INCLUDING its full system_prompt body.

    `item_id` is the `id` field from the list response — e.g.
    `agent::backend-development::backend-architect` or
    `skill::github`. We accept it as a path-with-colons via
    `{item_id:path}` so the FE doesn't have to URL-encode the
    double-colon.
    """
    cat = _load()
    for it in cat.get("items", []):
        if it.get("id") == item_id:
            return it
    raise HTTPException(status_code=404, detail=f"Unknown agent id: {item_id}")


# ---------------------------------------------------------------------------
# Persisted conversations
# ---------------------------------------------------------------------------
COLLECTION = "agent_conversations"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public(conv: dict) -> dict:
    """Strip Mongo `_id` from a conversation doc."""
    return {k: v for k, v in conv.items() if k != "_id"}


class NewConversationBody(BaseModel):
    item_id: str = Field(..., description="Agent or skill id from the catalog")
    title:   Optional[str] = Field(None, max_length=140)


@router.get("/agents/conversations/active")
async def list_active_conversations(user: str = Depends(verify_token)):
    """Conversations that have an in-flight invocation right now (the
    agent is generating a reply). The UI polls this to show a "Running"
    badge + toast a notification when a previously-running one finishes."""
    cur = (
        db[COLLECTION]
        .find({"user": user, "running": True}, {"_id": 0, "messages": 0})
        .sort("updated_at", -1)
        .limit(50)
    )
    return await cur.to_list(length=50)


@router.get("/agents/conversations")
async def list_conversations(user: str = Depends(verify_token)):
    """Return ALL conversations for the authenticated user, newest first.

    Each entry is a light summary (id, item_id, item_name, title,
    message_count, created_at, updated_at). No message bodies — fetch
    `/conversations/{cid}` when you actually need them.
    """
    cur = (
        db[COLLECTION]
        .find({"user": user}, {"_id": 0, "messages": 0})
        .sort("updated_at", -1)
        .limit(200)
    )
    return await cur.to_list(length=200)


@router.get("/agents/conversations/by-agent/{item_id:path}")
async def list_conversations_by_agent(item_id: str, user: str = Depends(verify_token)):
    """All conversations the user has had with one specific agent."""
    cur = (
        db[COLLECTION]
        .find({"user": user, "item_id": item_id}, {"_id": 0, "messages": 0})
        .sort("updated_at", -1)
        .limit(50)
    )
    return await cur.to_list(length=50)


@router.post("/agents/conversations")
async def create_conversation(body: NewConversationBody, user: str = Depends(verify_token)):
    cat = _load()
    item = next((i for i in cat.get("items", []) if i.get("id") == body.item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {body.item_id}")
    cid = str(uuid.uuid4())
    now = _now_iso()
    doc = {
        "id":          cid,
        "user":        user,
        "item_id":     item["id"],
        "item_name":   item["name"],
        "item_kind":   item["kind"],
        "title":       (body.title or f"Chat with {item['name']}")[:140],
        "messages":    [],
        "created_at":  now,
        "updated_at":  now,
    }
    await db[COLLECTION].insert_one(doc)
    # insert_one mutates the input dict and adds _id; strip before returning.
    return _public(doc)


@router.get("/agents/conversations/{cid}")
async def get_conversation(cid: str, user: str = Depends(verify_token)):
    doc = await db[COLLECTION].find_one({"id": cid, "user": user}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return doc


@router.delete("/agents/conversations/{cid}")
async def delete_conversation(cid: str, user: str = Depends(verify_token)):
    r = await db[COLLECTION].delete_one({"id": cid, "user": user})
    if not r.deleted_count:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Invocation (now persists into a conversation)
# ---------------------------------------------------------------------------
class InvokeBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000,
                          description="The user's task / question")


@router.post("/agents/conversations/{cid}/invoke")
async def invoke_in_conversation(
    cid: str,
    body: InvokeBody,
    user: str = Depends(verify_token),
):
    """Stream a reply for a specific conversation. Persists BOTH the
    user message (immediately) and the assistant reply (on close,
    even partial — so a cancelled stream still saves what was emitted)."""
    conv = await db[COLLECTION].find_one({"id": cid, "user": user}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    cat = _load()
    item = next((i for i in cat.get("items", []) if i.get("id") == conv["item_id"]), None)
    if not item:
        raise HTTPException(status_code=404, detail="Underlying agent missing from catalog")

    system_prompt = item.get("system_prompt") or ""
    if not system_prompt.strip():
        raise HTTPException(status_code=400, detail=f"Agent {item['name']} has no system prompt")

    # 1) Persist the user message immediately so it survives a refresh
    #    even before the reply finishes. Mark the conversation as
    #    `running` so the UI can show a "Working…" badge and toast a
    #    notification once it completes.
    user_msg = {
        "id":         str(uuid.uuid4()),
        "role":       "user",
        "content":    body.message.strip(),
        "created_at": _now_iso(),
    }
    await db[COLLECTION].update_one(
        {"id": cid, "user": user},
        {"$push": {"messages": user_msg},
         "$set":  {"updated_at": user_msg["created_at"],
                   "running":     True,
                   "started_at":  user_msg["created_at"]}},
    )

    # Build the history we'll send to the provider — recent 12 turns.
    history = (conv.get("messages") or []) + [user_msg]
    history = history[-12:]

    from services.ai_service import generate_text_stream  # local import

    asst_id = str(uuid.uuid4())
    buf: list[str] = []
    asst_started_at = _now_iso()

    async def persist_assistant_partial():
        """Save whatever the assistant has emitted so far (called on
        stream close even when cancelled — guarantees no message is
        lost mid-stream)."""
        text = "".join(buf).strip()
        if text:
            asst_msg = {
                "id":         asst_id,
                "role":       "assistant",
                "content":    text,
                "created_at": asst_started_at,
            }
            await db[COLLECTION].update_one(
                {"id": cid, "user": user},
                {"$push": {"messages": asst_msg},
                 "$set":  {"updated_at":  _now_iso(),
                           "running":     False,
                           "finished_at": _now_iso()}},
            )
        else:
            # Even with no content, clear the running flag so the UI
            # doesn't show a stuck spinner forever.
            await db[COLLECTION].update_one(
                {"id": cid, "user": user},
                {"$set": {"running": False, "finished_at": _now_iso()}},
            )

    async def streamer():
        try:
            async for chunk in generate_text_stream(
                system_prompt=system_prompt,
                messages=[{"role": m["role"], "content": m["content"]} for m in history],
                max_tokens=2400,
            ):
                if not chunk:
                    continue
                buf.append(chunk)
                yield chunk
        except asyncio.CancelledError:
            # Client disconnected / stop button. Persist what we have.
            await persist_assistant_partial()
            raise
        except Exception as e:
            logger.exception("agent invoke failed")
            buf.append(f"\n\n[Error: {e}]")
            yield f"\n\n[Error: {e}]"
        finally:
            await persist_assistant_partial()

    return StreamingResponse(streamer(), media_type="text/plain")


# ---------------------------------------------------------------------------
# Legacy stateless invoke — kept for back-compat with the old FE shape.
# New code should use `/conversations/{cid}/invoke`.
# ---------------------------------------------------------------------------
class LegacyInvokeBody(BaseModel):
    item_id: str
    message: str = Field(..., min_length=1, max_length=8000)
    history: Optional[list[dict]] = None


@router.post("/agents/invoke")
async def legacy_invoke(body: LegacyInvokeBody, _: str = Depends(verify_token)):
    cat = _load()
    item = next((i for i in cat.get("items", []) if i.get("id") == body.item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Unknown agent id: {body.item_id}")
    system_prompt = item.get("system_prompt") or ""
    if not system_prompt.strip():
        raise HTTPException(status_code=400, detail="No system prompt")

    from services.ai_service import generate_text_stream

    messages: list[dict] = []
    if body.history:
        for turn in body.history[-12:]:
            r = turn.get("role")
            c = (turn.get("content") or "").strip()
            if r in {"user", "assistant"} and c:
                messages.append({"role": r, "content": c[:8000]})
    messages.append({"role": "user", "content": body.message.strip()})

    async def streamer():
        try:
            async for chunk in generate_text_stream(
                system_prompt=system_prompt, messages=messages, max_tokens=2400,
            ):
                if chunk:
                    yield chunk
        except Exception as e:
            logger.exception("legacy agent invoke failed")
            yield f"\n\n[Error: {e}]"

    return StreamingResponse(streamer(), media_type="text/plain")
