"""Product / launch-readiness endpoints (Phase 9 foundation).

GET /api/projects/{id}/readiness — heuristic launch checklist
GET /api/projects/{id}/product-plan — AI-generated MVP plan from project intent
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services import agents as agents_svc
from services import runtime_service as rt_svc
from ._deps import db, verify_token

router = APIRouter(prefix="/api", tags=["product"])


class ProductPlanIn(BaseModel):
    brief: str  # high-level product idea ("Build a CRM for contractors")
    provider: Optional[str] = None


# ----- Launch readiness ----------------------------------------------------
@router.get("/projects/{project_id}/readiness")
async def project_readiness(project_id: str, _: str = Depends(verify_token)):
    """Return a launch-readiness checklist with pass/warn/fail per check."""
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")

    files = doc.get("files") or []
    env_vars = doc.get("env_vars") or []
    domains = doc.get("domains") or []
    deployments = doc.get("deployments") or []
    analysis = doc.get("analysis") or {}
    has_backend = any(f["path"].startswith("backend/") for f in files)

    checks: list[dict] = []

    # 1. Files present
    checks.append({
        "id": "has_files",
        "label": "Project has files",
        "status": "pass" if files else "fail",
        "detail": f"{len(files)} file{'s' if len(files) != 1 else ''}",
    })

    # 2. Index entry
    has_index = any(f["path"] in ("index.html", "src/App.jsx", "src/App.tsx") for f in files)
    checks.append({
        "id": "frontend_entry",
        "label": "Frontend entry present",
        "status": "pass" if has_index else "warn",
        "detail": "index.html or src/App.jsx" if has_index else "no clear entry file detected",
    })

    # 3. Backend
    checks.append({
        "id": "backend",
        "label": "Backend (optional)",
        "status": "pass" if has_backend else "skip",
        "detail": "backend/ folder present" if has_backend else "no backend yet",
    })

    # 4. Runtime alive (if backend)
    if has_backend:
        rt = rt_svc.get_handle(project_id)
        alive = bool(rt and rt.is_alive())
        checks.append({
            "id": "runtime_alive",
            "label": "Backend runtime running",
            "status": "pass" if alive else "warn",
            "detail": "running" if alive else "not running — deploy will not include live state",
        })

    # 5. Env vars referenced are filled
    referenced = set(analysis.get("env_keys") or [])
    set_keys = {v["key"] for v in env_vars if (v.get("value") or "").strip()}
    missing = sorted(referenced - set_keys)
    if referenced:
        checks.append({
            "id": "env_filled",
            "label": "Env vars referenced have values",
            "status": "pass" if not missing else "fail",
            "detail": f"missing: {', '.join(missing)}" if missing else f"{len(set_keys)} set",
            "missing": missing,
        })

    # 6. Last deployment
    last_dep = deployments[-1] if deployments else None
    if last_dep is None:
        checks.append({"id": "deployed", "label": "Has a deployment",
                       "status": "warn", "detail": "no deployments yet"})
    else:
        ok = last_dep.get("status") == "deployed"
        checks.append({
            "id": "deployed",
            "label": "Latest deployment status",
            "status": "pass" if ok else "fail",
            "detail": f"{last_dep.get('status')} via {last_dep.get('provider')}",
        })

    # 7. Domain
    primary = next((d for d in domains if d.get("is_primary")), domains[0] if domains else None)
    if primary:
        ok = primary.get("status") == "verified"
        checks.append({
            "id": "domain",
            "label": "Custom domain",
            "status": "pass" if ok else "warn",
            "detail": f"{primary.get('hostname')} · {primary.get('status')}",
        })
    else:
        checks.append({"id": "domain", "label": "Custom domain",
                       "status": "skip", "detail": "no domain connected"})

    # 8. README / metadata
    has_readme = any(f["path"].lower() in ("readme.md", "readme.txt") for f in files)
    checks.append({
        "id": "readme",
        "label": "README present",
        "status": "pass" if has_readme else "warn",
        "detail": "README found" if has_readme else "Add a README before launching",
    })

    # Score: pass=1, warn=0.5, fail=0, skip excluded
    scored = [c for c in checks if c["status"] in ("pass", "warn", "fail")]
    if scored:
        score = sum(1 if c["status"] == "pass" else 0.5 if c["status"] == "warn" else 0
                    for c in scored) / len(scored)
        score_pct = round(score * 100)
    else:
        score_pct = 0

    return {
        "project_id": project_id,
        "score": score_pct,
        "checks": checks,
        "fail_count": sum(1 for c in checks if c["status"] == "fail"),
        "warn_count": sum(1 for c in checks if c["status"] == "warn"),
    }


# ----- AI product plan -----------------------------------------------------
@router.post("/projects/{project_id}/product-plan")
async def generate_product_plan(project_id: str, body: ProductPlanIn,
                                _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "id": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")

    plan_prompt = (
        "You are a product manager / architect. Given the user's high-level "
        "product brief, output a STRICT JSON plan:\n"
        "{\n"
        '  "summary": "<one-line product summary>",\n'
        '  "user_personas": ["...", "..."],\n'
        '  "mvp_features": [{"name": "...", "why": "...", "priority": "P0"|"P1"|"P2"}],\n'
        '  "screens": [{"name": "...", "purpose": "..."}],\n'
        '  "api_routes": [{"method": "GET|POST|...", "path": "/...", "purpose": "..."}],\n'
        '  "data_model": [{"entity": "...", "fields": ["..."]}],\n'
        '  "milestones": [{"title": "...", "tasks": ["..."]}],\n'
        '  "deployment_notes": "..."\n'
        "}\n"
        "Be concrete. Cap mvp_features at 8, screens at 8, api_routes at 12, "
        "milestones at 5. No prose outside JSON. No markdown fences."
    )
    agent = agents_svc.get_agent("architecture", preferred_provider=body.provider)
    result = await agent.run(
        f"PRODUCT BRIEF:\n{body.brief[:2000]}",
        system_prompt_override=plan_prompt,
    )
    parsed = result.parsed or {}

    return {
        "ok": True,
        "plan": parsed,
        "raw_text_preview": result.text[:1000] if not parsed else None,
        "provider": result.provider,
        "model": result.model,
    }
