"""Runtime sandbox routes: start/stop/restart/status/logs/health/scaffold/try
+ public runtime proxy + AI page-from-route generator. (Phase 8 modular refactor)
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from services import ai_service
from services import runtime_service as rt_svc
from services import scaffold_service

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.runtime")

router = APIRouter(prefix="/api", tags=["runtime"])


# Pydantic models
class ScaffoldIn(BaseModel):
    kind: str  # 'fastapi' | 'express'
    auto_start: Optional[bool] = True


class TryItIn(BaseModel):
    method: str
    path: str
    body: Optional[dict] = None
    query: Optional[dict] = None


class RoutePageIn(BaseModel):
    method: str
    path: str
    target: Optional[str] = "auto"  # 'html' | 'react' | 'auto'
    provider: Optional[str] = None


def _project_env_dict(env_vars_list: list) -> dict:
    return {e["key"]: e.get("value", "") for e in env_vars_list or []}


@router.post("/projects/{project_id}/runtime/start")
async def runtime_start(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one(
        {"id": project_id}, {"_id": 0, "id": 1, "files": 1, "env_vars": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        handle = await rt_svc.start_runtime(
            project_id, doc.get("files", []),
            _project_env_dict(doc.get("env_vars", [])),
        )
        return handle.status_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/runtime/stop")
async def runtime_stop(project_id: str, _: str = Depends(verify_token)):
    ok = await rt_svc.stop_runtime(project_id)
    return {"ok": ok}


@router.post("/projects/{project_id}/runtime/restart")
async def runtime_restart(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one(
        {"id": project_id}, {"_id": 0, "id": 1, "files": 1, "env_vars": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        handle = await rt_svc.restart_runtime(
            project_id, doc.get("files", []),
            _project_env_dict(doc.get("env_vars", [])),
        )
        return handle.status_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/runtime")
async def runtime_status(project_id: str, _: str = Depends(verify_token)):
    h = rt_svc.get_handle(project_id)
    if not h:
        return {"alive": False, "stopped": True, "logs": [],
                "endpoints": [], "port": None}
    s = h.status_dict()
    s["logs"] = list(h.logs)[-300:]
    return s


@router.get("/projects/{project_id}/runtime/logs")
async def runtime_logs(project_id: str, since: int = 0,
                       _: str = Depends(verify_token)):
    h = rt_svc.get_handle(project_id)
    if not h:
        return {"logs": [], "total": 0}
    full = list(h.logs)
    return {"logs": full[since:], "total": len(full)}


@router.post("/projects/{project_id}/runtime/health")
async def runtime_health(project_id: str, path: str = "/api/health",
                         _: str = Depends(verify_token)):
    return await rt_svc.health_probe(project_id, path)


@router.post("/projects/{project_id}/scaffold")
async def project_scaffold(project_id: str, body: ScaffoldIn,
                           _: str = Depends(verify_token)):
    doc = await db.projects.find_one(
        {"id": project_id}, {"_id": 0, "files": 1, "env_vars": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        starter = scaffold_service.build_starter(body.kind)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    merged = scaffold_service.merge_into_files(doc.get("files", []), starter)
    now = datetime.now(timezone.utc).isoformat()
    snap = {
        "id": str(uuid.uuid4()),
        "label": f"Generated {body.kind} starter",
        "commit_message": f"NXT1 scaffolded a {body.kind} backend (health + echo + hello).",
        "type": "ai",
        "files": merged,
        "created_at": now,
    }
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"files": merged, "updated_at": now},
         "$push": {"versions": snap}},
    )
    started = None
    if body.auto_start:
        try:
            handle = await rt_svc.start_runtime(
                project_id, merged,
                _project_env_dict(doc.get("env_vars", [])),
            )
            started = handle.status_dict()
        except Exception as e:  # noqa: BLE001
            started = {"alive": False, "error": str(e)}
    return {"ok": True,
            "files_added": [f["path"] for f in starter],
            "runtime": started}


@router.post("/projects/{project_id}/runtime/try")
async def runtime_try(project_id: str, body: TryItIn,
                      _: str = Depends(verify_token)):
    method = (body.method or "GET").upper()
    path = (body.path or "/").lstrip("/")
    qs = ""
    if body.query:
        from urllib.parse import urlencode
        qs = urlencode(body.query)
    payload_bytes = b""
    headers = {}
    if body.body is not None:
        payload_bytes = json.dumps(body.body).encode("utf-8")
        headers["content-type"] = "application/json"
    status, out_headers, out_body = await rt_svc.proxy_request(
        project_id, method, path, headers, payload_bytes, qs,
    )
    text = out_body.decode("utf-8", errors="replace")
    parsed = None
    try:
        parsed = json.loads(text)
    except Exception:
        pass
    return {
        "status_code": status,
        "headers": dict(out_headers),
        "body_text": text[:8000],
        "body_json": parsed,
    }


# ---------- Generate frontend page that calls a backend route ----------
@router.post("/projects/{project_id}/generate-page-from-route")
async def generate_page_from_route(project_id: str, body: RoutePageIn,
                                   _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    backend_origin = os.environ.get("BACKEND_PUBLIC_ORIGIN", "").rstrip("/")
    if not backend_origin:
        raise HTTPException(status_code=503,
                            detail="Backend public origin not configured")
    proxy_url = f"{backend_origin}/api/runtime/{project_id}"

    target = (body.target or "auto").lower()
    if target == "auto":
        has_react = any(
            f["path"].endswith((".jsx", ".tsx")) or f["path"].startswith("src/")
            for f in doc.get("files", [])
        )
        target = "react" if has_react else "html"

    existing_paths = [f["path"] for f in doc.get("files", [])]
    try:
        gen = await ai_service.generate_route_page(
            method=body.method.upper(),
            path=body.path,
            proxy_url=proxy_url,
            target=target,
            existing_paths=existing_paths,
            preferred_provider=body.provider,
        )
    except ai_service.AIProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))

    new_path = gen["path"]
    base_path = new_path
    n = 2
    while any(f["path"] == new_path for f in doc.get("files", [])):
        if "." in base_path:
            stem, _, ext = base_path.rpartition(".")
            new_path = f"{stem}-{n}.{ext}"
        else:
            new_path = f"{base_path}-{n}"
        n += 1
    new_file = {"path": new_path, "content": gen["content"]}
    merged = list(doc.get("files", [])) + [new_file]
    now = datetime.now(timezone.utc).isoformat()
    snap = {
        "id": str(uuid.uuid4()),
        "label": gen["title"][:120],
        "commit_message": f"AI generated page for {body.method.upper()} {body.path}",
        "type": "ai",
        "files": merged,
        "created_at": now,
        "provider": gen.get("provider"),
        "model": gen.get("model"),
    }
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"files": merged, "updated_at": now},
         "$push": {"versions": snap}},
    )
    return {
        "ok": True,
        "path": new_path,
        "title": gen["title"],
        "explanation": gen["explanation"],
        "target": target,
        "provider": gen.get("provider"),
        "model": gen.get("model"),
    }


# ---------- Public proxy to project's running backend (no auth) ----------
@router.api_route("/runtime/{project_id}/{path:path}",
                  methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def runtime_proxy(project_id: str, path: str, request: Request):
    body = await request.body()
    headers = dict(request.headers)
    query = request.url.query or ""
    status, out_headers, out_body = await rt_svc.proxy_request(
        project_id, request.method, path, headers, body, query,
    )
    return Response(content=out_body, status_code=status, headers=out_headers)
