"""Public NXT Assistant — Claude-powered visitor-facing chatbot.

Lives on the marketing landing page in place of a generic contact form.
Visitors can ask anything about NXT One, request access, learn what we
build, etc. No auth required — but rate-limited per IP + per session.

Routes:
  POST /api/public/nxt-chat/message   send a message, get a streamed reply
  POST /api/public/nxt-chat/lead      capture an explicit interest lead
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import litellm
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("nxt1.public.chat")

router = APIRouter(prefix="/api/public/nxt-chat", tags=["public-chat"])


_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
_db = _client[os.environ["DB_NAME"]]

# ─── Rate limit (in-memory) ─────────────────────────────────────────────
# Per-IP: 30 messages / 10 min. Resets on process restart — that's fine
# for a marketing page chatbot.
_RATE: dict[str, list[float]] = {}
_RATE_WINDOW_SEC = 600
_RATE_MAX = 30


def _rate_ok(ip: str) -> bool:
    now = time.time()
    bucket = [t for t in _RATE.get(ip, []) if (now - t) < _RATE_WINDOW_SEC]
    if len(bucket) >= _RATE_MAX:
        _RATE[ip] = bucket
        return False
    bucket.append(now)
    _RATE[ip] = bucket
    return True


# ─── System prompt ──────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the NXT One assistant — the friendly, sharp public-facing
agent for nxtone.tech, a private AI app-building platform from Jwood Technologies.

PERSONALITY
- Confident, direct, founder-friendly. Speak like a real person, not a corporate FAQ.
- Premium tone, no emoji clutter, no exclamation point spam.
- Short paragraphs. 1–3 sentences usually beats 5.

WHAT NXT ONE IS
- A private platform that turns ideas into working software fast.
- Built for founders, makers, and operators shipping MVPs, internal tools,
  dashboards, marketing sites, and real apps.
- Tagline: Discover. Develop. Deliver.
- Access is curated — not publicly open. Visitors can ask for access; you collect
  email + a short note about what they're building.
- A product of Jwood Technologies.

WHAT NXT ONE IS NOT
- Not a generic AI chat tool. Not a credits-based SaaS. Not a "code completion"
  plugin. Don't position it that way.
- Never mention "Emergent", "emergentintegrations", or any internal platform names.
- Never say there's a free trial or pricing tiers — pricing isn't published.

WHAT YOU CAN HELP WITH
- Explain what NXT One does and who it's for
- Walk through what a typical build looks like (prompt → preview → deploy → connect domain)
- Help the visitor request access (ask for their email + one-line about what they want to build)
- Answer questions about the platform, its capabilities, the agent system, etc.
- If they ask something off-topic, redirect gracefully.

CAPTURING A LEAD
- If the user says they want access, ask for: (1) their email, (2) one line about what
  they want to build. Once you have both, confirm "Got it — I've added you to the list."
  In the same turn, include a hidden machine-readable JSON line at the very end like:
    <LEAD>{"email":"…","note":"…"}</LEAD>
  The frontend strips that out and uses it to persist the lead. Don't mention this tag
  to the user.

STYLE GUARDRAILS
- Do NOT output code, file diffs, or markdown headings.
- Do NOT promise specific features the platform doesn't have. If unsure, say so.
- Do NOT speak on behalf of Jwood Technologies on legal / financial / hiring matters.
"""


# ─── Models ─────────────────────────────────────────────────────────────
class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None


class LeadIn(BaseModel):
    email: EmailStr
    note: Optional[str] = ""
    session_id: Optional[str] = None
    source: Optional[str] = "nxt-chat"


# ─── Provider call ──────────────────────────────────────────────────────
def _claude_call_kwargs(messages: list[dict]) -> dict:
    """Wire to ANTHROPIC_API_KEY when present, else fall back to Emergent proxy."""
    anth = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if anth:
        return {
            "model": "anthropic/claude-sonnet-4-5-20250929",
            "api_key": anth,
            "messages": messages,
            "max_tokens": 800,
        }
    em = (os.environ.get("EMERGENT_LLM_KEY") or "").strip()
    if not em:
        raise RuntimeError("No Claude provider configured — set ANTHROPIC_API_KEY")
    base = (os.environ.get("INTEGRATION_PROXY_URL") or "https://integrations.emergentagent.com").rstrip("/") + "/llm"
    return {
        "model": "claude-sonnet-4-5-20250929",  # bare name for the proxy
        "api_key": em,
        "api_base": base,
        "custom_llm_provider": "openai",
        "messages": messages,
        "max_tokens": 800,
    }


# ─── History helpers ────────────────────────────────────────────────────
async def _load_history(session_id: str, limit: int = 16) -> list[dict]:
    cur = _db.public_chat_messages.find(
        {"session_id": session_id}, {"_id": 0, "role": 1, "content": 1},
    ).sort("ts", 1).limit(limit)
    return await cur.to_list(length=None)


async def _save_message(session_id: str, role: str, content: str, ip: Optional[str]) -> None:
    await _db.public_chat_messages.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "role": role,
        "content": content[:8000],
        "ip": ip,
        "ts": datetime.now(timezone.utc).isoformat(),
    })


# ─── Routes ─────────────────────────────────────────────────────────────
@router.post("/message")
async def chat_message(body: ChatIn, request: Request):
    ip = (request.client.host if request.client else "unknown")[:64]
    if not _rate_ok(ip):
        raise HTTPException(status_code=429, detail="Slow down — try again in a few minutes.")
    session_id = (body.session_id or str(uuid.uuid4()))[:64]
    history = await _load_history(session_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": body.message[:2000]})
    await _save_message(session_id, "user", body.message, ip)

    async def stream():
        # Always lead with session_id so the client can persist it for follow-ups
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
        chunks: list[str] = []
        try:
            kwargs = _claude_call_kwargs(messages)
            kwargs["stream"] = True
            try:
                response = await litellm.acompletion(**kwargs)
                async for chunk in response:
                    try:
                        delta = chunk.choices[0].delta.content or ""
                    except Exception:
                        delta = ""
                    if not delta:
                        continue
                    chunks.append(delta)
                    yield f"data: {json.dumps({'type': 'chunk', 'delta': delta})}\n\n"
                    await asyncio.sleep(0)
            except Exception:
                # Streaming failed → fall back to blocking
                kwargs.pop("stream", None)
                resp = await litellm.acompletion(**kwargs)
                full = resp["choices"][0]["message"]["content"] or ""
                chunks = [full]
                yield f"data: {json.dumps({'type': 'chunk', 'delta': full})}\n\n"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"public nxt-chat failed: {e}")
            chunks = ["I'm having trouble responding right now. Try again in a moment, or email hello@nxtone.tech."]
            yield f"data: {json.dumps({'type': 'chunk', 'delta': chunks[0]})}\n\n"

        full = "".join(chunks).strip()
        await _save_message(session_id, "assistant", full, ip)
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no",
    })


@router.post("/lead")
async def chat_lead(body: LeadIn, request: Request):
    ip = (request.client.host if request.client else "unknown")[:64]
    if not _rate_ok(ip):
        raise HTTPException(status_code=429, detail="Slow down — try again in a few minutes.")
    doc = {
        "id": str(uuid.uuid4()),
        "email": str(body.email).lower(),
        "note": (body.note or "")[:1000],
        "session_id": body.session_id,
        "source": body.source or "nxt-chat",
        "ip": ip,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await _db.public_chat_leads.insert_one(dict(doc))
    except Exception as e:
        logger.warning(f"lead save failed: {e}")
    doc.pop("_id", None)
    return {"ok": True, "id": doc["id"]}
