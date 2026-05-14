"""Durable workflow routes (Track B).

Endpoints exposing the LangGraph-backed workflow engine to the frontend.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import workflow_service as wfs

from ._deps import db, verify_token

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class StartIn(BaseModel):
    project_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1, max_length=8000)
    deploy_target: Optional[str] = "internal"


class ResumeIn(BaseModel):
    approval: Optional[bool] = True


@router.post("/start")
async def start(body: StartIn, user_id: str = Depends(verify_token)):
    proj = await db.projects.find_one({"id": body.project_id}, {"_id": 0, "id": 1})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return await wfs.start_workflow(body.project_id, body.prompt, user_id, body.deploy_target)


@router.get("/list")
async def list_all(
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="queued|running|waiting|completed|failed|cancelled"),
    limit: int = Query(50, ge=1, le=200),
    _: str = Depends(verify_token),
):
    return {"items": await wfs.list_workflows(project_id, status, limit)}


@router.get("/{workflow_id}")
async def get_one(workflow_id: str, _: str = Depends(verify_token)):
    doc = await wfs.get_workflow(workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return doc


@router.post("/{workflow_id}/resume")
async def resume(workflow_id: str, body: Optional[ResumeIn] = None,
                 _: str = Depends(verify_token)):
    approval = body.approval if body else True
    result = await wfs.resume_workflow(workflow_id, approval=approval)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "cannot resume"))
    return result


@router.post("/{workflow_id}/cancel")
async def cancel(workflow_id: str, _: str = Depends(verify_token)):
    result = await wfs.cancel_workflow(workflow_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail="Cannot cancel a finished workflow")
    return result
