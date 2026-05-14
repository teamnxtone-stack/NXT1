"""Autonomous fix endpoints (Phase 7+).

Runtime auto-fix: bundles runtime errors + relevant files → DebugAgent → file fix proposal.
Deploy auto-fix:  bundles deployment failure + logs + files → DevOpsAgent → file/config fix proposal.
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services import agents as agents_svc
from services import runtime_service as rt_svc
from ._deps import db, verify_token

router = APIRouter(prefix="/api", tags=["autofix"])


# ----- shared models -----
class AutoFixIn(BaseModel):
    error_text: Optional[str] = ""
    note: Optional[str] = ""


class AutoFixApplyIn(BaseModel):
    fix_id: str
    files: List[Dict[str, str]]
    fix_summary: Optional[str] = ""
    diagnosis: Optional[str] = ""
    restart_runtime: Optional[bool] = True


class DeployAutoFixIn(BaseModel):
    deployment_id: Optional[str] = None  # if None, use latest failed deployment
    note: Optional[str] = ""


def _short_diff(before: str, after: str) -> dict:
    before_lines = (before or "").splitlines()
    after_lines = (after or "").splitlines()
    return {
        "before_lines": len(before_lines),
        "after_lines": len(after_lines),
        "added": max(0, len(after_lines) - len(before_lines)),
        "removed": max(0, len(before_lines) - len(after_lines)),
    }


def _select_files_for_fix(files: list, hint_paths: Optional[list] = None,
                          backend_first: bool = True, max_files: int = 14) -> list:
    """Selective retrieval: prioritise files matching hint_paths and backend/."""
    if not files:
        return []
    hint_paths = hint_paths or []
    scored = []
    for f in files:
        score = 0
        if any(h in f["path"] for h in hint_paths):
            score += 10
        if backend_first and f["path"].startswith("backend/"):
            score += 3
        if f["path"] in (
            "package.json", "vercel.json", "netlify.toml", "Dockerfile",
            "backend/requirements.txt", "backend/server.py", "backend/server.js",
            "requirements.txt"):
            score += 5
        scored.append((score, f))
    scored.sort(key=lambda x: -x[0])
    return [f for _, f in scored[:max_files]]


def _files_blob(files: list, max_chars: int = 6000) -> str:
    parts = []
    for f in files:
        content = (f.get("content") or "")[:max_chars]
        parts.append(f"=== {f['path']} ===\n{content}")
    return "\n\n".join(parts) or "(no files)"


def _project_env_dict(env_vars: list) -> dict:
    out = {}
    for v in env_vars or []:
        if v.get("key"):
            out[v["key"]] = v.get("value") or ""
    return out


# ----- Runtime auto-fix -----
@router.post("/projects/{project_id}/runtime/auto-fix")
async def runtime_auto_fix(project_id: str, body: Optional[AutoFixIn] = None,
                           _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")

    err_ctx = rt_svc.extract_recent_errors(project_id)
    error_text = (body.error_text if body and body.error_text else err_ctx["error_text"]) or ""
    user_note = (body.note if body else "") or ""
    if not error_text.strip():
        return {
            "ok": True, "fix_id": None, "has_errors": False,
            "diagnosis": "No errors detected in the runtime buffer.",
            "files": [], "fix_summary": "", "next_check": "",
            "requires_approval": False,
        }

    files = doc.get("files", [])
    candidate = _select_files_for_fix(files, backend_first=True)
    user_prompt = (
        f"RUNTIME ERROR / LOG (most recent):\n{error_text[:4000]}\n\n"
        f"USER NOTE:\n{user_note[:600]}\n\n"
        f"PROJECT FILES (relevant subset):\n{_files_blob(candidate)}\n\n"
        "Diagnose the root cause. Propose minimal-but-correct file edits. "
        "Provide the FULL new content for each file you change in `files[].after`. "
        "Respond with the JSON now."
    )
    agent = agents_svc.get_agent("debug")
    result = await agent.run(user_prompt)
    parsed = result.parsed or {}
    by_path = {f["path"]: f.get("content", "") for f in files}
    proposed = []
    for f in (parsed.get("files") or []):
        path = (f.get("path") or "").strip().lstrip("/")
        after = f.get("after")
        if not path or after is None:
            continue
        before = by_path.get(path, "")
        proposed.append({"path": path, "before": before, "after": after,
                         "diff": _short_diff(before, after)})
    return {
        "ok": True, "fix_id": uuid.uuid4().hex[:12], "has_errors": True,
        "diagnosis": parsed.get("diagnosis") or "(no diagnosis returned)",
        "confidence": parsed.get("confidence") or "medium",
        "fix_summary": parsed.get("fix_summary") or "",
        "next_check": parsed.get("next_check") or "",
        "requires_approval": bool(parsed.get("requires_approval", False)),
        "post_fix_action": parsed.get("post_fix_action") or "restart_runtime",
        "files": proposed, "provider": result.provider, "model": result.model,
    }


@router.post("/projects/{project_id}/runtime/auto-fix/apply")
async def runtime_auto_fix_apply(project_id: str, body: AutoFixApplyIn,
                                 _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not body.files:
        raise HTTPException(status_code=400, detail="No files to apply")

    files = list(doc.get("files", []))
    by_path = {f["path"]: i for i, f in enumerate(files)}
    actually_written: List[str] = []
    for f in body.files:
        path = (f.get("path") or "").strip().lstrip("/")
        after = f.get("after")
        if not path or after is None:
            continue
        if path in by_path:
            files[by_path[path]] = {"path": path, "content": after}
        else:
            files.append({"path": path, "content": after})
            by_path[path] = len(files) - 1
        actually_written.append(path)

    if not actually_written:
        raise HTTPException(status_code=400,
                            detail="No valid file changes — each entry needs both 'path' and 'after'")

    now = datetime.now(timezone.utc).isoformat()
    snap = {
        "id": str(uuid.uuid4()),
        "label": (body.fix_summary or "AI auto-fix")[:120],
        "commit_message": (body.diagnosis or "AI applied an autonomous fix")[:600],
        "type": "auto-fix",
        "files": files,
        "created_at": now,
        "fix_id": body.fix_id,
    }
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"files": files, "updated_at": now},
         "$push": {"versions": snap}},
    )

    restarted = False
    runtime_status = None
    if body.restart_runtime:
        try:
            handle = await rt_svc.restart_runtime(
                project_id, files, _project_env_dict(doc.get("env_vars", [])),
            )
            restarted = True
            runtime_status = handle.status_dict()
        except Exception as e:  # noqa: BLE001
            runtime_status = {"alive": False, "error": str(e)}

    return {
        "ok": True, "fix_id": body.fix_id, "version_id": snap["id"],
        "applied_files": actually_written, "restarted": restarted,
        "runtime": runtime_status,
    }


# ----- Deploy auto-fix -----
def _detect_failing_step(logs: list, error: Optional[str]) -> str:
    """Return a short label for the failing step based on log lines."""
    text = "\n".join(l.get("msg", "") for l in (logs or []))
    if error:
        text += "\n" + error
    lower = text.lower()
    if "npm install" in lower or "yarn install" in lower or "pnpm install" in lower:
        return "dependency-install"
    if "build" in lower and ("failed" in lower or "error" in lower):
        return "build"
    if "deploy" in lower and "failed" in lower:
        return "provider-deploy"
    if any(k in lower for k in ("missing env", "no env", "is not defined", "modulenotfounderror")):
        return "env-or-imports"
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    return "unknown"


def _summarise_logs(logs: list, max_chars: int = 4000) -> str:
    if not logs:
        return ""
    body = "\n".join(f"[{l.get('level','info')}] {l.get('msg','')}" for l in logs[-200:])
    if len(body) > max_chars:
        body = body[-max_chars:]
    return body


@router.post("/projects/{project_id}/deploy/auto-fix")
async def deploy_auto_fix(project_id: str, body: Optional[DeployAutoFixIn] = None,
                          _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")

    deployments = list(doc.get("deployments") or [])
    if not deployments:
        raise HTTPException(status_code=400,
                            detail="No deployments to inspect — kick off a deploy first")

    target = None
    if body and body.deployment_id:
        target = next((d for d in deployments if d.get("id") == body.deployment_id), None)
    if not target:
        # Pick the latest failed deployment, fall back to the latest overall
        failed = [d for d in deployments if d.get("status") == "failed"]
        target = (failed or deployments)[-1]

    status = target.get("status")
    logs = target.get("logs") or []
    error = target.get("error")
    failing_step = _detect_failing_step(logs, error)

    if status not in ("failed", "cancelled") and not error:
        return {
            "ok": True, "fix_id": None, "has_errors": False,
            "deployment_id": target.get("id"),
            "deployment_status": status,
            "failing_step": failing_step,
            "diagnosis": "Deployment did not fail — nothing to fix.",
            "files": [], "fix_summary": "", "requires_approval": False,
        }

    files = doc.get("files", [])
    # Prioritise config files for deploy fixes
    hint_paths = ["package.json", "requirements.txt", "vercel.json", "netlify.toml",
                  "Dockerfile", "Procfile", "backend/server.py", "backend/server.js",
                  "next.config.js", "vite.config.js", ".env.example"]
    candidate = _select_files_for_fix(files, hint_paths=hint_paths, backend_first=False)

    env_keys = [e.get("key") for e in (doc.get("env_vars") or []) if e.get("key")]
    user_prompt = (
        f"DEPLOYMENT FAILURE\n"
        f"  provider: {target.get('provider')}\n"
        f"  status:   {status}\n"
        f"  failing step (heuristic): {failing_step}\n"
        f"  error: {(error or '(none)')[:1000]}\n"
        f"  env vars present: {', '.join(env_keys) or '(none)'}\n\n"
        f"DEPLOY LOGS (most recent):\n{_summarise_logs(logs)}\n\n"
        f"NOTE FROM USER: {(body.note if body else '') or '(none)'}\n\n"
        f"PROJECT CONFIG/CODE:\n{_files_blob(candidate)}\n\n"
        "Diagnose what made the deploy fail. Propose minimal file edits "
        "(package.json deps, requirements.txt, vercel.json, missing env hints, etc). "
        "If the fix needs a new env var, surface that as a SEPARATE entry in `next_check`. "
        "Provide the FULL new content for each file you change. Respond with the JSON now."
    )
    agent = agents_svc.get_agent("devops")
    result = await agent.run(user_prompt)
    parsed = result.parsed or {}

    by_path = {f["path"]: f.get("content", "") for f in files}
    proposed = []
    for f in (parsed.get("files") or []):
        path = (f.get("path") or "").strip().lstrip("/")
        after = f.get("after")
        if not path or after is None:
            continue
        before = by_path.get(path, "")
        proposed.append({"path": path, "before": before, "after": after,
                         "diff": _short_diff(before, after)})

    return {
        "ok": True,
        "fix_id": uuid.uuid4().hex[:12],
        "has_errors": True,
        "deployment_id": target.get("id"),
        "deployment_status": status,
        "deployment_provider": target.get("provider"),
        "failing_step": failing_step,
        "diagnosis": parsed.get("diagnosis") or "(no diagnosis returned)",
        "confidence": parsed.get("confidence") or "medium",
        "fix_summary": parsed.get("fix_summary") or "",
        "next_check": parsed.get("next_check") or "",
        "requires_approval": bool(parsed.get("requires_approval", False)),
        "post_fix_action": parsed.get("post_fix_action") or "redeploy",
        "files": proposed,
        "provider": result.provider,
        "model": result.model,
    }


class DeployAutoFixApplyIn(BaseModel):
    fix_id: str
    deployment_id: Optional[str] = None
    files: List[Dict[str, str]]
    fix_summary: Optional[str] = ""
    diagnosis: Optional[str] = ""
    auto_redeploy: Optional[bool] = True


@router.post("/projects/{project_id}/deploy/auto-fix/apply")
async def deploy_auto_fix_apply(project_id: str, body: DeployAutoFixApplyIn,
                                _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not body.files:
        raise HTTPException(status_code=400, detail="No files to apply")

    files = list(doc.get("files", []))
    by_path = {f["path"]: i for i, f in enumerate(files)}
    actually_written: List[str] = []
    for f in body.files:
        path = (f.get("path") or "").strip().lstrip("/")
        after = f.get("after")
        if not path or after is None:
            continue
        if path in by_path:
            files[by_path[path]] = {"path": path, "content": after}
        else:
            files.append({"path": path, "content": after})
            by_path[path] = len(files) - 1
        actually_written.append(path)
    if not actually_written:
        raise HTTPException(status_code=400, detail="No valid file changes")

    now = datetime.now(timezone.utc).isoformat()
    snap = {
        "id": str(uuid.uuid4()),
        "label": (body.fix_summary or "AI deploy auto-fix")[:120],
        "commit_message": (body.diagnosis or "AI applied a deploy auto-fix")[:600],
        "type": "deploy-auto-fix",
        "files": files,
        "created_at": now,
        "fix_id": body.fix_id,
    }
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"files": files, "updated_at": now},
         "$push": {"versions": snap}},
    )

    redeployed_id = None
    if body.auto_redeploy:
        try:
            from .deployments import _do_deploy
            new_dep = await _do_deploy(project_id, provider_name="internal")
            redeployed_id = new_dep.get("id") if new_dep else None
        except Exception:
            pass

    return {
        "ok": True,
        "fix_id": body.fix_id,
        "version_id": snap["id"],
        "applied_files": actually_written,
        "redeployed_deployment_id": redeployed_id,
    }
