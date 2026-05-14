"""NXT1 — Hosting provider registry (Phase 10C).

Thin discovery layer over the existing deployment_service. Provides a
UX-shaped catalogue of hosting targets (Vercel, Railway, Netlify, Custom,
plus the existing Cloudflare Pages/Workers + internal) with required env
var surfacing for the frontend.

The actual deploy/poll logic continues to live in deployment_service —
this module is the *catalogue + capability* index that the workspace UI
reads from to render the hosting picker.
"""
from .registry import (
    HOSTING_CATALOG,
    list_hosting_targets,
    get_hosting_target,
)

__all__ = ["HOSTING_CATALOG", "list_hosting_targets", "get_hosting_target"]
