"""Agent Threads — unified durable task threads.

Replaces the legacy split between `/api/agents/conversations` and
`/api/v1/agentos/*` task surfaces. One canonical model:

  agent_threads {
    id, user_id, project_id?, agent_id, title, status, created_at, updated_at,
    last_run_id, run_count, pinned, archived
  }

  agent_runs {
    id, thread_id, user_id, agent_id, status, started_at, ended_at,
    input, output, error, logs[], messages[], parent_run_id?,
    progress, phase, files_created[]
  }

Behaviour:
  - Thread = persistent conversation with one or more agents.
  - Run = one execution attempt inside a thread (can be forked / re-run).
  - Forking creates a new run with parent_run_id set, message history copied.
  - Cancel sets run.status=cancelled and triggers cooperative stop via job_service.
  - All terminal transitions emit a notification (via routes.notifications.emit).

Surface (all under /api/agents):
  POST   /threads                      create a new thread (optionally seed with first message)
  GET    /threads                      list user's threads (filters: project_id, agent_id, archived)
  GET    /threads/{id}                 single thread + last 50 messages
  PATCH  /threads/{id}                 rename / pin / archive
  DELETE /threads/{id}                 archive (soft delete)
  POST   /threads/{id}/runs            start a new run on the thread
  GET    /threads/{id}/runs            list runs for a thread
  POST   /runs/{id}/cancel             cooperative cancel
  POST   /runs/{id}/fork               fork into a new run with same history
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.agent_threads")

router = APIRouter(prefix="/api/agents", tags=["agent-threads"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Models ─────────────────────────────────────────────────────────────
class ThreadCreate(BaseModel):
    agent_id: str
    title: str = Field(default="Untitled thread")
    project_id: Optional[str] = None
    first_message: Optional[str] = None


class ThreadPatch(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None
    archived: Optional[bool] = None


class RunCreate(BaseModel):
    input: str = Field(..., min_length=1, max_length=10_000)
    agent_id: Optional[str] = None  # override thread's default agent


# ─── Threads ────────────────────────────────────────────────────────────
@router.post("/threads")
async def create_thread(body: ThreadCreate, user_id: str = Depends(verify_token)):
    thread_id = str(uuid.uuid4())
    doc = {
        "id": thread_id,
        "user_id": user_id,
        "project_id": body.project_id,
        "agent_id": body.agent_id,
        "title": body.title[:160],
        "status": "idle",
        "created_at": _now(),
        "updated_at": _now(),
        "last_run_id": None,
        "run_count": 0,
        "pinned": False,
        "archived": False,
    }
    await db.agent_threads.insert_one(dict(doc))
    doc.pop("_id", None)
    # Optionally start an initial run
    if body.first_message:
        run = await _start_run(thread_id, user_id, body.agent_id, body.first_message, parent_run_id=None)
        doc["last_run_id"] = run["id"]
        doc["run_count"] = 1
        await db.agent_threads.update_one(
            {"id": thread_id},
            {"$set": {"last_run_id": run["id"], "run_count": 1, "status": "running", "updated_at": _now()}},
        )
    return doc


@router.get("/threads")
async def list_threads(
    user_id: str = Depends(verify_token),
    project_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    archived: bool = False,
    limit: int = Query(50, le=200),
):
    q: dict = {"user_id": user_id, "archived": archived}
    if project_id:
        q["project_id"] = project_id
    if agent_id:
        q["agent_id"] = agent_id
    cur = db.agent_threads.find(q, {"_id": 0}).sort([("pinned", -1), ("updated_at", -1)]).limit(limit)
    items = await cur.to_list(length=None)
    return {"items": items, "total": len(items)}


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, user_id: str = Depends(verify_token)):
    doc = await db.agent_threads.find_one({"id": thread_id, "user_id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Thread not found")
    runs_cur = db.agent_runs.find({"thread_id": thread_id}, {"_id": 0}).sort("started_at", -1).limit(20)
    runs = await runs_cur.to_list(length=None)
    return {"thread": doc, "runs": runs}


@router.patch("/threads/{thread_id}")
async def patch_thread(thread_id: str, body: ThreadPatch, user_id: str = Depends(verify_token)):
    updates: dict = {"updated_at": _now()}
    if body.title is not None:
        updates["title"] = body.title[:160]
    if body.pinned is not None:
        updates["pinned"] = body.pinned
    if body.archived is not None:
        updates["archived"] = body.archived
    res = await db.agent_threads.update_one(
        {"id": thread_id, "user_id": user_id}, {"$set": updates}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"ok": True}


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, user_id: str = Depends(verify_token)):
    await db.agent_threads.update_one(
        {"id": thread_id, "user_id": user_id},
        {"$set": {"archived": True, "updated_at": _now()}},
    )
    return {"ok": True}


# ─── Runs ───────────────────────────────────────────────────────────────
async def _start_run(thread_id: str, user_id: str, agent_id: str, input_text: str, parent_run_id: Optional[str] = None) -> dict:
    """Persist a new agent_run row in `queued` status and return it.

    The actual execution is launched by job_service or by a router endpoint
    that has the live agent registry. We separate the row from the exec so
    durable storage is always the source of truth — even if the process
    crashes mid-execution, the run row stays as a resumable checkpoint.
    """
    run_id = str(uuid.uuid4())
    doc = {
        "id": run_id,
        "thread_id": thread_id,
        "user_id": user_id,
        "agent_id": agent_id,
        "status": "queued",
        "started_at": _now(),
        "ended_at": None,
        "input": input_text[:10_000],
        "output": None,
        "error": None,
        "logs": [],
        "messages": [{"role": "user", "content": input_text[:10_000], "ts": _now()}],
        "parent_run_id": parent_run_id,
        "progress": 0.0,
        "phase": "queued",
        "files_created": [],
    }
    await db.agent_runs.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.post("/threads/{thread_id}/runs")
async def create_run(thread_id: str, body: RunCreate, user_id: str = Depends(verify_token)):
    thread = await db.agent_threads.find_one({"id": thread_id, "user_id": user_id}, {"_id": 0})
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    agent_id = body.agent_id or thread.get("agent_id") or "custom"
    run = await _start_run(thread_id, user_id, agent_id, body.input)
    await db.agent_threads.update_one(
        {"id": thread_id},
        {"$set": {
            "last_run_id": run["id"], "status": "running", "updated_at": _now(),
        }, "$inc": {"run_count": 1}},
    )
    # Phase G — actually execute the run in the background (durable worker).
    try:
        from services.agent_runs_worker import spawn_run
        spawn_run(run["id"])
    except Exception as e:
        logger.warning(f"could not spawn agent run: {e}")
    return run


@router.get("/threads/{thread_id}/runs")
async def list_runs(thread_id: str, user_id: str = Depends(verify_token), limit: int = Query(20, le=100)):
    thread = await db.agent_threads.find_one({"id": thread_id, "user_id": user_id}, {"_id": 0})
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    cur = db.agent_runs.find({"thread_id": thread_id}, {"_id": 0}).sort("started_at", -1).limit(limit)
    items = await cur.to_list(length=None)
    return {"items": items}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user_id: str = Depends(verify_token)):
    doc = await db.agent_runs.find_one({"id": run_id, "user_id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Run not found")
    return doc


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, user_id: str = Depends(verify_token)):
    """Cooperative cancel. Sets run.status=cancelling and lets the worker
    poll for the flag at the next checkpoint."""
    res = await db.agent_runs.update_one(
        {"id": run_id, "user_id": user_id, "status": {"$in": ["queued", "running"]}},
        {"$set": {"status": "cancelling", "cancel_requested_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Run not found or already terminal")
    return {"ok": True}


@router.post("/runs/{run_id}/fork")
async def fork_run(run_id: str, body: RunCreate, user_id: str = Depends(verify_token)):
    parent = await db.agent_runs.find_one({"id": run_id, "user_id": user_id}, {"_id": 0})
    if not parent:
        raise HTTPException(status_code=404, detail="Parent run not found")
    new_run = await _start_run(
        parent["thread_id"], user_id, body.agent_id or parent["agent_id"],
        body.input, parent_run_id=run_id,
    )
    # Carry message history into the forked run for continuity
    history = parent.get("messages") or []
    if history:
        await db.agent_runs.update_one(
            {"id": new_run["id"]},
            {"$set": {"messages": history + new_run["messages"]}},
        )
    await db.agent_threads.update_one(
        {"id": parent["thread_id"]},
        {"$set": {"last_run_id": new_run["id"], "status": "running", "updated_at": _now()},
         "$inc": {"run_count": 1}},
    )
    return new_run
