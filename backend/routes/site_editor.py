"""AI Site Editor — admin-only meta-builder that lets the operator edit the
NXT1 site itself through natural language.

Flow:
  1. Admin types a prompt: "make the hero green and add a Pricing section"
  2. /api/site-editor/propose calls Claude Sonnet on a curated whitelist of
     source files and returns a structured set of file edits + a summary.
  3. Admin reviews the diff in the UI.
  4. /api/site-editor/apply writes those edits to disk and (optionally) pushes
     to GitHub via github_service. Vercel auto-deploys via its GitHub
     integration. A history record is appended in the `site_edits` collection.
  5. /api/site-editor/history & /api/site-editor/rollback expose the history.

WHITELIST: only files under SAFE_PATHS are exposed to the AI and writable.
This is a safety guarantee against the AI scribbling on infrastructure files
or .env values.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from services import github_service
from services.ai_service import get_active_provider

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.site_editor")

router = APIRouter(prefix="/api/site-editor", tags=["site-editor"])

REPO_ROOT = Path(os.environ.get("NXT1_REPO_ROOT", "/app")).resolve()

# Curated whitelist of files the AI may read & propose edits to. Only files
# under these paths are surfaced to the model and only paths matching this
# list will be applied on disk.
SAFE_PATHS: List[str] = [
    "frontend/src/pages/LandingPage.jsx",
    "frontend/src/pages/SignUpPage.jsx",
    "frontend/src/pages/SignInPage.jsx",
    "frontend/src/pages/OnboardingPage.jsx",
    "frontend/src/pages/PrivacyPage.jsx",
    "frontend/src/pages/TermsPage.jsx",
    "frontend/src/components/Brand.jsx",
    "frontend/src/components/PublicFooter.jsx",
    "frontend/src/components/GradientBackdrop.jsx",
    "frontend/src/index.css",
    "frontend/src/App.css",
]


def _admin_only(sub: str = Depends(verify_token)) -> str:
    if sub != "admin":
        raise HTTPException(status_code=403, detail="Site editor is admin-only")
    return sub


# ----- Models -----
class FileEdit(BaseModel):
    path: str
    content: str  # full new content; absent means delete (not used for v1)


class ProposeIn(BaseModel):
    prompt: str
    paths: Optional[List[str]] = None  # restrict to a subset of SAFE_PATHS


class ProposeOut(BaseModel):
    edit_id: str
    summary: str
    explanation: str
    files: List[FileEdit]


class ApplyIn(BaseModel):
    edit_id: str
    push_to_github: Optional[bool] = True
    repo_name: Optional[str] = "nxt1-platform"
    private: Optional[bool] = True


# ----- Helpers -----
def _safe_read(rel: str) -> Optional[str]:
    if rel not in SAFE_PATHS:
        return None
    p = REPO_ROOT / rel
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _safe_write(rel: str, content: str) -> bool:
    if rel not in SAFE_PATHS:
        return False
    p = REPO_ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return True


SYSTEM_PROMPT = """You are NXT1's site-editor agent. The operator is editing
the NXT1 product's own public site through natural language. They give you a
prompt and the current contents of one or more source files. You return a
JSON object describing the exact replacement contents for each file you wish
to change.

STRICT OUTPUT FORMAT — return EXACTLY this JSON shape, nothing else:
{
  "summary": "<one sentence>",
  "explanation": "<2-4 sentence first-person summary of the changes>",
  "files": [
    {"path": "<exact relative path you were given>", "content": "<full new file contents>"}
  ]
}

RULES:
- Only edit files you were explicitly given.
- ALWAYS return the FULL new content for each file you change. Never partial.
- Preserve every import, prop, data-testid, and existing design system class
  unless the prompt directly asks otherwise.
- Match the existing code style, formatting, and TailwindCSS conventions.
- If the prompt is ambiguous, make the smallest, safest change that is on-tone.
- NEVER touch routing, env vars, auth tokens, or backend code — those aren't
  in the whitelist and will be rejected.
"""


def _build_user_prompt(prompt: str, files_payload: dict) -> str:
    parts = [f"OPERATOR PROMPT:\n{prompt.strip()}\n\nFILES YOU MAY EDIT:\n"]
    for path, content in files_payload.items():
        parts.append(f"\n--- BEGIN {path} ---\n{content}\n--- END {path} ---\n")
    parts.append("\nReturn the JSON object now.")
    return "".join(parts)


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown fences if present
    fence = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except Exception:
        # Find the first { ... last } slice
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            return json.loads(text[first:last + 1])
        raise


# ----- Routes -----
@router.get("/files")
async def list_safe_files(_: str = Depends(_admin_only)):
    """Return the whitelist + their current contents (truncated for UI list)."""
    items = []
    for p in SAFE_PATHS:
        c = _safe_read(p) or ""
        items.append({
            "path": p,
            "size": len(c),
            "preview": c[:280],
        })
    return {"items": items, "repo_root": str(REPO_ROOT)}


@router.post("/propose", response_model=ProposeOut)
async def propose_edit(body: ProposeIn, _: str = Depends(_admin_only)):
    if not body.prompt or not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt required")
    paths = body.paths or SAFE_PATHS
    paths = [p for p in paths if p in SAFE_PATHS]
    if not paths:
        raise HTTPException(status_code=400, detail="No valid files in scope")
    files_payload = {}
    for p in paths:
        c = _safe_read(p)
        if c is not None:
            files_payload[p] = c

    provider = get_active_provider()
    user_prompt = _build_user_prompt(body.prompt, files_payload)
    session_id = f"site-edit-{uuid.uuid4().hex[:8]}"
    try:
        raw = await provider.generate(SYSTEM_PROMPT, user_prompt, session_id)
    except Exception as e:
        logger.exception("AI propose failed")
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}")
    try:
        parsed = _extract_json(raw)
    except Exception as e:
        logger.warning(f"AI returned non-JSON output: {raw[:300]}")
        raise HTTPException(status_code=502, detail=f"AI returned invalid output: {e}")

    edits: List[FileEdit] = []
    for f in parsed.get("files", []) or []:
        path = (f.get("path") or "").lstrip("/")
        if path not in SAFE_PATHS:
            continue
        edits.append(FileEdit(path=path, content=f.get("content") or ""))

    if not edits:
        raise HTTPException(status_code=502,
                            detail="AI didn't return any valid file edits. Try a more specific prompt.")

    edit_id = f"edit_{uuid.uuid4().hex[:12]}"
    record = {
        "edit_id": edit_id,
        "prompt": body.prompt,
        "summary": parsed.get("summary") or "Update site",
        "explanation": parsed.get("explanation") or "",
        "files": [e.model_dump() for e in edits],
        "status": "proposed",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.site_edits.insert_one(record)
    return ProposeOut(
        edit_id=edit_id,
        summary=record["summary"],
        explanation=record["explanation"],
        files=edits,
    )


@router.post("/apply")
async def apply_edit(body: ApplyIn, background: BackgroundTasks,
                     _: str = Depends(_admin_only)):
    rec = await db.site_edits.find_one({"edit_id": body.edit_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Edit not found")
    if rec.get("status") == "applied":
        raise HTTPException(status_code=409, detail="Edit already applied")

    # Capture pre-edit snapshot for rollback
    snapshot = {}
    written = []
    try:
        for fe in rec["files"]:
            path = fe["path"]
            if path not in SAFE_PATHS:
                continue
            snapshot[path] = _safe_read(path) or ""
            if not _safe_write(path, fe["content"]):
                raise HTTPException(status_code=400, detail=f"Refused to write {path}")
            written.append(path)
    except Exception:
        # Best-effort rollback if mid-write failure
        for p, c in snapshot.items():
            try:
                _safe_write(p, c)
            except Exception:
                pass
        raise

    push_result = None
    if body.push_to_github:
        # Build a project-shaped doc for the existing github_service
        project_doc = {
            "id": rec["edit_id"],
            "name": body.repo_name or "nxt1-platform",
            "files": [{"path": f["path"], "content": f["content"]} for f in rec["files"]],
        }
        try:
            push_result = github_service.save_project_to_github(
                project_doc,
                repo_name=body.repo_name or "nxt1-platform",
                private=bool(body.private if body.private is not None else True),
                commit_message=f"NXT1 site-editor: {rec.get('summary') or rec.get('prompt')[:60]}",
            )
        except github_service.GitHubError as e:
            logger.warning(f"site-editor github push failed: {e}")
            push_result = {"error": str(e)}
        except Exception as e:
            logger.exception("github push unexpected failure")
            push_result = {"error": f"GitHub push failed: {e}"}

    await db.site_edits.update_one(
        {"edit_id": body.edit_id},
        {"$set": {
            "status": "applied",
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "snapshot": snapshot,
            "github": push_result,
        }},
    )
    try:
        from services import audit_service
        await audit_service.record(
            db, tool="site-editor", action="apply",
            target=", ".join(written)[:200],
            status="ok" if (push_result is None or "error" not in (push_result or {})) else "partial",
            after={"files_written": written, "commit_sha": (push_result or {}).get("commit_sha")},
            details={"edit_id": body.edit_id},
        )
    except Exception:
        pass
    return {
        "ok": True,
        "edit_id": body.edit_id,
        "files_written": written,
        "github": push_result,
    }


@router.get("/history")
async def history(_: str = Depends(_admin_only)):
    cur = db.site_edits.find({}, {"_id": 0, "snapshot": 0}).sort("created_at", -1).limit(50)
    items = await cur.to_list(length=50)
    return {"items": items}


async def _do_rollback(edit_id: str) -> dict:
    """Rollback helper exposed for the audit service to call."""
    rec = await db.site_edits.find_one({"edit_id": edit_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Edit not found")
    if rec.get("status") != "applied":
        raise HTTPException(status_code=400, detail="Only applied edits can be rolled back")
    snap = rec.get("snapshot") or {}
    if not snap:
        raise HTTPException(status_code=400, detail="No snapshot available to roll back to")
    written = []
    for path, content in snap.items():
        if path not in SAFE_PATHS:
            continue
        if _safe_write(path, content):
            written.append(path)
    await db.site_edits.update_one(
        {"edit_id": edit_id},
        {"$set": {
            "status": "rolled_back",
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"ok": True, "rolled_back": written}


@router.post("/rollback/{edit_id}")
async def rollback(edit_id: str, _: str = Depends(_admin_only)):
    return await _do_rollback(edit_id)
