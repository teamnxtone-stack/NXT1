"""Deployments routes (Phase 8 modular refactor).

Exposes a `_do_deploy` helper used by chat (auto-publish-on-save) and by the
deploy auto-fix workflow (routes/autofix.py). Everything else is a thin CRUD
layer on top of `services.deployment_service`.

For external providers (Vercel, Cloudflare Pages) the actual deploy + polling
is moved to a background task so the HTTP request returns within milliseconds
and the frontend's deployment polling (every ~4s) drives the UI status updates.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from services.deployment_service import (
    get_provider as get_deploy_provider,
    new_deployment_record,
)

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.deployments")

router = APIRouter(prefix="/api", tags=["deployments"])


# ---------- Phase 10C: hosting catalogue endpoint ----------
# Surfaces the rich UX catalogue (label/blurb/capabilities/missing_env)
# merged with the runtime configured-state from deployment_service.
@router.get("/deploy/providers")
async def deploy_providers():
    """Hosting providers catalogue — used by the workspace hosting picker.

    Returns each provider with:
      - id, label, blurb, env_vars, missing_env, capabilities, tier, docs_url
      - configured: bool   (runtime — has all required env vars)

    Placeholder-safe: returns the full catalogue even when providers are
    not configured so the UI can render a "Connect" affordance.
    """
    from services.hosting import list_hosting_targets
    return {"providers": list_hosting_targets()}



# Providers that may take >30s to finish — run in background.
_ASYNC_PROVIDERS = {"vercel", "cloudflare-pages", "cloudflare-workers"}


class DeployIn(BaseModel):
    provider: Optional[str] = "internal"


async def _run_provider_and_persist(project_id: str, deployment: dict):
    """Background task: run the provider's deploy() and persist the final state."""
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        return
    provider = get_deploy_provider(deployment["provider"])
    try:
        await provider.deploy(doc, deployment)
    except Exception as e:
        logger.exception("background deploy failed")
        deployment["status"] = "failed"
        deployment["error"] = str(e)[:300]
        deployment["completed_at"] = datetime.now(timezone.utc).isoformat()

    update_set = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if deployment["status"] == "deployed" and deployment["provider"] == "internal":
        update_set["deployed"] = True
        update_set["deploy_slug"] = deployment["slug"]
        update_set["last_deployed_at"] = deployment["completed_at"]
    await db.projects.update_one(
        {"id": project_id, "deployments.id": deployment["id"]},
        {"$set": {**update_set, "deployments.$": deployment}},
    )


async def _do_deploy(project_id: str, provider_name: str = "internal") -> dict:
    """Internal helper: create + run a deployment, persist record & status.

    For internal provider — runs synchronously (fast). For external providers
    that may take minutes (Vercel, CF Pages) — schedules a background task and
    returns the building record immediately so the HTTP request doesn't time
    out. Frontend polls /deployments every ~4s to see status transitions.
    """
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    deployment = new_deployment_record(doc, doc.get("files", []), provider=provider_name)
    deployment["status"] = "building"
    deployment["logs"] = [{
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": "info",
        "msg": "› queued ✓ → starting build…",
    }]
    await db.projects.update_one(
        {"id": project_id},
        {"$push": {"deployments": {"$each": [deployment], "$slice": -30}}},
    )

    if provider_name in _ASYNC_PROVIDERS:
        # Fire-and-forget background task; the frontend will poll for status.
        asyncio.create_task(_run_provider_and_persist(project_id, deployment))
        return deployment

    # Synchronous path (internal + stubs)
    provider = get_deploy_provider(deployment["provider"])
    try:
        await provider.deploy(doc, deployment)
    except Exception as e:
        logger.exception("deploy provider error")
        deployment["status"] = "failed"
        deployment["error"] = str(e)
        deployment["completed_at"] = datetime.now(timezone.utc).isoformat()

    update_set = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if deployment["status"] == "deployed" and deployment["provider"] == "internal":
        update_set["deployed"] = True
        update_set["deploy_slug"] = deployment["slug"]
        update_set["last_deployed_at"] = deployment["completed_at"]
    await db.projects.update_one(
        {"id": project_id, "deployments.id": deployment["id"]},
        {"$set": {**update_set, "deployments.$": deployment}},
    )
    try:
        from services import audit_service
        await audit_service.record(
            db, tool="deploy", action=deployment["provider"],
            target=deployment.get("public_url") or deployment.get("slug") or "",
            project_id=project_id,
            status=deployment["status"],
            after={"id": deployment["id"], "url": deployment.get("public_url")},
        )
    except Exception:
        pass
    return deployment


@router.post("/projects/{project_id}/deployments")
async def create_deployment(project_id: str,
                            body: Optional[DeployIn] = Body(None),
                            _: str = Depends(verify_token)):
    provider_name = "internal"
    if body is not None and isinstance(body, DeployIn) and body.provider:
        provider_name = body.provider
    return await _do_deploy(project_id, provider_name)


@router.get("/projects/{project_id}/deployments")
async def list_deployments(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "deployments": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    deps = doc.get("deployments", [])
    out = []
    for d in reversed(deps):
        out.append({k: v for k, v in d.items() if k != "files"})
    return out


@router.get("/projects/{project_id}/deployments/{dep_id}")
async def get_deployment(project_id: str, dep_id: str,
                         _: str = Depends(verify_token)):
    doc = await db.projects.find_one(
        {"id": project_id, "deployments.id": dep_id},
        {"_id": 0, "deployments": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    target = next((d for d in doc.get("deployments", []) if d["id"] == dep_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return target


@router.post("/projects/{project_id}/deployments/{dep_id}/cancel")
async def cancel_deployment(project_id: str, dep_id: str,
                            _: str = Depends(verify_token)):
    res = await db.projects.update_one(
        {"id": project_id, "deployments.id": dep_id,
         "deployments.status": {"$in": ["pending", "building"]}},
        {"$set": {
            "deployments.$.status": "cancelled",
            "deployments.$.completed_at": datetime.now(timezone.utc).isoformat(),
        }, "$push": {"deployments.$.logs": {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": "warn",
            "msg": "✗ cancelled by user",
        }}},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=400,
                            detail="Deployment cannot be cancelled (already completed)")
    return {"ok": True}


# Backward-compat: legacy quick deploy endpoint
@router.post("/projects/{project_id}/deploy")
async def deploy_project(project_id: str, _: str = Depends(verify_token)):
    return await _do_deploy(project_id, "internal")
