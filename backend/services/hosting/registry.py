"""NXT1 — Hosting catalogue (Phase 10C).

A structured catalogue describing each hosting target NXT1 supports.
The frontend's Workspace “Hosting” module reads from
`GET /api/deploy/providers` (defined in routes/deployments.py) which
shapes its response from this catalogue + the runtime `is_configured`
from `services.deployment_service.list_providers()`.

New providers added here automatically appear in the UI — the rule is
placeholder-safe: providers without their required env vars present as
clickable but tagged “connect” so the user knows what's missing.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

# ---------- Catalogue entries ----------
# id   matches deployment_service.PROVIDERS keys
# label, blurb, env_vars are UI-shaped
# capabilities is a free-form list the picker can filter on
HOSTING_CATALOG: List[Dict] = [
    {
        "id": "internal",
        "label": "NXT1 Hosting",
        "blurb": "One-click preview hosting served from NXT1.",
        "env_vars": [],
        "capabilities": ["preview", "static", "instant"],
        "docs_url": "",
        "tier": "preview",
    },
    {
        "id": "vercel",
        "label": "Vercel",
        "blurb": "Production hosting for Next.js & static sites with edge + analytics.",
        "env_vars": ["VERCEL_TOKEN"],
        "capabilities": ["production", "nextjs", "edge", "custom-domains"],
        "docs_url": "https://vercel.com/docs/rest-api/deployments",
        "tier": "production",
    },
    {
        "id": "netlify",
        "label": "Netlify",
        "blurb": "Atomic deploys, edge functions, and built-in form handling.",
        "env_vars": ["NETLIFY_AUTH_TOKEN"],
        "capabilities": ["production", "static", "edge-functions", "custom-domains"],
        "docs_url": "https://docs.netlify.com/api/get-started/",
        "tier": "production",
    },
    {
        "id": "railway",
        "label": "Railway",
        "blurb": "Backend + DB hosting with one-command builds and a managed Postgres.",
        "env_vars": ["RAILWAY_TOKEN", "RAILWAY_PROJECT_ID"],
        "capabilities": ["backend", "docker", "databases", "long-running"],
        "docs_url": "https://docs.railway.app/reference/public-api",
        "tier": "production",
    },
    {
        "id": "cloudflare-pages",
        "label": "Cloudflare Pages",
        "blurb": "Global edge-hosted static + JAMstack sites with free SSL & domains.",
        "env_vars": ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"],
        "capabilities": ["production", "static", "edge", "custom-domains"],
        "docs_url": "https://developers.cloudflare.com/pages/",
        "tier": "production",
    },
    {
        "id": "cloudflare-workers",
        "label": "Cloudflare Workers",
        "blurb": "Edge compute with D1 + R2 bindings for full-stack JS apps.",
        "env_vars": ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"],
        "capabilities": ["production", "edge-compute", "d1", "r2"],
        "docs_url": "https://developers.cloudflare.com/workers/",
        "tier": "production",
    },
    {
        "id": "custom",
        "label": "Custom (SSH / Git push)",
        "blurb": "Deploy to your own server via SSH or `git push` to a remote endpoint.",
        "env_vars": ["CUSTOM_DEPLOY_HOST", "CUSTOM_DEPLOY_SSH_KEY"],
        "capabilities": ["production", "bring-your-own", "custom-domains"],
        "docs_url": "",
        "tier": "advanced",
    },
]


def _env_present(keys: List[str]) -> bool:
    if not keys:
        return True
    return all(bool((os.environ.get(k) or "").strip()) for k in keys)


def list_hosting_targets() -> List[Dict]:
    """Return the catalogue with runtime `configured` flags merged in."""
    out = []
    for h in HOSTING_CATALOG:
        item = dict(h)
        item["configured"] = _env_present(h["env_vars"])
        item["missing_env"] = [k for k in h["env_vars"] if not (os.environ.get(k) or "").strip()]
        out.append(item)
    return out


def get_hosting_target(provider_id: str) -> Optional[Dict]:
    for h in list_hosting_targets():
        if h["id"] == provider_id:
            return h
    return None
