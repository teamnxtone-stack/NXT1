"""Social publishing — OAuth client registry + per-platform posting calls.

Each platform's actual posting code only fires when its env-var credentials
are present. The user pastes them in Render env / `.env` and posting flips on.

Design:
  • OAuth metadata is computed from env at import time, but each posting call
    re-reads env so a restart isn't required after first paste.
  • Stored tokens live in `db.social_connections`:
        {
          user_id, platform, access_token, refresh_token,
          token_expires_at (ISO), account_id, account_name, scopes [], created_at
        }
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger("nxt1.social.publishing")

PLATFORMS = ("instagram", "linkedin", "twitter")

# ────────────────────────────────────────────────────────────────────── env
def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _public_base() -> str:
    return (_env("PUBLIC_BACKEND_URL") or _env("REACT_APP_BACKEND_URL")
            or "http://localhost:8001").rstrip("/")


def callback_url(platform: str) -> str:
    return f"{_public_base()}/api/social/oauth/{platform}/callback"


def platform_status() -> dict:
    """What the FE can show: which platforms have backend creds wired."""
    return {
        "instagram": {
            "configured": bool(_env("META_APP_ID") and _env("META_APP_SECRET")),
            "label": "Instagram",
            "redirect_uri": callback_url("instagram"),
        },
        "twitter": {
            "configured": bool(_env("X_CLIENT_ID") and _env("X_CLIENT_SECRET")),
            "label": "X (Twitter)",
            "redirect_uri": callback_url("twitter"),
        },
        "linkedin": {
            "configured": bool(_env("LINKEDIN_CLIENT_ID") and _env("LINKEDIN_CLIENT_SECRET")),
            "label": "LinkedIn",
            "redirect_uri": callback_url("linkedin"),
        },
    }


# ────────────────────────────────────────────────────────────── OAuth start
INSTAGRAM_SCOPES = "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement,business_management"
LINKEDIN_SCOPES  = "openid profile email w_member_social"
TWITTER_SCOPES   = "tweet.read tweet.write users.read offline.access"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def build_authorize_url(platform: str, state: str, code_verifier: Optional[str] = None) -> str:
    if platform == "instagram":
        params = {
            "client_id": _env("META_APP_ID"),
            "redirect_uri": callback_url("instagram"),
            "response_type": "code",
            "scope": INSTAGRAM_SCOPES,
            "state": state,
        }
        return "https://www.facebook.com/v21.0/dialog/oauth?" + urllib.parse.urlencode(params)

    if platform == "linkedin":
        params = {
            "client_id": _env("LINKEDIN_CLIENT_ID"),
            "redirect_uri": callback_url("linkedin"),
            "response_type": "code",
            "scope": LINKEDIN_SCOPES,
            "state": state,
        }
        return "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(params)

    if platform == "twitter":
        # PKCE required for X OAuth 2.0
        _, challenge = _pkce_pair() if not code_verifier else (None, _pkce_challenge_from(code_verifier))
        params = {
            "response_type": "code",
            "client_id": _env("X_CLIENT_ID"),
            "redirect_uri": callback_url("twitter"),
            "scope": TWITTER_SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return "https://twitter.com/i/oauth2/authorize?" + urllib.parse.urlencode(params)

    raise ValueError(f"Unknown platform: {platform}")


def _pkce_challenge_from(verifier: str) -> str:
    return base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()


# ───────────────────────────────────────────────── OAuth exchange (callback)
async def exchange_code(platform: str, code: str, code_verifier: Optional[str]) -> dict:
    """Trade the auth code for an access token. Returns connection dict."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        if platform == "instagram":
            return await _meta_exchange(client, code)
        if platform == "linkedin":
            return await _linkedin_exchange(client, code)
        if platform == "twitter":
            return await _twitter_exchange(client, code, code_verifier or "")
    raise ValueError(f"Unknown platform: {platform}")


async def _meta_exchange(client: httpx.AsyncClient, code: str) -> dict:
    # Step 1: short-lived user token
    r = await client.get(
        "https://graph.facebook.com/v21.0/oauth/access_token",
        params={
            "client_id": _env("META_APP_ID"),
            "client_secret": _env("META_APP_SECRET"),
            "redirect_uri": callback_url("instagram"),
            "code": code,
        },
    )
    r.raise_for_status()
    short = r.json()
    short_token = short["access_token"]

    # Step 2: long-lived user token (~60 days)
    r2 = await client.get(
        "https://graph.facebook.com/v21.0/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": _env("META_APP_ID"),
            "client_secret": _env("META_APP_SECRET"),
            "fb_exchange_token": short_token,
        },
    )
    r2.raise_for_status()
    long = r2.json()
    long_token = long["access_token"]
    expires_in = long.get("expires_in", 60 * 24 * 3600)

    # Step 3: find the IG Business Account ID via /me/accounts → page → instagram_business_account
    pages = await client.get(
        "https://graph.facebook.com/v21.0/me/accounts",
        params={"access_token": long_token},
    )
    pages.raise_for_status()
    page_list = pages.json().get("data", [])
    ig_account_id = None
    ig_account_name = None
    page_token = None
    for p in page_list:
        page_token = p.get("access_token")
        details = await client.get(
            f"https://graph.facebook.com/v21.0/{p['id']}",
            params={"fields": "instagram_business_account{id,username}", "access_token": page_token},
        )
        body = details.json() if details.status_code == 200 else {}
        ig = body.get("instagram_business_account")
        if ig:
            ig_account_id = ig["id"]
            ig_account_name = ig.get("username")
            break

    return {
        "access_token": page_token or long_token,
        "user_access_token": long_token,
        "token_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat(),
        "account_id": ig_account_id,
        "account_name": ig_account_name or "Connected Instagram account",
        "scopes": INSTAGRAM_SCOPES.split(","),
        "needs_ig_business_account": ig_account_id is None,
    }


async def _linkedin_exchange(client: httpx.AsyncClient, code: str) -> dict:
    r = await client.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": callback_url("linkedin"),
            "client_id": _env("LINKEDIN_CLIENT_ID"),
            "client_secret": _env("LINKEDIN_CLIENT_SECRET"),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    r.raise_for_status()
    tok = r.json()
    access = tok["access_token"]
    expires = tok.get("expires_in", 3600 * 24 * 60)
    # Identity (OpenID)
    me = await client.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access}"},
    )
    body = me.json() if me.status_code == 200 else {}
    return {
        "access_token": access,
        "token_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=int(expires))).isoformat(),
        "account_id": body.get("sub"),
        "account_name": body.get("name") or "LinkedIn member",
        "scopes": LINKEDIN_SCOPES.split(),
    }


async def _twitter_exchange(client: httpx.AsyncClient, code: str, verifier: str) -> dict:
    cid = _env("X_CLIENT_ID")
    sec = _env("X_CLIENT_SECRET")
    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    r = await client.post(
        "https://api.twitter.com/2/oauth2/token",
        data={
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": callback_url("twitter"),
            "code_verifier": verifier,
            "client_id": cid,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic}",
        },
    )
    r.raise_for_status()
    tok = r.json()
    access = tok["access_token"]
    refresh = tok.get("refresh_token")
    expires = tok.get("expires_in", 7200)
    # who are we
    me = await client.get(
        "https://api.twitter.com/2/users/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    body = me.json().get("data", {}) if me.status_code == 200 else {}
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=int(expires))).isoformat(),
        "account_id": body.get("id"),
        "account_name": "@" + body["username"] if body.get("username") else "X account",
        "scopes": TWITTER_SCOPES.split(),
    }


# ─────────────────────────────────────────────────────────── posting calls
async def publish_post(connection: dict, post: dict, media_url: Optional[str] = None) -> dict:
    """Return {ok, platform_post_id, url} or raise."""
    platform = connection["platform"]
    if platform == "instagram":
        return await _publish_instagram(connection, post, media_url)
    if platform == "linkedin":
        return await _publish_linkedin(connection, post, media_url)
    if platform == "twitter":
        return await _publish_twitter(connection, post, media_url)
    raise ValueError(f"Unsupported platform: {platform}")


def _caption_with_tags(post: dict, max_tags: int = 30) -> str:
    base = (post.get("caption") or "").strip()
    tags = " ".join("#" + t.lstrip("#") for t in (post.get("hashtags") or [])[:max_tags])
    return (base + ("\n\n" + tags if tags else "")).strip()


async def _publish_instagram(conn: dict, post: dict, media_url: Optional[str]) -> dict:
    if not conn.get("account_id"):
        raise RuntimeError("No Instagram Business Account linked to this Facebook Page.")
    if not media_url:
        raise RuntimeError("Instagram requires an image. Generate one before publishing.")
    token = conn["access_token"]
    igid = conn["account_id"]
    caption = _caption_with_tags(post)
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1) create media container
        r1 = await client.post(
            f"https://graph.facebook.com/v21.0/{igid}/media",
            params={"image_url": media_url, "caption": caption, "access_token": token},
        )
        r1.raise_for_status()
        creation_id = r1.json()["id"]
        # 2) publish
        r2 = await client.post(
            f"https://graph.facebook.com/v21.0/{igid}/media_publish",
            params={"creation_id": creation_id, "access_token": token},
        )
        r2.raise_for_status()
        media_id = r2.json()["id"]
        return {"ok": True, "platform_post_id": media_id, "url": f"https://www.instagram.com/p/{media_id}"}


async def _publish_linkedin(conn: dict, post: dict, media_url: Optional[str]) -> dict:
    """LinkedIn UGC post — supports an optional image via register-upload + upload binary."""
    token = conn["access_token"]
    author = f"urn:li:person:{conn['account_id']}"
    text = _caption_with_tags(post, max_tags=5)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    media_urn: Optional[str] = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        if media_url:
            try:
                # 1) Download the image bytes
                img_bytes = (await client.get(media_url)).content
                # 2) registerUpload
                reg = await client.post(
                    "https://api.linkedin.com/v2/assets?action=registerUpload",
                    headers=headers,
                    json={
                        "registerUploadRequest": {
                            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                            "owner": author,
                            "serviceRelationships": [
                                {"relationshipType": "OWNER",
                                 "identifier": "urn:li:userGeneratedContent"}
                            ],
                        }
                    },
                )
                reg.raise_for_status()
                rj = reg.json()["value"]
                upload_url = rj["uploadMechanism"][
                    "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
                ]["uploadUrl"]
                media_urn = rj["asset"]
                # 3) Binary upload to the returned URL
                up = await client.put(upload_url, content=img_bytes,
                                      headers={"Authorization": f"Bearer {token}"})
                up.raise_for_status()
            except Exception as e:
                logger.warning(f"LinkedIn image upload failed, falling back to text-only: {e}")
                media_urn = None

        if media_urn:
            share_content = {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "IMAGE",
                "media": [{
                    "status": "READY",
                    "media": media_urn,
                    "description": {"text": post.get("topic", "")[:200]},
                    "title": {"text": (post.get("topic") or "Post")[:80]},
                }],
            }
        else:
            share_content = {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }

        payload = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        r = await client.post("https://api.linkedin.com/v2/ugcPosts",
                              headers=headers, json=payload)
        r.raise_for_status()
        urn = r.headers.get("x-restli-id") or r.json().get("id")
        return {"ok": True, "platform_post_id": urn,
                "url": "https://www.linkedin.com/feed/"}


async def _twitter_upload_media(token: str, image_bytes: bytes) -> Optional[str]:
    """X v1.1 media/upload — yes, even with OAuth 2.0 bearer this is accepted."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"media": ("image.png", image_bytes, "application/octet-stream")}
            r = await client.post(
                "https://upload.twitter.com/1.1/media/upload.json",
                headers={"Authorization": f"Bearer {token}"},
                files=files,
            )
            if r.status_code >= 300:
                logger.warning(f"X media upload non-200: {r.status_code} {r.text[:200]}")
                return None
            return str(r.json().get("media_id_string") or "")
    except Exception as e:
        logger.warning(f"X media upload failed: {e}")
        return None


async def _publish_twitter(conn: dict, post: dict, media_url: Optional[str]) -> dict:
    token = conn["access_token"]
    text = _caption_with_tags(post, max_tags=3)
    if len(text) > 280:
        text = text[:277] + "…"

    media_id: Optional[str] = None
    if media_url:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                img_bytes = (await client.get(media_url)).content
            media_id = await _twitter_upload_media(token, img_bytes)
        except Exception as e:
            logger.warning(f"X image fetch failed: {e}")

    body: dict = {"text": text}
    if media_id:
        body["media"] = {"media_ids": [media_id]}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.twitter.com/2/tweets",
            json=body,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
        )
        r.raise_for_status()
        d = r.json().get("data", {})
        tid = d.get("id")
        uname = (conn.get("account_name") or "").lstrip("@")
        return {"ok": True, "platform_post_id": tid,
                "url": f"https://twitter.com/{uname}/status/{tid}" if uname and tid else ""}
