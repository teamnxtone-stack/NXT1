"""Durable workflow service (Track B — LangGraph).

A StateGraph that drives the planner → architect → coder → tester → debugger → deployer
pipeline with MongoDB-backed checkpointing so a workflow survives:
  - server restarts
  - user disconnects
  - explicit pauses (waiting for human approval)

Public API:
  start_workflow(project_id, prompt, user_id) -> workflow_id
  get_workflow(workflow_id) -> dict (state + history)
  resume_workflow(workflow_id, approval=None) -> dict
  cancel_workflow(workflow_id) -> dict
  list_workflows(project_id=None, status=None) -> list

The graph is intentionally non-LLM-heavy at each node — actual generation is
already handled by the existing chat-stream/builder pipeline. Each node here
records a phase transition + emits agent events. The point of LangGraph here
is durability, retry, and human-in-the-loop, NOT replacing the streaming generator.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, TypedDict

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("nxt1.workflows")

# Lazy imports — keep server boot fast even if langgraph install hiccups.
_LG_AVAILABLE: Optional[bool] = None
_StateGraph = None
_END = None


def _ensure_langgraph():
    """Lazy-load LangGraph. Returns True if available."""
    global _LG_AVAILABLE, _StateGraph, _END
    if _LG_AVAILABLE is not None:
        return _LG_AVAILABLE
    try:
        from langgraph.graph import END, StateGraph  # type: ignore

        _StateGraph = StateGraph
        _END = END
        _LG_AVAILABLE = True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"LangGraph unavailable, falling back to in-process executor: {e}")
        _LG_AVAILABLE = False
    return _LG_AVAILABLE


# ---------- Mongo handle (separate from routes/_deps to avoid circular) ----------
_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
_db = _client[os.environ["DB_NAME"]]
COL = _db.workflows


# ---------- State schema ----------
class WorkflowState(TypedDict, total=False):
    workflow_id: str
    project_id: str
    user_id: str
    prompt: str
    status: Literal["queued", "running", "waiting", "completed", "failed", "cancelled"]
    current_phase: str
    history: List[Dict[str, Any]]
    plan: Optional[Dict[str, Any]]
    test_results: Optional[Dict[str, Any]]
    deploy_target: Optional[str]
    error: Optional[str]
    attempts: int
    requires_approval: bool
    created_at: str
    updated_at: str


PHASES = ["planner", "architect", "coder", "tester", "debugger", "deployer"]
AGENT_FOR_PHASE = {
    "planner": "planner",
    "architect": "architect",
    "coder": "coder",
    "tester": "tester",
    "debugger": "debugger",
    "deployer": "devops",
}


# ---------- Node implementations ----------
async def _record_phase(state: WorkflowState, phase: str, agent: str, message: str,
                        status: str = "running", extra: Optional[Dict] = None) -> WorkflowState:
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "phase": phase,
        "agent": agent,
        "message": message,
        "status": status,
        "at": now,
    }
    if extra:
        entry.update(extra)
    history = list(state.get("history") or [])
    history.append(entry)
    state["history"] = history
    state["current_phase"] = phase
    state["updated_at"] = now
    await COL.update_one(
        {"workflow_id": state["workflow_id"]},
        {"$set": {
            "history": history,
            "current_phase": phase,
            "status": state.get("status", "running"),
            "updated_at": now,
        }},
    )
    return state


async def node_planner(state: WorkflowState) -> WorkflowState:
    state["status"] = "running"
    await _record_phase(state, "planner", "planner",
                        "Decomposing prompt into a build plan...", status="running")
    # Pull inference (deterministic, no LLM cost)
    try:
        from services.inference_service import infer_project_kind  # noqa
        inf = infer_project_kind(state["prompt"])
        plan = {
            "kind": inf.kind,
            "framework": inf.framework,
            "rationale": inf.rationale,
            "steps": [
                {"step": "infer", "detail": f"Project kind: {inf.kind} ({inf.framework})"},
                {"step": "scaffold", "detail": f"Inject the {inf.kind} scaffold pack."},
                {"step": "build", "detail": "Generate requested features."},
                {"step": "test", "detail": "Smoke checks."},
                {"step": "deploy", "detail": "Hand off to chosen hosting target."},
            ],
        }
        state["plan"] = plan
        await _record_phase(state, "planner", "planner",
                            f"Plan ready: {inf.kind}/{inf.framework}",
                            status="done", extra={"plan": plan})
    except Exception as e:  # noqa: BLE001
        state["error"] = f"planner failed: {e}"
        state["status"] = "failed"
        await _record_phase(state, "planner", "planner",
                            f"Planner failed: {e}", status="failed")
    return state


async def node_architect(state: WorkflowState) -> WorkflowState:
    await _record_phase(state, "architect", "architect",
                        "Picking premium UI blocks + project structure...", status="running")
    # Pull from UI registry to bias generation
    try:
        from routes.ui_registry import load_registry  # noqa
        reg = load_registry()
        plan = state.get("plan") or {}
        kind_to_blocks = {"hero": [], "feature": [], "card": []}
        for b in reg.get("blocks", []):
            k = b.get("kind")
            if k in kind_to_blocks:
                kind_to_blocks[k].append(b.get("id"))
        plan["ui_blocks_proposed"] = {
            "hero": (kind_to_blocks["hero"] or [None])[0],
            "features": (kind_to_blocks["feature"] or [None])[0],
            "cards": (kind_to_blocks["card"] or [None])[0],
        }
        state["plan"] = plan
        await _record_phase(state, "architect", "architect",
                            f"Selected premium blocks: {plan['ui_blocks_proposed']}",
                            status="done")
    except Exception as e:  # noqa: BLE001
        await _record_phase(state, "architect", "architect",
                            f"Architect note: registry unavailable ({e})",
                            status="done")
    return state


async def node_coder(state: WorkflowState) -> WorkflowState:
    await _record_phase(state, "coder", "coder",
                        "Builder is generating files via streaming chat...",
                        status="running")
    # NOTE: actual code generation is owned by the existing /chat/stream pipeline
    # so the user can watch the cinematic stream in real time. This node just
    # records the handoff. A subsequent UI step will reconcile the workflow's
    # `coder` phase as "done" once the chat stream completes.
    await _record_phase(state, "coder", "coder",
                        "Builder handoff complete — see chat stream for file emission.",
                        status="done")
    return state


_ENTRY_PATHS = frozenset({
    "index.html",
    "src/main.tsx", "src/main.jsx", "src/main.js",
    "app/page.tsx", "app/page.jsx",
})


def _has_entry(files: list) -> bool:
    """Return True if the file list contains any recognised entry-point path.

    Shared by `node_tester` and `reconcile_coder_phase` so the two paths
    can never drift apart on what "build healthy" means.
    """
    return any((f.get("path") or "").lower() in _ENTRY_PATHS for f in (files or []))


async def node_tester(state: WorkflowState) -> WorkflowState:
    await _record_phase(state, "tester", "tester",
                        "Running structural checks on generated files...",
                        status="running")
    # Pull current project files
    try:
        from routes._deps import db as proj_db  # avoid circular at import
        doc = await proj_db.projects.find_one({"id": state["project_id"]}, {"_id": 0, "files": 1})
        files = (doc or {}).get("files", [])
        has_entry = _has_entry(files)
        results = {
            "file_count": len(files),
            "has_entry": has_entry,
            "ok": has_entry,
        }
        state["test_results"] = results
        status = "done" if has_entry else "failed"
        msg = f"{len(files)} file(s) emitted; entry present: {has_entry}"
        await _record_phase(state, "tester", "tester", msg, status=status,
                            extra={"results": results})
        if not has_entry:
            # Trigger debugger
            state["status"] = "running"
    except Exception as e:  # noqa: BLE001
        await _record_phase(state, "tester", "tester",
                            f"Tester error: {e}", status="failed")
    return state


async def node_debugger(state: WorkflowState) -> WorkflowState:
    # Debugger runs only if tester failed; bounded by attempts.
    results = state.get("test_results") or {}
    if results.get("ok", True):
        return state
    attempts = state.get("attempts", 0) + 1
    state["attempts"] = attempts
    max_attempts = int(os.environ.get("WORKFLOW_MAX_RETRIES", "3"))
    if attempts > max_attempts:
        state["status"] = "failed"
        state["error"] = f"Exceeded {max_attempts} repair attempts."
        await _record_phase(state, "debugger", "debugger",
                            state["error"], status="failed")
        return state
    await _record_phase(state, "debugger", "debugger",
                        f"Repair attempt {attempts}/{max_attempts}: re-routing through coder.",
                        status="running",
                        extra={"attempt": attempts, "max_attempts": max_attempts})
    # Loop back to coder happens via the graph edges below.
    return state


async def node_deployer(state: WorkflowState) -> WorkflowState:
    """Auto-complete the deploy hand-off — runs in the background, no UI popup.

    Previously this set status='waiting' + requires_approval=True so users
    had to click "Approve & deploy". We removed that interruption per UX
    feedback: builds finish silently and users hit Deploy explicitly when
    they're ready.
    """
    target = state.get("deploy_target") or "internal"
    await _record_phase(state, "deployer", "devops",
                        f"Deploy hand-off prepared (target: {target}).",
                        status="completed")
    state["status"] = "completed"
    state["requires_approval"] = False
    await COL.update_one(
        {"workflow_id": state["workflow_id"]},
        {"$set": {"status": "completed", "requires_approval": False}},
    )
    return state


# ---------- Graph wiring ----------
def _build_graph():
    """Build LangGraph StateGraph. Falls back to in-process linear runner."""
    if not _ensure_langgraph():
        return None
    sg = _StateGraph(WorkflowState)
    sg.add_node("planner", node_planner)
    sg.add_node("architect", node_architect)
    sg.add_node("coder", node_coder)
    sg.add_node("tester", node_tester)
    sg.add_node("debugger", node_debugger)
    sg.add_node("deployer", node_deployer)

    sg.set_entry_point("planner")
    sg.add_edge("planner", "architect")
    sg.add_edge("architect", "coder")
    sg.add_edge("coder", "tester")

    def tester_router(state: WorkflowState):
        results = state.get("test_results") or {}
        if results.get("ok", True):
            return "deployer"
        return "debugger"

    sg.add_conditional_edges("tester", tester_router, {
        "deployer": "deployer",
        "debugger": "debugger",
    })

    def debugger_router(state: WorkflowState):
        if state.get("status") == "failed":
            return _END
        return "coder"

    sg.add_conditional_edges("debugger", debugger_router, {
        "coder": "coder",
        _END: _END,
    })

    sg.add_edge("deployer", _END)
    return sg.compile()


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


# ---------- Public API ----------
async def start_workflow(project_id: str, prompt: str, user_id: str = "admin",
                         deploy_target: Optional[str] = None) -> Dict:
    workflow_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    state: WorkflowState = {
        "workflow_id": workflow_id,
        "project_id": project_id,
        "user_id": user_id,
        "prompt": prompt[:4000],
        "status": "queued",
        "current_phase": "queued",
        "history": [],
        "plan": None,
        "test_results": None,
        "deploy_target": deploy_target or "internal",
        "error": None,
        "attempts": 0,
        "requires_approval": False,
        "created_at": now,
        "updated_at": now,
    }
    await COL.insert_one(dict(state))

    # Execute the graph in background — survives the HTTP call.
    asyncio.create_task(_run_to_completion(state))
    return {"workflow_id": workflow_id, "status": "queued"}


async def _run_to_completion(state: WorkflowState) -> None:
    """Drive the graph until completion / waiting / failure."""
    graph = get_graph()
    try:
        if graph is None:
            # Fallback: linear execution
            for fn in [node_planner, node_architect, node_coder, node_tester,
                       node_debugger, node_deployer]:
                state = await fn(state)
                if state.get("status") in ("failed", "waiting"):
                    break
        else:
            # LangGraph async execution. astream surfaces intermediate states
            # which we already persist inside each node.
            async for _ in graph.astream(state):
                pass
        # If we reach here and status was never marked terminal, mark completed.
        final = await COL.find_one({"workflow_id": state["workflow_id"]}, {"_id": 0})
        if final and final.get("status") in (None, "running", "queued"):
            await COL.update_one(
                {"workflow_id": state["workflow_id"]},
                {"$set": {"status": "completed",
                          "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
    except Exception as e:  # noqa: BLE001
        logger.exception("workflow run failed")
        await COL.update_one(
            {"workflow_id": state["workflow_id"]},
            {"$set": {"status": "failed", "error": str(e)[:400],
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
        )


async def get_workflow(workflow_id: str) -> Optional[Dict]:
    doc = await COL.find_one({"workflow_id": workflow_id}, {"_id": 0})
    return doc


async def list_workflows(project_id: Optional[str] = None,
                          status: Optional[str] = None,
                          limit: int = 50) -> List[Dict]:
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    cursor = COL.find(q, {"_id": 0}).sort("updated_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def resume_workflow(workflow_id: str, approval: Optional[bool] = True) -> Dict:
    doc = await COL.find_one({"workflow_id": workflow_id}, {"_id": 0})
    if not doc:
        return {"ok": False, "error": "not found"}
    if doc.get("status") != "waiting":
        return {"ok": False, "error": f"cannot resume; status={doc.get('status')}"}
    if not approval:
        await COL.update_one(
            {"workflow_id": workflow_id},
            {"$set": {"status": "cancelled",
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True, "status": "cancelled"}
    now = datetime.now(timezone.utc).isoformat()
    history = list(doc.get("history") or [])
    history.append({
        "phase": "deployer", "agent": "devops",
        "message": "User approved deploy hand-off — marking workflow complete.",
        "status": "done", "at": now,
    })
    await COL.update_one(
        {"workflow_id": workflow_id},
        {"$set": {"status": "completed", "requires_approval": False,
                  "history": history, "updated_at": now}},
    )
    return {"ok": True, "status": "completed"}


async def cancel_workflow(workflow_id: str) -> Dict:
    res = await COL.update_one(
        {"workflow_id": workflow_id, "status": {"$nin": ["completed", "failed"]}},
        {"$set": {"status": "cancelled",
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": res.modified_count > 0}


async def reconcile_coder_phase(project_id: str, files_count: int = 0,
                                 explanation: str = "") -> Optional[Dict]:
    """When the chat-stream pipeline finishes emitting files, mark the most
    recent non-terminal workflow for this project's `coder` phase as `done`
    and advance the tester (it re-evaluates the now-real file count).

    Called from /chat/stream success path. Best-effort: never raises.
    """
    try:
        doc = await COL.find_one(
            {"project_id": project_id,
             "status": {"$in": ["queued", "running", "waiting"]}},
            sort=[("created_at", -1)],
            projection={"_id": 0},
        )
        if not doc:
            return None
        history = list(doc.get("history") or [])
        # Replace the last `coder` "running"/"handoff" entry with a `done` one
        for entry in reversed(history):
            if entry.get("phase") == "coder" and entry.get("status") != "done":
                entry["status"] = "done"
                entry["message"] = (
                    f"Builder finished — {files_count} file(s) persisted."
                )
                break
        # Append a reconciliation event
        now = datetime.now(timezone.utc).isoformat()
        history.append({
            "phase": "coder",
            "agent": "coder",
            "message": f"Files reconciled from chat stream ({files_count} files).",
            "status": "done",
            "at": now,
            "files_count": files_count,
        })
        # Re-run tester with real file data — uses the shared _has_entry helper
        # so this stays in lockstep with node_tester.
        proj_db_handle = _db  # reuse our own client
        proj = await proj_db_handle.projects.find_one(
            {"id": project_id}, {"_id": 0, "files": 1})
        files = (proj or {}).get("files", [])
        has_entry = _has_entry(files)
        results = {"file_count": len(files), "has_entry": has_entry, "ok": has_entry}
        history.append({
            "phase": "tester",
            "agent": "tester",
            "message": f"Re-check after stream: {len(files)} files, entry={has_entry}.",
            "status": "done" if has_entry else "failed",
            "at": now,
            "results": results,
        })
        # If tester now passes, advance to deployer (waiting for approval)
        next_status = "waiting" if has_entry else "running"
        if has_entry:
            history.append({
                "phase": "deployer",
                "agent": "devops",
                "message": "Build healthy — awaiting deploy approval.",
                "status": "waiting",
                "at": now,
            })
        await COL.update_one(
            {"workflow_id": doc["workflow_id"]},
            {"$set": {
                "history": history,
                "status": next_status,
                "test_results": results,
                "requires_approval": bool(has_entry),
                "current_phase": "deployer" if has_entry else "tester",
                "updated_at": now,
            }},
        )
        return {"workflow_id": doc["workflow_id"], "reconciled": True,
                "files_count": len(files), "tester_ok": has_entry}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reconcile_coder_phase failed: {e}")
        return None
