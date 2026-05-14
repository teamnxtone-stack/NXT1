"""AgentOS — REST + WebSocket routes (Phase 22).

Exposes the task runner to the dashboard frontend:

  GET  /api/agentos/agents
  POST /api/agentos/tasks                  body: {agent, payload, label?}
  GET  /api/agentos/tasks                  ?agent=&status=&limit=
  GET  /api/agentos/tasks/{task_id}
  POST /api/agentos/tasks/{task_id}/cancel
  WS   /api/agentos/ws/tasks/{task_id}     live stream of step/log/complete events
  GET  /api/agentos/stats                  for the home dashboard cards
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Optional

from fastapi import (
    APIRouter, Depends, HTTPException, Query, UploadFile, File,
    WebSocket, WebSocketDisconnect,
)
from pydantic import BaseModel, Field

# Side-effect import: registers all agents into agentos_runner.
from services import agentos_agents  # noqa: F401
from services import agentos_runner as ar

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.agentos.routes")
router = APIRouter(prefix="/api/agentos", tags=["agentos-v2"])


# ─── Agent registry ──────────────────────────────────────────────────────
AGENT_META: Dict[str, Dict] = {
    "custom": {
        "id":          "custom",
        "label":       "Custom Agent",
        "icon":        "Sparkles",
        "color":       "#a78bfa",
        "description": "Free-form research / planning. Give it any task; it executes over time.",
        "examples":    [
            "Research top 10 VC firms investing in AI startups",
            "Write a 5-email cold outreach sequence for enterprise clients",
            "Summarize everything happening in AI this week",
            "Find 20 potential customers for a B2B SaaS tool",
        ],
        "engine":      "Claude + DuckDuckGo + web fetch (lightweight OpenHands shape)",
    },
    "job_scout": {
        "id":          "job_scout",
        "label":       "Job Scout",
        "icon":        "Briefcase",
        "color":       "#22d3ee",
        "description": "Scans LinkedIn, Indeed, Glassdoor, ZipRecruiter for relevant roles.",
        "examples":    [
            "Product Manager · Remote",
            "Head of Product · New York",
        ],
        "engine":      "JobSpy (speedyapply/JobSpy)",
    },
    "founders_scout": {
        "id":          "founders_scout",
        "label":       "Founders Scout",
        "icon":        "Users",
        "color":       "#10b981",
        "description": "Scans X / Reddit / GitHub for people seeking technical cofounders.",
        "examples":    [
            "AI cofounder signals on Reddit r/startups",
            "GitHub users with 'looking for cofounder' in bio",
        ],
        "engine":      "Reddit JSON + GitHub Search (X requires API key)",
    },
    "social_strategist": {
        "id":          "social_strategist",
        "label":       "Social Strategist",
        "icon":        "Megaphone",
        "color":       "#f472b6",
        "description": "Generates a week of social content. Pushes to Postiz when configured.",
        "examples":    [
            "7-day content plan for AI / startups, founder tone",
            "5-day plan for ecommerce, casual tone",
        ],
        "engine":      "Claude + Postiz REST (env: POSTIZ_URL, POSTIZ_API_KEY)",
    },
    "resume_tailor": {
        "id":          "resume_tailor",
        "label":       "Resume Tailor",
        "icon":        "FileText",
        "color":       "#fb923c",
        "description": "ATS-grade keyword extraction + truthful tailored rewrite for any job description.",
        "examples":    [
            "Tailor resume for Senior PM @ Stripe",
            "ATS score check against a Staff Engineer JD",
        ],
        "engine":      "Native keyword/cosine scoring + Claude rewrite",
    },
}


@router.get("/agents")
async def list_agents(_: str = Depends(verify_token)):
    return {
        "agents":     list(AGENT_META.values()),
        "registered": ar.list_registered_agents(),
    }


# ─── Tasks ───────────────────────────────────────────────────────────────
class SubmitIn(BaseModel):
    agent:   str = Field(min_length=1)
    payload: Dict
    label:   Optional[str] = None


@router.post("/tasks")
async def submit(body: SubmitIn, user_id: str = Depends(verify_token)):
    if body.agent not in AGENT_META:
        raise HTTPException(status_code=400,
                             detail=f"Unknown agent: {body.agent}")
    try:
        task_id = await ar.submit_task(body.agent, body.payload, user_id,
                                        body.label)
        return {"task_id": task_id, "status": "queued"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.get("/tasks")
async def list_all(
    agent: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user_id: str = Depends(verify_token),
):
    items = await ar.list_tasks(agent=agent, status=status,
                                 user_id=user_id, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/tasks/{task_id}")
async def get_one(task_id: str, _: str = Depends(verify_token)):
    doc = await ar.get_task(task_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    return doc


@router.post("/tasks/{task_id}/cancel")
async def cancel(task_id: str, _: str = Depends(verify_token)):
    ok = await ar.cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=400,
                             detail="Cannot cancel a finished task")
    return {"ok": True}


# ─── WebSocket ───────────────────────────────────────────────────────────
@router.websocket("/ws/tasks/{task_id}")
async def task_ws(websocket: WebSocket, task_id: str):
    # JWT-via-query for WS (browsers can't set Authorization on WS upgrade)
    token = websocket.query_params.get("token") or websocket.query_params.get("auth")
    try:
        # Lightweight auth check — reuses the same JWT verifier
        from ._deps import verify_token_value
        verify_token_value(token or "")
    except Exception:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        async for event in ar.subscribe(task_id):
            await websocket.send_text(json.dumps(event, default=str))
    except WebSocketDisconnect:
        return
    except Exception as e:  # noqa: BLE001
        logger.warning(f"WS error: {e}")
        try:
            await websocket.close()
        except Exception:
            pass


# ─── Stats for the home dashboard ────────────────────────────────────────
@router.get("/stats")
async def stats(user_id: str = Depends(verify_token)):
    out: Dict[str, Dict] = {}
    for agent_id in AGENT_META:
        recent = await ar.list_tasks(agent=agent_id, user_id=user_id, limit=5)
        running = [t for t in recent if t["status"] == "running"]
        last_done = next(
            (t for t in recent if t["status"] in ("done", "failed")),
            None,
        )
        out[agent_id] = {
            "running":     len(running),
            "running_now": running[0]["label"] if running else None,
            "last_done":   last_done["label"] if last_done else None,
            "last_at":     last_done["updated_at"] if last_done else None,
            "status":      "running" if running else "idle",
        }
    return {"agents": out}



# ─── Resume file extraction helper ───────────────────────────────────────
@router.post("/resume/extract")
async def extract_resume(
    file: UploadFile = File(...),
    _: str = Depends(verify_token),
):
    """Extract plain-text from an uploaded PDF / DOCX / TXT resume.

    Returns `{text, filename, char_count}`. The frontend then submits the
    text alongside the JD to the `resume_tailor` agent. Kept stateless on
    purpose so the file never has to hit disk.
    """
    name = (file.filename or "resume").lower()
    raw  = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB).")

    text = ""
    try:
        if name.endswith(".pdf"):
            import io
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                text = "\n\n".join(
                    (page.extract_text() or "") for page in pdf.pages
                )
        elif name.endswith(".docx"):
            import io
            from docx import Document
            doc = Document(io.BytesIO(raw))
            text = "\n".join(p.text for p in doc.paragraphs)
        elif name.endswith(".txt") or name.endswith(".md"):
            text = raw.decode("utf-8", errors="ignore")
        else:
            # Fallback: try utf-8 decode
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as e:
                raise HTTPException(
                    status_code=400,
                    detail="Unsupported file type. Use PDF, DOCX, TXT or paste text.",
                ) from e
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning(f"resume extract failed for {name}: {e}")
        raise HTTPException(status_code=400,
                             detail=f"Couldn't read file: {e}") from None

    text = (text or "").strip()
    if len(text) < 80:
        raise HTTPException(
            status_code=400,
            detail="Couldn't extract enough text — paste your resume manually.",
        )
    return {
        "filename":   file.filename,
        "text":       text,
        "char_count": len(text),
    }
