"""Persistent background job system.

Every long-running task (build / deploy / import / push) is recorded as a job
so the user can leave the thread, refresh, or come back hours later and still
see the result (or current progress).

Collection: `jobs`
Document shape:
    {
        id: str (uuid),
        project_id: str | None,        # scope; None for system-level jobs
        kind: "build" | "deploy" | "import" | "github-push" | "migration" | ...,
        status: "queued" | "running" | "completed" | "failed" | "cancelled",
        progress: float (0..1),
        phase: str | None,             # latest phase label
        logs: [{ts, level, msg}, ...]  # bounded buffer (last 200)
        result: dict | None,           # final payload (preview_url, deploy_url, etc.)
        error: str | None,
        created_at, updated_at, completed_at: ISO timestamps,
        actor: "admin" | user_id,
    }
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

logger = logging.getLogger("nxt1.jobs")

MAX_LOG_LINES = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def start(db, *, kind: str, project_id: Optional[str],
                actor: str = "admin", initial_logs: Optional[list] = None) -> dict:
    rec = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "kind": kind,
        "status": "running",
        "progress": 0.0,
        "phase": "queued",
        "logs": list(initial_logs or []),
        "result": None,
        "error": None,
        "actor": actor,
        "created_at": _now(),
        "updated_at": _now(),
        "completed_at": None,
    }
    await db.jobs.insert_one(dict(rec))
    return rec


async def append_log(db, job_id: str, level: str, msg: str,
                     phase: Optional[str] = None,
                     progress: Optional[float] = None) -> None:
    """Append a single log line (bounded). Never raises into caller."""
    if not job_id:
        return
    try:
        entry = {"ts": _now(), "level": (level or "info")[:16], "msg": (msg or "")[:600]}
        set_doc: dict = {"updated_at": entry["ts"]}
        if phase is not None:
            set_doc["phase"] = phase[:64]
        if progress is not None:
            set_doc["progress"] = max(0.0, min(1.0, float(progress)))
        await db.jobs.update_one(
            {"id": job_id},
            {
                "$push": {"logs": {"$each": [entry], "$slice": -MAX_LOG_LINES}},
                "$set": set_doc,
            },
        )
    except Exception as e:
        logger.warning(f"job log append failed: {e}")


async def complete(db, job_id: str, *, status: str, result: Optional[Any] = None,
                   error: Optional[str] = None) -> None:
    if not job_id:
        return
    try:
        await db.jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": status,
                "result": result,
                "error": error,
                "progress": 1.0 if status == "completed" else None,
                "phase": status,
                "completed_at": _now(),
                "updated_at": _now(),
            }},
        )
    except Exception as e:
        logger.warning(f"job complete failed: {e}")


async def fail(db, job_id: str, message: str, partial_result: Optional[dict] = None) -> None:
    await complete(db, job_id, status="failed", error=message[:500], result=partial_result)


async def cancel(db, job_id: str) -> bool:
    res = await db.jobs.update_one(
        {"id": job_id, "status": {"$in": ["queued", "running"]}},
        {"$set": {"status": "cancelled", "completed_at": _now(), "updated_at": _now()}},
    )
    return res.modified_count > 0


async def list_for_project(db, project_id: str, *, limit: int = 25,
                           include_completed: bool = True) -> List[dict]:
    q: dict = {"project_id": project_id}
    if not include_completed:
        q["status"] = {"$in": ["queued", "running"]}
    cur = db.jobs.find(q, {"_id": 0}).sort("created_at", -1).limit(max(1, min(limit, 200)))
    return [doc async for doc in cur]


async def list_active(db, project_id: Optional[str] = None) -> List[dict]:
    q: dict = {"status": {"$in": ["queued", "running"]}}
    if project_id:
        q["project_id"] = project_id
    cur = db.jobs.find(q, {"_id": 0}).sort("created_at", -1).limit(50)
    return [doc async for doc in cur]


async def get(db, job_id: str) -> Optional[dict]:
    return await db.jobs.find_one({"id": job_id}, {"_id": 0})
