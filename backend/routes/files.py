"""File operations: create/update, delete, rename (Phase 8 modular refactor)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ._deps import db, verify_token

router = APIRouter(prefix="/api", tags=["files"])


class FilePatch(BaseModel):
    content: str


class FileRename(BaseModel):
    new_path: str


@router.put("/projects/{project_id}/files/{path:path}")
async def upsert_file(project_id: str, path: str, body: FilePatch,
                      _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "files": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    files = doc.get("files", [])
    found = False
    for f in files:
        if f["path"] == path:
            f["content"] = body.content
            found = True
            break
    if not found:
        files.append({"path": path, "content": body.content})
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"files": files, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "path": path}


@router.delete("/projects/{project_id}/files/{path:path}")
async def delete_file(project_id: str, path: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "files": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    files = [f for f in doc.get("files", []) if f["path"] != path]
    if len(files) == len(doc.get("files", [])):
        raise HTTPException(status_code=404, detail="File not found")
    if not any(f["path"].lower() == "index.html" for f in files):
        raise HTTPException(status_code=400, detail="Cannot delete index.html (entry file)")
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"files": files, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}


@router.post("/projects/{project_id}/files/{path:path}/rename")
async def rename_file(project_id: str, path: str, body: FileRename,
                      _: str = Depends(verify_token)):
    if not body.new_path or body.new_path.strip().startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid new_path")
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "files": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    files = doc.get("files", [])
    src = next((f for f in files if f["path"] == path), None)
    if not src:
        raise HTTPException(status_code=404, detail="File not found")
    if path.lower() == "index.html":
        raise HTTPException(status_code=400, detail="Cannot rename index.html (entry file)")
    if any(f["path"] == body.new_path for f in files):
        raise HTTPException(status_code=409, detail="A file with that path already exists")
    new_files = [
        {**f, "path": body.new_path} if f["path"] == path else f
        for f in files
    ]
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"files": new_files, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "from": path, "to": body.new_path}
