"""Asset storage helper. Uses Cloudflare R2 when configured, otherwise falls
back to Emergent Object Storage."""
import logging
import os
from typing import Optional, Tuple

import requests
from fastapi import HTTPException

from services import r2_service

logger = logging.getLogger("nxt1.storage")

STORAGE_URL = os.environ.get(
    "EMERGENT_STORAGE_URL",
    f"{os.environ.get('EMERGENT_BASE_URL', 'https://integrations.emergentagent.com')}/objstore/api/v1/storage",
)
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
_storage_key: Optional[str] = None


def init_storage() -> Optional[str]:
    """Initialize the active backend. R2 takes precedence when configured."""
    global _storage_key
    if r2_service.is_configured():
        try:
            r2_service.ensure_bucket()
            logger.info("Storage initialized · backend=r2 bucket=%s", r2_service._bucket())
            return "r2"
        except Exception as e:
            logger.warning("R2 init failed (%s) — falling back to Emergent storage", e)
    if _storage_key:
        return _storage_key
    if not EMERGENT_LLM_KEY:
        logger.warning("EMERGENT_LLM_KEY not set, storage disabled")
        return None
    try:
        resp = requests.post(
            f"{STORAGE_URL}/init",
            json={"emergent_key": EMERGENT_LLM_KEY},
            timeout=30,
        )
        resp.raise_for_status()
        _storage_key = resp.json()["storage_key"]
        logger.info("Storage initialized · backend=emergent")
        return _storage_key
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
        return None


def active_backend() -> str:
    if r2_service.is_configured():
        return "r2"
    if _storage_key or EMERGENT_LLM_KEY:
        return "emergent"
    return "none"


def status() -> dict:
    backend = active_backend()
    out = {"active": backend}
    out["r2"] = r2_service.status()
    out["emergent"] = {"configured": bool(EMERGENT_LLM_KEY)}
    return out


def put_object(path: str, data: bytes, content_type: str) -> dict:
    if r2_service.is_configured():
        try:
            return r2_service.put_object(path, data, content_type)
        except Exception as e:
            logger.warning(f"R2 PUT failed ({e}) — falling back to Emergent")
    key = init_storage()
    if not key:
        raise HTTPException(status_code=500, detail="Storage not available")
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    body["provider"] = "emergent"
    body["path"] = path
    body["size"] = len(data)
    return body


def get_object(path: str) -> Tuple[bytes, str]:
    if r2_service.is_configured():
        try:
            return r2_service.get_object(path)
        except Exception as e:
            logger.warning(f"R2 GET failed ({e}) — trying Emergent")
    key = init_storage()
    if not key:
        raise HTTPException(status_code=500, detail="Storage not available")
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
