"""Tool-contract audit log + persistent rollback memory v2.

Every meaningful side-effecting action — file edit, runtime restart, deploy,
env mutation, secret update, db provision/migrate, brand change, GitHub push
— is logged to a single `audit_log` collection so we have:

  - a chronological audit trail across every contract/agent invocation
  - a single rollback target per record (when applicable)
  - a forward path to containerised execution: each entry already carries
    actor + tool + target + before/after snapshots

Public surface:
    record(tool, action, target, *, actor, status, before, after, details)
    list_recent(limit, project_id, tool)
    rollback(audit_id) -> dict          # plumbing only — replays before-state
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("nxt1.audit")

MAX_PAYLOAD_CHARS = 12_000  # truncate snapshots so the collection stays light


def _trim(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        try:
            import json
            s = json.dumps(value, default=str)
        except Exception:
            s = str(value)
    else:
        s = str(value)
    if len(s) > MAX_PAYLOAD_CHARS:
        return s[:MAX_PAYLOAD_CHARS] + f"… [+{len(s) - MAX_PAYLOAD_CHARS} chars trimmed]"
    return s


async def record(
    db,
    *,
    tool: str,
    action: str,
    target: str,
    actor: str = "admin",
    project_id: Optional[str] = None,
    status: str = "ok",
    before: Any = None,
    after: Any = None,
    details: Optional[dict] = None,
) -> dict:
    """Insert one audit entry. Best-effort — never raises into the caller."""
    try:
        entry = {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool[:64],          # site-editor | deploy | env | secrets | db | runtime | brand | github
            "action": action[:64],      # create | update | delete | run | rollback | etc.
            "target": (target or "")[:240],
            "actor": (actor or "anon")[:64],
            "project_id": project_id,
            "status": status[:32],      # ok | failed | partial | rolled_back
            "before": _trim(before),
            "after": _trim(after),
            "details": details or {},
            "host": os.environ.get("BACKEND_PUBLIC_ORIGIN", ""),
            "rolled_back": False,
        }
        await db.audit_log.insert_one(dict(entry))
        return entry
    except Exception as e:
        # Audit must NOT block the original operation
        logger.warning(f"audit insert failed (tool={tool}, action={action}): {e}")
        return {}


async def list_recent(db, *, limit: int = 50, project_id: Optional[str] = None,
                      tool: Optional[str] = None) -> list:
    q: dict = {}
    if project_id:
        q["project_id"] = project_id
    if tool:
        q["tool"] = tool
    cursor = db.audit_log.find(q, {"_id": 0}).sort("ts", -1).limit(max(1, min(limit, 500)))
    return [doc async for doc in cursor]


async def get(db, audit_id: str) -> Optional[dict]:
    return await db.audit_log.find_one({"id": audit_id}, {"_id": 0})


async def mark_rolled_back(db, audit_id: str) -> None:
    await db.audit_log.update_one(
        {"id": audit_id},
        {"$set": {"rolled_back": True, "rolled_back_at": datetime.now(timezone.utc).isoformat()}},
    )
