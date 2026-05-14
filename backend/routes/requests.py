"""Saved-request collection (Postman-lite) endpoints — Phase 8 refactor."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ._deps import db, verify_token

router = APIRouter(prefix="/api", tags=["requests"])


class SavedRequestIn(BaseModel):
    name: str
    method: str
    path: str
    body: Optional[dict] = None
    headers: Optional[Dict[str, str]] = None
    description: Optional[str] = ""


@router.get("/projects/{project_id}/requests")
async def list_saved_requests(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one(
        {"id": project_id}, {"_id": 0, "id": 1, "saved_requests": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return doc.get("saved_requests") or []


@router.post("/projects/{project_id}/requests")
async def save_request(project_id: str, body: SavedRequestIn,
                       _: str = Depends(verify_token)):
    rec = {
        "id": uuid.uuid4().hex[:12],
        "name": body.name.strip()[:80] or "untitled",
        "method": body.method.upper(),
        "path": body.path,
        "body": body.body,
        "headers": body.headers or {},
        "description": (body.description or "")[:240],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.projects.update_one(
        {"id": project_id},
        {"$push": {"saved_requests": rec},
         "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    return rec


@router.delete("/projects/{project_id}/requests/{req_id}")
async def delete_saved_request(project_id: str, req_id: str,
                               _: str = Depends(verify_token)):
    res = await db.projects.update_one(
        {"id": project_id},
        {"$pull": {"saved_requests": {"id": req_id}}},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"ok": True}
