"""Project env-vars (Phase 8 modular refactor)."""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from services import audit_service

from ._deps import db, verify_token

router = APIRouter(prefix="/api", tags=["env"])


class EnvVarItem(BaseModel):
    key: str
    value: str
    scope: Optional[str] = "runtime"  # "runtime" | "all"


def _mask_value(v: str) -> str:
    if not v:
        return ""
    if len(v) <= 4:
        return "•" * len(v)
    return v[:2] + "•" * (max(len(v) - 4, 4)) + v[-2:]


@router.get("/projects/{project_id}/env")
async def list_env(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "env_vars": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    items = doc.get("env_vars", []) or []
    return [
        {"key": e["key"], "value_masked": _mask_value(e.get("value", "")),
         "scope": e.get("scope", "runtime"), "updated_at": e.get("updated_at")}
        for e in items
    ]


@router.post("/projects/{project_id}/env")
async def upsert_env(project_id: str, body: EnvVarItem,
                     sub: str = Depends(verify_token)):
    if not re.match(r"^[A-Z_][A-Z0-9_]*$", body.key):
        raise HTTPException(status_code=400,
                            detail="Key must be UPPER_SNAKE_CASE (A-Z, 0-9, _)")
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "key": body.key,
        "value": body.value,
        "scope": body.scope or "runtime",
        "updated_at": now,
    }
    res = await db.projects.update_one(
        {"id": project_id, "env_vars.key": body.key},
        {"$set": {"env_vars.$": record, "updated_at": now}},
    )
    if res.matched_count == 0:
        await db.projects.update_one(
            {"id": project_id},
            {"$push": {"env_vars": record}, "$set": {"updated_at": now}},
        )
    await audit_service.record(
        db, tool="env", action="upsert", target=body.key, project_id=project_id,
        actor=sub, after={"key": body.key, "scope": record["scope"]},
    )
    return {"ok": True, "key": body.key, "value_masked": _mask_value(body.value)}


@router.delete("/projects/{project_id}/env/{key}")
async def delete_env(project_id: str, key: str,
                     sub: str = Depends(verify_token)):
    res = await db.projects.update_one(
        {"id": project_id}, {"$pull": {"env_vars": {"key": key}}},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Env var not found")
    await audit_service.record(
        db, tool="env", action="delete", target=key, project_id=project_id, actor=sub,
    )
    return {"ok": True}
