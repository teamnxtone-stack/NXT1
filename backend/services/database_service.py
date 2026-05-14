"""Database connection registry for NXT1.

Phase 5 foundation. Lets users register external database connections
(Supabase / PostgreSQL / MongoDB Atlas) per project. Connections are stored
encrypted-at-rest (same masking pattern as env vars) and can be:
  - injected as `DATABASE_URL` env var into the runtime sandbox
  - referenced by the AI when generating database access code

This module deliberately does NOT provision DBs. That requires per-provider
SDKs (Supabase admin API, AWS RDS, etc.) and is left for Phase 6. This is the
clean abstraction that future provisioning will plug into.
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone
import re


SUPPORTED_KINDS = ["postgres", "mongodb", "supabase", "mysql", "sqlite"]


def validate_kind(kind: str) -> str:
    k = (kind or "").lower().strip()
    if k not in SUPPORTED_KINDS:
        raise ValueError(f"Unsupported db kind: {kind}. Supported: {', '.join(SUPPORTED_KINDS)}")
    return k


def mask_url(url: str) -> str:
    """Mask credentials in a DB URL for display."""
    if not url:
        return ""
    # postgres://user:password@host:port/db  → postgres://user:***@host:port/db
    return re.sub(r"(://[^:/@]+):([^@]+)@", r"\1:***@", url)


def schema_template(kind: str) -> str:
    """A minimal AI-generation hint for each db kind."""
    k = validate_kind(kind)
    if k == "postgres":
        return (
            "-- Postgres schema starter\n"
            "create table if not exists users (\n"
            "  id uuid primary key default gen_random_uuid(),\n"
            "  email text unique not null,\n"
            "  created_at timestamptz default now()\n"
            ");\n"
        )
    if k == "mongodb":
        return (
            '// MongoDB collection plan\n'
            '// db.users.createIndex({ email: 1 }, { unique: true })\n'
        )
    if k == "supabase":
        return (
            "-- Supabase / Postgres + RLS starter\n"
            "create table public.profiles (\n"
            "  id uuid primary key references auth.users(id) on delete cascade,\n"
            "  username text unique,\n"
            "  created_at timestamptz default now()\n"
            ");\n"
            "alter table public.profiles enable row level security;\n"
            "create policy \"public read\" on public.profiles for select using (true);\n"
        )
    if k == "mysql":
        return "create table users (id int auto_increment primary key, email varchar(255) unique not null);\n"
    return "-- sqlite schema starter\ncreate table users (id integer primary key, email text unique);\n"


def make_record(kind: str, name: str, url: str, notes: str = "") -> dict:
    return {
        "id": __import__("uuid").uuid4().hex[:12],
        "kind": validate_kind(kind),
        "name": (name or "default").strip()[:64],
        "url": url or "",
        "notes": (notes or "")[:500],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def public_view(record: dict) -> dict:
    """What we expose to the frontend (URL masked)."""
    return {
        "id": record["id"],
        "kind": record["kind"],
        "name": record["name"],
        "url_masked": mask_url(record.get("url", "")),
        "notes": record.get("notes", ""),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }
