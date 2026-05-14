"""Unified asset storage facade — R2 when configured, local disk fallback.

This is the SINGLE entry point every upload path uses. It wraps the existing
`services.r2_service` (already in the codebase) and adds a local-disk fallback
so the platform works the same in:

  • dev / preview pod (no R2 keys → local files served by FastAPI routes)
  • Render production (R2 keys present → durable object storage + public CDN)

The moment the user pastes R2 keys into Render env and restarts the service,
every new upload automatically lands in R2 with **zero code changes**.
"""
from __future__ import annotations

import logging
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Optional

from services import r2_service

logger = logging.getLogger("nxt1.asset_storage")

BASE_STATIC = Path(__file__).resolve().parent.parent / "static"
BASE_STATIC.mkdir(parents=True, exist_ok=True)

# folder → URL prefix mapping for the LOCAL fallback. These match the FastAPI
# routes already defined in routes/social.py and routes/video.py.
_LOCAL_URL_PREFIX = {
    "social":           "/api/social/assets",
    "social/logos":     "/api/social/logo",
    "social/refs":      "/api/social/reference",
    "video/clips":      "/api/video/clips",
    "video/refs":       "/api/video/refs",
    "video/exports":    "/api/video/exports",
}


def backend() -> str:
    return "r2" if r2_service.is_configured() else "local"


def status() -> dict:
    return {"backend": backend(), **r2_service.status()}


def new_filename(suffix: str = ".bin") -> str:
    return f"{uuid.uuid4().hex}{suffix}"


def _local_url(folder: str, filename: str) -> str:
    prefix = _LOCAL_URL_PREFIX.get(folder, f"/api/{folder}")
    return f"{prefix}/{filename}"


def put_bytes(
    *,
    folder: str,                     # e.g. "social", "video/clips"
    filename: str,                   # final basename (caller decides uniqueness)
    data: bytes,
    content_type: Optional[str] = None,
) -> dict:
    """Persist bytes. Returns dict with at least {url, backend, key/file_path}.

    On R2: returns the public URL (requires `R2_PUBLIC_BASE` to be set; r2_service
    builds a `pub-…r2.dev` fallback otherwise). On local: returns the
    `/api/.../filename` URL the routes already serve.

    On R2 failure (network blip etc.), falls back to local disk so the upload
    NEVER hard-fails for the user.
    """
    ct = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    if r2_service.is_configured():
        try:
            key = f"{folder.strip('/')}/{filename}"
            res = r2_service.put_object(key, data, ct)
            return {
                "url": res.get("public_url") or _local_url(folder, filename),
                "key": key,
                "backend": "r2",
                "size": len(data),
                "content_type": ct,
            }
        except Exception as e:
            logger.exception(f"R2 put failed for {folder}/{filename}; using local: {e}")

    folder_path = BASE_STATIC / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    out = folder_path / filename
    out.write_bytes(data)
    return {
        "url": _local_url(folder, filename),
        "file_path": str(out),
        "key": str(out),
        "backend": "local",
        "size": len(data),
        "content_type": ct,
    }


def put_file(*, folder: str, filename: str, src_path: str,
             content_type: Optional[str] = None) -> dict:
    return put_bytes(
        folder=folder, filename=filename,
        data=Path(src_path).read_bytes(),
        content_type=content_type,
    )


def delete(folder: str, filename_or_key: str) -> None:
    """Best-effort delete from R2 (if configured) and local. Never raises."""
    if r2_service.is_configured():
        key = filename_or_key if "/" in filename_or_key else f"{folder.strip('/')}/{filename_or_key}"
        try:
            r2_service.delete_object(key)
        except Exception as e:
            logger.warning(f"R2 delete failed for {key}: {e}")
    try:
        # If the caller gave us a full file_path, try that first
        p = Path(filename_or_key)
        if p.is_absolute() and p.exists():
            p.unlink(missing_ok=True)
            return
        (BASE_STATIC / folder / filename_or_key).unlink(missing_ok=True)
    except Exception:
        pass
