"""Per-user Cloudflare connect service (Track C).

Lets a user paste their own Cloudflare API token to enable one-click
DNS-record creation for their own domains — without putting the token
in a server-wide env var.

Tokens are stored encrypted at rest per-user in MongoDB and decrypted
on demand for DNS calls.

NOTE: encryption key is derived from JWT_SECRET so secrets stay
portable across redeploys. If the user wants stronger separation they
can set CF_TOKEN_KEY env var.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import requests
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("nxt1.cf_user")

CF_API = "https://api.cloudflare.com/client/v4"


def _fernet() -> Fernet:
    raw = os.environ.get("CF_TOKEN_KEY") or os.environ.get("JWT_SECRET", "nxt1-secret")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    return Fernet(key)


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(token_blob: str) -> Optional[str]:
    if not token_blob:
        return None
    try:
        return _fernet().decrypt(token_blob.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def verify_token_with_cloudflare(token: str) -> dict:
    """Hit CF `/user/tokens/verify` to confirm the token is valid + active.

    Returns: { ok, status, expires_on?, error? }
    """
    try:
        r = requests.get(
            f"{CF_API}/user/tokens/verify",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code >= 400:
            return {"ok": False, "error": f"CF API {r.status_code}: {r.text[:200]}"}
        data = r.json()
        if not data.get("success"):
            return {"ok": False, "error": str(data.get("errors"))[:200]}
        result = data.get("result") or {}
        return {
            "ok": True,
            "status": result.get("status"),
            "expires_on": result.get("expires_on"),
            "not_before": result.get("not_before"),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def list_zones(token: str) -> dict:
    """List the Cloudflare zones (domains) the token has access to."""
    try:
        r = requests.get(
            f"{CF_API}/zones",
            headers={"Authorization": f"Bearer {token}"},
            params={"per_page": 50},
            timeout=15,
        )
        if r.status_code >= 400:
            return {"ok": False, "error": f"CF API {r.status_code}"}
        data = r.json()
        if not data.get("success"):
            return {"ok": False, "error": str(data.get("errors"))[:200]}
        zones = [{"id": z["id"], "name": z["name"], "status": z.get("status")}
                 for z in (data.get("result") or [])]
        return {"ok": True, "zones": zones}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def create_dns_record(token: str, zone_id: str, host: str, target: str,
                       record_type: str = "CNAME", proxied: bool = True) -> dict:
    body = {
        "type": record_type,
        "name": host,
        "content": target,
        "ttl": 1,
        "proxied": proxied,
    }
    try:
        r = requests.post(
            f"{CF_API}/zones/{zone_id}/dns_records",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json=body,
            timeout=20,
        )
        if r.status_code >= 400:
            return {"ok": False, "error": f"CF API {r.status_code}: {r.text[:200]}"}
        data = r.json()
        if not data.get("success"):
            return {"ok": False, "error": str(data.get("errors"))[:200]}
        return {"ok": True, "record_id": data["result"]["id"]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


async def save_user_cf_token(db_handle, user_id: str, token: str,
                              verify_result: dict) -> dict:
    """Persist the encrypted token in the users collection."""
    enc = encrypt_token(token)
    payload = {
        "cloudflare": {
            "connected": True,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "status": verify_result.get("status"),
            "expires_on": verify_result.get("expires_on"),
            "token_enc": enc,
        }
    }
    await db_handle.users.update_one(
        {"id": user_id}, {"$set": payload}, upsert=True,
    )
    return {"ok": True}


async def get_user_cf_token(db_handle, user_id: str) -> Optional[str]:
    doc = await db_handle.users.find_one({"id": user_id},
                                          {"_id": 0, "cloudflare": 1})
    if not doc:
        return None
    cf = doc.get("cloudflare") or {}
    return decrypt_token(cf.get("token_enc") or "")


async def disconnect_user_cf(db_handle, user_id: str) -> dict:
    await db_handle.users.update_one(
        {"id": user_id},
        {"$unset": {"cloudflare": ""}},
    )
    return {"ok": True}
