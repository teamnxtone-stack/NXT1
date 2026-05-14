"""Agents endpoints (Phase 7+).

GET  /api/agents       — list registered agent roles
POST /api/agents/run   — run a single agent on a free-form prompt
POST /api/agents/route — heuristic router: pick the best agent for a prompt
"""
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services import agents as agents_svc
from ._deps import verify_token

router = APIRouter(prefix="/api", tags=["agents"])


class AgentRunIn(BaseModel):
    role: str
    prompt: str
    provider: Optional[str] = None


class AgentRouteIn(BaseModel):
    prompt: str


# Simple keyword-based router — this is the "AI orchestration" foundation.
_ROUTER_HINTS: list[tuple[str, list[str]]] = [
    ("debug",        ["error", "errors", "traceback", "exception", "broken", "crash", "crashes",
                      "crashing", "stack trace", "fix the bug", "fix this", "doesn't work",
                      "fails when", "nameerror", "typeerror", "valueerror", "attributeerror",
                      "modulenotfounderror", "syntaxerror", "runtimeerror"]),
    ("devops",       ["deploy", "deployment", "deploying", "deploys", "vercel", "cloudflare",
                      "build failed", "ssl", "domain", "dns", "cname", "production", "redeploy"]),
    ("backend",      ["api", "endpoint", "route", "fastapi", "express", "backend",
                      "database", "schema", "auth", "jwt", "crud", "rest"]),
    ("frontend",     ["ui", "page", "component", "responsive", "tailwind", "react", "css",
                      "design", "layout", "modal", "dropdown", "form"]),
    ("architecture", ["build a", "create a", "saas", "platform", "dashboard",
                      "product", "architect", "plan", "milestones", "roadmap", "system"]),
]


def _route_for(prompt: str) -> str:
    p = (prompt or "").lower()
    # Word-boundary tokens to avoid false positives (e.g. 'ui' inside 'build')
    scores: dict[str, int] = {}
    for role, hints in _ROUTER_HINTS:
        score = 0
        for h in hints:
            # Use word boundary for short hints; substring for multi-word phrases
            if " " in h:
                if h in p:
                    score += 1
            else:
                if re.search(rf"\b{re.escape(h)}\b", p):
                    score += 1
        scores[role] = score
    role = max(scores.items(), key=lambda kv: kv[1])[0]
    # Default to architecture for substantial prompts (>= 12 words) with no clear signal
    if scores[role] == 0:
        words = len(p.split())
        return "architecture" if words >= 12 else "frontend"
    # Tie-breaker: if architecture has the same top score and prompt starts with 'build'/'create'/'design',
    # prefer architecture (high-level intent).
    top = scores[role]
    if scores.get("architecture", 0) == top and re.match(r"^\s*(build|create|design|plan)\b", p):
        return "architecture"
    return role


@router.get("/agents")
async def list_available_agents(_: str = Depends(verify_token)):
    return agents_svc.list_agents()


@router.post("/agents/run")
async def run_agent(body: AgentRunIn, _: str = Depends(verify_token)):
    try:
        agent = agents_svc.get_agent(body.role, preferred_provider=body.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = await agent.run(body.prompt)
    return {
        "role": result.role,
        "text": result.text[:8000],
        "parsed": result.parsed,
        "provider": result.provider,
        "model": result.model,
    }


@router.post("/agents/route")
async def route_to_agent(body: AgentRouteIn, _: str = Depends(verify_token)):
    """Heuristic router: returns the best agent role for a prompt without invoking it."""
    role = _route_for(body.prompt or "")
    return {"role": role, "label": next(
        (a["label"] for a in agents_svc.list_agents() if a["role"] == role),
        role,
    )}



# ============================================================
# Phase 10E — Lifecycle orchestration endpoints (additive).
#
# These power the cinematic Activity Stream's agent attribution
# (planner → builder → tester → deployer). They sit alongside the
# domain agents above (architecture / frontend / backend / debug /
# devops) without disturbing them.
#
# The lifecycle agents live in `services.orchestration` so the
# back-compat `services.agents` module stays untouched.
# ============================================================
from services.orchestration import default_orchestrator, AgentRole as _LifecycleRole


class _LifecycleDispatchIn(BaseModel):
    role: str
    payload: dict = {}


class _LifecyclePipelineIn(BaseModel):
    payload: dict = {}
    roles: Optional[list[str]] = None


@router.get("/agents/lifecycle")
async def list_lifecycle_agents():
    """List lifecycle agents (planner/builder/tester/deployer) — used by
    the Activity Stream + future autonomous flows to render attribution.
    Domain agents remain reachable via `GET /api/agents`.
    """
    out = []
    for r in default_orchestrator.roles():
        agent = default_orchestrator.get(r)
        out.append({
            "role": r,
            "description": getattr(agent, "description", ""),
        })
    return {"agents": out, "all_roles": _LifecycleRole.all()}


@router.post("/agents/lifecycle/dispatch")
async def dispatch_lifecycle_agent(body: _LifecycleDispatchIn):
    """Diagnostics: dispatch a single lifecycle agent. Does NOT trigger a
    real build (chat SSE owns that). Most useful for the Planner role as a
    plan-preview before the user hits Build.
    """
    res = await default_orchestrator.dispatch(body.role, body.payload)
    return res.to_dict()


@router.post("/agents/lifecycle/pipeline")
async def run_lifecycle_pipeline(body: _LifecyclePipelineIn):
    """Run the full lifecycle pipeline (planner → builder → tester →
    deployer). Diagnostic surface for future autonomous flows.
    """
    results = await default_orchestrator.run_pipeline(body.payload, roles=body.roles)
    return {"results": [r.to_dict() for r in results]}
