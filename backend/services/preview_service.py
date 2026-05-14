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
    """Where preview URLs are rooted. Falls back to the preview env if unset."""
    return (
        os.environ.get("PREVIEW_PUBLIC_ORIGIN")
        or os.environ.get("BACKEND_PUBLIC_ORIGIN")
        or "https://nxtone.tech"
    ).rstrip("/")


def build_url(slug: str) -> str:
    return f"{public_origin()}/p/{slug}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_initial(project_name: str) -> dict:
    slug = _new_slug(project_name)
    ts = now()
    return {
        "slug": slug,
        "url": build_url(slug),
        "created_at": ts,
        "updated_at": ts,
        "build_count": 1,
        "public": True,
        "password": None,
        "expires_at": None,
    }


def refresh(existing: dict) -> dict:
    """Bump the build count + updated_at, keep the slug stable."""
    rec = dict(existing or {})
    rec["updated_at"] = now()
    rec["build_count"] = int(rec.get("build_count") or 0) + 1
    # If somehow URL was stored against an old origin, refresh it too.
    if rec.get("slug"):
        rec["url"] = build_url(rec["slug"])
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
