"""Database registry + real provisioning.

GET /projects/{id}/databases
POST /projects/{id}/databases                  — register an existing URL
DELETE /projects/{id}/databases/{db_id}
GET /projects/{id}/databases/{db_id}/schema-template
GET /databases/providers                       — provisioning provider readiness
POST /projects/{id}/databases/provision        — REAL Neon/Supabase provisioning
POST /projects/{id}/databases/{db_id}/migrate  — run SQL via asyncpg
POST /projects/{id}/databases/{db_id}/test     — connection test
POST /projects/{id}/databases/{db_id}/generate-schema  — AI-generated SQL (no auto-run)
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import database_service, provisioning_service, audit_service
from services.ai_service import get_active_provider

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.databases")

router = APIRouter(prefix="/api", tags=["databases"])


# ---------- registry ----------
class DatabaseIn(BaseModel):
    kind: str
    name: str
    url: str
    notes: Optional[str] = ""


@router.get("/projects/{project_id}/databases")
async def list_databases(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id},
                                     {"_id": 0, "id": 1, "databases": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return [database_service.public_view(d) for d in (doc.get("databases") or [])]


@router.post("/projects/{project_id}/databases")
async def add_database(project_id: str, body: DatabaseIn,
                       _: str = Depends(verify_token)):
    try:
        rec = database_service.make_record(body.kind, body.name, body.url, body.notes or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    res = await db.projects.update_one(
        {"id": project_id},
        {"$push": {"databases": rec},
         "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    return database_service.public_view(rec)


@router.delete("/projects/{project_id}/databases/{db_id}")
async def remove_database(project_id: str, db_id: str,
                          _: str = Depends(verify_token)):
    res = await db.projects.update_one(
        {"id": project_id},
        {"$pull": {"databases": {"id": db_id}}},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Database connection not found")
    return {"ok": True}


@router.get("/projects/{project_id}/databases/{db_id}/schema-template")
async def database_schema_template(project_id: str, db_id: str,
                                   _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id},
                                     {"_id": 0, "id": 1, "databases": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    rec = next((d for d in (doc.get("databases") or []) if d["id"] == db_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")
    return {"kind": rec["kind"], "schema": database_service.schema_template(rec["kind"])}


# ---------- provisioning ----------
@router.get("/databases/providers")
async def databases_providers(_: str = Depends(verify_token)):
    return provisioning_service.providers_status()


class ProvisionIn(BaseModel):
    provider: str = Field(..., description="neon | supabase")
    name: str
    region: Optional[str] = None
    org_id: Optional[str] = None
    inject_env: bool = True
    env_key: str = "DATABASE_URL"


async def _inject_project_env(project_id: str, key: str, value: str) -> None:
    if not re.match(r"^[A-Z_][A-Z0-9_]*$", key):
        raise HTTPException(status_code=400, detail="env_key must be UPPER_SNAKE_CASE")
    now = datetime.now(timezone.utc).isoformat()
    record = {"key": key, "value": value, "scope": "runtime", "updated_at": now}
    res = await db.projects.update_one(
        {"id": project_id, "env_vars.key": key},
        {"$set": {"env_vars.$": record, "updated_at": now}},
    )
    if res.matched_count == 0:
        await db.projects.update_one(
            {"id": project_id},
            {"$push": {"env_vars": record}, "$set": {"updated_at": now}},
        )


@router.post("/projects/{project_id}/databases/provision")
async def provision_database(project_id: str, body: ProvisionIn,
                             _: str = Depends(verify_token)):
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0, "id": 1, "name": 1})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    provider = body.provider.lower().strip()
    name = (body.name or proj.get("name") or "nxt1-app").strip()[:48]

    try:
        if provider == "neon":
            region = body.region or provisioning_service.DEFAULT_NEON_REGION
            result = provisioning_service.provision_neon(name, region=region)
            kind = "postgres"
        elif provider == "supabase":
            region = body.region or provisioning_service.DEFAULT_SUPABASE_REGION
            result = provisioning_service.provision_supabase(name, region=region, org_id=body.org_id)
            kind = "supabase"
        elif provider == "atlas":
            region = body.region or "US_EAST_1"
            result = provisioning_service.provision_atlas(name, region=region)
            kind = "mongodb"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    except HTTPException:
        raise
    except RuntimeError as e:
        # Surfaces missing-key + 4xx upstream messages cleanly to the UI
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("provision failed")
        raise HTTPException(status_code=500, detail=f"Provisioning failed: {e}")

    rec = database_service.make_record(kind, name, result["url"],
                                       notes=f"provisioned · {provider} · {result['metadata'].get('region','')}")
    rec["provisioned"] = True
    rec["provider_meta"] = result["metadata"]
    await db.projects.update_one(
        {"id": project_id},
        {"$push": {"databases": rec},
         "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )

    injected = []
    if body.inject_env:
        await _inject_project_env(project_id, body.env_key, result["url"])
        injected.append(body.env_key)
        # For Supabase, also inject the public anon URL so the AI can wire the JS client.
        if provider == "supabase" and result["metadata"].get("anon_url"):
            await _inject_project_env(project_id, "SUPABASE_URL", result["metadata"]["anon_url"])
            injected.append("SUPABASE_URL")

    await audit_service.record(
        db, tool="db", action=f"provision-{provider}",
        target=f"{name} · {result['metadata'].get('region','')}",
        project_id=project_id,
        after={"db_id": rec["id"], "kind": kind, "env_injected": injected},
    )

    return {
        "ok": True,
        "database": database_service.public_view(rec),
        "provider_meta": result["metadata"],
        "connection_url": result["url"],  # surfaced ONCE; UI must save/reveal-and-go
        "env_injected": injected,
    }


def _resolve_db_record(project_doc: dict, db_id: str) -> dict:
    rec = next((d for d in (project_doc.get("databases") or []) if d.get("id") == db_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")
    return rec


class MigrateIn(BaseModel):
    sql: str
    label: Optional[str] = "manual migration"


@router.post("/projects/{project_id}/databases/{db_id}/migrate")
async def run_migration(project_id: str, db_id: str, body: MigrateIn,
                        _: str = Depends(verify_token)):
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0, "databases": 1})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    rec = _resolve_db_record(proj, db_id)
    if rec.get("kind") not in ("postgres", "supabase"):
        raise HTTPException(status_code=400, detail="Migrations supported on postgres/supabase only.")
    url = rec.get("url") or ""
    res = await provisioning_service.run_sql(url, body.sql)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "label": (body.label or "")[:80],
        "ok": res.get("ok", False),
        "result": res.get("result") or res.get("error", ""),
        "sql_preview": (body.sql or "")[:240],
    }
    await db.projects.update_one(
        {"id": project_id, "databases.id": db_id},
        {"$push": {"databases.$.migrations": entry}},
    )
    await audit_service.record(
        db, tool="db", action="migrate", target=f"{rec.get('name')} · {entry.get('label')}",
        project_id=project_id, status="ok" if entry["ok"] else "failed",
        after={"db_id": db_id, "ok": entry["ok"], "result": entry["result"][:200]},
    )
    return {"ok": res.get("ok", False), "result": entry}


@router.post("/projects/{project_id}/databases/{db_id}/test")
async def test_db(project_id: str, db_id: str, _: str = Depends(verify_token)):
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0, "databases": 1})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    rec = _resolve_db_record(proj, db_id)
    if rec.get("kind") not in ("postgres", "supabase"):
        return {"ok": False, "error": "Connection test supported on postgres/supabase only."}
    return await provisioning_service.test_connection(rec.get("url") or "")


class GenerateSchemaIn(BaseModel):
    prompt: str = Field(..., description="What the user wants the schema to support.")


@router.post("/projects/{project_id}/databases/{db_id}/generate-schema")
async def generate_schema(project_id: str, db_id: str, body: GenerateSchemaIn,
                          _: str = Depends(verify_token)):
    proj = await db.projects.find_one(
        {"id": project_id},
        {"_id": 0, "name": 1, "description": 1, "files": 1, "databases": 1},
    )
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    rec = _resolve_db_record(proj, db_id)
    kind = rec.get("kind", "postgres")

    # Compact context: project name + description + top 8 file paths
    file_paths = [f.get("path", "") for f in (proj.get("files") or [])][:8]
    sys_prompt = (
        "You are a senior database engineer. Generate a clean, idempotent "
        f"{kind} schema (using `CREATE TABLE IF NOT EXISTS`) plus indexes and "
        "row-level-security policies if Supabase. Output ONLY raw SQL — no "
        "markdown fences, no commentary, no `BEGIN`/`COMMIT`. Use lowercase "
        "snake_case identifiers. Prefer `uuid` PKs with `gen_random_uuid()`. "
        "Add `created_at timestamptz default now()` to every table."
    )
    user_prompt = (
        f"Project: {proj.get('name','(unnamed)')}\n"
        f"Description: {proj.get('description','')}\n"
        f"Existing files:\n- " + "\n- ".join(file_paths) + "\n\n"
        f"Schema requirement:\n{body.prompt.strip()}\n"
    )
    try:
        provider = get_active_provider("anthropic")
        text = await provider.generate(sys_prompt, user_prompt, session_id=f"db-schema-{db_id}")
    except Exception:
        # Fall back to whatever's active
        try:
            provider = get_active_provider()
            text = await provider.generate(sys_prompt, user_prompt, session_id=f"db-schema-{db_id}")
        except Exception as e2:
            raise HTTPException(status_code=502, detail=f"AI generation failed: {e2}")

    # Strip accidental markdown fences just in case.
    sql = text.strip()
    if sql.startswith("```"):
        sql = re.sub(r"^```[a-zA-Z]*\n", "", sql)
        sql = sql.rstrip("`").rstrip()
        if sql.endswith("```"):
            sql = sql[:-3].rstrip()
    return {"sql": sql, "kind": kind}
