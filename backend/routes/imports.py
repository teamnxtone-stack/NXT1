"""Project import (ZIP / GitHub) + cached analysis (Phase 8 modular refactor)."""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from services import import_service

from ._deps import db, verify_token

router = APIRouter(prefix="/api", tags=["imports"])


class GitImportIn(BaseModel):
    repo_url: str
    branch: Optional[str] = None
    project_name: Optional[str] = ""


def _make_imported_project_doc(name: str, files: list, analysis: dict) -> dict:
    from services import preview_service as _ps
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "name": name[:120] or "Imported Project",
        "description": f"Imported · {analysis.get('summary', '')}",
        "files": files,
        "assets": [],
        "messages": [],
        # Auto-create preview slug so imported projects are previewable right
        # away (falls back to live URL when the project isn't iframe-able).
        "preview": _ps.make_initial(name or "imported"),
        "versions": [{
            "id": str(uuid.uuid4()),
            "label": "Initial import",
            "commit_message": analysis.get("summary", "Imported project"),
            "type": "import",
            "files": files,
            "created_at": now,
        }],
        "deployments": [],
        "domains": [],
        "env_vars": [
            {"key": k, "value": "", "scope": "runtime", "updated_at": now}
            for k in (analysis.get("env_keys") or [])[:20]
        ],
        "databases": [],
        "saved_requests": [],
        "deployed": False,
        "deploy_slug": None,
        "publish_on_save": False,
        "analysis": analysis,
        "created_at": now,
        "updated_at": now,
    }


@router.post("/projects/import/zip")
async def import_zip(file: UploadFile = File(...),
                     project_name: Optional[str] = Query(None),
                     _: str = Depends(verify_token)):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip archive")
    raw = await file.read()
    try:
        files = import_service.extract_zip_to_files(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read zip: {e}")
    if not files:
        raise HTTPException(status_code=400,
                            detail="No importable text/code files found in zip")
    analysis = import_service.analyse(files)
    name = (project_name or os.path.splitext(file.filename)[0]).strip()[:120]
    doc = _make_imported_project_doc(name, files, analysis)
    await db.projects.insert_one(dict(doc))
    return {"id": doc["id"], "name": doc["name"],
            "files_count": len(files), "analysis": analysis}


@router.post("/projects/import/github")
async def import_github(body: GitImportIn, _: str = Depends(verify_token)):
    try:
        files = import_service.clone_github_repo(body.repo_url, body.branch)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {e}")
    if not files:
        raise HTTPException(status_code=400, detail="No importable files found in repo")
    analysis = import_service.analyse(files)
    name = (
        body.project_name.strip() if body.project_name
        else body.repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    )
    doc = _make_imported_project_doc(name, files, analysis)
    # Remember the source repo so Save-to-GitHub can push back to the same place.
    parsed = _parse_github_url(body.repo_url)
    if parsed:
        doc["github"] = {
            "source_repo_url": body.repo_url,
            "source_owner": parsed[0],
            "source_name": parsed[1],
            "branch": body.branch or "main",
            "imported_at": datetime.now(timezone.utc).isoformat(),
        }
    await db.projects.insert_one(dict(doc))
    return {"id": doc["id"], "name": doc["name"],
            "files_count": len(files), "analysis": analysis,
            "github": doc.get("github")}


def _parse_github_url(url: str):
    """Return (owner, name) from a GitHub URL or None."""
    import re as _re
    m = _re.match(r"^(?:https?://)?github\.com/([^/]+)/([^/.]+)(?:\.git)?/?$", (url or "").strip())
    if not m:
        return None
    return m.group(1), m.group(2)


@router.get("/projects/{project_id}/analysis")
async def get_analysis(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one(
        {"id": project_id}, {"_id": 0, "id": 1, "analysis": 1, "files": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    cached = doc.get("analysis")
    if cached:
        return cached
    a = import_service.analyse(doc.get("files", []))
    await db.projects.update_one({"id": project_id}, {"$set": {"analysis": a}})
    return a


@router.post("/projects/{project_id}/analysis/refresh")
async def refresh_analysis(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one(
        {"id": project_id}, {"_id": 0, "id": 1, "files": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    a = import_service.analyse(doc.get("files", []))
    await db.projects.update_one({"id": project_id}, {"$set": {"analysis": a}})
    return a
