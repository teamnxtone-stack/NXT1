"""NXT1 Action Runner — orchestration primitive.

Inspired by chef's `app/lib/runtime/action-runner.ts` and dyad's
`process_manager.ts`. The runner is the canonical place to:

  • track per-action status (pending → running → complete | aborted | failed)
  • aggregate output (terminal text, file mutations, exit codes)
  • support cancel/abort cleanly
  • emit status events the SSE layer can forward verbatim

This module is intentionally light: it owns no shells, no fs, no LLM. It is
a state machine + dispatcher that PLUGS INTO existing services
(`runtime_service` for shell, `tag_protocol` for file writes, etc.).

Today's surface
===============

  runner = ActionRunner(project_id="…")
  runner.register("write",  handler=_apply_write)        # sync handler
  runner.register("shell",  handler=_run_shell, async_=True)
  await runner.submit(Action(type="write", path="a.txt", body="…"))
  await runner.submit(Action(type="shell", cmd="npm install react-icons"))
  await runner.run()                                     # drains queue
  print(runner.timeline())

Status events streamed via `runner.events()` (async generator):

  {"type":"action", "action_id": "…", "kind": "write",
   "status": "pending"|"running"|"complete"|"aborted"|"failed",
   "path": "…", "output": "…", "error": "…", "duration_ms": …}

Why this lives next to (and doesn't replace) the tag-protocol apply layer:
the tag parser owns the *what* (decoded actions), the runner owns the *how*
(execution semantics, status, abort). Both today's JSON path and tag path
can opt in by piping their applied actions through the runner — that's the
next step (Phase B.1.2) once we wire shell actions in.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

logger = logging.getLogger("nxt1.action_runner")


ActionStatus = str   # "pending" | "running" | "complete" | "aborted" | "failed"


@dataclass
class Action:
    """A single unit of work."""
    type: str                           # "write" | "edit" | "shell" | "deps" | …
    payload: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: ActionStatus = "pending"
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    output: str = ""
    error: Optional[str] = None

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at is None:
            return None
        end = self.ended_at if self.ended_at is not None else time.monotonic()
        return int((end - self.started_at) * 1000)

    def to_event(self) -> Dict[str, Any]:
        return {
            "type": "action",
            "action_id": self.id,
            "kind": self.type,
            "status": self.status,
            "payload": dict(self.payload),
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


# A handler is either sync (returns str/None) or async (awaitable). The
# return value is captured as `output` on the action; raising fails it.
Handler = Callable[[Action, "ActionRunner"], Union[Optional[str], Awaitable[Optional[str]]]]


class ActionRunner:
    def __init__(self, project_id: Optional[str] = None,
                  on_event: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.project_id = project_id
        self._handlers: Dict[str, Handler] = {}
        self._async_kinds: set = set()
        self._actions: List[Action] = []
        self._queue: asyncio.Queue = asyncio.Queue()
        self._events: asyncio.Queue = asyncio.Queue()
        self._abort = asyncio.Event()
        self._on_event = on_event
        self._draining_done = asyncio.Event()

    # ─── registration / submission ───
    def register(self, kind: str, handler: Handler, async_: bool = False) -> None:
        self._handlers[kind] = handler
        if async_:
            self._async_kinds.add(kind)

    async def submit(self, action: Action) -> None:
        self._actions.append(action)
        await self._queue.put(action)
        await self._emit_event(action)   # initial 'pending'

    # ─── observation ───
    def actions(self) -> List[Action]:
        return list(self._actions)

    def timeline(self) -> List[Dict[str, Any]]:
        return [a.to_event() for a in self._actions]

    async def events(self):
        """Async generator over status events. Caller breaks out when done."""
        while True:
            ev = await self._events.get()
            if ev is None:
                return
            yield ev

    async def _emit_event(self, action: Action) -> None:
        ev = action.to_event()
        await self._events.put(ev)
        if self._on_event:
            try:
                self._on_event(ev)
            except Exception:
                logger.exception("on_event callback raised (suppressed)")

    # ─── execution ───
    def abort(self) -> None:
        """Request abort. Currently-running action finishes; nothing pending starts."""
        self._abort.set()

    async def run(self, parallel: bool = False, max_workers: int = 2) -> None:
        """Drain the queue. `parallel=True` runs up to `max_workers` actions
        concurrently — only useful when actions are independent (we currently
        run sequentially in NXT1 to keep file mutations deterministic).
        """
        try:
            if not parallel:
                while not self._queue.empty():
                    if self._abort.is_set():
                        await self._cancel_remaining()
                        return
                    action = await self._queue.get()
                    await self._run_one(action)
            else:
                sem = asyncio.Semaphore(max_workers)

                async def _worker(a: Action):
                    async with sem:
                        if self._abort.is_set():
                            await self._mark_aborted(a)
                            return
                        await self._run_one(a)

                pending = []
                while not self._queue.empty():
                    pending.append(asyncio.create_task(_worker(await self._queue.get())))
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
        finally:
            await self._events.put(None)
            self._draining_done.set()

    async def _run_one(self, action: Action) -> None:
        handler = self._handlers.get(action.type)
        if not handler:
            action.status = "failed"
            action.error = f"No handler registered for kind '{action.type}'"
            await self._emit_event(action)
            return
        action.status = "running"
        action.started_at = time.monotonic()
        await self._emit_event(action)
        try:
            if action.type in self._async_kinds:
                result = await handler(action, self)  # type: ignore[misc]
            else:
                result = handler(action, self)
                if asyncio.iscoroutine(result):
                    result = await result
            if result is not None:
                action.output = (action.output or "") + str(result)
            action.status = "complete"
        except asyncio.CancelledError:
            action.status = "aborted"
            raise
        except Exception as e:
            action.status = "failed"
            action.error = str(e)
            logger.warning(f"action {action.id} ({action.type}) failed: {e}")
        finally:
            action.ended_at = time.monotonic()
            await self._emit_event(action)

    async def _cancel_remaining(self) -> None:
        while not self._queue.empty():
            try:
                a = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            await self._mark_aborted(a)

    async def _mark_aborted(self, a: Action) -> None:
        a.status = "aborted"
        a.ended_at = time.monotonic()
        await self._emit_event(a)


__all__ = ["Action", "ActionRunner"]
