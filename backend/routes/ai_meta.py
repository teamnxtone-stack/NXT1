"""AI introspection endpoints — lets the UI query provider specs, availability,
and recommended defaults without owning that knowledge in the frontend.

All endpoints are public-safe in the sense that they expose only declarative
metadata, never API keys. The configured/available flags are computed from
environment variables but no secret material is returned.
"""
from fastapi import APIRouter, Depends

from services.ai_service import list_provider_specs, provider_health
from services.inference_service import infer_project_kind
from services.providers.catalog import merge_into_spec, list_provider_variants
from services.providers.task_routing import (
    suggest_for_task,
    available_for_task,
    task_routing_table,
)
from pydantic import BaseModel

from ._deps import verify_token

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/providers")
async def ai_providers(_: str = Depends(verify_token)):
    """Return full provider catalog + availability + rich model variants
    for the UI model picker.
    """
    specs = [merge_into_spec(s) for s in list_provider_specs()]
    return {
        "providers": specs,
        "health": provider_health(),
    }


@router.get("/models")
async def ai_models(_: str = Depends(verify_token)):
    """Flattened model catalogue grouped by provider — drives the new
    ModelVariantPicker in the workspace. Includes tier / badge / context /
    note metadata per model. Authoritative source: services.providers.catalog.
    """
    out = []
    for spec in list_provider_specs():
        pid = spec.get("id")
        variants = list_provider_variants(pid)
        if not variants:
            continue
        out.append({
            "provider_id":   pid,
            "provider_name": spec.get("display_name"),
            "default_model": spec.get("default_model"),
            "recommended":   next((v["id"] for v in variants if v.get("recommended")), None),
            "variants":      variants,
        })
    return {"providers": out}


class InferIn(BaseModel):
    prompt: str


@router.post("/infer")
async def ai_infer(body: InferIn, _: str = Depends(verify_token)):
    """Run the prompt inference engine on a free-form prompt.
    Useful for the UI to preview the foundation NXT1 would scaffold before
    actually creating a project.
    """
    result = infer_project_kind(body.prompt or "")
    return result.to_dict()


# ============================================================
#   Task-typed routing (Phase 11 W4 — Track 7)
# ============================================================
@router.get("/task-routing")
async def ai_task_routing(_: str = Depends(verify_token)):
    """Return the full task -> provider/model preference table + which
    provider+model NXT1 would pick *right now* for each task type.
    """
    table = task_routing_table()
    suggestions = {task: suggest_for_task(task) for task in table.keys()}
    return {"table": table, "suggestions": suggestions}


@router.get("/task-routing/{task_type}")
async def ai_task_route(task_type: str, _: str = Depends(verify_token)):
    """Return the suggestion + fallback chain for a single task type."""
    return {
        "task":        task_type,
        "suggestion":  suggest_for_task(task_type),
        "fallbacks":   available_for_task(task_type),
    }
