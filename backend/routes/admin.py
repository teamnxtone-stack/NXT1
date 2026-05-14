"""Admin workspace routes — unified backend for the /admin console.

- GET /api/admin/github/status — checks the configured GITHUB_TOKEN: returns
  authenticated user + which scopes are present + whether write access is
  available. Used by the Site Editor banner so the operator sees the exact
  upgrade required.
- GET /api/admin/overview — small status snapshot (recent edits, deploy host,
  active providers, integration health) for the admin landing page.
- POST /api/admin/brand — structured "Brand & Theme" mutation. Routes the
  form payload through the existing site_editor `propose+apply` pipeline so
  every change is diffed, history-recorded, and pushed via NXT1 GitHub.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import github_service
from services.ai_service import get_active_provider
from services import audit_service

from ._deps import db, verify_token
from .site_editor import (
    SAFE_PATHS,
    SYSTEM_PROMPT,
    _build_user_prompt,
    _extract_json,
    _safe_read,
    _safe_write,
)

logger = logging.getLogger("nxt1.admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _admin_only(sub: str = Depends(verify_token)) -> str:
    if sub != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return sub


# ---------- GitHub status ----------
@router.get("/github/status")
async def github_status(_: str = Depends(_admin_only)):
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return {
            "configured": False,
            "ready": False,
            "summary": "Add a GITHUB_TOKEN to /app/backend/.env to enable Save / Site Editor pushes.",
        }
    try:
        r = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "NXT1-Admin",
            },
            timeout=15,
        )
    except Exception as e:
        return {"configured": True, "ready": False, "summary": f"GitHub unreachable: {e}"}
    if r.status_code != 200:
        return {
            "configured": True,
            "ready": False,
            "status_code": r.status_code,
            "summary": f"Token rejected by GitHub ({r.status_code}). Re-issue a fresh fine-grained PAT.",
        }
    user = r.json()
    # Probe write access by attempting a read against /user/repos (always works
    # with read scope) and checking the X-OAuth-Scopes header for classic
    # tokens. Fine-grained PATs don't expose scopes via headers — we verify
    # write access by attempting a dry repo lookup; if creation later fails we
    # already surface a friendly error from github_service.
    scopes_header = r.headers.get("X-OAuth-Scopes", "") or r.headers.get("X-Github-Scopes", "")
    scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]

    # Best-effort write probe: check if we can list the user's repos with
    # full data (which fine-grained PATs allow only when granted contents
    # read/write or admin perms on at least one repo).
    write_probe = "unknown"
    try:
        rp = requests.get(
            "https://api.github.com/user/repos?per_page=1&visibility=all",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "NXT1-Admin",
            },
            timeout=10,
        )
        if rp.status_code == 200:
            write_probe = "ok"
        elif rp.status_code in (401, 403):
            write_probe = "denied"
    except Exception:
        pass

    # ready = "we have at least basic access". Real write capability is only
    # confirmed when a push succeeds; we expose this as a separate flag.
    return {
        "configured": True,
        "ready": True,
        "login": user.get("login"),
        "name": user.get("name"),
        "avatar_url": user.get("avatar_url"),
        "scopes": scopes,
        "write_probe": write_probe,
        "summary": (
            f"Authenticated as {user.get('login')}. "
            "Push will only succeed if the fine-grained PAT grants `Contents: read & write` "
            "and `Administration: read & write` for the target repo. If a push returns "
            "a 403 hint, upgrade scopes at https://github.com/settings/tokens?type=beta."
        ),
    }


# ---------- Overview ----------
@router.get("/overview")
async def admin_overview(_: str = Depends(_admin_only)):
    edits_count = await db.site_edits.count_documents({})
    last_edit = await db.site_edits.find_one(
        {}, {"_id": 0, "snapshot": 0}, sort=[("created_at", -1)]
    )
    users_count = await db.users.count_documents({})
    pending_count = await db.users.count_documents({"access_status": "pending"})
    projects_count = await db.projects.count_documents({})
    return {
        "users": {"total": users_count, "pending": pending_count},
        "projects": {"total": projects_count},
        "site_edits": {"total": edits_count, "last": last_edit},
        "providers": {
            "openai": bool(os.environ.get("OPENAI_API_KEY")),
            "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "groq": bool(os.environ.get("GROQ_API_KEY")),
            "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
            "vercel": bool(os.environ.get("VERCEL_TOKEN")),
            "cloudflare": bool(os.environ.get("CLOUDFLARE_API_TOKEN")),
            "supabase": bool(os.environ.get("SUPABASE_ACCESS_TOKEN") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
            "neon": bool(os.environ.get("NEON_API_KEY")),
            "atlas": bool(
                os.environ.get("MONGODB_ATLAS_PUBLIC_KEY")
                and os.environ.get("MONGODB_ATLAS_PRIVATE_KEY")
                and os.environ.get("MONGODB_ATLAS_ORG_ID")
            ),
            "r2": bool(
                os.environ.get("R2_ACCOUNT_ID")
                and os.environ.get("R2_ACCESS_KEY_ID")
                and os.environ.get("R2_SECRET_ACCESS_KEY")
            ),
            "github": bool(os.environ.get("GITHUB_TOKEN")),
        },
        "deploy_origin": os.environ.get("PREVIEW_PUBLIC_ORIGIN")
        or os.environ.get("BACKEND_PUBLIC_ORIGIN", ""),
    }


# ---------- Editable secrets (env vars) ----------
# Whitelist of keys that can be edited from the UI. We never expose values —
# only presence + a 4-char fingerprint hash.
EDITABLE_KEYS = [
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "EMERGENT_LLM_KEY",
    "GROQ_API_KEY", "OPENROUTER_API_KEY",
    "VERCEL_TOKEN",
    "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_ZONE_ID",
    "GITHUB_TOKEN",
    "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ACCESS_TOKEN", "SUPABASE_ORG_ID",
    "NEON_API_KEY", "NEON_ORG_ID",
    "MONGODB_ATLAS_PUBLIC_KEY", "MONGODB_ATLAS_PRIVATE_KEY", "MONGODB_ATLAS_ORG_ID",
    "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET", "R2_PUBLIC_BASE",
    "AI_PROVIDER", "DEPLOY_HOST", "PREVIEW_PUBLIC_ORIGIN", "BACKEND_PUBLIC_ORIGIN",
]

PROTECTED_KEYS = {"MONGO_URL", "DB_NAME", "JWT_SECRET", "APP_PASSWORD"}

ENV_PATH = os.environ.get("NXT1_ENV_PATH", "/app/backend/.env")


def _read_env_file() -> dict:
    out = {}
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return out


def _write_env_file(updates: dict) -> None:
    """Merge `updates` into the .env file. Empty string deletes the key.
    Preserves order and untouched keys; never edits PROTECTED_KEYS."""
    existing_lines = []
    seen = set()
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    existing_lines.append(line)
                    continue
                k = stripped.split("=", 1)[0].strip()
                if k in PROTECTED_KEYS:
                    existing_lines.append(line)
                    continue
                if k in updates:
                    new_val = updates[k]
                    if new_val == "":
                        # Delete by skipping this line
                        seen.add(k)
                        continue
                    existing_lines.append(f"{k}={new_val}")
                    seen.add(k)
                else:
                    existing_lines.append(line)
    except FileNotFoundError:
        pass
    # Append new keys
    for k, v in updates.items():
        if k in seen or k in PROTECTED_KEYS or v == "":
            continue
        existing_lines.append(f"{k}={v}")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(existing_lines).rstrip("\n") + "\n")


@router.get("/secrets")
async def list_editable_secrets(_: str = Depends(_admin_only)):
    env = _read_env_file()
    items = []
    for k in EDITABLE_KEYS:
        v = (env.get(k) or os.environ.get(k) or "").strip()
        items.append({
            "key": k,
            "present": bool(v),
            "fingerprint": (v[:2] + "…" + v[-2:]) if len(v) >= 6 else ("set" if v else ""),
            "editable": True,
            "protected": False,
        })
    return {"items": items, "env_path": ENV_PATH}


class SecretsUpdateIn(BaseModel):
    updates: dict  # { KEY: "value", ... }; empty string = delete


@router.post("/secrets")
async def update_secrets(body: SecretsUpdateIn, _: str = Depends(_admin_only)):
    safe_updates = {}
    for k, v in (body.updates or {}).items():
        if k in PROTECTED_KEYS:
            raise HTTPException(status_code=400, detail=f"{k} is protected and cannot be edited from the UI.")
        if k not in EDITABLE_KEYS:
            raise HTTPException(status_code=400, detail=f"{k} is not in the editable whitelist.")
        if not isinstance(v, str):
            raise HTTPException(status_code=400, detail=f"{k} must be a string (use '' to delete).")
        safe_updates[k] = v.strip()
    _write_env_file(safe_updates)
    # Also patch the live process env so changes take effect without restart.
    for k, v in safe_updates.items():
        if v == "":
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    await audit_service.record(
        db, tool="secrets", action="update",
        target=",".join(sorted(safe_updates.keys()))[:200],
        details={"keys": list(safe_updates.keys())},
    )
    return {"ok": True, "updated": list(safe_updates.keys())}


@router.post("/restart")
async def restart_backend(_: str = Depends(_admin_only)):
    """Re-load .env into the running process. Restarting via supervisor would
    kill this very request; we just refresh os.environ from disk so the change
    is visible without a hard restart."""
    env = _read_env_file()
    refreshed = []
    for k, v in env.items():
        if k in PROTECTED_KEYS:
            continue
        os.environ[k] = v
        refreshed.append(k)
    return {"ok": True, "refreshed": refreshed}


# ---------- Brand & Theme ----------
class BrandThemeIn(BaseModel):
    # Colors (hex). Empty values are ignored.
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    background_color: Optional[str] = None
    # Typography
    heading_font: Optional[str] = None
    body_font: Optional[str] = None
    # Wordmark + brand
    wordmark: Optional[str] = None
    tagline: Optional[str] = None
    # Public copy
    hero_headline: Optional[str] = None
    hero_subhead: Optional[str] = None
    primary_cta_label: Optional[str] = None
    secondary_cta_label: Optional[str] = None
    # Footer / legal
    footer_attribution: Optional[str] = None
    # Layout / spacing
    button_style: Optional[str] = Field(None, description="rounded | pill | sharp")
    section_spacing: Optional[str] = Field(None, description="compact | comfortable | airy")
    # Optional human note for context
    notes: Optional[str] = None


class BrandThemeOut(BaseModel):
    edit_id: str
    summary: str
    explanation: str
    files: List[dict]


def _build_brand_prompt(payload: BrandThemeIn) -> str:
    """Translate the structured form payload into a precise NL prompt that
    the existing site_editor system prompt can act on. We keep the output
    surface tiny and concrete to maximize reliability."""
    parts = ["Update the NXT1 site Brand & Theme as follows. Apply ALL items."]
    if payload.primary_color:
        parts.append(f"- Primary brand color: {payload.primary_color}.")
    if payload.accent_color:
        parts.append(f"- Accent color: {payload.accent_color}.")
    if payload.background_color:
        parts.append(f"- Page background color: {payload.background_color}.")
    if payload.heading_font:
        parts.append(f"- Heading font: {payload.heading_font} (preserve fallback to system-ui, sans-serif).")
    if payload.body_font:
        parts.append(f"- Body font: {payload.body_font} (preserve fallback to system-ui, sans-serif).")
    if payload.wordmark:
        parts.append(
            f'- Wordmark text: "{payload.wordmark}" (replace any current "NXT1" wordmark text in components/Brand.jsx).'
        )
    if payload.tagline:
        parts.append(f'- Tagline: "{payload.tagline}".')
    if payload.hero_headline:
        parts.append(f'- Hero headline (LandingPage.jsx): "{payload.hero_headline}".')
    if payload.hero_subhead:
        parts.append(f'- Hero sub-headline / paragraph (LandingPage.jsx): "{payload.hero_subhead}".')
    if payload.primary_cta_label:
        parts.append(f'- Primary CTA label: "{payload.primary_cta_label}".')
    if payload.secondary_cta_label:
        parts.append(f'- Secondary CTA label: "{payload.secondary_cta_label}".')
    if payload.footer_attribution:
        parts.append(f'- Footer attribution text (PublicFooter.jsx): "{payload.footer_attribution}".')
    if payload.button_style:
        parts.append(
            f"- Button style: {payload.button_style} "
            "(translate to TailwindCSS: rounded -> rounded-lg, pill -> rounded-full, sharp -> rounded-sm)."
        )
    if payload.section_spacing:
        parts.append(
            f"- Section spacing: {payload.section_spacing} "
            "(compact -> py-12, comfortable -> py-20, airy -> py-32 on the public sections)."
        )
    if payload.notes:
        parts.append(f"\nADDITIONAL OPERATOR NOTES:\n{payload.notes.strip()}")

    parts.append(
        "\nRULES:\n"
        "- Edit ONLY the files needed for these changes.\n"
        "- Preserve every existing data-testid, prop, route, import, and design-system class.\n"
        "- For colors, prefer Tailwind arbitrary values (e.g. text-[#3ec5b9]) or update CSS variables in index.css.\n"
        "- Do NOT remove any sections or rewrite unrelated code.\n"
    )
    return "\n".join(parts)


@router.post("/brand", response_model=BrandThemeOut)
async def update_brand_theme(body: BrandThemeIn, _: str = Depends(_admin_only)):
    """Generate a Brand & Theme proposal via the existing site-editor pipeline.
    Returns the proposed edit (NOT applied). The admin reviews + applies
    through the standard site_editor /apply route — same history, same diff,
    same rollback path."""
    prompt = _build_brand_prompt(body)
    target_paths = [
        p for p in [
            "frontend/src/pages/LandingPage.jsx",
            "frontend/src/components/Brand.jsx",
            "frontend/src/components/PublicFooter.jsx",
            "frontend/src/index.css",
        ] if p in SAFE_PATHS
    ]
    files_payload = {p: _safe_read(p) or "" for p in target_paths}

    provider = get_active_provider()
    user_prompt = _build_user_prompt(prompt, files_payload)
    try:
        raw = await provider.generate(SYSTEM_PROMPT, user_prompt, "brand-theme")
    except Exception as e:
        logger.exception("brand propose failed")
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}")
    try:
        parsed = _extract_json(raw)
    except Exception as e:
        logger.warning(f"brand non-JSON: {raw[:300]}")
        raise HTTPException(status_code=502, detail=f"AI returned invalid output: {e}")

    edits = []
    for f in parsed.get("files", []) or []:
        path = (f.get("path") or "").lstrip("/")
        if path not in SAFE_PATHS:
            continue
        edits.append({"path": path, "content": f.get("content") or ""})
    if not edits:
        raise HTTPException(status_code=502,
                            detail="Brand agent didn't return any valid file edits.")

    import uuid as _uuid
    edit_id = f"brand_{_uuid.uuid4().hex[:12]}"
    record = {
        "edit_id": edit_id,
        "prompt": prompt,
        "source": "brand_theme",
        "summary": parsed.get("summary") or "Brand & Theme update",
        "explanation": parsed.get("explanation") or "",
        "files": edits,
        "status": "proposed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "form_payload": json.loads(body.model_dump_json()),
    }
    await db.site_edits.insert_one(record)
    return BrandThemeOut(
        edit_id=edit_id,
        summary=record["summary"],
        explanation=record["explanation"],
        files=edits,
    )
