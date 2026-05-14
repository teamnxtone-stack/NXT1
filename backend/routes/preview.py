"""Shareable preview-link routes.

- POST /api/projects/{id}/preview — create or refresh the project's preview link.
- GET  /api/projects/{id}/preview — get current preview metadata.
- DELETE /api/projects/{id}/preview — remove the preview link.

- GET /api/preview/{slug}                 (public) → serves index.html
- GET /api/preview/{slug}/{path:path}     (public) → serves any asset/page

Public routes don't require auth (same model as /api/deploy/{slug}) but read
straight from `project.preview.slug` rather than `project.deploy_slug`. This
keeps preview links separate from production deploys.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from services import preview_service
from services.storage_service import get_object

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.preview")

router = APIRouter(prefix="/api", tags=["preview"])


# ------------------ authenticated CRUD ------------------

class PreviewIn(BaseModel):
    public: Optional[bool] = True
    password: Optional[str] = None  # set to "" to clear, anything else to set


class PreviewUnlockIn(BaseModel):
    password: str


@router.get("/projects/{project_id}/preview-info")
async def preview_info(project_id: str, _: str = Depends(verify_token)):
    """Surface the import preview-detection so the builder UI can decide
    whether to render in-iframe or fall back to the live deploy URL."""
    doc = await db.projects.find_one(
        {"id": project_id},
        {"_id": 0, "analysis": 1, "preview": 1, "deployments": 1,
         "github": 1, "name": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    info = (doc.get("analysis") or {}).get("preview_info") or {}
    live = None
    deploys = doc.get("deployments") or []
    deployed = next(
        (d for d in reversed(deploys) if d.get("status") == "deployed" and d.get("public_url")),
        None,
    )
    if deployed:
        live = deployed["public_url"]
    elif (doc.get("github") or {}).get("name"):
        live = f"https://{doc['github']['name']}.vercel.app"
    return {
        "preview_info": info or {"kind": "unknown", "preview_ok": True},
        "live_url": live,
        "preview_slug": (doc.get("preview") or {}).get("slug"),
    }


@router.post("/projects/{project_id}/preview")
async def create_or_refresh_preview(project_id: str, body: Optional[PreviewIn] = None,
                                    _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    files = doc.get("files") or []
    if not files:
        raise HTTPException(status_code=400, detail="Build the project before generating a preview link")
    existing = doc.get("preview") or {}
    if existing.get("slug"):
        rec = preview_service.refresh(existing)
    else:
        rec = preview_service.make_initial(doc.get("name") or project_id)
    if body and body.public is not None:
        rec["public"] = bool(body.public)
    if body and body.password is not None:
        if body.password == "":
            rec.pop("password_hash", None)
        else:
            if len(body.password) < 4:
                raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")
            rec["password_hash"] = preview_service.hash_password(body.password)
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {
            "preview": rec,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return preview_service.public_view(rec)


@router.get("/projects/{project_id}/preview")
async def get_preview(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "preview": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return preview_service.public_view(doc.get("preview") or {})


@router.delete("/projects/{project_id}/preview")
async def delete_preview(project_id: str, _: str = Depends(verify_token)):
    res = await db.projects.update_one(
        {"id": project_id},
        {"$unset": {"preview": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True}


# ------------------ PUBLIC preview serving (no auth) ------------------

def _inline_referenced(html: str, files: dict, slug: str,
                       rewrite_root: Optional[str] = None) -> str:
    """Inline referenced CSS/JS and rewrite asset URLs.

    When the html came from a sub-folder (e.g. frontend/dist/index.html),
    pass `rewrite_root="frontend/dist"` so relative `./assets/...` and
    `/static/...` references find their files in the bundle map.

    Improvements for imported apps:
    - Resolves absolute paths (`/assets/foo.js`) against the dist root
    - Handles `<script type="module">` (Vite ESM bundles)
    - Handles self-closing and unclosed script tags
    - Rewrites image/font asset URLs to /api/preview/{slug}/{path}
    """
    def resolve(href: str) -> Optional[str]:
        if not href:
            return None
        # Try literal
        if href in files:
            return href
        cleaned = href.lstrip("/")
        if cleaned in files:
            return cleaned
        # If it starts with ./ or ../ resolve relative to rewrite_root
        if rewrite_root:
            # Strip leading ./
            stripped = href[2:] if href.startswith("./") else href
            stripped = stripped.lstrip("/")
            for joined in (f"{rewrite_root}/{stripped}",
                           f"{rewrite_root}/{cleaned}"):
                if joined in files:
                    return joined
            # Also try assets/ directly under root (Vite default)
            if href.startswith("/assets/") or href.startswith("assets/"):
                under_root = f"{rewrite_root}/{cleaned}"
                if under_root in files:
                    return under_root
        return None

    def repl_link(m: re.Match) -> str:
        href = m.group(1)
        resolved = resolve(href)
        if resolved is None:
            return m.group(0)
        return f"<style data-from=\"{resolved}\">{files[resolved]}</style>"

    # CSS links — both attribute orderings
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
        resolved = resolve(src)
        if resolved is None:
            # Couldn't inline — rewrite the src so the asset endpoint can serve it
            if src.startswith("/") or src.startswith("./") or src.startswith("assets/"):
                new_src = f"/api/preview/{slug}/{src.lstrip('./').lstrip('/')}"
                return m.group(0).replace(src, new_src)
            return m.group(0)
        # Preserve type="module" if present
        had_module = 'type="module"' in m.group(0) or "type='module'" in m.group(0)
        type_attr = ' type="module"' if had_module else ""
        return f"<script data-from=\"{resolved}\"{type_attr}>{files[resolved]}</script>"

    # Script with src — handles both `<script src="…"></script>` and self-closing
    html = re.sub(
        r'<script\b[^>]*?\bsrc=["\']([^"\']+\.m?js)["\'][^>]*?>\s*</script>',
        repl_script, html, flags=re.IGNORECASE,
    )

    # Rewrite relative asset references (img/href to images/fonts) → preview endpoint
    html = re.sub(
        r'(src|href)=["\']assets/([^"\']+)["\']',
        rf'\1="/api/preview/{slug}/assets/\2"', html,
    )
    # Vite absolute paths starting with /assets/ → preview endpoint with dist root
    if rewrite_root:
        html = re.sub(
            r'(src|href)=["\']/assets/([^"\']+)["\']',
            rf'\1="/api/preview/{slug}/{rewrite_root}/assets/\2"', html,
        )
    return html


async def _find_by_preview_slug(slug: str, projection: Optional[dict] = None):
    return await db.projects.find_one(
        {"preview.slug": slug},
        projection or {"_id": 0},
    )


def _has_unlock_cookie(request, slug: str) -> bool:
    val = request.cookies.get(f"nxt1_pw_{slug}")
    return bool(val) and val == "ok"


@router.post("/preview/{slug}/unlock")
async def public_preview_unlock(slug: str, body: PreviewUnlockIn):
    doc = await _find_by_preview_slug(slug, {"_id": 0, "preview": 1})
    if doc is None or not doc.get("preview", {}).get("slug"):
        raise HTTPException(status_code=404, detail="Preview not found")
    pv = doc["preview"]
    if not pv.get("password_hash"):
        return {"ok": True}  # no password required
    if not preview_service.verify_password(body.password, pv["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong password")
    resp = Response(content='{"ok":true}', media_type="application/json")
    resp.set_cookie(
        f"nxt1_pw_{slug}", "ok",
        max_age=60 * 60 * 12,  # 12 hours
        httponly=True, secure=True, samesite="none", path="/",
    )
    return resp


_STATIC_MIME = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".map": "application/json",
    ".webmanifest": "application/manifest+json",
    ".txt": "text/plain",
    ".xml": "application/xml",
    ".wasm": "application/wasm",
}


def _resolve_static_path(path: str, files: dict, preview_info: dict) -> Optional[str]:
    """Find a static asset by trying common dist-root prefixes.

    Imported SPA bundles reference assets via absolute paths (`/assets/foo.js`)
    or as dist-relative (`assets/foo.js`). Map them back to file entries.
    """
    if path in files:
        return path
    cleaned = path.lstrip("/")
    if cleaned in files:
        return cleaned
    # Try under the detected dist_root
    dist_root = (preview_info or {}).get("dist_root") or (preview_info or {}).get("root")
    if dist_root:
        for joined in (f"{dist_root}/{cleaned}",
                       f"{dist_root}/{path}",
                       f"{dist_root}/assets/{cleaned}"):
            if joined in files:
                return joined
    # Common monorepo fallbacks
    for prefix in ("frontend/", "client/", "web/", "apps/web/", "public/", "static/"):
        candidate = f"{prefix}{cleaned}"
        if candidate in files:
            return candidate
    return None


async def _serve_preview_page(slug: str, path: str, request) -> HTMLResponse:
    doc = await _find_by_preview_slug(slug)
    if doc is None:
        return HTMLResponse(_NOT_FOUND_HTML, status_code=404)
    pv = doc.get("preview") or {}
    if pv.get("public") is False:
        return HTMLResponse(_PRIVATE_HTML, status_code=403)
    if pv.get("password_hash") and not _has_unlock_cookie(request, slug):
        return HTMLResponse(_PASSWORD_HTML.replace("__SLUG__", slug), status_code=401)
    files = {f["path"]: f["content"] for f in (doc.get("files") or [])}

    # Imported repo? Use the detected entry path so React/Vite/static-HTML
    # projects render the FULL site instead of a blank "index.html missing".
    preview_info = ((doc.get("analysis") or {}).get("preview_info") or {})
    requested_index = path in ("index.html", "")
    if requested_index and preview_info.get("entry_path"):
        target = preview_info["entry_path"]
        if target in files:
            return HTMLResponse(_inline_referenced(files[target], files, slug,
                                                  rewrite_root=target.rsplit("/", 1)[0]))
        # Entry was detected but not in `files` map — fall through.

    html = files.get(path)
    if html is None:
        # SPA client-side routing: if the requested HTML path doesn't exist
        # but the project has a preview entry, serve the entry HTML so React
        # Router / Next router can pick up the route on the client.
        if preview_info.get("preview_ok") and preview_info.get("entry_path"):
            entry = preview_info["entry_path"]
            if entry in files:
                return HTMLResponse(_inline_referenced(files[entry], files, slug,
                                                      rewrite_root=entry.rsplit("/", 1)[0]))
        # Imported projects without a renderable preview → surface a fallback page
        # pointing at the live deploy URL (Vercel / Render) when we have one.
        if requested_index and preview_info and not preview_info.get("preview_ok"):
            live = _resolve_live_url(doc)
            return HTMLResponse(
                _FALLBACK_HTML
                    .replace("__KIND__", preview_info.get("kind", "unknown"))
                    .replace("__HINT__", preview_info.get("hint", ""))
                    .replace("__LIVE__", live or "")
                    .replace("__HASLIVE__", "block" if live else "none"),
                status_code=200,
            )
        return HTMLResponse(_NOT_FOUND_HTML, status_code=404)
    return HTMLResponse(_inline_referenced(html, files, slug))


def _resolve_live_url(doc: dict) -> Optional[str]:
    """Pick the best 'live' URL for an imported/deployed project."""
    deploys = doc.get("deployments") or []
    deployed = next(
        (d for d in reversed(deploys) if d.get("status") == "deployed" and d.get("public_url")),
        None,
    )
    if deployed:
        return deployed["public_url"]
    gh = doc.get("github") or {}
    if gh.get("repo_url"):
        # Best-effort guess: most NXT1 exports auto-deploy to <repo>.vercel.app
        return f"https://{gh.get('name', '')}.vercel.app" if gh.get("name") else gh["repo_url"]
    return None


async def _serve_preview_static(slug: str, path: str, request) -> Response:
    doc = await _find_by_preview_slug(slug, {"_id": 0, "files": 1, "preview": 1, "analysis": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Preview not found")
    pv = doc.get("preview") or {}
    if pv.get("public") is False:
        raise HTTPException(status_code=403, detail="Preview is private")
    if pv.get("password_hash") and not _has_unlock_cookie(request, slug):
        raise HTTPException(status_code=401, detail="Password required")
    files = {f["path"]: f["content"] for f in (doc.get("files") or [])}
    preview_info = ((doc.get("analysis") or {}).get("preview_info") or {})
    # Resolve via dist-root awareness for imported bundles
    resolved = _resolve_static_path(path, files, preview_info)
    if not resolved:
        raise HTTPException(status_code=404, detail="Not found")
    # Map MIME by suffix (covers css/js/svg/woff/png/etc for imported bundles)
    ext = ""
    for e in _STATIC_MIME:
        if resolved.lower().endswith(e):
            ext = e
            break
    media = _STATIC_MIME.get(ext, "text/plain")
    return Response(content=files[resolved], media_type=media)


async def _serve_preview_asset(slug: str, filename: str, request) -> Response:
    doc = await _find_by_preview_slug(slug, {"_id": 0, "assets": 1, "preview": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Preview not found")
    pv = doc.get("preview") or {}
    if pv.get("public") is False:
        raise HTTPException(status_code=403, detail="Preview is private")
    if pv.get("password_hash") and not _has_unlock_cookie(request, slug):
        raise HTTPException(status_code=401, detail="Password required")
    asset = next((a for a in doc.get("assets", []) if a["filename"] == filename), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    data, ct = get_object(asset["storage_path"])
    return Response(content=data, media_type=asset.get("content_type", ct))


@router.get("/preview/{slug}", response_class=HTMLResponse)
async def public_preview_index(slug: str, request: Request):
    return await _serve_preview_page(slug, "index.html", request)


@router.get("/preview/{slug}/{page:path}")
async def public_preview_page_or_asset(slug: str, page: str, request: Request):
    # 1) `assets/<filename>` — uploaded user assets live in object storage
    if page.startswith("assets/"):
        filename = page.split("/", 1)[1]
        try:
            return await _serve_preview_asset(slug, filename, request)
        except HTTPException as e:
            # Imported apps store bundled `assets/` in the files map — fall
            # through to the static-file handler if the object-storage lookup
            # missed (so /assets/index-abc.js etc. on imported repos still work)
            if e.status_code != 404:
                raise
    # 2) HTML pages get the SPA-fallback-aware page handler
    if page.endswith(".html"):
        return await _serve_preview_page(slug, page, request)
    # 3) Everything else (css/js/svg/woff/png/json/etc.) → static file handler
    return await _serve_preview_static(slug, page, request)


_FALLBACK_HTML = """<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>NXT1 — Preview unavailable</title>
<style>body{margin:0;background:#070707;color:#e5e5e5;font-family:system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}
.card{max-width:520px;width:100%;padding:36px;border:1px solid #1f1f22;border-radius:18px;
background:#0a0a0a}
.brand{font-size:11px;letter-spacing:.28em;color:#3ec5b9;margin-bottom:18px;text-transform:uppercase}
h1{margin:0 0 8px;font-size:22px;font-weight:700;letter-spacing:-.01em}
p{color:#a0a0a0;font-size:13px;line-height:1.7;margin:0 0 18px}
.kind{display:inline-block;font-size:10px;mono;letter-spacing:.18em;text-transform:uppercase;
padding:4px 10px;border-radius:999px;border:1px solid #2a2a2e;color:#9aa;margin-bottom:14px}
.btn{display:__HASLIVE__;background:linear-gradient(90deg,#3ec5b9,#ffb86b);color:#0a0a0a;
font-weight:700;border:0;padding:11px 18px;border-radius:999px;cursor:pointer;
font-size:13px;letter-spacing:.04em;text-decoration:none;width:max-content}
.foot{font-size:10px;letter-spacing:.28em;color:#444;margin-top:22px;text-transform:uppercase}
</style></head>
<body><div class='card'><div class='brand'>NXT1 · preview</div>
<div class='kind'>kind: __KIND__</div>
<h1>This project needs a live deploy to preview.</h1>
<p>__HINT__</p>
<a class='btn' href='__LIVE__' target='_top'>Open live site →</a>
<div class='foot'>built with nxt1 · jwood technologies</div>
</div></body></html>"""

_NOT_FOUND_HTML = """<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>NXT1 — Preview not found</title>
<style>body{margin:0;background:#070707;color:#e5e5e5;font-family:system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{max-width:420px;padding:36px;border:1px solid #1f1f22;border-radius:18px;
background:#0a0a0a;text-align:center}
h1{margin:0 0 8px;font-size:22px}p{color:#888;font-size:13px;line-height:1.6;margin:0}
.brand{font-size:11px;letter-spacing:.28em;color:#3ec5b9;margin-bottom:18px;text-transform:uppercase}
</style></head>
<body><div class='card'><div class='brand'>NXT1</div>
<h1>Preview unavailable</h1><p>This preview link is invalid, has been removed, or the project hasn't been built yet.</p></div></body></html>"""

_PRIVATE_HTML = """<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>NXT1 — Private preview</title>
<style>body{margin:0;background:#070707;color:#e5e5e5;font-family:system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{max-width:420px;padding:36px;border:1px solid #1f1f22;border-radius:18px;
background:#0a0a0a;text-align:center}
h1{margin:0 0 8px;font-size:22px}p{color:#888;font-size:13px;line-height:1.6;margin:0}
.brand{font-size:11px;letter-spacing:.28em;color:#3ec5b9;margin-bottom:18px;text-transform:uppercase}
</style></head>
<body><div class='card'><div class='brand'>NXT1</div>
<h1>Private preview</h1><p>The owner has set this preview to private.</p></div></body></html>"""

_PASSWORD_HTML = """<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>NXT1 — Locked preview</title>
<style>body{margin:0;background:#070707;color:#e5e5e5;font-family:system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{max-width:380px;width:90%;padding:32px 28px;border:1px solid #1f1f22;border-radius:20px;
background:#0a0a0a}
.brand{font-size:11px;letter-spacing:.28em;color:#3ec5b9;margin-bottom:16px;text-transform:uppercase}
h1{margin:0 0 8px;font-size:20px}p{color:#888;font-size:13px;line-height:1.6;margin:0 0 18px}
form{display:flex;gap:8px}
input{flex:1;background:#000;border:1px solid #2a2a2e;color:#fff;padding:11px 14px;border-radius:10px;
font-size:14px;font-family:inherit;outline:none}
input:focus{border-color:#3ec5b9}
button{background:linear-gradient(90deg,#3ec5b9,#ffb86b);color:#0a0a0a;font-weight:700;
border:0;padding:0 18px;border-radius:10px;cursor:pointer;font-size:13px;letter-spacing:.06em}
.err{color:#f87171;font-size:12px;margin-top:10px;min-height:16px}
.foot{font-size:10px;letter-spacing:.28em;color:#444;margin-top:22px;text-transform:uppercase;text-align:center}
</style></head>
<body><div class='card'>
<div class='brand'>NXT1 · preview</div>
<h1>Password required</h1>
<p>This preview is locked. Enter the password your reviewer shared with you.</p>
<form id='f'>
  <input id='p' type='password' placeholder='Password' autofocus required />
  <button type='submit'>Unlock</button>
</form>
<div class='err' id='e'></div>
<div class='foot'>built with nxt1 · jwood technologies</div>
</div>
<script>
const slug='__SLUG__';
document.getElementById('f').addEventListener('submit',async e=>{
  e.preventDefault();
  const pw=document.getElementById('p').value;
  const err=document.getElementById('e');err.textContent='';
  try{
    const r=await fetch('/api/preview/'+slug+'/unlock',{method:'POST',
      headers:{'Content-Type':'application/json'},credentials:'include',
      body:JSON.stringify({password:pw})});
    if(r.ok){location.reload();}
    else{const j=await r.json().catch(()=>({}));err.textContent=j.detail||'Wrong password.';}
  }catch(_){err.textContent='Network error — try again.';}
});
</script></body></html>"""
