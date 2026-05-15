"""Per-project chat history for the headless bolt.diy builder.

The integrated builder (`/builder/{projectId}`) renders NXT1's own chat panel
on the left and an invisible bolt.diy iframe on the right. Bolt streams
assistant tokens back into the NXT1 chat through `window.__nxt1BoltBridge`,
and the NXT1 panel mirrors every user + assistant message into Mongo so the
conversation survives reloads.

Mongo collection: `builder_chats`
  { project_id: str, messages: [{id, role, content, ts}], updated_at }
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient

router = APIRouter(prefix="/api/v1/builder", tags=["builder-chat"])

_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
_db = _client[os.environ["DB_NAME"]]
_coll = _db["builder_chats"]


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: f"m_{uuid.uuid4().hex[:12]}")
    role: str  # "user" | "assistant"
    content: str
    ts: float = Field(default_factory=lambda: time.time())


class ChatHistoryOut(BaseModel):
    project_id: str
    messages: List[ChatMessage]


class AppendMessageIn(BaseModel):
    role: str
    content: str
    id: Optional[str] = None


@router.get("/chat/{project_id}", response_model=ChatHistoryOut)
async def get_chat(project_id: str):
    doc = await _coll.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        return ChatHistoryOut(project_id=project_id, messages=[])
    return ChatHistoryOut(
        project_id=project_id,
        messages=[ChatMessage(**m) for m in doc.get("messages", [])],
    )


@router.post("/chat/{project_id}", response_model=ChatMessage)
async def append_message(project_id: str, body: AppendMessageIn):
    if body.role not in ("user", "assistant"):
        raise HTTPException(status_code=400, detail="role must be 'user' or 'assistant'")
    msg = ChatMessage(
        id=body.id or f"m_{uuid.uuid4().hex[:12]}",
        role=body.role,
        content=body.content,
    )
    await _coll.update_one(
        {"project_id": project_id},
        {
            "$push": {"messages": msg.model_dump()},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
            "$setOnInsert": {"project_id": project_id},
        },
        upsert=True,
    )
    return msg


class ReplaceHistoryIn(BaseModel):
    messages: List[ChatMessage]


@router.put("/chat/{project_id}", response_model=ChatHistoryOut)
async def replace_history(project_id: str, body: ReplaceHistoryIn):
    """Full replace — used after the bolt bridge finishes streaming so the
    final canonical message (with any tool-calls / file edits inlined) lands
    in Mongo. The client batches updates so we don't write on every chunk."""
    await _coll.update_one(
        {"project_id": project_id},
        {
            "$set": {
                "project_id": project_id,
                "messages": [m.model_dump() for m in body.messages],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return ChatHistoryOut(project_id=project_id, messages=body.messages)


@router.delete("/chat/{project_id}")
async def clear_chat(project_id: str):
    await _coll.delete_one({"project_id": project_id})
    return {"ok": True}
