"""User auth service — email + password signup/signin with bcrypt + JWT.

Coexists with the existing admin password gate at /api/auth/login (which
returns a JWT with sub='admin'). User-token sub is the user_id (UUID).
verify_token doesn't care which one — both pass.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "nxt1-secret")
JWT_ALG = "HS256"
USER_TOKEN_DAYS = 30

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


def validate_password(password: str) -> Optional[str]:
    """Return error message if invalid, else None."""
    if not password or len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 128:
        return "Password must be 128 characters or less."
    return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), (password_hash or "").encode("utf-8"))
    except Exception:
        return False


def make_user_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "kind": "user",
        "exp": datetime.now(timezone.utc) + timedelta(days=USER_TOKEN_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def new_user_record(email: str, password: str, name: str = "") -> dict:
    user_id = f"u_{uuid.uuid4().hex[:14]}"
    now = datetime.now(timezone.utc).isoformat()
    return {
        "user_id": user_id,
        "email": normalize_email(email),
        "name": (name or "").strip()[:80],
        "password_hash": hash_password(password),
        "created_at": now,
        "updated_at": now,
        "onboarded": False,
        "access_status": "pending",  # pending | approved | denied
        "role": "user",
    }


def public_user(record: dict) -> dict:
    return {
        "user_id": record["user_id"],
        "email": record.get("email"),
        "name": record.get("name") or "",
        "onboarded": bool(record.get("onboarded")),
        "access_status": record.get("access_status") or "pending",
        "role": record.get("role") or "user",
        "created_at": record.get("created_at"),
    }
