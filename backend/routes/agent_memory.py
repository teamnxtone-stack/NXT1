"""Agent Memory routes — per-user persistent context shared across all agents.

  GET    /api/memory                 → list user memories (filter by scope/kind)
  POST   /api/memory                 → add (summary, payload, pinned, scope, kind)
  PATCH  /api/memory/{id}            → update summary or pin
  DELETE /api/memory/{id}            → forget
  GET    /api/memory/context         → composed prompt block (auto-built)
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import agent_memory as mem
from ._deps import db, verify_token

router = APIRouter(prefix="/api/memory", tags=["agent-memory"])


class MemoryIn(BaseModel):
    scope: str = "global"     # global | social | studio | agents
    kind: str = "fact"        # fact | preference | example | feedback | image | system
    summary: str = Field(..., max_length=300)
    payload: Optional[dict] = None
    pinned: bool = False


class MemoryPatch(BaseModel):
    summary: Optional[str] = None
    pinned: Optional[bool] = None


@router.get("")
async def list_memory(
    scope: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 50,
    user_id: str = Depends(verify_token),
):
    items = await mem.recall(db, user_id=user_id, scope=scope, kind=kind, limit=limit)
    return {"items": items}


@router.post("")
async def create_memory(body: MemoryIn, user_id: str = Depends(verify_token)):
    try:
        doc = await mem.remember(
            db, user_id=user_id, scope=body.scope, kind=body.kind,
            summary=body.summary, payload=body.payload, pinned=body.pinned,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return doc


@router.patch("/{memory_id}")
async def patch_memory(memory_id: str, body: MemoryPatch,
                       user_id: str = Depends(verify_token)):
    n = 0
    if body.summary is not None:
        n += await mem.update_summary(db, user_id=user_id, memory_id=memory_id,
                                      summary=body.summary)
    if body.pinned is not None:
        n += await mem.pin(db, user_id=user_id, memory_id=memory_id,
                           pinned=body.pinned)
    if n == 0:
        raise HTTPException(404, "Memory not found")
    return {"ok": True}


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, user_id: str = Depends(verify_token)):
    n = await mem.forget(db, user_id=user_id, memory_id=memory_id)
    if not n:
        raise HTTPException(404, "Memory not found")
    return {"ok": True}


@router.get("/context")
async def get_context(scope: str = "global", user_id: str = Depends(verify_token)):
    block = await mem.build_context_block(db, user_id=user_id, scope=scope)
    return {"context": block, "scope": scope}
