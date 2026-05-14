"""Migration assistant routes.

GET /api/projects/{id}/migration-plan — analyse an imported project, return a
structured reconnect plan with detected integrations + missing env vars + steps.
"""
from fastapi import APIRouter, Depends, HTTPException

from services import migration_service, provisioning_service

from ._deps import db, verify_token

router = APIRouter(prefix="/api", tags=["migration"])


@router.get("/projects/{project_id}/migration-plan")
async def get_migration_plan(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one(
        {"id": project_id},
        {"_id": 0},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    files = doc.get("files") or []
    if not files:
        # Don't 400 — empty plan is fine for fresh projects.
        return {
            "detected": [], "missing_env": [], "provided_env": [],
            "env_refs": [], "steps": [],
            "note": "No files yet — import a repo or build to populate the plan.",
        }
    providers = provisioning_service.providers_status()
    plan = migration_service.build_plan(files, doc, providers_status=providers)
    return plan
