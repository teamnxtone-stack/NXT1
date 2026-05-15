"""Asset upload + project ZIP download (Phase 8 modular refactor)."""
import io
import logging
import re
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse

from services.storage_service import get_object, put_object

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.assets")

router = APIRouter(prefix="/api", tags=["assets"])

APP_NAME = "nxt1"


@router.post("/projects/{project_id}/upload")
async def upload_asset(project_id: str, file: UploadFile = File(...),
                       _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "id": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    ext = (file.filename or "bin").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_",
                       (file.filename or "asset").rsplit(".", 1)[0])[:40] or "asset"
    storage_path = f"{APP_NAME}/projects/{project_id}/{uuid.uuid4().hex[:12]}-{safe_name}.{ext}"
    data = await file.read()
    # 64MB ceiling — covers short videos + most PDFs/docs.
    if len(data) > 64 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 64MB)")
    result = put_object(storage_path, data, file.content_type or "application/octet-stream")
    # Discriminate the asset so the chat pipeline can reason about it.
    ct = (file.content_type or "").lower()
    if ct.startswith("image/"):
        kind = "image"
    elif ct.startswith("video/"):
        kind = "video"
    elif ct.startswith("audio/"):
        kind = "audio"
    elif "pdf" in ct or ext == "pdf":
        kind = "pdf"
    elif ext in {"doc", "docx", "rtf", "odt", "txt", "md"}:
        kind = "document"
    elif ext in {"csv", "xls", "xlsx", "tsv", "json"}:
        kind = "data"
    elif ext in {"zip", "tar", "gz"}:
        kind = "archive"
    else:
        kind = "file"
    asset_record = {
        "id": str(uuid.uuid4()),
        "filename": f"{safe_name}.{ext}",
        "storage_path": result["path"],
        "content_type": file.content_type or "application/octet-stream",
        "kind": kind,
        "size": result.get("size", len(data)),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.projects.update_one(
        {"id": project_id},
        {"$push": {"assets": asset_record},
         "$set": {"updated_at": asset_record["created_at"]}},
    )
    return asset_record


@router.get("/projects/{project_id}/assets")
async def list_assets(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "assets": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return doc.get("assets", [])


@router.delete("/projects/{project_id}/assets/{asset_id}")
async def delete_asset(project_id: str, asset_id: str,
                       _: str = Depends(verify_token)):
    res = await db.projects.update_one(
        {"id": project_id}, {"$pull": {"assets": {"id": asset_id}}},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"ok": True}


@router.get("/projects/{project_id}/assets/{filename}")
async def get_asset(project_id: str, filename: str,
                    auth: Optional[str] = Query(None),
                    authorization: Optional[str] = Header(None)):
    token_str = authorization or (f"Bearer {auth}" if auth else None)
    verify_token(token_str)
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "assets": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    asset = next((a for a in doc.get("assets", []) if a["filename"] == filename), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    data, ct = get_object(asset["storage_path"])
    return Response(content=data, media_type=asset.get("content_type", ct))


@router.get("/projects/{project_id}/download")
async def download_project(project_id: str,
                           auth: Optional[str] = Query(None),
                           authorization: Optional[str] = Header(None)):
    token_str = authorization or (f"Bearer {auth}" if auth else None)
    verify_token(token_str)
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in doc.get("files", []):
            z.writestr(f["path"], f["content"])
        for a in doc.get("assets", []):
            try:
                data, _ct = get_object(a["storage_path"])
                z.writestr(f"assets/{a['filename']}", data)
            except Exception as e:
                logger.warning(f"asset zip skip: {e}")
    buf.seek(0)
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", doc.get("name", "project"))[:40] or "project"
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe}.zip"'},
    )
