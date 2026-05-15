"""Shareable preview-link service.
... (truncated for brevity — see source for full module docstring)
"""
from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

import bcrypt


SLUG_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o/1/i/l ambiguity


def _new_slug(seed: Optional[str] = None) -> str:
    """8-char URL-safe slug, optionally seeded by a project name fragment."""
    head = ""
    if seed:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "", seed.lower())[:5]
        head = cleaned
    rand_n = 8 - len(head)
    rand = "".join(secrets.choice(SLUG_ALPHABET) for _ in range(max(rand_n, 4)))
    return f"{head}{rand}" if head else rand


def public_origin() -> str:
    """Where preview URLs are rooted. Falls back to the platform default.

    Resolution order:
      1. PREVIEW_PUBLIC_ORIGIN env (explicit override)
      2. BACKEND_PUBLIC_ORIGIN env (legacy)
      3. NXT One default: https://nxtone.ai
    Emergent-managed hostnames are never used here.
    """
    return (
        os.environ.get("PREVIEW_PUBLIC_ORIGIN")
        or os.environ.get("BACKEND_PUBLIC_ORIGIN")
        or "https://nxtone.ai"
    ).rstrip("/")


def build_url(slug: str, *, custom_host: Optional[str] = None) -> str:
    """Build the public preview URL for a slug. When `custom_host` is provided
    (e.g. `preview.project.nxtone.ai` or `demo.clientdomain.com`), serve from
    there instead of the platform origin."""
    if custom_host:
        host = custom_host.strip()
        # Strip scheme prefixes correctly (lstrip() strips chars, not a prefix).
        for scheme in ("https://", "http://"):
            if host.lower().startswith(scheme):
                host = host[len(scheme):]
                break
        host = host.rstrip("/")
        return f"https://{host}/p/{slug}"
    return f"{public_origin()}/p/{slug}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_initial(project_name: str, *, custom_host: Optional[str] = None) -> dict:
    slug = _new_slug(project_name)
    ts = now()
    return {
        "slug": slug,
        "url": build_url(slug, custom_host=custom_host),
        "custom_host": custom_host,
        "created_at": ts,
        "updated_at": ts,
        "build_count": 1,
        "public": True,
        "password": None,
        "expires_at": None,
    }


def refresh(existing: dict, *, custom_host: Optional[str] = None) -> dict:
    """Bump the build count + updated_at, keep the slug stable. Optionally
    re-issue the URL against a new custom host (e.g. the user just connected
    `preview.client.com` to this project)."""
    rec = dict(existing or {})
    rec["updated_at"] = now()
    rec["build_count"] = int(rec.get("build_count") or 0) + 1
    host = custom_host if custom_host is not None else rec.get("custom_host")
    if rec.get("slug"):
        rec["url"] = build_url(rec["slug"], custom_host=host)
    if custom_host is not None:
        rec["custom_host"] = custom_host
    return rec


def public_view(rec: dict) -> dict:
    """What we expose to authenticated frontend (full record except password)."""
    if not rec:
        return {}
    out = {k: v for k, v in rec.items() if k not in {"password", "password_hash"}}
    out["password_protected"] = bool(rec.get("password_hash"))
    return out


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False
