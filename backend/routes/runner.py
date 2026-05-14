"""Sandboxed runner + self-healing routes (Track D)."""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services import runner_service as rs

from ._deps import db, verify_token

router = APIRouter(prefix="/api/runner", tags=["runner"])


class QuickBuildIn(BaseModel):
    pass


@router.post("/projects/{project_id}/quick-build")
async def quick_build(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "files": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    return await rs.quick_build(project_id, doc.get("files") or [])


class HealIn(BaseModel):
    max_attempts: Optional[int] = None


@router.post("/projects/{project_id}/self-heal")
async def self_heal(project_id: str, body: Optional[HealIn] = None,
                    _: str = Depends(verify_token)):
    """SSE stream of the bounded self-healing build loop."""
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "files": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    files = doc.get("files") or []
    max_attempts = (body.max_attempts if body and body.max_attempts else
                    rs.MAX_ATTEMPTS_DEFAULT)
    max_attempts = max(1, min(int(max_attempts), 5))

    async def event_stream():
        try:
            async for event in rs.self_heal_loop(project_id, files,
                                                  max_attempts=max_attempts):
                yield f"data: {json.dumps(event)}\n\n"
                # tiny breathing gap so the UI sees the staggered events
                await asyncio.sleep(0.05)
            yield "data: {\"phase\": \"loop.end\", \"agent\": \"devops\", \"status\": \"done\"}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'phase':'loop.error','message':str(e)[:300]})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/config")
async def runner_config(_: str = Depends(verify_token)):
    return {
        "runner_root": rs.RUNNER_ROOT,
        "max_attempts_default": rs.MAX_ATTEMPTS_DEFAULT,
        "mode": "subprocess",
        "docker_available": False,
    }
