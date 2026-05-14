"""Audit log + rollback v2 routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from services import audit_service
from ._deps import db, verify_token

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _admin_only(sub: str = Depends(verify_token)) -> str:
    if sub != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return sub


@router.get("")
async def list_audit(
    limit: int = Query(50, ge=1, le=500),
    project_id: Optional[str] = None,
    tool: Optional[str] = None,
    _: str = Depends(_admin_only),
):
    items = await audit_service.list_recent(db, limit=limit, project_id=project_id, tool=tool)
    return {"items": items, "count": len(items)}


@router.get("/{audit_id}")
async def get_audit(audit_id: str, _: str = Depends(_admin_only)):
    item = await audit_service.get(db, audit_id)
    if not item:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    return item


@router.post("/{audit_id}/rollback")
async def rollback_audit(audit_id: str, _: str = Depends(_admin_only)):
    """Replay an audit entry's `before` state.

    Currently supports rollback for `site-editor` (delegates to the existing
    /api/site-editor/rollback) — other tools surface the snapshot back to the
    caller so the operator can manually reverse them. Plumbing for fully
    automated rollback across every tool will land in v3.
    """
    item = await audit_service.get(db, audit_id)
    if not item:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    if item.get("rolled_back"):
        raise HTTPException(status_code=409, detail="Already rolled back")
    if item.get("tool") == "site-editor" and (item.get("details") or {}).get("edit_id"):
        # Defer to site_editor.rollback to keep file-state authoritative.
        from .site_editor import _do_rollback  # type: ignore
        result = await _do_rollback((item["details"] or {})["edit_id"])
        await audit_service.mark_rolled_back(db, audit_id)
        return {"ok": True, "result": result, "via": "site-editor"}

    # Generic rollback — surface the previous state for manual re-application.
    return {
        "ok": False,
        "reason": (
            f"Automated rollback for tool={item.get('tool')!r} action={item.get('action')!r} "
            "is not wired yet. The before-snapshot is included so you can revert manually."
        ),
        "before": item.get("before"),
        "after": item.get("after"),
    }
