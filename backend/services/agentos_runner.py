"""AgentOS — background task runner (Phase 22).

In-process Celery-shaped runner that:
  * persists every task in `db.agentos_tasks` (status, logs, steps, result)
  * executes the task in an asyncio background task (so the HTTP request
    returns immediately, mimicking Celery semantics)
  * streams progress to subscribed WebSockets via a per-task channel

For production self-hosting, swap `submit_task()` to push onto a real
Celery queue — the persistence shape stays identical.

Public API:
    submit_task(agent, payload, user_id) -> task_id
    get_task(task_id) -> dict
    list_tasks(agent=None, status=None, limit=50) -> list
    cancel_task(task_id) -> bool
    push_step(task_id, step) -> None   (called from agent code)
    push_log(task_id, line, level)     (called from agent code)
    complete_task(task_id, result, status="done")
    subscribe(task_id) -> async generator of events
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("nxt1.agentos")

_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
_db = _client[os.environ["DB_NAME"]]
TASKS = _db.agentos_tasks

# WebSocket fan-out: task_id -> set of asyncio.Queue
_SUBSCRIBERS: Dict[str, set] = defaultdict(set)
# Registered agent handlers: agent_name -> async callable(task_dict)
_AGENTS: Dict[str, Callable] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_agent(name: str):
    """Decorator: @register_agent('custom') async def run(task): ..."""
    def deco(fn: Callable):
        _AGENTS[name] = fn
        logger.info(f"agentos: registered '{name}' agent")
        return fn
    return deco


async def submit_task(agent: str, payload: Dict, user_id: str = "admin",
                      label: Optional[str] = None) -> str:
    """Create a task row + kick off the agent. Returns task_id."""
    if agent not in _AGENTS:
        raise ValueError(f"Unknown agent: {agent}. Available: {list(_AGENTS)}")
    task_id = uuid.uuid4().hex
    doc = {
        "task_id":   task_id,
        "agent":     agent,
        "user_id":   user_id,
        "label":     (label or payload.get("title") or
                      payload.get("prompt") or f"{agent} task")[:140],
        "payload":   payload,
        "status":    "queued",
        "steps":     [],
        "logs":      [],
        "result":    None,
        "error":     None,
        "created_at": _now(),
        "updated_at": _now(),
        "started_at": None,
        "completed_at": None,
    }
    await TASKS.insert_one(doc)
    asyncio.create_task(_run_task_safely(task_id, agent))
    return task_id


async def _run_task_safely(task_id: str, agent_name: str) -> None:
    """Wrap agent.run() with status transitions + error capture."""
    handler = _AGENTS.get(agent_name)
    if not handler:
        await complete_task(task_id, None, status="failed",
                            error=f"Unknown agent {agent_name}")
        return
    await TASKS.update_one(
        {"task_id": task_id},
        {"$set": {"status": "running", "started_at": _now(),
                  "updated_at": _now()}},
    )
    await _broadcast(task_id, {"type": "status", "status": "running"})
    doc = await TASKS.find_one({"task_id": task_id}, {"_id": 0})
    try:
        result = await handler(doc)
        await complete_task(task_id, result, status="done")
    except asyncio.CancelledError:
        await complete_task(task_id, None, status="cancelled",
                            error="Cancelled by user")
    except Exception as e:  # noqa: BLE001
        logger.exception(f"agentos task {task_id} failed")
        await complete_task(task_id, None, status="failed", error=str(e)[:400])


async def push_step(task_id: str, label: str, status: str = "running",
                    detail: Optional[str] = None) -> None:
    step = {
        "id":     uuid.uuid4().hex[:8],
        "label":  label,
        "status": status,
        "detail": detail,
        "at":     _now(),
    }
    await TASKS.update_one(
        {"task_id": task_id},
        {"$push": {"steps": step}, "$set": {"updated_at": _now()}},
    )
    await _broadcast(task_id, {"type": "step", "step": step})


async def push_log(task_id: str, line: str, level: str = "info") -> None:
    entry = {"line": line, "level": level, "at": _now()}
    await TASKS.update_one(
        {"task_id": task_id},
        {"$push": {"logs": {"$each": [entry], "$slice": -500}},
         "$set":  {"updated_at": _now()}},
    )
    await _broadcast(task_id, {"type": "log", "entry": entry})


async def complete_task(task_id: str, result: Any,
                        status: str = "done",
                        error: Optional[str] = None) -> None:
    await TASKS.update_one(
        {"task_id": task_id},
        {"$set": {
            "status":      status,
            "result":      result,
            "error":       error,
            "completed_at": _now(),
            "updated_at":  _now(),
        }},
    )
    await _broadcast(task_id, {"type": "complete",
                                "status": status,
                                "result": result,
                                "error":  error})


async def get_task(task_id: str) -> Optional[Dict]:
    doc = await TASKS.find_one({"task_id": task_id}, {"_id": 0})
    return _sanitize(doc) if doc else None


async def list_tasks(agent: Optional[str] = None,
                     status: Optional[str] = None,
                     user_id: Optional[str] = None,
                     limit: int = 50) -> List[Dict]:
    q: Dict[str, Any] = {}
    if agent:   q["agent"]   = agent
    if status:  q["status"]  = status
    if user_id: q["user_id"] = user_id
    cur = TASKS.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    rows = await cur.to_list(length=limit)
    return [_sanitize(r) for r in rows]


def _sanitize(obj):
    """Recursively strip NaN / Infinity / -Infinity / pandas NaT from a
    document so it survives the strict default `json.dumps` Starlette uses.
    Without this, a single bad value (e.g. JobSpy `salary_min: NaN`) makes
    the whole /tasks list return 500.
    """
    import math
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_sanitize(v) for v in obj)
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


async def cancel_task(task_id: str) -> bool:
    res = await TASKS.update_one(
        {"task_id": task_id, "status": {"$in": ["queued", "running"]}},
        {"$set": {"status": "cancelled", "updated_at": _now()}},
    )
    if res.modified_count:
        await _broadcast(task_id, {"type": "status", "status": "cancelled"})
    return bool(res.modified_count)


# ─── WebSocket fan-out ───────────────────────────────────────────────────
async def _broadcast(task_id: str, event: Dict) -> None:
    listeners = list(_SUBSCRIBERS.get(task_id, []))
    for q in listeners:
        try:
            q.put_nowait(event)
        except Exception:
            pass


async def subscribe(task_id: str) -> AsyncIterator[Dict]:
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    _SUBSCRIBERS[task_id].add(q)
    try:
        # Replay current state on subscribe so late joiners catch up.
        doc = await get_task(task_id)
        if doc:
            yield {"type": "snapshot", "task": doc}
            if doc["status"] in ("done", "failed", "cancelled"):
                return
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30)
                yield event
                if event.get("type") == "complete":
                    return
            except asyncio.TimeoutError:
                yield {"type": "heartbeat", "at": _now()}
    finally:
        _SUBSCRIBERS[task_id].discard(q)


def list_registered_agents() -> List[str]:
    return list(_AGENTS.keys())
