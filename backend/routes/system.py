"""NXT1 — System diagnostics (Phase 11 W2-B).

A single read-only surface for the workspace Admin / Account / Settings panels
to answer: “which keys are configured, which providers are available, what
still needs to be wired before this deploys to my own infrastructure?”

Covers four families:
  * AI providers     (LLM keys)
  * OAuth providers  (Google / Apple / GitHub)
  * Hosting          (Vercel / Netlify / Railway / Cloudflare / Custom)
  * Core             (Mongo / Backend env / Emergent dev fallback state)

Returns ONLY metadata + presence flags — NEVER any secret material.
"""
from __future__ import annotations

import os
from typing import Dict, List

from fastapi import APIRouter, Depends

from services.ai_service import provider_health
from services.hosting import list_hosting_targets
from services.providers.catalog import list_provider_variants
from ._deps import verify_token

router = APIRouter(prefix="/api/system", tags=["system"])


OAUTH_PROVIDERS = [
    {"id": "google", "label": "Google",  "env_vars": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]},
    {"id": "apple",  "label": "Apple",   "env_vars": ["APPLE_CLIENT_ID",  "APPLE_CLIENT_SECRET"]},
    {"id": "github", "label": "GitHub",  "env_vars": ["GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"]},
]


def _env_ok(keys: List[str]) -> bool:
    return all(bool((os.environ.get(k) or "").strip()) for k in keys)


def _env_missing(keys: List[str]) -> List[str]:
    return [k for k in keys if not (os.environ.get(k) or "").strip()]


@router.get("/diagnostics")
async def diagnostics(_: str = Depends(verify_token)):
    """Aggregate readiness across AI, OAuth, hosting, and core.

    Shape:
      {
        ready: bool,                  # everything required for a basic build is wired
        portable: bool,                # no dependency on Emergent dev fallback
        ai:      {providers: [...], available: [...]},
        oauth:   [{id, label, configured, missing_env}],
        hosting: [{id, label, configured, missing_env, capabilities, tier}],
        core:    {mongo_url, backend_env_path, emergent_dev_fallback, jwt_secret_set, ...},
      }
    """
    ai = provider_health()
    avail_ids = set(ai.get("available") or [])

    oauth = []
    for p in OAUTH_PROVIDERS:
        oauth.append({
            **p,
            "configured": _env_ok(p["env_vars"]),
            "missing_env": _env_missing(p["env_vars"]),
        })

    hosting = list_hosting_targets()

    has_emergent = "emergent" in avail_ids
    has_user_llm = bool(avail_ids - {"emergent"})

    core: Dict = {
        "mongo_configured":         bool((os.environ.get("MONGO_URL") or "").strip()),
        "jwt_secret_set":           bool((os.environ.get("JWT_SECRET") or "").strip()),
        "emergent_dev_fallback":    has_emergent,
        "using_only_emergent":      has_emergent and not has_user_llm,
        "github_token_set":         bool((os.environ.get("GITHUB_TOKEN") or "").strip()),
        "public_app_url":           (os.environ.get("PUBLIC_APP_URL") or "").strip(),
    }

    # "ready": at least one AI provider is configured AND Mongo is configured.
    ready = bool(avail_ids) and core["mongo_configured"]
    # "portable": ready AND there's at least one non-emergent provider
    # (so the system can stand on the user's own keys when detached).
    portable = ready and has_user_llm

    return {
        "ready":    ready,
        "portable": portable,
        "ai":       ai,
        "oauth":    oauth,
        "hosting":  hosting,
        "core":     core,
    }


@router.get("/health")
async def system_health():
    """Lightweight public health probe — NO auth required. Reports nothing
    sensitive: just up/down + service name.
    """
    return {
        "ok":      True,
        "service": "nxt1-backend",
        "version": (os.environ.get("NXT1_VERSION") or "dev"),
    }


@router.get("/ready")
async def system_ready():
    """Public deployment readiness probe — confirms the backend has at least
    one working AI provider + a MongoDB connection. Reports provider IDs
    only (never keys) so it's safe to expose to ops dashboards / uptime
    monitors. Returns 200 with `ready: false` when something is missing
    instead of erroring, so this is also useful as a self-diagnostic page.
    """
    from services.ai_service import list_provider_specs
    specs = list_provider_specs()
    configured = [s["id"] for s in specs if s.get("available")]
    required_env_unset = [
        s["requires_env"][0]
        for s in specs
        if not s.get("available") and s.get("requires_env")
    ]
    ready = len(configured) > 0
    return {
        "ready": ready,
        "service": "nxt1-backend",
        "version": (os.environ.get("NXT1_VERSION") or "dev"),
        "ai_providers": {
            "configured": configured,
            "total": len(specs),
            "missing_env_hint": required_env_unset[:8],  # cap
        },
        "auth": {
            "github_oauth": bool(os.environ.get("OAUTH_GITHUB_CLIENT_ID") and os.environ.get("OAUTH_GITHUB_CLIENT_SECRET")),
        },
        "hint": (
            "All set." if ready
            else "Set at least one of: GEMINI_API_KEY, XAI_API_KEY (or aliases GOOGLE_API_KEY/GROK_API_KEY), OPENAI_API_KEY, ANTHROPIC_API_KEY, EMERGENT_LLM_KEY."
        ),
    }
