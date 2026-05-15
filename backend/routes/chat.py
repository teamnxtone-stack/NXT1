"""Chat / AI generation routes (Phase 8 modular refactor).

Includes:
- GET  /projects/{id}/messages
- POST /projects/{id}/chat        (non-streaming)
- POST /projects/{id}/chat/stream (SSE)
- POST /projects/{id}/debug
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, field_validator

from services import ai_service, job_service
from services.ai_service import AIProviderError, generate_project, is_imported_project, merge_with_protection
from services.inference_service import infer_project_kind
from services.scaffolds import build_scaffold, pack_kinds

from ._deps import db, verify_token
from .deployments import _do_deploy

logger = logging.getLogger("nxt1.chat")

router = APIRouter(prefix="/api", tags=["chat"])


# ─── Conversational gate ────────────────────────────────────────────────
# Stops the build pipeline from firing on greetings, questions, or unclear
# intent. Returns True only when the message looks like an actual build /
# edit instruction. Errs on the side of "conversation first, build later".
_BUILD_VERBS = (
    "build", "create", "make", "generate", "scaffold", "design", "code",
    "implement", "add", "wire up", "wire", "set up", "setup", "ship",
    "deploy", "remove", "delete", "fix", "rename", "refactor", "convert",
    "turn into", "redesign", "revamp", "edit", "update", "change", "rewrite",
    "replace", "swap", "extract", "split", "merge", "migrate", "port",
    "improve", "polish", "tighten", "simplify", "rebuild", "regenerate",
    "add a", "add an", "add the", "make the", "make a", "make it",
    "give me", "build me", "create me",
)
_GREETING_PATTERNS = (
    "hi", "hello", "hey", "yo", "sup", "hola", "howdy",
    "good morning", "good afternoon", "good evening", "gm", "ga", "ge",
    "thanks", "thank you", "thx", "ty", "ok", "okay", "cool", "nice",
    "great", "awesome", "what's up", "whats up",
)
_QUESTION_HINTS = ("?", "can you", "could you", "would you", "do you", "are you",
                   "what is", "what's", "how do", "how does", "why ", "when ",
                   "where ", "who ", "tell me about", "explain")


def classify_intent(message: str, has_prior_messages: bool = False) -> dict:
    """Light-weight intent classifier. Returns {intent, confidence, reason}.

    intent ∈ {"build", "edit", "chat", "ambiguous"}.

    We deliberately do NOT call an LLM here — the classifier is fast,
    deterministic, and reliable for the obvious cases. Genuinely ambiguous
    inputs fall through to "chat" so the assistant responds first.
    """
    raw = (message or "").strip()
    if not raw:
        return {"intent": "chat", "confidence": 1.0, "reason": "empty"}
    lower = raw.lower()
    word_count = len(raw.split())
    # 1. Pure greeting / single-word ack: always chat.
    if word_count <= 3 and any(lower == g or lower.startswith(g + " ") or lower.startswith(g + "!") for g in _GREETING_PATTERNS):
        return {"intent": "chat", "confidence": 0.98, "reason": "greeting"}
    # 2. Ends with a question mark AND no build verb in first 6 words: chat.
    leading = " ".join(raw.split()[:6]).lower()
    if any(h in lower for h in _QUESTION_HINTS) and not any(v in leading for v in _BUILD_VERBS):
        return {"intent": "chat", "confidence": 0.85, "reason": "question"}
    # 3. Clear build verb at the start: build.
    first_word = raw.split()[0].lower().rstrip(",.!?")
    if first_word in {"build", "create", "make", "generate", "design", "scaffold", "ship", "spin", "build me", "create me"}:
        return {"intent": "build" if not has_prior_messages else "edit", "confidence": 0.95, "reason": "verb-start"}
    # 4. Any build verb anywhere AND >5 words: build/edit.
    if word_count > 5 and any(v in lower for v in _BUILD_VERBS):
        return {"intent": "build" if not has_prior_messages else "edit", "confidence": 0.78, "reason": "verb-in-prompt"}
    # 5. Very short non-question, no verb: chat (treat as ack/chitchat).
    if word_count <= 6 and "?" not in raw:
        return {"intent": "chat", "confidence": 0.7, "reason": "short-statement"}
    # 6. Long descriptive prompt, no greeting, no question: assume build on
    #    blank project, edit on existing.
    if word_count >= 10:
        return {"intent": "build" if not has_prior_messages else "edit", "confidence": 0.6, "reason": "long-descriptive"}
    return {"intent": "ambiguous", "confidence": 0.4, "reason": "fallthrough"}



def _looks_like_default_scaffold(files: list) -> bool:
    """Heuristic: a project is 'blank' if it only has the original default
    scaffold files (index.html + styles/main.css + scripts/app.js + README.md)
    and nothing else has been written yet.
    """
    if not files:
        return True
    paths = {f.get("path") for f in files}
    default_paths = {"index.html", "styles/main.css", "scripts/app.js", "README.md"}
    # If the project's paths are exactly the default set (or a subset of it),
    # it's still blank.
    return paths.issubset(default_paths)


def _merge_scaffold_files(existing: list, scaffold_files: list) -> list:
    """Replace the existing default scaffold with the new one. Existing files
    not in the new scaffold are kept; existing files that share a path with
    the new scaffold are overwritten by the new content.
    """
    by_path = {f["path"]: f for f in existing}
    for sf in scaffold_files:
        by_path[sf["path"]] = sf
    return list(by_path.values())


# ---------- Models ----------
class ChatIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: str = ""
    provider: Optional[str] = None  # "openai" | "anthropic" | "emergent"

    @field_validator("message", mode="before")
    @classmethod
    def _v_message(cls, v):
        if v is None:
            return ""
        return str(v)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    role: str
    content: str
    explanation: Optional[str] = None
    created_at: str
    provider: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None              # "completed" | "failed"
    tool_receipts: Optional[List[dict]] = None
    phases: Optional[List[str]] = None
    build_summary: Optional[dict] = None
    error: Optional[dict] = None              # {message, stage, raw_preview, at}
    timeline: Optional[List[dict]] = None     # [{phase, at, ms_since_start}]
    validation: Optional[dict] = None         # ValidationReport.to_dict()
    protocol_used: Optional[str] = None       # "tag" | "json"

    @field_validator("content", "role", "id", "created_at", mode="before")
    @classmethod
    def _v_required_str(cls, v):
        # Persist legacy / partial messages without 422-ing out.
        if v is None:
            return ""
        return str(v)


class DebugIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    error_text: Optional[str] = ""
    note: Optional[str] = ""



async def _conversational_reply_stream(project_id: str, doc: dict, user_message: str, intent_info: dict):
    """Stream a conversational SSE reply when the user isn't asking to build.

    Wire format matches the existing chat stream just enough for the frontend
    to render:
      data: {"type": "start"}
      data: {"type": "chunk", "delta": "..."}     (repeated)
      data: {"type": "complete", "message": {...}, "intent": "chat"}
    """
    import asyncio
    from fastapi.responses import StreamingResponse
    from services.providers.registry import registry
    from services.providers.base import RouteIntent

    now = datetime.now(timezone.utc).isoformat()
    user_msg_id = str(uuid.uuid4())
    user_msg = {"id": user_msg_id, "role": "user", "content": user_message,
                "explanation": None, "created_at": now}

    # Persist the user message right away so reloads keep history.
    try:
        await db.projects.update_one(
            {"id": project_id},
            {"$push": {"messages": user_msg},
             "$set": {"updated_at": now}},
        )
    except Exception:
        pass

    # Build a tight context for the model.
    file_count = len(doc.get("files") or [])
    project_name = doc.get("name") or "this project"
    history = doc.get("messages") or []
    history_lines = []
    for m in history[-8:]:
        role = "User" if m.get("role") == "user" else "Assistant"
        content = (m.get("content") or "")[:600]
        history_lines.append(f"{role}: {content}")
    history_block = "\n".join(history_lines)

    system_prompt = (
        "You are the NXT One assistant — a friendly, direct, premium AI partner for founders "
        "building software. The user is currently in the builder for project "
        f"'{project_name}' (currently {file_count} files).\n\n"
        "STYLE: warm but concise, founder-to-founder. No emoji clutter. No filler. "
        "Be conversational, not robotic. Address what they're asking. "
        "If they greet you, greet them back and ask what they want to build or change. "
        "If they ask a question about the project / their codebase / a concept, answer it directly. "
        "If they're hinting at a build request but it's vague, ask one clarifying question THEN "
        "describe what you'll do — do NOT start generating code yet. "
        "Never invent code blocks or file diffs in a conversational turn. "
        "Keep replies under ~5 short lines unless they ask for detail."
    )
    user_prompt = (
        (f"Recent chat:\n{history_block}\n\n" if history_block else "")
        + f"User just said: {user_message.strip()[:2000]}\n\n"
        "Respond conversationally. Do NOT produce code, file blocks, JSON, or markdown headings. "
        "If they want you to build something, acknowledge it and outline the plan in 1-3 sentences "
        "without writing the code — that step comes next."
    )

    async def event_gen():
        yield f"data: {json.dumps({'type': 'start', 'mode': 'chat'})}\n\n"
        try:
            intent = RouteIntent(task="agent-router", routing_mode="auto", tier=None)
            provider = registry.resolve(intent)
            chunks: list[str] = []
            try:
                async for delta in provider.generate_stream(system_prompt, user_prompt, project_id):
                    if not delta:
                        continue
                    chunks.append(delta)
                    yield f"data: {json.dumps({'type': 'chunk', 'delta': delta})}\n\n"
                    await asyncio.sleep(0)
            except Exception:
                # Fall back to blocking
                text = await provider.generate(system_prompt, user_prompt, project_id)
                chunks = [text or ""]
                yield f"data: {json.dumps({'type': 'chunk', 'delta': text})}\n\n"
            reply = "".join(chunks).strip() or "I'm here. What do you want to build today?"
        except Exception as e:  # noqa: BLE001
            reply = f"(Conversation fallback) {str(e)[:160]}"
            yield f"data: {json.dumps({'type': 'chunk', 'delta': reply})}\n\n"

        # Persist assistant message
        assistant_msg = {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": reply,
            "explanation": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": "chat",
            "intent_info": intent_info,
        }
        try:
            await db.projects.update_one(
                {"id": project_id},
                {"$push": {"messages": assistant_msg},
                 "$set": {"updated_at": assistant_msg["created_at"]}},
            )
        except Exception:
            pass
        yield f"data: {json.dumps({'type': 'complete', 'message': assistant_msg, 'intent': 'chat'})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



# ---------- Runtime context (shared with AI prompt) ----------
def _build_runtime_ctx(project_id: str, project_doc: dict) -> Optional[dict]:
    try:
        from services import runtime_service as _rt
        handle = _rt.get_handle(project_id)
    except Exception:
        handle = None
    files = project_doc.get("files") or []
    has_backend = any(f["path"].startswith("backend/") for f in files)
    if not has_backend and not handle:
        return None
    env_keys = [e.get("key") for e in (project_doc.get("env_vars") or []) if e.get("key")]
    endpoints: list = []
    if handle:
        endpoints = handle.endpoints_full or []
    else:
        try:
            from services.runtime_service import _detect_endpoints_full
            endpoints = _detect_endpoints_full(files)
        except Exception:
            endpoints = []
    backend_origin = os.environ.get("BACKEND_PUBLIC_ORIGIN", "").rstrip("/")
    proxy_url = f"{backend_origin}/api/runtime/{project_id}" if backend_origin else None
    deploy_slug = project_doc.get("deploy_slug")
    deployed_url = (
        f"{backend_origin}/api/deploy/{deploy_slug}"
        if (backend_origin and deploy_slug and project_doc.get("deployed"))
        else None
    )
    return {
        "endpoints": endpoints,
        "env_keys": env_keys,
        "proxy_url": proxy_url,
        "deployed_url": deployed_url,
        "runtime_alive": bool(handle and handle.is_alive()),
    }


# ---------- Routes ----------
@router.get("/projects/{project_id}/messages", response_model=List[ChatMessage])
async def get_messages(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "messages": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return [ChatMessage(**m) for m in doc.get("messages", [])]


@router.post("/projects/{project_id}/chat/stream")
async def chat_stream(project_id: str, body: ChatIn,
                      request: Request,
                      auth: Optional[str] = Query(None),
                      protocol: Optional[str] = Query(None),
                      authorization: Optional[str] = Header(None)):
    """SSE chat stream.

    `protocol` (optional):
        - omitted / "auto"           → smart default (tag if project has >5 files, else JSON)
        - "json" / "blob" / "legacy" → force JSON-blob path
        - "tag" / "tags" / "nxt1"    → force streaming-tag protocol
    """
    token_str = authorization or (f"Bearer {auth}" if auth else None)
    verify_token(token_str)

    # Resolve protocol selector once per request.
    #   • explicit query param wins
    #   • else NXT1_DEFAULT_PROTOCOL env wins
    #   • else "auto" — pick tag for incremental edits on non-trivial existing
    #     projects (>5 files), keep JSON for blank-start full builds. Tag mode
    #     is 10-100x cheaper for surgical edits; JSON mode is more reliable
    #     for blank-canvas full-app generation today.
    _proto_raw = (protocol or os.environ.get("NXT1_DEFAULT_PROTOCOL") or "auto").lower().strip()
    _existing_doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "files": 1})
    _file_count = len((_existing_doc or {}).get("files") or [])
    if _proto_raw in {"tag", "tags", "nxt1", "nxt1-tags"}:
        use_tag_protocol = True
    elif _proto_raw in {"json", "blob", "legacy"}:
        use_tag_protocol = False
    else:  # "auto" / unknown
        use_tag_protocol = _file_count > 5

    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")

    runtime_ctx = _build_runtime_ctx(project_id, doc)

    # Phase H — Conversational gate.
    # If the user is just chatting (greeting, question, ack), DON'T fire the
    # build pipeline. Stream a conversational reply via the provider and
    # persist it as a normal assistant message. The build only runs when the
    # user actually asks to create or edit something.
    _prior_messages = doc.get("messages") or []
    _has_prior_assistant = any(m.get("role") == "assistant" for m in _prior_messages)
    _intent_info = classify_intent(body.message, has_prior_messages=_has_prior_assistant)
    if _intent_info["intent"] in ("chat", "ambiguous"):
        return await _conversational_reply_stream(
            project_id=project_id,
            doc=doc,
            user_message=body.message,
            intent_info=_intent_info,
        )


    now = datetime.now(timezone.utc).isoformat()
    user_msg = {"id": str(uuid.uuid4()), "role": "user", "content": body.message,
                "explanation": None, "created_at": now}
    snapshot = {"id": str(uuid.uuid4()),
                "label": f"Before: {body.message[:60]}",
                "created_at": now, "files": doc.get("files", [])}

    # ------------------------------------------------------------------
    # BACKGROUND-PERSISTENT BUILD ARCHITECTURE
    # ------------------------------------------------------------------
    # The AI generation runs as a real `asyncio.create_task` that's parented
    # to the event loop, NOT the request. This means:
    #   • SSE client streams events live for as long as they're connected.
    #   • If the user closes the tab / navigates away, the background task
    #     keeps running to completion and writes the final result to MongoDB.
    #   • When the user returns, GET /messages shows the completed build.
    #   • job_service tracks status for the resumable-jobs banner.
    #
    # A shared `asyncio.Queue` is the bridge: the background task writes
    # events, the SSE handler reads them. On disconnect the SSE handler
    # bails, but the background task keeps draining its generator.

    import asyncio  # local — keeps top of file clean

    event_queue: asyncio.Queue = asyncio.Queue()
    DONE_SENTINEL = object()

    # State accumulated by the background task (survives disconnect)
    state = {
        "final_files": None,            # type: Optional[list]
        "final_explanation": "Updated files.",
        "final_provider": None,
        "final_model": None,
        "tool_receipts": [],
        "phases": [],
        "error_payload": None,
        "cancelled": None,              # set if user pressed Stop mid-stream
        "raw_stream_acc": [],
        # Build telemetry (Phase B orchestration surface). Persisted on the
        # assistant message so the workspace can render a cinematic timeline.
        "timeline": [],                 # [{phase, at, ms_since_start}]
        "validation": None,             # latest ValidationReport.to_dict()
        "protocol_used": "tag" if use_tag_protocol else "json",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    import time as _t
    _build_start = _t.monotonic()

    async def run_build_in_background(job_id: str):
        """Drives the AI generator to completion + persists everything to
        MongoDB. Lives in its own task so it survives client disconnect."""
        # Cancel check: query the job's status; True if user requested cancel.
        async def _cancel_check() -> bool:
            try:
                j = await db.jobs.find_one({"id": job_id}, {"_id": 0, "status": 1})
                return bool(j and j.get("status") == "cancelled")
            except Exception:
                return False

        try:
            # --------------------------------------------------------
            # PRE-AI INTELLIGENT INFERENCE + SCAFFOLDING
            # --------------------------------------------------------
            # If this is the first build on a blank project, infer the
            # right foundation (Next.js / Vite / Expo / etc.) and inject
            # those scaffold files BEFORE the AI starts editing. This
            # makes NXT1 feel like it "understands what you're building".
            #
            # The inference result is surfaced to the SSE client as a
            # `phase` event so the cinematic UI can show the foundation
            # being loaded, and persisted to projects.analysis.inference
            # for audit / future builds.
            current_files_for_build = doc.get("files", [])
            inference_payload = None
            history_has_assistant = any(
                m.get("role") != "user" for m in (doc.get("messages") or [])
            )
            try:
                if _looks_like_default_scaffold(current_files_for_build) and not history_has_assistant:
                    inf = infer_project_kind(body.message)
                    inference_payload = inf.to_dict()
                    # Emit inference phase to SSE
                    try:
                        event_queue.put_nowait({
                            "type": "phase",
                            "label": f"Inferring foundation \u00b7 {inf.framework}",
                            "inference": inference_payload,
                        })
                    except Exception:
                        pass
                    state["phases"].append(f"Inferring foundation \u00b7 {inf.framework}")
                    # Build + merge scaffold
                    if inf.kind in pack_kinds():
                        scaffold_files = build_scaffold(inf.kind, doc.get("name") or "NXT1 Project")
                        current_files_for_build = _merge_scaffold_files(
                            current_files_for_build, scaffold_files,
                        )
                        # Emit scaffold tool receipts (one per file) for UX
                        for sf in scaffold_files:
                            try:
                                event_queue.put_nowait({
                                    "type": "tool",
                                    "action": "scaffold",
                                    "path": sf["path"],
                                })
                            except Exception:
                                pass
                        # Persist scaffolded files + inference to project NOW so a
                        # disconnect mid-build still leaves us in a coherent state.
                        try:
                            await db.projects.update_one(
                                {"id": project_id},
                                {"$set": {
                                    "files": current_files_for_build,
                                    "template_kind": inf.kind,
                                    "framework": inf.framework,
                                    "analysis.inference": inference_payload,
                                    "updated_at": datetime.now(timezone.utc).isoformat(),
                                }},
                            )
                        except Exception:
                            logger.exception("scaffold persist failed (continuing)")
                        try:
                            event_queue.put_nowait({
                                "type": "phase",
                                "label": f"Foundation loaded \u00b7 {inf.framework}",
                                "inference": inference_payload,
                            })
                        except Exception:
                            pass
                        state["phases"].append(f"Foundation loaded \u00b7 {inf.framework}")
            except Exception:
                logger.exception("inference/scaffold pass failed (continuing)")

            # Select streaming generator based on requested protocol.
            if use_tag_protocol:
                from services.ai_service_tag import generate_project_stream_tag
                _gen = generate_project_stream_tag(
                    user_message=body.message,
                    current_files=current_files_for_build,
                    history=doc.get("messages", []),
                    project_id=project_id,
                    preferred_provider=body.provider,
                    runtime_ctx=runtime_ctx,
                    cancel_check=_cancel_check,
                )
            else:
                _gen = ai_service.generate_project_stream(
                    user_message=body.message,
                    current_files=current_files_for_build,
                    history=doc.get("messages", []),
                    project_id=project_id,
                    preferred_provider=body.provider,
                    runtime_ctx=runtime_ctx,
                    cancel_check=_cancel_check,
                )
            async for ev in _gen:
                # Push event to SSE queue (non-blocking — SSE may have left)
                try:
                    event_queue.put_nowait(ev)
                except Exception:
                    pass
                # Update state regardless of whether SSE is reading
                t = ev.get("type")
                if t == "chunk":
                    delta = ev.get("delta")
                    if delta:
                        state["raw_stream_acc"].append(delta)
                elif t == "phase":
                    state["phases"].append(ev.get("label"))
                    # Persistent timeline (orchestration surface)
                    state["timeline"].append({
                        "phase": ev.get("label"),
                        "at": datetime.now(timezone.utc).isoformat(),
                        "ms_since_start": int((_t.monotonic() - _build_start) * 1000),
                    })
                    try:
                        await job_service.append_log(
                            db, job_id, "info", ev.get("label", ""),
                            phase=ev.get("label"),
                            progress=min(0.9, 0.1 + 0.1 * len(state["phases"])),
                        )
                    except Exception:
                        pass
                elif t == "validate":
                    state["validation"] = ev.get("report")
                elif t == "tool":
                    state["tool_receipts"].append({
                        "action": ev.get("action"),
                        "path": ev.get("path"),
                    })
                elif t == "done":
                    state["final_files"] = ev["files"]
                    state["final_explanation"] = ev.get("explanation") or state["final_explanation"]
                    state["final_provider"] = ev.get("provider")
                    state["final_model"] = ev.get("model")
                elif t == "error":
                    state["error_payload"] = {
                        "message": ev.get("message"),
                        "stage": ev.get("stage"),
                        "raw_preview": ev.get("raw_preview"),
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                elif t == "cancelled":
                    # User pressed Stop. Record on state; the generator returns
                    # next iteration. _persist_build_state will write a
                    # 'cancelled' assistant message instead of success/failure.
                    state["cancelled"] = {
                        "stage": ev.get("stage", "unknown"),
                        "partial_size": ev.get("partial_size", 0),
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
        except asyncio.CancelledError:
            # Only happens if explicit task.cancel() — we don't do that
            raise
        except Exception as e:
            logger.exception("Background build failed")
            state["error_payload"] = {
                "message": f"Stream failed: {e}",
                "stage": "stream",
                "raw_preview": None,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                event_queue.put_nowait({"type": "error", "message": str(e), "stage": "stream"})
            except Exception:
                pass
        finally:
            # Persist final state to MongoDB. This runs whether or not the
            # SSE client is still connected — that's the whole point.
            await _persist_build_state(
                project_id=project_id,
                user_msg=user_msg,
                snapshot=snapshot,
                state=state,
                job_id=job_id,
                publish_on_save=bool(doc.get("publish_on_save")),
                event_queue=event_queue,
                original_files=doc.get("files") or [],
                project_doc=doc,
            )
            try:
                event_queue.put_nowait(DONE_SENTINEL)
            except Exception:
                pass

    async def event_stream():
        # Persistent job — survives the SSE stream so the user can see status
        # after refresh/leave/return.
        job = await job_service.start(
            db, kind="build", project_id=project_id, actor="admin",
            initial_logs=[{"ts": datetime.now(timezone.utc).isoformat(),
                           "level": "info", "msg": f"prompt: {body.message[:120]}"}],
        )
        job_id = job["id"]

        # Spawn the BACKGROUND task — this is the key to persistence
        build_task = asyncio.create_task(run_build_in_background(job_id))

        yield f"data: {json.dumps({'type':'job', 'job_id': job_id})}\n\n"
        yield f"data: {json.dumps({'type':'user_message','message':user_msg})}\n\n"

        disconnected = False
        try:
            while True:
                # Heartbeat / disconnect check every 1s
                try:
                    ev = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    # No event yet — check if client is still here
                    try:
                        if await request.is_disconnected():
                            disconnected = True
                            break
                    except Exception:
                        disconnected = True
                        break
                    continue

                if ev is DONE_SENTINEL:
                    break

                # If client is gone, stop yielding (task keeps draining state)
                if not disconnected:
                    try:
                        if await request.is_disconnected():
                            disconnected = True
                    except Exception:
                        disconnected = True

                if not disconnected:
                    yield f"data: {json.dumps(ev)}\n\n"

                # On "done" or "error", surface the assistant_message event
                # IF the build task has already persisted state (which it does
                # in `finally`). We synthesize the event for the live client.
                if ev.get("type") == "done" and not disconnected:
                    # State has been persisted by the background task's finally;
                    # build the assistant_msg view here from state for the client
                    assistant_msg = _build_assistant_msg(state)
                    yield f"data: {json.dumps({'type':'assistant_message','message':assistant_msg})}\n\n"
                    if doc.get("publish_on_save"):
                        # Auto-deploy notification (the actual deploy is queued
                        # by _persist_build_state via the background task)
                        yield f"data: {json.dumps({'type':'auto_deploy','queued':True})}\n\n"
                    yield f"data: {json.dumps({'type':'end'})}\n\n"
        except Exception as e:
            logger.exception("SSE handler failed (build task continues in background)")
            if not disconnected:
                yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"
        # IMPORTANT: do NOT cancel build_task — let it run to natural completion
        # in the background. Its `finally` block will persist results to MongoDB.

    return StreamingResponse(
        event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _push_event(event_queue, ev: dict) -> None:
    """Best-effort push into the SSE event queue.

    Safe to call from any persistence path even after the client has
    disconnected — the queue will drain regardless.
    """
    try:
        event_queue.put_nowait(ev)
    except Exception:
        pass


def _build_assistant_msg(state: dict) -> dict:
    """Build the assistant message dict from streaming state (used by both the
    live SSE client and the background persistence)."""
    tool_receipts = state.get("tool_receipts") or []
    return {
        "id": str(uuid.uuid4()),
        "role": "assistant",
        "content": state.get("final_explanation") or "Updated files.",
        "explanation": state.get("final_explanation"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": state.get("final_provider"),
        "model": state.get("final_model"),
        "status": "completed",
        "tool_receipts": tool_receipts,
        "phases": state.get("phases") or [],
        # Orchestration surface: persistent timeline + validation report so
        # the UI can render a cinematic build log without re-running the AI.
        "timeline": state.get("timeline") or [],
        "validation": state.get("validation"),
        "protocol_used": state.get("protocol_used"),
        "build_summary": {
            "created": sum(1 for r in tool_receipts if r["action"] == "created"),
            "edited":  sum(1 for r in tool_receipts if r["action"] == "edited"),
            "viewed":  sum(1 for r in tool_receipts if r["action"] == "viewed"),
            "deleted": sum(1 for r in tool_receipts if r["action"] == "deleted"),
            "actions": ["preview", "share", "deploy", "github"],
        },
    }


async def _persist_build_state(*, project_id: str, user_msg: dict, snapshot: dict,
                                state: dict, job_id: str,
                                publish_on_save: bool,
                                event_queue,
                                original_files: Optional[list] = None,
                                project_doc: Optional[dict] = None) -> None:
    """Final DB write for a build — runs from the background task so it
    completes whether or not the SSE client is still connected.

    Applies precision-editing guardrails: for imported projects, protected
    paths (package.json, configs, lockfiles, public/) get their original
    content restored UNLESS the user's prompt explicitly mentioned them.
    """
    # Cancelled path (user pressed Stop mid-stream)
    if state.get("cancelled"):
        partial_raw = "".join(state.get("raw_stream_acc") or [])
        cancel_meta = state["cancelled"]
        cancelled_msg = {
            "id": str(uuid.uuid4()), "role": "assistant",
            "content": "Build cancelled by user.",
            "explanation": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "cancelled",
            "phases": state.get("phases") or [],
            "tool_receipts": state.get("tool_receipts") or [],
            "cancelled": cancel_meta,
            "error": {
                "message": f"Cancelled at stage: {cancel_meta.get('stage')}",
                "stage": "cancelled",
                "raw_preview": partial_raw[-2000:] if partial_raw else None,
                "at": cancel_meta.get("at"),
            },
        }
        try:
            await db.projects.update_one(
                {"id": project_id},
                {"$push": {"messages": {"$each": [user_msg, cancelled_msg]}}},
            )
            # job_service status will already be 'cancelled' (set by the
            # cancel endpoint), so we just append a final log line. No status
            # flip — the job is already in its terminal cancelled state.
            try:
                await job_service.append_log(
                    db, job_id, "info",
                    f"Generator bailed at stage={cancel_meta.get('stage')} "
                    f"(partial {cancel_meta.get('partial_size', 0)} bytes)",
                )
            except Exception:
                pass
        except Exception:
            logger.exception("persist cancelled path failed")
        # Tell the live SSE client so the chat shows the cancelled bubble.
        _push_event(event_queue, {"type": "assistant_message", "message": cancelled_msg})
        return

    # Error path
    if state.get("error_payload") and not state.get("final_files"):
        err_msg = {
            "id": str(uuid.uuid4()), "role": "assistant",
            "content": f"Generation failed: {state['error_payload']['message']}",
            "explanation": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "error": state["error_payload"],
            "phases": state.get("phases") or [],
        }
        try:
            await db.projects.update_one(
                {"id": project_id},
                {"$push": {"messages": {"$each": [user_msg, err_msg]}}},
            )
            await job_service.fail(
                db, job_id, state["error_payload"]["message"],
                partial_result={"raw_preview": state["error_payload"].get("raw_preview")},
            )
        except Exception:
            logger.exception("persist error path failed")
        # Surface the failed message to the live SSE client — without this
        # the FE just sees "Editing files…" forever and the user has no idea
        # the build failed (2026-05-13 bugfix from user report).
        _push_event(event_queue, {"type": "assistant_message", "message": err_msg})
        return

    # No-files (build never produced anything)
    if not state.get("final_files"):
        partial_raw = "".join(state.get("raw_stream_acc") or [])
        interrupted_msg = {
            "id": str(uuid.uuid4()), "role": "assistant",
            "content": "Build incomplete — partial output saved.",
            "explanation": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "interrupted",
            "phases": state.get("phases") or [],
            "tool_receipts": state.get("tool_receipts") or [],
            "error": {
                "message": "Stream ended before completion.",
                "stage": "stream",
                "raw_preview": partial_raw[-2000:] if partial_raw else None,
                "at": datetime.now(timezone.utc).isoformat(),
            },
        }
        try:
            await db.projects.update_one(
                {"id": project_id},
                {"$push": {"messages": {"$each": [user_msg, interrupted_msg]}}},
            )
            await job_service.fail(
                db, job_id, "No files produced",
                partial_result={"raw_preview": partial_raw[-4000:] if partial_raw else None,
                                "phases": state.get("phases") or []},
            )
        except Exception:
            logger.exception("persist no-files path failed")
        # Surface to live SSE client — same fix as the error path above.
        _push_event(event_queue, {"type": "assistant_message", "message": interrupted_msg})
        return

    # ---- PRECISION-EDITING GUARDRAILS ----
    # For imported projects, restore protected paths (package.json, configs,
    # lockfiles, public/) UNLESS the user explicitly mentioned them. This
    # prevents the AI from accidentally wiping framework configuration.
    final_files = state["final_files"]
    reverted: list = []
    try:
        if project_doc and is_imported_project(project_doc):
            final_files, reverted = merge_with_protection(
                current_files=original_files or [],
                new_files=final_files,
                user_message=user_msg.get("content") or "",
                is_imported_project=True,
            )
            if reverted:
                logger.info(
                    f"Precision guard: reverted {len(reverted)} protected path(s): {reverted[:5]}"
                )
                # Notify the live SSE client (best-effort)
                try:
                    event_queue.put_nowait({
                        "type": "info",
                        "message": (
                            f"Preserved {len(reverted)} framework/config file(s) "
                            "you didn't ask to change."
                        ),
                        "reverted_paths": reverted[:10],
                    })
                except Exception:
                    pass
    except Exception:
        logger.exception("precision guard failed (continuing without it)")

    # Success — save files, message, version snapshot, then mark job completed
    assistant_msg = _build_assistant_msg(state)
    if reverted:
        # Surface reverted paths in the assistant message for transparency
        assistant_msg.setdefault("build_summary", {})
        assistant_msg["build_summary"]["preserved_paths"] = reverted[:20]
    try:
        await db.projects.update_one(
            {"id": project_id},
            {
                "$set": {"files": final_files,
                         "updated_at": datetime.now(timezone.utc).isoformat()},
                "$push": {
                    "messages": {"$each": [user_msg, assistant_msg]},
                    "versions": {"$each": [snapshot], "$slice": -50},
                },
            },
        )
        await job_service.complete(db, job_id, status="completed", result={
            "files_count": len(final_files),
            "explanation": (state.get("final_explanation") or "")[:240],
            "phases": state.get("phases") or [],
            "preserved_paths": reverted[:20] if reverted else None,
        })
        # Reconcile any in-flight LangGraph workflow for this project:
        # flip coder → done, re-run tester with real files, surface
        # deployer awaiting-approval state.
        try:
            from services.workflow_service import reconcile_coder_phase
            recon = await reconcile_coder_phase(
                project_id, files_count=len(final_files),
                explanation=(state.get("final_explanation") or "")[:240],
            )
            if recon:
                try:
                    event_queue.put_nowait({
                        "type": "workflow_reconciled",
                        "workflow_id": recon.get("workflow_id"),
                        "files_count": recon.get("files_count"),
                        "tester_ok": recon.get("tester_ok"),
                    })
                except Exception:
                    pass
        except Exception:
            logger.exception("workflow reconcile failed (non-fatal)")
    except Exception:
        logger.exception("persist success path failed")

    # Auto-deploy if publish_on_save was on — runs in this same background task
    if publish_on_save:
        try:
            deployment = await _do_deploy(project_id, "internal")
            # Notify the live client if still connected
            try:
                event_queue.put_nowait({
                    "type": "auto_deploy",
                    "deployment": {
                        "id": deployment.get("id"),
                        "status": deployment.get("status"),
                        "public_url": deployment.get("public_url"),
                    },
                })
            except Exception:
                pass
        except Exception as e:
            logger.exception("auto-deploy failed (background)")
            try:
                event_queue.put_nowait({"type": "auto_deploy", "error": str(e)})
            except Exception:
                pass


@router.post("/projects/{project_id}/chat")
async def chat_with_ai(project_id: str, body: ChatIn,
                       _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")

    runtime_ctx = _build_runtime_ctx(project_id, doc)

    now = datetime.now(timezone.utc).isoformat()
    user_msg = {"id": str(uuid.uuid4()), "role": "user", "content": body.message,
                "explanation": None, "created_at": now}
    snapshot = {"id": str(uuid.uuid4()),
                "label": f"Before: {body.message[:60]}",
                "created_at": now, "files": doc.get("files", [])}

    try:
        result = await generate_project(
            user_message=body.message,
            current_files=doc.get("files", []),
            history=doc.get("messages", []),
            project_id=project_id,
            preferred_provider=body.provider,
            runtime_ctx=runtime_ctx,
        )
    except AIProviderError as e:
        err_msg = {"id": str(uuid.uuid4()), "role": "assistant",
                   "content": f"Generation failed: {e}", "explanation": None,
                   "created_at": datetime.now(timezone.utc).isoformat()}
        await db.projects.update_one(
            {"id": project_id},
            {"$push": {"messages": {"$each": [user_msg, err_msg]}}},
        )
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("AI generation failed")
        err_msg = {"id": str(uuid.uuid4()), "role": "assistant",
                   "content": f"Generation failed: {str(e)[:280]}",
                   "explanation": None,
                   "created_at": datetime.now(timezone.utc).isoformat()}
        await db.projects.update_one(
            {"id": project_id},
            {"$push": {"messages": {"$each": [user_msg, err_msg]}}},
        )
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")

    # Apply precision-editing guardrails for imported projects
    final_files = result["files"]
    reverted = []
    try:
        if is_imported_project(doc):
            final_files, reverted = merge_with_protection(
                current_files=doc.get("files") or [],
                new_files=final_files,
                user_message=body.message,
                is_imported_project=True,
            )
    except Exception:
        logger.exception("precision guard (non-streaming) failed")

    assistant_msg = {
        "id": str(uuid.uuid4()), "role": "assistant",
        "content": result["explanation"], "explanation": result["explanation"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": result.get("provider"), "model": result.get("model"),
    }
    if reverted:
        assistant_msg["build_summary"] = {"preserved_paths": reverted[:20]}

    await db.projects.update_one(
        {"id": project_id},
        {
            "$set": {"files": final_files,
                     "updated_at": datetime.now(timezone.utc).isoformat()},
            "$push": {
                "messages": {"$each": [user_msg, assistant_msg]},
                "versions": {"$each": [snapshot], "$slice": -50},
            },
        },
    )
    # Reconcile any in-flight workflow (non-streaming path).
    workflow_reconciled = None
    try:
        from services.workflow_service import reconcile_coder_phase
        workflow_reconciled = await reconcile_coder_phase(
            project_id, files_count=len(final_files),
            explanation=result.get("explanation", "")[:240],
        )
    except Exception:
        logger.exception("workflow reconcile failed (non-fatal)")

    return {
        "user_message": user_msg,
        "assistant_message": assistant_msg,
        "files": final_files,
        "explanation": result["explanation"],
        "notes": result.get("notes"),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "preserved_paths": reverted[:20] if reverted else None,
        "workflow_reconciled": workflow_reconciled,
    }


@router.post("/projects/{project_id}/debug")
async def ai_debug(project_id: str, body: DebugIn,
                   _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "files": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        result = await ai_service.debug_error(
            error_text=body.error_text,
            current_files=doc.get("files", []),
            user_note=body.note or "",
        )
        return result
    except AIProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("debug failed")
        raise HTTPException(status_code=500, detail=str(e))
