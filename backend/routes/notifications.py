"""Notification Center routes — durable, DB-backed agent/system notices.

Replaces the legacy `agentActivity.js` global watcher that fired random
bottom toasts. Notifications are produced server-side by:
  - workflow_service (build complete, deploy ready, repair-loop exhausted)
  - social scheduler (post auto-published / failed)
  - social_content_service (calendar generated)
  - import_service (URL clone complete)
  - agent_threads (any thread terminal status)

Each notification has: id, user_id, kind, title, body, link, read, created_at.
The frontend bell polls /list?unread=true every 30s and shows the unread count.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.notifications")

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Notification(BaseModel):
    id: str
    user_id: str
    kind: str  # build_complete | deploy_ready | social_posted | social_failed | url_imported | agent_done | system
    title: str
    body: str = ""
    link: Optional[str] = None
    read: bool = False
    created_at: str


async def emit(
    user_id: str,
    *,
    kind: str,
    title: str,
    body: str = "",
    link: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
) -> dict:
    """Server-side helper. Other services call this to drop a notification."""
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "kind": kind,
        "title": title[:200],
        "body": body[:600],
        "link": link,
        "meta": meta or {},
        "read": False,
        "created_at": _now(),
    }
    try:
        await db.notifications.insert_one(doc)
    except Exception as e:
        logger.warning(f"notification emit failed: {e}")
    doc.pop("_id", None)
    return doc


@router.get("/list")
async def list_notifications(
    user_id: str = Depends(verify_token),
    unread: bool = False,
    limit: int = 50,
):
    q: dict = {"user_id": user_id}
    if unread:
        q["read"] = False
    cur = db.notifications.find(q, {"_id": 0}).sort("created_at", -1).limit(min(limit, 200))
    items = await cur.to_list(length=None)
    unread_count = await db.notifications.count_documents({"user_id": user_id, "read": False})
    return {"items": items, "unread": unread_count}


@router.post("/{notif_id}/read")
async def mark_read(notif_id: str, user_id: str = Depends(verify_token)):
    res = await db.notifications.update_one(
        {"id": notif_id, "user_id": user_id},
        {"$set": {"read": True, "read_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(user_id: str = Depends(verify_token)):
    res = await db.notifications.update_many(
        {"user_id": user_id, "read": False},
        {"$set": {"read": True, "read_at": _now()}},
    )
    return {"ok": True, "marked": res.modified_count}


@router.delete("/{notif_id}")
async def delete_notification(notif_id: str, user_id: str = Depends(verify_token)):
    res = await db.notifications.delete_one({"id": notif_id, "user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}
