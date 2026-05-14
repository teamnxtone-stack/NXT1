"""Custom domain routes (Phase 8 modular refactor)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.domain_service import (
    cf_check_ssl,
    cf_configured,
    cf_create_cname,
    cf_delete_record,
    cf_token_only,
    detect_domain_management,
    is_valid_hostname,
    new_domain_record,
    normalize_hostname,
    verify_dns,
)

from ._deps import db, verify_token

router = APIRouter(prefix="/api", tags=["domains"])


class DomainAdd(BaseModel):
    hostname: str


@router.get("/domains/detect")
async def domain_detect(host: str, _: str = Depends(verify_token)):
    """Detect whether NXT1 can manage DNS for `host` automatically."""
    h = normalize_hostname(host)
    if not is_valid_hostname(h):
        raise HTTPException(status_code=400, detail="Invalid hostname")
    return {"hostname": h, **detect_domain_management(h)}


@router.post("/projects/{project_id}/domains")
async def add_domain(project_id: str, body: DomainAdd,
                     _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    host = normalize_hostname(body.hostname)
    if not is_valid_hostname(host):
        raise HTTPException(status_code=400, detail="Invalid hostname")
    if any(d["hostname"] == host for d in doc.get("domains", []) or []):
        raise HTTPException(status_code=409, detail="Domain already added to this project")
    rec = new_domain_record(project_id, host, doc.get("deploy_slug"))
    if not doc.get("domains"):
        rec["primary"] = True

    detection = detect_domain_management(host) if cf_token_only() else None
    rec["managed"] = bool(detection and detection.get("managed"))
    rec["zone_id"] = (detection or {}).get("zone_id")
    rec["zone_name"] = (detection or {}).get("zone_name")

    if rec["managed"]:
        cf = cf_create_cname(host, zone_id=rec["zone_id"])
        if cf.get("ok"):
            rec["cf_dns_id"] = cf["record_id"]
            rec["status"] = "verified"
            ssl = cf_check_ssl(host, zone_id=rec["zone_id"])
            rec["ssl_status"] = ssl.get("status")
        else:
            rec["error"] = cf.get("error")
    elif cf_configured():
        # Backwards-compat: env-pinned zone fallback (legacy single-zone setup).
        cf = cf_create_cname(host)
        if cf.get("ok"):
            rec["cf_dns_id"] = cf["record_id"]
            rec["zone_id"] = cf.get("zone_id")
            rec["status"] = "verified"
            rec["managed"] = True
            ssl = cf_check_ssl(host, zone_id=rec["zone_id"])
            rec["ssl_status"] = ssl.get("status")
        else:
            rec["error"] = cf.get("error")

    await db.projects.update_one(
        {"id": project_id},
        {"$push": {"domains": rec},
         "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return rec


@router.get("/projects/{project_id}/domains")
async def list_domains(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "domains": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return doc.get("domains", []) or []


@router.delete("/projects/{project_id}/domains/{domain_id}")
async def remove_domain(project_id: str, domain_id: str,
                        _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "domains": 1})
    if doc:
        target = next((d for d in doc.get("domains", []) if d["id"] == domain_id), None)
        if target and target.get("cf_dns_id") and cf_token_only():
            cf_delete_record(target["cf_dns_id"], zone_id=target.get("zone_id"))
    res = await db.projects.update_one(
        {"id": project_id}, {"$pull": {"domains": {"id": domain_id}}},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Domain not found")
    return {"ok": True}


@router.post("/projects/{project_id}/domains/{domain_id}/verify")
async def domain_verify(project_id: str, domain_id: str,
                        _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "domains": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    target = next((d for d in doc.get("domains", []) if d["id"] == domain_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Domain not found")
    check = verify_dns(target["hostname"])
    new_status = "verified" if check.get("matches_target") else (
        "pending" if check.get("resolved") else "failed"
    )
    update = {
        "domains.$.status": new_status,
        "domains.$.last_checked_at": datetime.now(timezone.utc).isoformat(),
        "domains.$.error": check.get("error"),
        "domains.$.dns_check": check,
    }
    if new_status == "verified" and cf_token_only():
        ssl_check = cf_check_ssl(target["hostname"], zone_id=target.get("zone_id"))
        update["domains.$.ssl_status"] = ssl_check.get("status")
        if ssl_check.get("status") == "active":
            update["domains.$.status"] = "active"
            new_status = "active"
    await db.projects.update_one(
        {"id": project_id, "domains.id": domain_id},
        {"$set": update},
    )
    return {"status": new_status, "check": check, "ssl": update.get("domains.$.ssl_status")}


@router.post("/projects/{project_id}/domains/{domain_id}/primary")
async def domain_primary(project_id: str, domain_id: str,
                         _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "domains": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    domains = doc.get("domains", []) or []
    if not any(d["id"] == domain_id for d in domains):
        raise HTTPException(status_code=404, detail="Domain not found")
    for d in domains:
        d["primary"] = (d["id"] == domain_id)
    await db.projects.update_one({"id": project_id}, {"$set": {"domains": domains}})
    return {"ok": True}
