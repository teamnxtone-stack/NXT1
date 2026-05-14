"""Custom-domain management for NXT1.

Active:
  Manual DNS instructions + verification by DNS resolution.
  CloudflareDomainProvider — real Cloudflare DNS API (requires CLOUDFLARE_API_TOKEN + CLOUDFLARE_ZONE_ID).
"""
import os
import re
import socket
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional

import requests

logger = logging.getLogger("nxt1.domain")

HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)([a-zA-Z0-9](-?[a-zA-Z0-9]){0,62}\.)+[a-zA-Z]{2,63}$")
DOMAIN_STATUS = ("pending", "verified", "active", "failed")
CF_API = "https://api.cloudflare.com/client/v4"


def normalize_hostname(host: str) -> str:
    h = (host or "").strip().lower()
    h = re.sub(r"^https?://", "", h)
    return h.split("/")[0]


def is_valid_hostname(host: str) -> bool:
    return bool(HOSTNAME_RE.match(host or ""))


def deploy_target() -> str:
    return os.environ.get("DEPLOY_HOST", "").strip() or "deploy.nxt1.app"


def cf_configured() -> bool:
    return bool(
        os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
        and os.environ.get("CLOUDFLARE_ZONE_ID", "").strip()
    )


def cf_token_only() -> bool:
    """Token is set but no fixed zone — we can still auto-detect zones per host."""
    return bool(os.environ.get("CLOUDFLARE_API_TOKEN", "").strip())


def _cf_apex(host: str) -> str:
    """Return the apex (last two labels) for any subdomain. Best-effort —
    common ccTLDs like co.uk are NOT specially handled (rare for our use)."""
    parts = (host or "").lower().strip().split(".")
    if len(parts) <= 2:
        return ".".join(parts)
    return ".".join(parts[-2:])


def cf_lookup_zone_for(host: str) -> Optional[dict]:
    """Find the Cloudflare zone that owns `host` via the CF API.

    Returns the zone dict ({id, name, status, ...}) or None if not found
    (host's apex isn't on the configured CF account).
    """
    if not cf_token_only():
        return None
    apex = _cf_apex(host)
    try:
        r = requests.get(
            f"{CF_API}/zones",
            params={"name": apex, "status": "active"},
            headers=_cf_headers(),
            timeout=15,
        )
        if r.status_code >= 400:
            return None
        data = r.json()
        if not data.get("success"):
            return None
        zones = data.get("result") or []
        return zones[0] if zones else None
    except Exception:
        return None


def detect_domain_management(host: str) -> dict:
    """Auto-detect whether NXT1 can manage DNS for `host`.

    Returns: {
        managed: bool,                 # True iff CF zone exists for this apex
        provider: "cloudflare"|None,
        zone_id: str|None,             # the discovered (or env-pinned) zone
        zone_name: str|None,
        instructions: list,            # manual records to surface when not managed
    }
    """
    instructions = dns_instructions(host, slug=None)
    if not cf_token_only():
        return {"managed": False, "provider": None, "zone_id": None,
                "zone_name": None, "instructions": instructions}

    # Prefer per-host lookup (so any domain on the user's CF account works),
    # but accept the env-pinned zone as a hint when it matches the apex.
    pinned = (os.environ.get("CLOUDFLARE_ZONE_ID") or "").strip()
    zone = cf_lookup_zone_for(host)
    if zone:
        return {"managed": True, "provider": "cloudflare", "zone_id": zone["id"],
                "zone_name": zone.get("name"), "instructions": instructions,
                "pinned": pinned == zone["id"]}
    return {"managed": False, "provider": None, "zone_id": None,
            "zone_name": None, "instructions": instructions}


def dns_instructions(hostname: str, slug: Optional[str]) -> List[dict]:
    target = deploy_target()
    is_apex = hostname.count(".") == 1
    instructions = []
    if is_apex:
        instructions.append({"type": "ALIAS / ANAME", "name": "@", "value": target,
                             "note": "If your DNS provider doesn't support ALIAS/ANAME on apex, use the A record below."})
        instructions.append({"type": "A", "name": "@", "value": "76.76.21.21",
                             "note": "Fallback A record."})
    instructions.append({"type": "CNAME", "name": "www" if is_apex else hostname.split(".", 1)[0],
                         "value": target, "note": "Primary record routing this hostname to NXT1."})
    if slug:
        instructions.append({"type": "TXT", "name": f"_nxt1-verification.{hostname}",
                             "value": f"nxt1-slug={slug}",
                             "note": "Optional verification record."})
    return instructions


def new_domain_record(project_id: str, hostname: str, slug: Optional[str]) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "hostname": hostname,
        "status": "pending",
        "primary": False,
        "dns_records": dns_instructions(hostname, slug),
        "last_checked_at": None,
        "error": None,
        "cf_dns_id": None,
        "ssl_status": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def verify_dns(hostname: str) -> dict:
    target = deploy_target()
    result: dict = {"resolved": False, "ips": [], "cname": None, "matches_target": False, "error": None}
    try:
        infos = socket.getaddrinfo(hostname, None)
        ips = sorted({i[4][0] for i in infos})
        result["ips"] = ips
        result["resolved"] = bool(ips)
        try:
            target_ips = sorted({i[4][0] for i in socket.getaddrinfo(target, None)})
            result["cname"] = target if set(ips) & set(target_ips) else None
            result["matches_target"] = bool(set(ips) & set(target_ips))
        except Exception as e:  # noqa: BLE001
            result["error"] = f"target resolve failed: {e}"
    except Exception as e:  # noqa: BLE001
        result["error"] = f"resolve failed: {e}"
    return result


# ---------- Cloudflare API automation ----------
def _cf_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ.get('CLOUDFLARE_API_TOKEN', '').strip()}",
        "Content-Type": "application/json",
    }


def cf_create_cname(hostname: str, zone_id: Optional[str] = None) -> dict:
    """Create or upsert a CNAME record in the Cloudflare zone that owns
    `hostname`. If `zone_id` isn't provided, auto-detect it via cf_lookup_zone_for.
    Returns: { ok, record_id, zone_id, zone_name, error? }
    """
    if not cf_token_only():
        return {"ok": False, "error": "Cloudflare not configured (CLOUDFLARE_API_TOKEN missing)."}
    if not zone_id:
        env_zone = (os.environ.get("CLOUDFLARE_ZONE_ID") or "").strip()
        zone = cf_lookup_zone_for(hostname)
        if zone:
            zone_id = zone["id"]
        elif env_zone:
            zone_id = env_zone
        else:
            return {"ok": False,
                    "error": f"No Cloudflare zone found for {hostname}. Add the apex to your CF account or fall back to manual DNS."}
    target = deploy_target()
    body = {
        "type": "CNAME",
        "name": hostname,
        "content": target,
        "ttl": 1,  # auto
        "proxied": True,
    }
    try:
        r = requests.post(f"{CF_API}/zones/{zone_id}/dns_records",
                          headers=_cf_headers(), json=body, timeout=20)
        if r.status_code >= 400:
            return {"ok": False, "error": f"CF API {r.status_code}: {r.text[:200]}",
                    "zone_id": zone_id}
        data = r.json()
        if not data.get("success"):
            return {"ok": False, "error": str(data.get("errors"))[:200],
                    "zone_id": zone_id}
        return {"ok": True, "record_id": data["result"]["id"], "zone_id": zone_id}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def cf_delete_record(record_id: str, zone_id: Optional[str] = None) -> dict:
    if not cf_token_only() or not record_id:
        return {"ok": False, "error": "not configured"}
    zone = zone_id or (os.environ.get("CLOUDFLARE_ZONE_ID") or "").strip()
    if not zone:
        return {"ok": False, "error": "zone_id required"}
    try:
        r = requests.delete(f"{CF_API}/zones/{zone}/dns_records/{record_id}",
                            headers=_cf_headers(), timeout=20)
        return {"ok": r.status_code < 400, "status": r.status_code}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def cf_check_ssl(hostname: str, zone_id: Optional[str] = None) -> dict:
    """Best-effort SSL status check via CF universal SSL endpoint."""
    if not cf_token_only():
        return {"status": "unknown", "error": "not configured"}
    zone = zone_id or (os.environ.get("CLOUDFLARE_ZONE_ID") or "").strip()
    if not zone:
        return {"status": "unknown", "error": "zone_id required"}
    try:
        r = requests.get(f"{CF_API}/zones/{zone}/ssl/universal/settings",
                         headers=_cf_headers(), timeout=15)
        if r.status_code >= 400:
            return {"status": "unknown", "error": f"{r.status_code}"}
        data = r.json()
        return {"status": "active" if data.get("result", {}).get("enabled") else "inactive"}
    except Exception as e:  # noqa: BLE001
        return {"status": "unknown", "error": str(e)}



# ─── Phase F — Vercel + Coolify auto-domain attachment ──────────────────
# Vercel: official REST endpoints
#   POST /v10/projects/{idOrName}/domains       attach domain
#   GET  /v6/domains/{domain}/config            verify config / get DNS instructions
#
# Coolify: official REST endpoint (Coolify v4+)
#   POST /api/v1/applications/{uuid}/domains    attach domain to a Coolify app
#
# Caddy: no API needed — auto-HTTPS via on-demand TLS picks up new hosts
# automatically when its `auto_https` + `on_demand_tls` are enabled. We
# expose a no-op success here so the UI flow stays consistent.

VERCEL_API = "https://api.vercel.com"
COOLIFY_API_DEFAULT = "https://app.coolify.io"


def vercel_configured() -> bool:
    return bool(os.environ.get("VERCEL_TOKEN", "").strip())


def _vercel_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['VERCEL_TOKEN'].strip()}",
        "Content-Type": "application/json",
    }


def vercel_attach_domain(project_name: str, hostname: str) -> dict:
    """Attach a domain to a Vercel project. Returns {ok, dns_instructions?, error?}."""
    if not vercel_configured():
        return {"ok": False, "error": "VERCEL_TOKEN not set"}
    try:
        r = requests.post(
            f"{VERCEL_API}/v10/projects/{project_name}/domains",
            headers=_vercel_headers(),
            json={"name": hostname},
            timeout=15,
        )
        if r.status_code >= 400:
            try:
                err = r.json().get("error", {}).get("message")
            except Exception:
                err = r.text[:200]
            # 409 = already exists; treat as success
            if r.status_code == 409:
                return {"ok": True, "attached": True, "note": "already attached"}
            return {"ok": False, "error": f"{r.status_code}: {err}"}
        data = r.json()
        # Pull DNS instructions for manual DNS users
        cfg = vercel_domain_config(hostname)
        return {
            "ok": True,
            "attached": True,
            "domain": data.get("name"),
            "verified": data.get("verified", False),
            "dns_instructions": cfg,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def vercel_domain_config(hostname: str) -> dict:
    """Pull DNS instructions for a Vercel-managed domain."""
    if not vercel_configured():
        return {"error": "VERCEL_TOKEN not set"}
    try:
        r = requests.get(
            f"{VERCEL_API}/v6/domains/{hostname}/config",
            headers=_vercel_headers(),
            timeout=12,
        )
        if r.status_code >= 400:
            return {"error": f"{r.status_code}: {r.text[:200]}"}
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def vercel_remove_domain(project_name: str, hostname: str) -> dict:
    if not vercel_configured():
        return {"ok": False, "error": "VERCEL_TOKEN not set"}
    try:
        r = requests.delete(
            f"{VERCEL_API}/v9/projects/{project_name}/domains/{hostname}",
            headers=_vercel_headers(),
            timeout=12,
        )
        return {"ok": r.status_code < 400, "status": r.status_code}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# ─── Coolify (self-hosted) ─────────────────────────────────────────────
def coolify_configured() -> bool:
    return bool(
        os.environ.get("COOLIFY_API_TOKEN", "").strip()
        and os.environ.get("COOLIFY_APP_UUID", "").strip()
    )


def coolify_attach_domain(hostname: str) -> dict:
    if not coolify_configured():
        return {"ok": False, "error": "COOLIFY_API_TOKEN / COOLIFY_APP_UUID not set"}
    base = (os.environ.get("COOLIFY_BASE_URL") or COOLIFY_API_DEFAULT).rstrip("/")
    uuid_ = os.environ["COOLIFY_APP_UUID"].strip()
    try:
        r = requests.post(
            f"{base}/api/v1/applications/{uuid_}/domains",
            headers={"Authorization": f"Bearer {os.environ['COOLIFY_API_TOKEN'].strip()}",
                     "Content-Type": "application/json"},
            json={"domain": hostname},
            timeout=15,
        )
        if r.status_code >= 400:
            return {"ok": False, "error": f"{r.status_code}: {r.text[:200]}"}
        return {"ok": True, "attached": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def detect_deploy_host_provider() -> str:
    """Returns 'vercel' | 'coolify' | 'caddy' | 'manual' based on env config.

    Used by the /domains/add route to pick the right attachment flow."""
    if vercel_configured():
        return "vercel"
    if coolify_configured():
        return "coolify"
    # Caddy auto-HTTPS — no API needed; just confirm the deploy host points at us.
    if (os.environ.get("CADDY_AUTO_HTTPS") or "").strip().lower() in ("1", "true", "yes"):
        return "caddy"
    return "manual"
