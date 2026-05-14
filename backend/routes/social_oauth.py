"""Social OAuth + connections + publishing + auto-pilot routes.

Endpoints:
  GET  /api/social/oauth/status            → which platforms have backend creds
  GET  /api/social/oauth/{platform}/start  → returns auth URL + sets pending state
  GET  /api/social/oauth/{platform}/callback?code=...&state=... (browser redirect)
  GET  /api/social/connections             → user's connected accounts
  POST /api/social/connections/{platform}/disconnect

  POST /api/social/posts/{id}/publish      → publish now (one platform = post.platform)
  POST /api/social/posts/{id}/schedule     → set status=scheduled, scheduled_at=ISO

  POST /api/social/autopilot               → set autopilot config
  GET  /api/social/autopilot               → get autopilot config
"""
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from services import job_service, social_publishing_service as pub

from ._deps import db, verify_token, verify_token_value

logger = logging.getLogger("nxt1.social.oauth")
router = APIRouter(prefix="/api/social", tags=["social-oauth"])


def _now():
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────── oauth status
@router.get("/oauth/status")
async def oauth_status(_: str = Depends(verify_token)):
    return pub.platform_status()


# ─────────────────────────────────────────────────────────── start oauth
class StartOut(BaseModel):
    auth_url: str
    state: str


@router.get("/oauth/{platform}/start", response_model=StartOut)
async def oauth_start(platform: str, user_id: str = Depends(verify_token)):
    if platform not in pub.PLATFORMS:
        raise HTTPException(400, "Unknown platform")
    status = pub.platform_status().get(platform, {})
    if not status.get("configured"):
        raise HTTPException(
            400,
            f"{status.get('label', platform)} OAuth credentials not configured on the server. "
            f"Set the platform env vars and restart backend.",
        )
    state = secrets.token_urlsafe(24)
    # Generate PKCE verifier for twitter; store with state.
    verifier = secrets.token_urlsafe(64) if platform == "twitter" else None
    await db.social_oauth_states.insert_one({
        "state": state,
        "user_id": user_id,
        "platform": platform,
        "code_verifier": verifier,
        "created_at": _now(),
    })
    auth_url = pub.build_authorize_url(platform, state, code_verifier=verifier)
    return StartOut(auth_url=auth_url, state=state)


# ─────────────────────────────────────────────────────────── callback
@router.get("/oauth/{platform}/callback")
async def oauth_callback(platform: str, code: Optional[str] = None,
                         state: Optional[str] = None, error: Optional[str] = None):
    """Browser-redirect endpoint. NOT JWT-gated — uses `state` to look up the user."""
    fe_base = (os.environ.get("REACT_APP_BACKEND_URL")
               or os.environ.get("PUBLIC_BACKEND_URL") or "/").rstrip("/")
    fe_redirect = f"{fe_base}/workspace/social?connected={platform}"

    if error:
        return RedirectResponse(f"{fe_redirect}&error={error}", status_code=302)
    if not code or not state:
        return RedirectResponse(f"{fe_redirect}&error=missing_code", status_code=302)
    if platform not in pub.PLATFORMS:
        return RedirectResponse(f"{fe_redirect}&error=bad_platform", status_code=302)

    rec = await db.social_oauth_states.find_one({"state": state, "platform": platform})
    if not rec:
        return RedirectResponse(f"{fe_redirect}&error=state_expired", status_code=302)
    user_id = rec["user_id"]
    verifier = rec.get("code_verifier")

    try:
        info = await pub.exchange_code(platform, code, verifier)
    except Exception as e:
        logger.exception("oauth exchange failed")
        return RedirectResponse(f"{fe_redirect}&error=exchange_failed", status_code=302)

    conn = {
        "user_id": user_id,
        "platform": platform,
        **info,
        "updated_at": _now(),
    }
    await db.social_connections.update_one(
        {"user_id": user_id, "platform": platform},
        {"$set": conn, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    await db.social_oauth_states.delete_one({"state": state})
    return RedirectResponse(fe_redirect, status_code=302)


# ─────────────────────────────────────────────────────────── connections
def _scrub(c: dict) -> dict:
    """Strip secrets before sending to client."""
    if not c:
        return {}
    out = {k: v for k, v in c.items() if k not in {"access_token", "refresh_token",
                                                   "user_access_token", "_id"}}
    out["connected"] = True
    return out


@router.get("/connections")
async def list_connections(user_id: str = Depends(verify_token)):
    cur = db.social_connections.find({"user_id": user_id}, {"_id": 0})
    items = [c async for c in cur]
    by_plat = {c["platform"]: _scrub(c) for c in items}
    out = []
    status = pub.platform_status()
    for p in pub.PLATFORMS:
        out.append({
            "platform": p,
            "label": status[p]["label"],
            "configured": status[p]["configured"],
            "redirect_uri": status[p]["redirect_uri"],
            **(by_plat.get(p) or {"connected": False}),
        })
    return {"items": out}


@router.post("/connections/{platform}/disconnect")
async def disconnect(platform: str, user_id: str = Depends(verify_token)):
    if platform not in pub.PLATFORMS:
        raise HTTPException(400, "Unknown platform")
    await db.social_connections.delete_one({"user_id": user_id, "platform": platform})
    return {"ok": True}


# ─────────────────────────────────────────────────────────── publish / schedule
class ScheduleBody(BaseModel):
    scheduled_at: str  # ISO timestamp


@router.post("/posts/{post_id}/publish")
async def publish_now(post_id: str, user_id: str = Depends(verify_token)):
    post = await db.social_posts.find_one({"id": post_id, "user_id": user_id}, {"_id": 0})
    if not post:
        raise HTTPException(404, "Post not found")
    conn = await db.social_connections.find_one(
        {"user_id": user_id, "platform": post["platform"]}, {"_id": 0})
    if not conn:
        raise HTTPException(400, f"No {post['platform']} account connected.")

    media_abs = None
    if post.get("image_url"):
        media_abs = pub._public_base() + post["image_url"] if post["image_url"].startswith("/") else post["image_url"]
    try:
        result = await pub.publish_post(conn, post, media_url=media_abs)
    except Exception as e:
        logger.exception("publish failed")
        await db.social_posts.update_one(
            {"id": post_id},
            {"$set": {"last_publish_error": str(e)[:300], "updated_at": _now()}},
        )
        raise HTTPException(500, f"Publish failed: {e}")

    await db.social_posts.update_one(
        {"id": post_id},
        {"$set": {
            "status": "posted",
            "platform_post_id": result.get("platform_post_id"),
            "platform_url": result.get("url"),
            "posted_at": _now(),
            "last_publish_error": None,
            "updated_at": _now(),
        }},
    )
    return {"ok": True, **result}


@router.post("/posts/{post_id}/schedule")
async def schedule_post(post_id: str, body: ScheduleBody, user_id: str = Depends(verify_token)):
    res = await db.social_posts.update_one(
        {"id": post_id, "user_id": user_id},
        {"$set": {"status": "scheduled", "scheduled_at": body.scheduled_at, "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    return {"ok": True}


# ─────────────────────────────────────────────────────────── autopilot
class AutopilotBody(BaseModel):
    enabled: bool = False
    brief: str = ""
    tone: str = "professional"
    platforms: list[str] = Field(default_factory=lambda: ["linkedin", "twitter"])
    duration: str = "this week"
    cadence_day: int = 1   # 0=Mon … 6=Sun
    cadence_hour: int = 9


@router.get("/autopilot")
async def get_autopilot(user_id: str = Depends(verify_token)):
    rec = await db.social_autopilot.find_one({"user_id": user_id}, {"_id": 0})
    if not rec:
        return {
            "user_id": user_id, "enabled": False, "brief": "", "tone": "professional",
            "platforms": ["linkedin", "twitter"], "duration": "this week",
            "cadence_day": 1, "cadence_hour": 9, "last_run_at": None, "next_run_at": None,
        }
    return rec


@router.post("/autopilot")
async def set_autopilot(body: AutopilotBody, user_id: str = Depends(verify_token)):
    payload = body.model_dump()
    payload["user_id"] = user_id
    payload["updated_at"] = _now()
    await db.social_autopilot.update_one(
        {"user_id": user_id},
        {"$set": payload, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    return payload
