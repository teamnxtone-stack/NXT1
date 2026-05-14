"""NXT1 — Project Context Memory routes (Phase 11 W2-E).

Exposes the project_memory service via /api/projects/{project_id}/context.

NOTE: This is *event-style* project memory (decisions, framework locks,
integration receipts). It is distinct from the existing
`/api/projects/{project_id}/memory` endpoint in routes/projects.py which
returns a *file-tree* summary + AI summary of the project's code. Both
together give the orchestrator structured + semantic project recall.

Guarded by the standard bearer token so only authenticated clients can
read or write project context.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import project_memory as pm
from ._deps import verify_token

router = APIRouter(prefix="/api/projects", tags=["project-context"])


class MemoryIn(BaseModel):
    kind:    str          = Field(..., description="decision | file-map | framework | integration | note")
    summary: str          = Field(..., max_length=500)
    payload: Optional[Dict] = None
    pinned:  bool         = False


class MemoryPinIn(BaseModel):
    pinned: bool = True


@router.get("/{project_id}/context")
async def list_context(project_id: str, kind: Optional[str] = None,
                        limit: int = 50, _: str = Depends(verify_token)) -> Dict[str, List[Dict]]:
    items = await pm.recall(project_id, kind=kind, limit=limit)
    return {"items": items}


@router.get("/{project_id}/context/pinned")
async def list_pinned_context(project_id: str, _: str = Depends(verify_token)) -> Dict[str, List[Dict]]:
    items = await pm.recall_pinned(project_id)
    return {"items": items}


@router.post("/{project_id}/context")
async def create_context(project_id: str, body: MemoryIn, _: str = Depends(verify_token)):
    try:
        doc = await pm.remember(project_id, kind=body.kind, summary=body.summary,
                                  payload=body.payload, pinned=body.pinned)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return doc


@router.patch("/{project_id}/context/{memory_id}/pin")
async def pin_context(project_id: str, memory_id: str, body: MemoryPinIn,
                       _: str = Depends(verify_token)):
    matched = await pm.pin(project_id, memory_id=memory_id, pinned=body.pinned)
    if not matched:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "pinned": body.pinned}


@router.delete("/{project_id}/context/{memory_id}")
async def delete_context(project_id: str, memory_id: str, _: str = Depends(verify_token)):
    deleted = await pm.forget(project_id, memory_id=memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}
