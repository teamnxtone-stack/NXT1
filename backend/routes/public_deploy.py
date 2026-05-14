"""Public deploy serving (multi-page + assets) — Phase 8 modular refactor.

These endpoints are intentionally PUBLIC (no auth) — same security model as the
deployed-site URLs. Mounted on the FastAPI app directly via /api/deploy/*.
"""
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

from services.storage_service import get_object

from ._deps import db

router = APIRouter(prefix="/api", tags=["public-deploy"])


def _inline_referenced(html: str, files: dict, slug: str) -> str:
    def repl_link(m: re.Match) -> str:
        href = m.group(1)
        css = files.get(href)
        if css is None:
            return m.group(0)
        return f"<style data-from=\"{href}\">{css}</style>"

    html = re.sub(
        r'<link\s+[^>]*?rel=["\']stylesheet["\'][^>]*?href=["\']([^"\']+\.css)["\'][^>]*?/?>',
        repl_link, html, flags=re.IGNORECASE,
    )
    html = re.sub(
        r'<link\s+[^>]*?href=["\']([^"\']+\.css)["\'][^>]*?rel=["\']stylesheet["\'][^>]*?/?>',
        repl_link, html, flags=re.IGNORECASE,
    )

    def repl_script(m: re.Match) -> str:
        src = m.group(1)
        js = files.get(src)
        if js is None:
            return m.group(0)
        return f"<script data-from=\"{src}\">{js}</script>"

    html = re.sub(
        r'<script\s+[^>]*?src=["\']([^"\']+\.js)["\'][^>]*?>\s*</script>',
        repl_script, html, flags=re.IGNORECASE,
    )

    html = re.sub(
        r'(src|href)=["\']assets/([^"\']+)["\']',
        rf'\1="/api/deploy/{slug}/assets/\2"', html,
    )
    return html


async def _serve_deploy_page(slug: str, path: str) -> HTMLResponse:
    doc = await db.projects.find_one(
        {"deploy_slug": slug, "deployed": True}, {"_id": 0},
    )
    if doc is None:
        return HTMLResponse("<h1>404 — not deployed</h1>", status_code=404)
    files = {f["path"]: f["content"] for f in doc.get("files", [])}
    html = files.get(path)
    if html is None:
        return HTMLResponse(f"<h1>404 — {path} not found</h1>", status_code=404)
    return HTMLResponse(_inline_referenced(html, files, slug))


async def _serve_deploy_static(slug: str, path: str) -> Response:
    doc = await db.projects.find_one(
        {"deploy_slug": slug, "deployed": True}, {"_id": 0, "files": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Not deployed")
    files = {f["path"]: f["content"] for f in doc.get("files", [])}
    if path not in files:
        raise HTTPException(status_code=404, detail="Not found")
    media = (
        "text/css" if path.endswith(".css")
        else "application/javascript" if path.endswith(".js")
        else "text/plain"
    )
    return Response(content=files[path], media_type=media)


async def _serve_deploy_asset(slug: str, filename: str) -> Response:
    doc = await db.projects.find_one(
        {"deploy_slug": slug, "deployed": True}, {"_id": 0, "assets": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Not deployed")
    asset = next((a for a in doc.get("assets", []) if a["filename"] == filename), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    data, ct = get_object(asset["storage_path"])
    return Response(content=data, media_type=asset.get("content_type", ct))


@router.get("/deploy/{slug}", response_class=HTMLResponse)
async def deploy_index(slug: str):
    return await _serve_deploy_page(slug, "index.html")


@router.get("/deploy/{slug}/{page:path}")
async def deploy_page_or_asset(slug: str, page: str):
    if page.startswith("assets/"):
        filename = page.split("/", 1)[1]
        return await _serve_deploy_asset(slug, filename)
    if not page.endswith(".html"):
        return await _serve_deploy_static(slug, page)
    return await _serve_deploy_page(slug, page)
