"""Auth + system status routes (Phase 8 modular refactor)."""
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.ai_service import list_provider_status
from services.deployment_service import list_providers as list_deploy_providers
from services.domain_service import cf_configured

from ._deps import JWT_ALG, JWT_SECRET, verify_token

router = APIRouter(prefix="/api", tags=["auth"])

APP_PASSWORD = os.environ.get("APP_PASSWORD", "nxt1admin")


class LoginIn(BaseModel):
    password: str


class LoginOut(BaseModel):
    token: str


def _make_token() -> str:
    payload = {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(days=30)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


@router.post("/auth/login", response_model=LoginOut)
async def login(body: LoginIn):
    if body.password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    return LoginOut(token=_make_token())


@router.get("/auth/verify")
async def auth_verify(_: str = Depends(verify_token)):
    return {"ok": True}


@router.get("/system/providers")
async def system_providers(_: str = Depends(verify_token)):
    return {
        "ai": list_provider_status(),
        "deploy": list_deploy_providers(),
        "cloudflare_dns_configured": cf_configured(),
    }


# Known config keys we surface in the masked Settings panel.
_KNOWN_SECRET_KEYS = [
    ("APP_PASSWORD", "Login passkey", "core"),
    ("MONGO_URL", "Database connection", "core"),
    ("BACKEND_PUBLIC_ORIGIN", "Public API origin", "core"),
    ("AI_PROVIDER", "Default AI provider", "ai"),
    ("OPENAI_API_KEY", "OpenAI", "ai"),
    ("ANTHROPIC_API_KEY", "Claude (Anthropic)", "ai"),
    ("EMERGENT_LLM_KEY", "Emergent universal key", "ai"),
    ("OPENROUTER_API_KEY", "OpenRouter", "ai"),
    ("GROQ_API_KEY", "Groq", "ai"),
    ("VERCEL_TOKEN", "Vercel deploys", "deploy"),
    ("CLOUDFLARE_API_TOKEN", "Cloudflare API", "deploy"),
    ("CLOUDFLARE_ACCOUNT_ID", "Cloudflare account", "deploy"),
    ("CLOUDFLARE_ZONE_ID", "Cloudflare DNS zone", "deploy"),
    ("GITHUB_TOKEN", "GitHub", "deploy"),
    ("R2_ACCESS_KEY_ID", "Cloudflare R2 access", "data"),
    ("R2_SECRET_ACCESS_KEY", "Cloudflare R2 secret", "data"),
    ("R2_ACCOUNT_ID", "Cloudflare R2 account", "data"),
    ("SUPABASE_URL", "Supabase URL", "data"),
    ("SUPABASE_SERVICE_ROLE_KEY", "Supabase service role", "data"),
    ("NEON_API_KEY", "Neon Postgres", "data"),
]


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "•" * len(value)
    return "•" * 18  # uniform mask, like the reference screenshot


@router.get("/system/secrets")
async def system_secrets(_: str = Depends(verify_token)):
    """Returns a Settings-friendly list of known config keys with a uniform
    mask (NEVER the real value). The frontend uses this to render a
    'configured / not configured' status sheet without exposing sensitive
    material to the client.
    """
    out = []
    for key, label, group in _KNOWN_SECRET_KEYS:
        v = (os.environ.get(key) or "").strip()
        out.append({
            "key": key,
            "label": label,
            "group": group,
            "configured": bool(v),
            "masked": _mask(v),
        })
    return {"items": out}


@router.get("/")
async def root():
    return {"app": "NXT1", "status": "ok", "version": "0.6.0"}
