"""Real database provisioning for NXT1.

Calls the Supabase Management API + Neon Platform API to actually create
databases on the user's behalf. Returns a connection URL + provider metadata
that the database registry stores.

This module purposely keeps the surface narrow:
  - provision(provider, name, region, ...) -> dict
  - run_sql(url, sql) -> dict
  - providers_status() -> dict

So the route layer can stay thin and the registry can keep its existing shape.

Required environment:
  - NEON_API_KEY                   (from console.neon.tech/app/settings/api-keys)
  - SUPABASE_ACCESS_TOKEN          (sbp_... from supabase.com/dashboard/account/tokens)
  - SUPABASE_ORG_ID                (optional; otherwise we list orgs and pick the first)
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from typing import Optional

import requests

logger = logging.getLogger("nxt1.provisioning")

NEON_API = "https://console.neon.tech/api/v2"
SUPABASE_API = "https://api.supabase.com/v1"

# Sensible defaults — operators can override per-call.
DEFAULT_NEON_REGION = "aws-us-east-1"
DEFAULT_SUPABASE_REGION = "us-east-1"


# ---------- status ----------
def providers_status() -> dict:
    """Which providers are ready to provision right now."""
    neon_key = (os.environ.get("NEON_API_KEY") or "").strip()
    supa_token = (os.environ.get("SUPABASE_ACCESS_TOKEN") or "").strip()
    atlas_pub = (os.environ.get("MONGODB_ATLAS_PUBLIC_KEY") or "").strip()
    atlas_priv = (os.environ.get("MONGODB_ATLAS_PRIVATE_KEY") or "").strip()
    atlas_org = (os.environ.get("MONGODB_ATLAS_ORG_ID") or "").strip()
    atlas_ready = bool(atlas_pub and atlas_priv and atlas_org)
    atlas_missing = [k for k, v in (
        ("MONGODB_ATLAS_PUBLIC_KEY", atlas_pub),
        ("MONGODB_ATLAS_PRIVATE_KEY", atlas_priv),
        ("MONGODB_ATLAS_ORG_ID", atlas_org),
    ) if not v]
    return {
        "neon": {
            "configured": bool(neon_key),
            "ready": bool(neon_key),
            "missing": [] if neon_key else ["NEON_API_KEY"],
            "regions": [
                "aws-us-east-1", "aws-us-east-2", "aws-us-west-2",
                "aws-eu-central-1", "aws-eu-west-2", "aws-ap-southeast-1",
            ],
            "label": "Neon Postgres",
        },
        "supabase": {
            "configured": bool(supa_token),
            "ready": bool(supa_token),
            "missing": [] if supa_token else ["SUPABASE_ACCESS_TOKEN"],
            "regions": [
                "us-east-1", "us-west-1", "eu-west-1", "eu-central-1",
                "ap-southeast-1", "ap-northeast-1", "sa-east-1",
            ],
            "label": "Supabase",
        },
        "atlas": {
            "configured": atlas_ready,
            "ready": atlas_ready,
            "missing": atlas_missing,
            "regions": ["US_EAST_1", "US_WEST_2", "EU_WEST_1", "AP_SOUTHEAST_1"],
            "label": "MongoDB Atlas",
        },
    }


# ---------- Neon ----------
def _neon_headers() -> dict:
    key = (os.environ.get("NEON_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("NEON_API_KEY missing — set it in /admin → Keys.")
    return {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _neon_resolve_org() -> Optional[str]:
    explicit = (os.environ.get("NEON_ORG_ID") or "").strip()
    if explicit:
        return explicit
    try:
        r = requests.get(f"{NEON_API}/users/me/organizations", headers=_neon_headers(), timeout=20)
        if r.status_code < 400:
            j = r.json() or {}
            orgs = j.get("organizations") or j.get("items") or (j if isinstance(j, list) else [])
            if orgs:
                first = orgs[0] if isinstance(orgs, list) else None
                if first:
                    return first.get("id") or first.get("organization_id")
    except Exception:
        pass
    return None


def provision_neon(name: str, region: str = DEFAULT_NEON_REGION) -> dict:
    """Create a fresh Neon project and return its connection URI.

    Neon's POST /projects response includes `connection_uris[].connection_uri`
    pointing at the default branch. We surface the first one.
    """
    body = {"project": {"name": name[:32] or "nxt1-app", "region_id": region}}
    org_id = _neon_resolve_org()
    if org_id:
        body["project"]["org_id"] = org_id
    r = requests.post(f"{NEON_API}/projects", json=body, headers=_neon_headers(), timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Neon: {r.status_code} {r.text[:240]}")
    data = r.json()
    conns = data.get("connection_uris") or []
    if not conns:
        # Fallback: list endpoints + roles to compose the URL ourselves
        raise RuntimeError("Neon: project created but no connection_uris returned")
    uri = conns[0].get("connection_uri")
    project = (data.get("project") or {})
    branch = (data.get("branch") or {})
    return {
        "provider": "neon",
        "url": uri,
        "metadata": {
            "project_id": project.get("id"),
            "branch_id": branch.get("id"),
            "host": (data.get("endpoints") or [{}])[0].get("host"),
            "region": project.get("region_id") or region,
            "name": project.get("name") or name,
        },
        "raw": {"project_id": project.get("id"), "branch_id": branch.get("id")},
    }


# ---------- Supabase ----------
def _supabase_headers() -> dict:
    token = (os.environ.get("SUPABASE_ACCESS_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "SUPABASE_ACCESS_TOKEN missing — get a personal access token at "
            "supabase.com/dashboard/account/tokens and add it in /admin → Keys."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _supabase_resolve_org() -> str:
    explicit = (os.environ.get("SUPABASE_ORG_ID") or "").strip()
    if explicit:
        return explicit
    r = requests.get(f"{SUPABASE_API}/organizations", headers=_supabase_headers(), timeout=20)
    if r.status_code >= 400:
        raise RuntimeError(f"Supabase: list orgs failed: {r.status_code} {r.text[:200]}")
    orgs = r.json() or []
    if not orgs:
        raise RuntimeError("Supabase: no organizations found for this access token.")
    return orgs[0].get("id") or orgs[0].get("organization_id")


def _supabase_wait_active(ref: str, timeout_s: int = 240) -> dict:
    """Poll the project until it's ACTIVE_HEALTHY (or timeout)."""
    start = __import__("time").time()
    while True:
        r = requests.get(f"{SUPABASE_API}/projects/{ref}", headers=_supabase_headers(), timeout=20)
        if r.status_code < 400:
            j = r.json()
            status = j.get("status")
            if status in ("ACTIVE_HEALTHY", "ACTIVE", "HEALTHY"):
                return j
            if status in ("INIT_FAILED", "REMOVED", "PAUSED"):
                raise RuntimeError(f"Supabase project entered status {status}")
        if __import__("time").time() - start > timeout_s:
            # Don't fail hard — the project IS being created. Surface what we
            # have and let the caller mark it pending.
            return {"status": "INIT_PENDING", "ref": ref}
        __import__("time").sleep(5)


def provision_supabase(
    name: str,
    region: str = DEFAULT_SUPABASE_REGION,
    org_id: Optional[str] = None,
    db_pass: Optional[str] = None,
    plan: str = "free",
) -> dict:
    """Create a Supabase project. Returns the standard postgres connection URL."""
    org_id = org_id or _supabase_resolve_org()
    pw = db_pass or secrets.token_urlsafe(24)
    body = {
        "name": (name[:48] or "nxt1-app"),
        "db_pass": pw,
        "organization_id": org_id,
        "plan": plan,
        "region": region,
    }
    r = requests.post(f"{SUPABASE_API}/projects", json=body, headers=_supabase_headers(), timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Supabase: {r.status_code} {r.text[:240]}")
    created = r.json()
    ref = created.get("id") or created.get("reference_id")
    # Wait for the project to become healthy so the URL is reachable.
    _supabase_wait_active(ref)
    # Standard pooler URL:
    #   postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres
    host = f"db.{ref}.supabase.co"
    url = f"postgresql://postgres:{pw}@{host}:5432/postgres"
    return {
        "provider": "supabase",
        "url": url,
        "metadata": {
            "project_ref": ref,
            "region": region,
            "name": name,
            "anon_url": f"https://{ref}.supabase.co",
            "host": host,
        },
        "raw": {"project_ref": ref, "host": host},
    }


# ---------- migrations ----------
async def run_sql(url: str, sql: str, timeout_s: int = 60) -> dict:
    """Execute a SQL block against a Postgres URL via asyncpg.

    Returns {ok, rows_returned, statements_run, error}.
    """
    if not url:
        raise RuntimeError("Database URL is empty")
    if not sql or not sql.strip():
        raise RuntimeError("SQL is empty")
    try:
        import asyncpg  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"asyncpg not installed: {e}")

    # Neon and Supabase URLs sometimes start with postgres:// — asyncpg accepts
    # both, but normalise just in case.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    conn = None
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(url, ssl="require"),
            timeout=timeout_s,
        )
        # `execute` runs multi-statement SQL when sent through the simple
        # protocol (which asyncpg's execute uses for non-prepared text).
        result = await asyncio.wait_for(conn.execute(sql), timeout=timeout_s)
        return {"ok": True, "result": str(result)[:240]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}
    finally:
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass


async def test_connection(url: str, timeout_s: int = 15) -> dict:
    """Quick ping — `SELECT 1`."""
    if not url:
        return {"ok": False, "error": "empty url"}
    try:
        import asyncpg  # type: ignore
    except ImportError as e:
        return {"ok": False, "error": str(e)}
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    try:
        conn = await asyncio.wait_for(asyncpg.connect(url, ssl="require"), timeout=timeout_s)
        try:
            v = await conn.fetchval("SELECT version()")
            return {"ok": True, "version": str(v)[:200]}
        finally:
            await conn.close()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


# ---------- MongoDB Atlas ----------
ATLAS_API = "https://cloud.mongodb.com/api/atlas/v2"


def _atlas_auth():
    pub = (os.environ.get("MONGODB_ATLAS_PUBLIC_KEY") or "").strip()
    priv = (os.environ.get("MONGODB_ATLAS_PRIVATE_KEY") or "").strip()
    if not (pub and priv):
        raise RuntimeError(
            "MongoDB Atlas not configured — set MONGODB_ATLAS_PUBLIC_KEY + "
            "MONGODB_ATLAS_PRIVATE_KEY (Project API key with `Project Cluster Manager` role)."
        )
    return requests.auth.HTTPDigestAuth(pub, priv)


def _atlas_headers() -> dict:
    return {
        "Accept": "application/vnd.atlas.2024-08-05+json",
        "Content-Type": "application/json",
    }


def provision_atlas(name: str, region: str = "US_EAST_1",
                    cluster_tier: str = "M0", db_pass: Optional[str] = None) -> dict:
    """Create a new Atlas project + free-tier serverless-ish cluster + DB user.

    Atlas requires a `Project` (groupId) before the cluster — we create one in
    the configured org if it doesn't already exist for this name.
    """
    org_id = (os.environ.get("MONGODB_ATLAS_ORG_ID") or "").strip()
    if not org_id:
        raise RuntimeError("MONGODB_ATLAS_ORG_ID missing.")

    auth = _atlas_auth()
    pw = db_pass or secrets.token_urlsafe(20)

    # 1) Create project under the org (Atlas v2 API uses groups for projects)
    proj_body = {"name": name[:64] or "nxt1-app", "orgId": org_id}
    pr = requests.post(
        f"{ATLAS_API}/groups", json=proj_body, headers=_atlas_headers(),
        auth=auth, timeout=30,
    )
    if pr.status_code >= 400:
        raise RuntimeError(f"Atlas: create project: {pr.status_code} {pr.text[:240]}")
    project = pr.json()
    group_id = project.get("id")

    # 2) Allow connections from anywhere (best-effort — operator should
    #    tighten this in Atlas later).
    try:
        requests.post(
            f"{ATLAS_API}/groups/{group_id}/accessList",
            json=[{"cidrBlock": "0.0.0.0/0", "comment": "NXT1-default"}],
            headers=_atlas_headers(), auth=auth, timeout=20,
        )
    except Exception:
        pass

    # 3) Create a free-tier M0 cluster on the AWS provider
    cluster_body = {
        "name": "Cluster0",
        "clusterType": "REPLICASET",
        "replicationSpecs": [{
            "regionConfigs": [{
                "providerName": "TENANT",
                "backingProviderName": "AWS",
                "regionName": region,
                "electableSpecs": {"instanceSize": cluster_tier},
                "priority": 7,
            }],
        }],
    }
    cr = requests.post(
        f"{ATLAS_API}/groups/{group_id}/clusters",
        json=cluster_body, headers=_atlas_headers(), auth=auth, timeout=30,
    )
    if cr.status_code >= 400:
        raise RuntimeError(f"Atlas: create cluster: {cr.status_code} {cr.text[:240]}")

    # 4) Create the DB user
    user_body = {
        "username": "nxt1_app",
        "password": pw,
        "databaseName": "admin",
        "roles": [{"databaseName": "admin", "roleName": "readWriteAnyDatabase"}],
    }
    ur = requests.post(
        f"{ATLAS_API}/groups/{group_id}/databaseUsers",
        json=user_body, headers=_atlas_headers(), auth=auth, timeout=20,
    )
    if ur.status_code >= 400:
        raise RuntimeError(f"Atlas: create user: {ur.status_code} {ur.text[:240]}")

    # 5) Poll cluster until IDLE so we can read the connection string
    import time as _t
    deadline = _t.time() + 240
    srv_uri = None
    while _t.time() < deadline:
        gr = requests.get(
            f"{ATLAS_API}/groups/{group_id}/clusters/Cluster0",
            headers=_atlas_headers(), auth=auth, timeout=20,
        )
        if gr.status_code < 400:
            j = gr.json()
            state = j.get("stateName")
            cs = (j.get("connectionStrings") or {})
            srv_uri = cs.get("standardSrv") or cs.get("standard")
            if state == "IDLE" and srv_uri:
                break
        _t.sleep(8)

    if not srv_uri:
        return {
            "provider": "atlas",
            "url": "",
            "metadata": {"group_id": group_id, "status": "INIT_PENDING", "name": name},
            "raw": {"group_id": group_id},
        }

    # Build the user-friendly connection string with credentials
    if srv_uri.startswith("mongodb+srv://"):
        host = srv_uri[len("mongodb+srv://"):]
        full = f"mongodb+srv://nxt1_app:{pw}@{host}/?retryWrites=true&w=majority"
    else:
        full = srv_uri

    return {
        "provider": "atlas",
        "url": full,
        "metadata": {
            "group_id": group_id,
            "cluster_name": "Cluster0",
            "region": region,
            "tier": cluster_tier,
            "db_user": "nxt1_app",
            "name": name,
        },
        "raw": {"group_id": group_id, "srv_uri": srv_uri},
    }
