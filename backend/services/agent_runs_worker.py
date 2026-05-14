"""Agent Runs Worker — durable executor for `agent_runs` rows.

Counterpart to `workflow_service.resume_orphaned_workflows`:
  - A queued/running run with no live process gets re-spawned.
  - The actual execution drives through `services.ai_service` (provider chain)
    so the user's own ANTHROPIC_API_KEY / OPENAI_API_KEY / etc. powers it.
  - Cooperative cancel via `status == "cancelling"` polled before each token.

Each run terminates with one of: completed | failed | cancelled.
On any terminal transition we emit a bell notification.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("nxt1.agent_runs")

_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
_db     = _client[os.environ["DB_NAME"]]

_RUNNING_RUNS: Dict[str, asyncio.Task] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _register_task(run_id: str, task: asyncio.Task) -> None:
    _RUNNING_RUNS[run_id] = task
    task.add_done_callback(lambda _t: _RUNNING_RUNS.pop(run_id, None))


async def _emit_notification(user_id: str, *, kind: str, title: str, body: str = "", link: str | None = None, meta: dict | None = None) -> None:
    try:
        from routes import notifications as _notifs
        await _notifs.emit(user_id, kind=kind, title=title, body=body, link=link, meta=meta)
    except Exception as e:
        logger.debug(f"notification emit skipped: {e}")


async def _append_log(run_id: str, level: str, msg: str) -> None:
    await _db.agent_runs.update_one(
        {"id": run_id},
        {"$push": {"logs": {"level": level, "msg": msg[:500], "ts": _now()}}},
    )


async def _cancel_requested(run_id: str) -> bool:
    doc = await _db.agent_runs.find_one({"id": run_id}, {"_id": 0, "status": 1})
    return bool(doc and doc.get("status") == "cancelling")


async def execute_run(run_id: str) -> None:
    """Execute a single queued run end-to-end.

    Pulls the run + its thread, builds a conversation from `messages`,
    streams the response token-by-token from the configured provider,
    appends an assistant message, and marks the run completed.
    """
    run = await _db.agent_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        return
    if run["status"] not in ("queued", "running"):
        return  # someone already finished it

    user_id = run["user_id"]
    thread_id = run["thread_id"]

    try:
        await _db.agent_runs.update_one(
            {"id": run_id, "status": {"$in": ["queued", "running"]}},
            {"$set": {"status": "running", "phase": "thinking", "progress": 0.1}},
        )
        await _append_log(run_id, "info", f"Run started — agent={run['agent_id']}")

        # Build provider via shared registry. Uses ANTHROPIC_API_KEY /
        # OPENAI_API_KEY / EMERGENT_LLM_KEY (whatever the user has set).
        from services.providers.registry import registry
        from services.providers.base import RouteIntent

        intent = RouteIntent(task="agent-router", routing_mode="auto")
        try:
            provider = registry.resolve(intent)
        except Exception as e:
            raise RuntimeError(f"No AI provider available: {e}")

        # Conversation = prior messages from this run (forks carry parent history).
        messages = run.get("messages") or []
        system = (
            "You are an NXT1 agent helping the user accomplish a task. "
            "Be concise, direct, and accurate. If asked to write code or build "
            "files, return them in fenced code blocks with a leading // path/to/file "
            "comment so the orchestrator can persist them."
        )
        # Use the most recent user message as the live prompt; earlier ones
        # serve as conversation context.
        user_prompt = ""
        history_lines = []
        for m in messages:
            role = m.get("role")
            content = (m.get("content") or "")[:6000]
            if role == "user":
                user_prompt = content
                history_lines.append(f"User: {content}")
            elif role == "assistant":
                history_lines.append(f"Assistant: {content}")
        full_prompt = "\n".join(history_lines[-12:])

        # Stream tokens; check cancel between chunks.
        await _db.agent_runs.update_one(
            {"id": run_id},
            {"$set": {"phase": "streaming", "progress": 0.3}},
        )
        chunks: list[str] = []
        try:
            async for delta in provider.generate_stream(system, full_prompt or user_prompt, run_id):
                if not delta:
                    continue
                chunks.append(delta)
                # Cancel check every ~10 chunks
                if len(chunks) % 10 == 0 and await _cancel_requested(run_id):
                    raise asyncio.CancelledError()
        except asyncio.CancelledError:
            await _db.agent_runs.update_one(
                {"id": run_id},
                {"$set": {"status": "cancelled", "ended_at": _now(),
                          "phase": "cancelled", "progress": 1.0,
                          "output": "".join(chunks)[:20_000]}},
            )
            await _db.agent_threads.update_one(
                {"id": thread_id}, {"$set": {"status": "idle", "updated_at": _now()}},
            )
            await _append_log(run_id, "warn", "Cancelled by user")
            return
        except Exception:
            # Streaming failed — try blocking call as a fallback so the user
            # still gets a response.
            text = await provider.generate(system, full_prompt or user_prompt, run_id)
            chunks = [text or ""]

        output = "".join(chunks).strip() or "(no output)"
        await _db.agent_runs.update_one(
            {"id": run_id},
            {"$set": {
                "status": "completed",
                "ended_at": _now(),
                "phase": "completed",
                "progress": 1.0,
                "output": output[:20_000],
            }, "$push": {"messages": {"role": "assistant", "content": output[:20_000], "ts": _now()}}},
        )
        await _db.agent_threads.update_one(
            {"id": thread_id},
            {"$set": {"status": "idle", "updated_at": _now()}},
        )
        await _append_log(run_id, "info", "Run completed")
        await _emit_notification(
            user_id, kind="agent_done",
            title=f"Agent finished — {run['agent_id']}",
            body=output[:280],
            link=f"/agents/threads/{thread_id}",
            meta={"run_id": run_id, "thread_id": thread_id},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"agent run {run_id} failed: {e}")
        await _db.agent_runs.update_one(
            {"id": run_id},
            {"$set": {"status": "failed", "ended_at": _now(),
                      "phase": "failed", "error": str(e)[:400]}},
        )
        await _db.agent_threads.update_one(
            {"id": thread_id}, {"$set": {"status": "idle", "updated_at": _now()}},
        )
        await _append_log(run_id, "error", f"Failed: {str(e)[:300]}")
        await _emit_notification(
            user_id, kind="agent_failed",
            title=f"Agent failed — {run['agent_id']}",
            body=str(e)[:280],
            link=f"/agents/threads/{thread_id}",
            meta={"run_id": run_id, "thread_id": thread_id},
        )


def spawn_run(run_id: str) -> None:
    """Fire-and-forget — start execution in a background task, register it
    so the recovery sweeper doesn't re-spawn while it's live."""
    if run_id in _RUNNING_RUNS and not _RUNNING_RUNS[run_id].done():
        return
    task = asyncio.create_task(execute_run(run_id))
    _register_task(run_id, task)


async def resume_orphaned_runs() -> dict:
    """Recovery sweeper — runs in `queued`/`running` with no live task get
    re-spawned. Older than 24h with no progress → marked failed."""
    cutoff_dead = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    resumed = 0
    dropped = 0
    cur = _db.agent_runs.find(
        {"status": {"$in": ["queued", "running"]}},
        {"_id": 0, "id": 1, "started_at": 1, "user_id": 1, "thread_id": 1},
    )
    async for doc in cur:
        rid = doc["id"]
        if rid in _RUNNING_RUNS and not _RUNNING_RUNS[rid].done():
            continue
        if (doc.get("started_at") or "") < cutoff_dead:
            await _db.agent_runs.update_one(
                {"id": rid},
                {"$set": {"status": "failed", "error": "Stalled — auto-failed by recovery sweep",
                          "ended_at": _now()}},
            )
            dropped += 1
            continue
        try:
            spawn_run(rid)
            resumed += 1
        except Exception as e:
            logger.warning(f"could not resume run {rid}: {e}")
    if resumed or dropped:
        logger.info(f"agent run recovery: resumed={resumed} dropped={dropped}")
    return {"resumed": resumed, "dropped": dropped}
