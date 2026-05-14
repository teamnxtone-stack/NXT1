"""Hosting routes (Track C) — Caddy config + per-user Cloudflare connect."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.domain_service import deploy_target
from services.hosting import caddy_service, cloudflare_user as cfu

from ._deps import db, verify_token

router = APIRouter(prefix="/api/hosting", tags=["hosting"])


# ---------- Caddy ----------
class CaddyGenIn(BaseModel):
    domains: List[str]
    upstream: Optional[str] = None
    email: Optional[str] = None
    include_hsts: bool = True


@router.post("/caddy/generate")
async def caddy_generate(body: CaddyGenIn, _: str = Depends(verify_token)):
    upstream = body.upstream or deploy_target()
    caddyfile = caddy_service.generate_caddyfile(
        body.domains, upstream, email=body.email, include_hsts=body.include_hsts,
    )
    return {
        "caddyfile": caddyfile,
        "compose_snippet": caddy_service.generate_compose_snippet(),
        "upstream": upstream,
        "domains": [d.strip().lower() for d in body.domains if d],
    }


@router.get("/caddy/install-guide")
async def caddy_install_guide(domain: str, _: str = Depends(verify_token)):
    return caddy_service.describe_install_steps([domain], deploy_target())


# ---------- Cloudflare (per-user token) ----------
class CFConnectIn(BaseModel):
    token: str


@router.post("/cloudflare/connect")
async def cf_connect(body: CFConnectIn, user_id: str = Depends(verify_token)):
    token = (body.token or "").strip()
    if not token or len(token) < 20:
        raise HTTPException(status_code=400, detail="Cloudflare token looks invalid")
    verify = cfu.verify_token_with_cloudflare(token)
    if not verify.get("ok"):
        raise HTTPException(status_code=400, detail=verify.get("error", "Token verify failed"))
    await cfu.save_user_cf_token(db, user_id, token, verify)
    zones = cfu.list_zones(token)
    return {
        "ok": True,
        "status": verify.get("status"),
        "expires_on": verify.get("expires_on"),
        "zones": zones.get("zones") if zones.get("ok") else [],
    }


@router.get("/cloudflare/status")
async def cf_status(user_id: str = Depends(verify_token)):
    doc = await db.users.find_one({"id": user_id}, {"_id": 0, "cloudflare": 1})
    cf = (doc or {}).get("cloudflare") or {}
    return {
        "connected": bool(cf.get("connected")),
        "status": cf.get("status"),
        "expires_on": cf.get("expires_on"),
        "verified_at": cf.get("verified_at"),
    }


@router.get("/cloudflare/zones")
async def cf_zones(user_id: str = Depends(verify_token)):
    token = await cfu.get_user_cf_token(db, user_id)
    if not token:
        raise HTTPException(status_code=400, detail="Cloudflare not connected for this user")
    result = cfu.list_zones(token)
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "CF list zones failed"))
    return result


class CFAttachIn(BaseModel):
    hostname: str
    zone_id: str
    target: Optional[str] = None


@router.post("/cloudflare/dns")
async def cf_dns_attach(body: CFAttachIn, user_id: str = Depends(verify_token)):
    token = await cfu.get_user_cf_token(db, user_id)
    if not token:
        raise HTTPException(status_code=400, detail="Cloudflare not connected for this user")
    target = body.target or deploy_target()
    result = cfu.create_dns_record(token, body.zone_id, body.hostname, target)
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "CF DNS create failed"))
    return {"ok": True, "record_id": result["record_id"], "hostname": body.hostname, "target": target}


@router.post("/cloudflare/disconnect")
async def cf_disconnect(user_id: str = Depends(verify_token)):
    return await cfu.disconnect_user_cf(db, user_id)


# ---------- Readiness ----------
@router.get("/readiness")
async def hosting_readiness(user_id: str = Depends(verify_token)):
    """Aggregate readiness checks for hosting: domain + SSL + cloudflare + caddy."""
    doc = await db.users.find_one({"id": user_id}, {"_id": 0, "cloudflare": 1})
    cf = (doc or {}).get("cloudflare") or {}
    return {
        "upstream": deploy_target(),
        "cloudflare_user_connected": bool(cf.get("connected")),
        "caddy_install_available": True,
        "checklist": [
            {"key": "upstream", "label": "NXT1 upstream resolved",
             "ok": bool(deploy_target())},
            {"key": "cf_connected", "label": "User Cloudflare token saved",
             "ok": bool(cf.get("connected"))},
            {"key": "caddy_guide", "label": "Caddyfile generator available",
             "ok": True},
        ],
    }
