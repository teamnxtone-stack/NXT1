"""Public access-request inbox (Phase 8 / branding rollout).

Anyone can POST a request via the public landing page; admin-only endpoints
list/delete entries. Stored in the `access_requests` collection.
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ._deps import db, verify_token

router = APIRouter(prefix="/api", tags=["access"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccessRequestIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: str = Field(..., min_length=3, max_length=200)
    company: Optional[str] = ""
    project_type: Optional[str] = ""  # "app" | "website" | "platform" | "other"
    description: str = Field(..., min_length=4, max_length=2000)
    budget: Optional[str] = ""
    timeline: Optional[str] = ""


class AccessRequestPatch(BaseModel):
    status: Optional[str] = None  # "new" | "contacted" | "closed"
    notes: Optional[str] = None


VALID_STATUSES = {"new", "contacted", "closed"}


@router.post("/access/request")
async def submit_access_request(body: AccessRequestIn):
    if not EMAIL_RE.match(body.email):
        raise HTTPException(status_code=400, detail="Invalid email")
    rec = {
        "id": uuid.uuid4().hex[:14],
        "name": body.name.strip()[:120],
        "email": body.email.strip().lower()[:200],
        "company": (body.company or "").strip()[:160],
        "project_type": (body.project_type or "").strip()[:40],
        "description": body.description.strip()[:2000],
        "budget": (body.budget or "").strip()[:80],
        "timeline": (body.timeline or "").strip()[:80],
        "status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.access_requests.insert_one(dict(rec))
    return {"ok": True, "id": rec["id"]}


@router.get("/access/requests")
async def list_access_requests(_: str = Depends(verify_token)):
    docs = (
        await db.access_requests.find({}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(500)
    )
    return docs


@router.delete("/access/requests/{req_id}")
async def delete_access_request(req_id: str, _: str = Depends(verify_token)):
    res = await db.access_requests.delete_one({"id": req_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"ok": True}


@router.patch("/access/requests/{req_id}")
async def update_access_request(req_id: str, body: AccessRequestPatch,
                                _: str = Depends(verify_token)):
    update: dict = {}
    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=400,
                                detail=f"status must be one of {VALID_STATUSES}")
        update["status"] = body.status
    if body.notes is not None:
        update["notes"] = body.notes[:2000]
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.access_requests.update_one({"id": req_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"ok": True, **update}
