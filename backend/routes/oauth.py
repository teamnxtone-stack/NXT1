"""NXT1 OAuth foundation — Google / GitHub / Apple.

This module implements the full OAuth dance shape (start → redirect →
callback → token exchange → identity fetch → user upsert → JWT) for all
three providers, but is intentionally **placeholder-safe**: when client
credentials are not configured, the /start endpoint returns a friendly
"not_configured" payload that the frontend uses to show a toast — the
code path remains stable so we can wire real credentials later without
any rewrites.

Env vars consumed (all optional):
    OAUTH_GOOGLE_CLIENT_ID, OAUTH_GOOGLE_CLIENT_SECRET
    OAUTH_GITHUB_CLIENT_ID, OAUTH_GITHUB_CLIENT_SECRET
    OAUTH_APPLE_CLIENT_ID  (Apple uses signed JWT for secret — stub for now)
    OAUTH_REDIRECT_BASE  (e.g. "https://nxt1.example.com")
    BACKEND_PUBLIC_ORIGIN (fallback if OAUTH_REDIRECT_BASE missing)
    FRONTEND_PUBLIC_ORIGIN (where to land the user after success)

All endpoints are mounted under /api/oauth.

Database shape (extends `users` collection):
  users.auth_methods = {
    email_password: bool,
    google:   { sub, email, name, picture, linked_at },
    github:   { id, login, email, avatar_url, linked_at },
    apple:    { sub, email, linked_at }
  }
  users.primary_email

Account linking strategy: if the OAuth identity's email matches an existing
user, attach the provider info to that user. Otherwise create a new user.
Admins can later expose linking UI; the schema already supports it.
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from services import user_service

from ._deps import db

logger = logging.getLogger("nxt1.oauth")

router = APIRouter(prefix="/api/oauth", tags=["oauth"])


# ---------- Helpers ----------
def _redirect_base() -> str:
    """Where the OAuth provider should send the user back. This MUST match
    what's configured in the provider's dashboard. We prefer an explicit
    OAUTH_REDIRECT_BASE, falling back to BACKEND_PUBLIC_ORIGIN.
    """
    base = (os.environ.get("OAUTH_REDIRECT_BASE")
            or os.environ.get("BACKEND_PUBLIC_ORIGIN")
            or "").rstrip("/")
    return base


def _frontend_base() -> str:
    return (os.environ.get("FRONTEND_PUBLIC_ORIGIN")
            or os.environ.get("BACKEND_PUBLIC_ORIGIN")
            or "").rstrip("/")


def _provider_config(provider: str) -> dict:
    """Return per-provider {client_id, client_secret, authorize_url, token_url,
    userinfo_url, scope, configured} tuple."""
    if provider == "google":
        cid = os.environ.get("OAUTH_GOOGLE_CLIENT_ID", "").strip()
        csec = os.environ.get("OAUTH_GOOGLE_CLIENT_SECRET", "").strip()
        return {
            "client_id": cid,
            "client_secret": csec,
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            "scope": "openid email profile",
            "configured": bool(cid and csec),
        }
    if provider == "github":
        cid = os.environ.get("OAUTH_GITHUB_CLIENT_ID", "").strip()
        csec = os.environ.get("OAUTH_GITHUB_CLIENT_SECRET", "").strip()
        return {
            "client_id": cid,
            "client_secret": csec,
            "authorize_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "userinfo_url": "https://api.github.com/user",
            "emails_url": "https://api.github.com/user/emails",
            "scope": "read:user user:email",
            "configured": bool(cid and csec),
        }
    if provider == "apple":
        cid = os.environ.get("OAUTH_APPLE_CLIENT_ID", "").strip()
        # Apple requires a signed JWT as client secret — we treat the presence
        # of a private key env var as "configured" without implementing the
        # signing dance yet (it requires `apple_jwt` library + .p8 key).
        secret_ready = bool(
            os.environ.get("OAUTH_APPLE_PRIVATE_KEY", "").strip()
            and os.environ.get("OAUTH_APPLE_KEY_ID", "").strip()
            and os.environ.get("OAUTH_APPLE_TEAM_ID", "").strip()
        )
        return {
            "client_id": cid,
            "client_secret": "",   # generated at runtime when implemented
            "authorize_url": "https://appleid.apple.com/auth/authorize",
            "token_url": "https://appleid.apple.com/auth/token",
            "userinfo_url": "",    # Apple returns identity in the id_token claim
            "scope": "name email",
            "configured": bool(cid and secret_ready),
        }
    raise HTTPException(status_code=400, detail=f"Unknown OAuth provider '{provider}'")


# ---------- Status endpoint ----------
@router.get("/status")
async def oauth_status():
    """Public status — the frontend uses this to decide whether to show real
    OAuth buttons (configured) or graceful placeholders (not configured)."""
    return {
        "google": {"configured": _provider_config("google")["configured"]},
        "github": {"configured": _provider_config("github")["configured"]},
        "apple":  {"configured": _provider_config("apple")["configured"]},
        "redirect_base": _redirect_base() or None,
    }


# ---------- Start (redirect to provider) ----------
@router.get("/{provider}/start")
async def oauth_start(
    provider: str,
    request: Request,
    return_to: Optional[str] = Query(None, alias="return"),
    prompt: Optional[str] = Query(None),
):
    """Kicks off the OAuth dance.

    If the provider is configured: stores state + return_to in the db, then
    redirects to the provider's authorize_url.

    If not configured: returns a structured JSON payload so the frontend can
    show a friendly "not configured yet" toast without surfacing a 500.
    """
    cfg = _provider_config(provider)
    if not cfg["configured"]:
        # Placeholder-safe response. Frontend interprets `configured: false`
        # and shows a graceful message; the URL we'd redirect to is exposed
        # for inspection/admin.
        return {
            "ok": False,
            "configured": False,
            "provider": provider,
            "message": f"{provider.capitalize()} OAuth not yet configured. Set OAUTH_{provider.upper()}_CLIENT_ID / SECRET to enable.",
            "would_redirect_to": cfg["authorize_url"],
        }

    redirect_base = _redirect_base()
    if not redirect_base:
        raise HTTPException(
            status_code=503,
            detail="OAuth redirect base not configured (OAUTH_REDIRECT_BASE or BACKEND_PUBLIC_ORIGIN).",
        )

    # Persist state so the callback can verify + recover return_to/prompt.
    state = secrets.token_urlsafe(32)
    await db.oauth_states.insert_one({
        "state": state,
        "provider": provider,
        "return_to": return_to or "",
        "prompt": prompt or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    redirect_uri = f"{redirect_base}/api/oauth/{provider}/callback"
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    if provider == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"
    if provider == "apple":
        params["response_mode"] = "form_post"

    url = f"{cfg['authorize_url']}?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


# ---------- Callback (provider → NXT1) ----------
@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """Exchange the code for an identity, upsert a user, mint a JWT, and
    redirect the browser back to the frontend with `?oauth=success&token=...`
    so the SPA can store it and continue."""
    if error:
        return _frontend_error_redirect(provider, error)
    if not code or not state:
        return _frontend_error_redirect(provider, "missing_code_or_state")

    saved = await db.oauth_states.find_one({"state": state}, {"_id": 0})
    if not saved or saved.get("provider") != provider:
        return _frontend_error_redirect(provider, "invalid_state")

    try:
        identity = await _exchange_and_fetch_identity(provider, code)
    except Exception as e:
        logger.exception("OAuth callback failed")
        return _frontend_error_redirect(provider, f"exchange_failed:{str(e)[:80]}")

    # Upsert user by email (account linking by email).
    email = (identity.get("email") or "").lower().strip() or None
    name = identity.get("name") or ""
    now = datetime.now(timezone.utc).isoformat()

    user = None
    if email:
        user = await db.users.find_one({"email": email}, {"_id": 0})

    if user:
        # Link this provider into the existing account.
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                f"auth_methods.{provider}": {**identity, "linked_at": now},
                "last_login_at": now,
                "updated_at": now,
            }},
        )
        token = user_service.make_user_token(user["user_id"])
    else:
        # New user. Generate a placeholder password hash (unused for OAuth login).
        if not email:
            # Synthesize a stable identifier when provider didn't expose email.
            email = f"oauth-{provider}-{identity.get('sub') or identity.get('id') or secrets.token_hex(6)}@nxt1.local"
        rec = user_service.new_user_record(
            email=email,
            password=secrets.token_urlsafe(24),  # never used — they sign in via OAuth
            name=name,
        )
        rec["auth_methods"] = {provider: {**identity, "linked_at": now}}
        rec["primary_email"] = email
        rec["emails"] = [email]
        rec["last_login_at"] = now
        await db.users.insert_one(rec)
        token = user_service.make_user_token(rec["user_id"])

    # Clean up the state record.
    await db.oauth_states.delete_one({"state": state})

    # Redirect into the frontend with the token so the SPA can persist it.
    return _frontend_success_redirect(provider, token, saved.get("return_to", ""),
                                        saved.get("prompt", ""))


# ---------- Linking endpoints (foundation; can be invoked later from UI) ----------
class LinkIn(BaseModel):
    provider: str
    identity: dict


@router.post("/unlink")
async def oauth_unlink(body: LinkIn):
    """Stub — surfaced for future account settings UI. The frontend will
    eventually call this with a valid bearer token; we keep the shape ready.
    """
    # NOTE: Real implementation should verify the bearer token via _deps.verify_token.
    return {"ok": True, "note": "unlink is a foundation stub; wire UI later."}


# ---------- Frontend redirects ----------
def _frontend_success_redirect(provider: str, token: str, return_to: str, prompt: str) -> RedirectResponse:
    base = _frontend_base() or ""
    # Default destination after OAuth: workspace.
    dest = return_to or "/workspace"
    sep = "&" if "?" in dest else "?"
    extras = {"oauth": "success", "provider": provider, "token": token}
    if prompt:
        extras["prompt"] = prompt
    url = f"{base}{dest}{sep}{urlencode(extras)}"
    return RedirectResponse(url, status_code=302)


def _frontend_error_redirect(provider: str, reason: str) -> RedirectResponse:
    base = _frontend_base() or ""
    url = f"{base}/signin?{urlencode({'oauth': 'error', 'provider': provider, 'reason': reason})}"
    return RedirectResponse(url, status_code=302)


# ---------- Identity fetchers ----------
async def _exchange_and_fetch_identity(provider: str, code: str) -> dict:
    cfg = _provider_config(provider)
    redirect_uri = f"{_redirect_base()}/api/oauth/{provider}/callback"
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Token exchange
        token_resp = await client.post(
            cfg["token_url"],
            data={
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        tok = token_resp.json()
        access_token = tok.get("access_token")
        if not access_token:
            raise RuntimeError("no access_token in provider response")

        # Identity fetch
        if provider == "google":
            ui = await client.get(
                cfg["userinfo_url"], headers={"Authorization": f"Bearer {access_token}"},
            )
            ui.raise_for_status()
            d = ui.json()
            return {
                "sub": d.get("sub"),
                "email": d.get("email"),
                "name": d.get("name") or "",
                "picture": d.get("picture") or "",
            }

        if provider == "github":
            ui = await client.get(
                cfg["userinfo_url"],
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            )
            ui.raise_for_status()
            d = ui.json()
            email = d.get("email")
            if not email:
                # GitHub only returns email here if it's public. Use /emails for the rest.
                em = await client.get(
                    cfg["emails_url"],
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
                )
                if em.status_code == 200:
                    emails = em.json() or []
                    primary = next((e for e in emails if e.get("primary")), emails[0] if emails else None)
                    if primary:
                        email = primary.get("email")
            return {
                "id": d.get("id"),
                "login": d.get("login"),
                "email": email,
                "name": d.get("name") or d.get("login") or "",
                "avatar_url": d.get("avatar_url"),
            }

        if provider == "apple":
            # Apple returns identity inside the id_token JWT — decoded without
            # verifying signature here (production should verify via Apple's JWKs).
            id_token = tok.get("id_token") or ""
            if not id_token:
                raise RuntimeError("no id_token from Apple")
            import base64
            import json
            try:
                _, payload, _ = id_token.split(".")
                payload += "=" * (-len(payload) % 4)
                claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
            except Exception as e:
                raise RuntimeError(f"apple id_token decode failed: {e}")
            return {
                "sub": claims.get("sub"),
                "email": claims.get("email"),
                "name": "",  # Apple only returns name on first login via form_post
            }

    raise RuntimeError(f"Unsupported provider {provider}")
