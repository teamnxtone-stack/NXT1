"""Versions / commits (history) routes (Phase 8 modular refactor)."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ._deps import db, verify_token

router = APIRouter(prefix="/api", tags=["versions"])


class VersionMeta(BaseModel):
    id: str
    label: str
    created_at: str


class CommitLabel(BaseModel):
    label: str
    message: Optional[str] = ""


@router.get("/projects/{project_id}/versions", response_model=List[VersionMeta])
async def list_versions(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "versions": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    versions = doc.get("versions", [])
    return [
        VersionMeta(id=v["id"], label=v["label"], created_at=v["created_at"])
        for v in reversed(versions)
    ]


@router.post("/projects/{project_id}/versions/{version_id}/restore")
async def restore_version(project_id: str, version_id: str,
                          _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    versions = doc.get("versions", [])
    target = next((v for v in versions if v["id"] == version_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Version not found")
    now = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "id": str(uuid.uuid4()),
        "label": f"Before restore at {now[:19]}",
        "created_at": now,
        "files": doc.get("files", []),
    }
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"files": target["files"], "updated_at": now},
         "$push": {"versions": {"$each": [snapshot], "$slice": -50}}},
    )
    return {"ok": True}


@router.get("/projects/{project_id}/versions/{version_id}")
async def get_version(project_id: str, version_id: str,
                      _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "versions": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    target = next((v for v in doc.get("versions", []) if v["id"] == version_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Version not found")
    return target


@router.post("/projects/{project_id}/versions/{version_id}/label")
async def label_version(project_id: str, version_id: str, body: CommitLabel,
                        _: str = Depends(verify_token)):
    res = await db.projects.update_one(
        {"id": project_id, "versions.id": version_id},
        {"$set": {
            "versions.$.label": body.label[:120],
            "versions.$.commit_message": (body.message or "")[:600],
            "versions.$.edited_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"ok": True}


@router.get("/projects/{project_id}/commits")
async def list_commits(project_id: str, q: Optional[str] = None,
                       _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "versions": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    versions = doc.get("versions", []) or []
    qq = (q or "").lower().strip()
    out = []
    for v in reversed(versions):
        if qq and qq not in (v.get("label", "") + " " + v.get("commit_message", "")).lower():
            continue
        out.append({
            "id": v["id"],
            "label": v.get("label", ""),
            "commit_message": v.get("commit_message", ""),
            "type": v.get("type", "ai"),
            "created_at": v["created_at"],
            "deploy_id": v.get("deploy_id"),
        })
    return out
