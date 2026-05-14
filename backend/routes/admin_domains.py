"""Admin-level domains for NXT1 itself.

Lets the operator point any domain at the NXT1 platform (not a per-project
deployment). When CF-managed, NXT1 auto-creates the CNAME. Otherwise it
surfaces manual DNS records.

Routes:
    GET    /api/admin/domains
    POST   /api/admin/domains            body: {hostname, role?}
    DELETE /api/admin/domains/{id}
    POST   /api/admin/domains/{id}/verify
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services import audit_service
from services.domain_service import (
    cf_check_ssl,
    cf_create_cname,
    cf_delete_record,
    cf_token_only,
    detect_domain_management,
    dns_instructions,
    is_valid_hostname,
    normalize_hostname,
    verify_dns,
)

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.admin.domains")
router = APIRouter(prefix="/api/admin/domains", tags=["admin"])


def _admin_only(sub: str = Depends(verify_token)) -> str:
    if sub != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return sub


class AdminDomainIn(BaseModel):
    hostname: str
    role: Optional[str] = "primary"  # primary | app | api | preview | other


def _public_view(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k not in ("_id",)}


@router.get("")
async def list_admin_domains(_: str = Depends(_admin_only)):
    cursor = db.admin_domains.find({}, {"_id": 0}).sort("created_at", -1)
    items = [doc async for doc in cursor]
    return {"items": items, "count": len(items)}


@router.post("")
async def add_admin_domain(body: AdminDomainIn, _: str = Depends(_admin_only)):
    host = normalize_hostname(body.hostname)
    if not is_valid_hostname(host):
        raise HTTPException(status_code=400, detail="Invalid hostname")
    existing = await db.admin_domains.find_one({"hostname": host}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="Already added")

    detection = detect_domain_management(host) if cf_token_only() else {
        "managed": False, "provider": None, "zone_id": None, "zone_name": None,
        "instructions": dns_instructions(host, slug=None),
    }
    rec = {
        "id": str(uuid.uuid4()),
        "hostname": host,
        "role": (body.role or "primary")[:24],
        "managed": bool(detection.get("managed")),
        "zone_id": detection.get("zone_id"),
        "zone_name": detection.get("zone_name"),
        "instructions": detection.get("instructions"),
        "status": "pending",
        "ssl_status": "unknown",
        "cf_dns_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if rec["managed"]:
        cf = cf_create_cname(host, zone_id=rec["zone_id"])
        if cf.get("ok"):
            rec["cf_dns_id"] = cf["record_id"]
            rec["status"] = "verified"
            ssl = cf_check_ssl(host, zone_id=rec["zone_id"])
            rec["ssl_status"] = ssl.get("status", "unknown")
        else:
            rec["error"] = cf.get("error")
    await db.admin_domains.insert_one(dict(rec))
    await audit_service.record(
        db, tool="domains", action="add", target=host,
        after={"id": rec["id"], "managed": rec["managed"], "status": rec["status"]},
    )
    return _public_view(rec)


@router.delete("/{domain_id}")
async def delete_admin_domain(domain_id: str, _: str = Depends(_admin_only)):
    rec = await db.admin_domains.find_one({"id": domain_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Domain not found")
    if rec.get("cf_dns_id") and cf_token_only():
        cf_delete_record(rec["cf_dns_id"], zone_id=rec.get("zone_id"))
    await db.admin_domains.delete_one({"id": domain_id})
    await audit_service.record(
        db, tool="domains", action="delete", target=rec.get("hostname", ""),
        before={"id": domain_id, "managed": rec.get("managed")},
    )
    return {"ok": True}


@router.post("/{domain_id}/verify")
async def verify_admin_domain(domain_id: str, _: str = Depends(_admin_only)):
    rec = await db.admin_domains.find_one({"id": domain_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Domain not found")
    status = verify_dns(rec["hostname"])
    new_status = "verified" if status.get("matches_target") else "pending"
    ssl_status = "unknown"
    if new_status == "verified" and cf_token_only():
        ssl_status = (cf_check_ssl(rec["hostname"], zone_id=rec.get("zone_id"))
                      or {}).get("status", "unknown")
    await db.admin_domains.update_one(
        {"id": domain_id},
        {"$set": {
            "status": new_status,
            "ssl_status": ssl_status,
            "verify_detail": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"ok": True, "status": new_status, "ssl_status": ssl_status, "detail": status}
