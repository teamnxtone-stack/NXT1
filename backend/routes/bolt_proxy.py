"""Reverse-proxy /api/bolt-engine/* requests to the local bolt.diy service.

bolt.diy runs on port 5173 (managed by supervisor at
`/etc/supervisor/conf.d/bolt-engine.conf`). We expose it to the public
under `/api/bolt-engine/...` so the frontend iframe at `/builder/{id}`
can load it without users needing to know about the internal port.

CRITICAL: WebContainers (StackBlitz tech bolt.diy uses for the live
preview) require COOP/COEP isolation. We force `credentialless` COEP +
`same-origin` COOP on every response so the cross-origin-isolated iframe
can boot even if the public ingress strips bolt.diy's own headers.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

router = APIRouter(prefix="/api/bolt-engine", tags=["bolt-engine"])

BOLT_INTERNAL_URL = (
    os.environ.get("BOLT_ENGINE_INTERNAL_URL")
    or os.environ.get("BOLT_DIY_URL")
    or "http://127.0.0.1:5173"
).rstrip("/")

# Headers we strip from the inbound request before forwarding to bolt.diy
_STRIP_REQ = {"host", "content-length", "x-forwarded-host", "x-forwarded-proto"}
# Headers we strip from bolt.diy's response before returning to the client
_STRIP_RES = {
    "content-length", "transfer-encoding", "content-encoding", "connection",
    # We set these fresh below to guarantee correct WebContainer isolation.
    "cross-origin-embedder-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
}


@router.api_route(
    "",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def bolt_proxy(request: Request, path: Optional[str] = ""):
    # We keep the `/api/bolt-engine/` prefix when forwarding because the
    # bolt.diy Vite/Remix dev server is configured with `base` + `basename`
    # of `/api/bolt-engine/` (so its emitted HTML/asset/HMR paths match
    # the public-facing URL it lives behind).
    target = f"{BOLT_INTERNAL_URL}/api/bolt-engine/{path or ''}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    fwd_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in _STRIP_REQ
    }
    fwd_headers["host"] = BOLT_INTERNAL_URL.split("://", 1)[-1].split("/")[0]

    body = await request.body()

    timeout = httpx.Timeout(60.0, connect=10.0)
    client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    try:
        req = client.build_request(
            request.method,
            target,
            headers=fwd_headers,
            content=body,
        )
        upstream = await client.send(req, stream=True)
    except httpx.RequestError as e:
        await client.aclose()
        return Response(
            content=f"Builder engine unreachable: {e}",
            status_code=502,
            media_type="text/plain",
        )

    out_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in _STRIP_RES
    }
    # Force WebContainer-friendly isolation headers. bolt.diy sets these on
    # its own root document already, but the ingress in front of us can
    # strip them; setting again is harmless and guarantees the iframe boots.
    out_headers["Cross-Origin-Embedder-Policy"] = "credentialless"
    out_headers["Cross-Origin-Opener-Policy"] = "same-origin"
    out_headers["Cross-Origin-Resource-Policy"] = "cross-origin"

    async def stream():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        stream(),
        status_code=upstream.status_code,
        headers=out_headers,
        media_type=upstream.headers.get("content-type"),
    )
