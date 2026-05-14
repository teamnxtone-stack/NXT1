"""NXT1 Tag-protocol streaming generator.

Sits ALONGSIDE the existing JSON-based `ai_service.generate_project_stream`.
Selected when the request specifies `?protocol=tag` on the SSE endpoint, or
when the project explicitly opts in.

Surface
=======
    async for ev in generate_project_stream_tag(user_message, current_files,
                                                history, project_id, ...):
        # ev is a dict — same envelope shape as ai_service.generate_project_stream:
        # {"type":"start"|"phase"|"chunk"|"tool"|"info"|"error"|"done"|"cancelled", ...}
        ...

The final {"type":"done"} payload carries the merged file list + receipts so
the route handler can persist it identically to the JSON path.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Awaitable, Callable, Dict, List, Optional

# NOTE: emergentintegrations was removed (Phase B.12 deploy fix). This file
# uses provider adapters from `services.providers` which now route via
# litellm only.

from .ai_service import (
    _aiter,
    _stream_narration,
    get_provider_for_task,
)
from .providers.base import RouteIntent
from .providers.registry import registry as _REG
from .tag_protocol import ApplyResult, TagApplyError, TagStreamParser, apply_tag_action

logger = logging.getLogger("nxt1.ai_tag")


TAG_SYSTEM_PROMPT = """You are NXT1 — an elite full-stack AI app builder. You generate REAL,
production-quality web apps and edit existing projects with surgical precision.

OUTPUT PROTOCOL — STRICT
========================
You communicate with NXT1 using XML-like action tags inline in your response.
Each tag triggers an immediate file-system mutation. Tags are processed in
the exact order you emit them.

The following tags are the ONLY way to change the project:

  <nxt1-write path="src/App.jsx">
  …complete file contents…
  </nxt1-write>
      Creates or overwrites a file. Use for new files, or for rewrites where
      the change touches more than ~10 lines.

  <nxt1-edit path="src/App.jsx">
    <search>EXACT existing snippet, must match exactly once</search>
    <replace>new snippet that replaces it</replace>
  </nxt1-edit>
      Surgical replacement. PREFER THIS over <nxt1-write> for small edits —
      it is 10–100× more token-efficient and never accidentally rewrites
      unrelated code. The `search` text MUST appear EXACTLY ONCE in the
      current file content (verbatim — including whitespace). If you are not
      certain the snippet is unique, widen it with surrounding context.

  <nxt1-rename from="src/Old.jsx" to="src/New.jsx" />
      Rename a file. Self-closing.

  <nxt1-delete path="src/Unused.jsx" />
      Delete a file. Self-closing.

  <nxt1-deps action="install">react-icons lucide-react</nxt1-deps>
  <nxt1-deps action="uninstall">moment</nxt1-deps>
      Schedule dependency changes. NXT1 will run them.

  <nxt1-shell>npm run build</nxt1-shell>
      Run an arbitrary shell command inside the project's sandboxed workdir.
      Use SPARINGLY — only when truly needed (build verification, codegen,
      one-off migrations). Each command has a 90s timeout and is subject to
      a safety denylist. PREFER explicit edits via <nxt1-write>/<nxt1-edit>
      over `sed`/`awk` in shell. NEVER use `sudo`, `rm -rf /`, `curl … | sh`.
      Execution is OFF by default; if disabled the command is recorded as
      intent so the operator can review.

  <nxt1-explanation>One short sentence summarising what you changed.</nxt1-explanation>
      Required at the end. Sentence case. No markdown.

  <nxt1-notes>Optional: deps to install, env vars to set, follow-ups.</nxt1-notes>
      Optional. Plain text. No markdown.

CRITICAL RULES
==============
1. NO prose between tags except brief inline explanations (≤1 short sentence).
   The system streams your tags directly to the user; chatter is noise.
2. NO markdown code fences. Code goes inside the tag content as-is.
3. <nxt1-write> content is the COMPLETE file body — no diffs, no placeholders,
   no "…rest of code unchanged".
4. <nxt1-edit> `<search>` MUST match the current file EXACTLY ONCE. If your
   snippet is ambiguous you MUST widen it until it is unique.
5. Touch only the files needed to satisfy the user's request. Do NOT
   refactor, reformat, rename, or "improve" unrelated files. Do NOT touch
   `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`,
   `tsconfig.json`, `vite.config.*`, `next.config.*`, `tailwind.config.*`,
   `postcss.config.*`, `.env*`, `.gitignore`, anything in `public/`,
   `static/`, `dist/`, `build/`, `node_modules/`, or `.git/` UNLESS the user
   explicitly asked you to.
6. End every response with exactly one <nxt1-explanation> tag.

ACTION SEQUENCING (very important for first-turn reliability)
=============================================================
When generating from a blank prompt (no prior project files):
  STEP A. If you need a build dep, emit <nxt1-deps> FIRST.
  STEP B. Write entry files in dependency order: layout/theme → primitives →
          pages → routing/wiring → entry HTML.
  STEP C. NEVER reference a file in an import statement that you haven't
          also written this turn (a missing import is the #1 cause of
          broken previews — the AI used to assume utilities existed).
  STEP D. Wire the app together with a top-level `App.jsx` (Vite/CRA) or
          `app/page.tsx` (Next) or `index.html` (static). The PREVIEW
          surface boots from one of these — if it's missing nothing renders.
  STEP E. End with <nxt1-explanation>.

For EDITS on an existing project:
  STEP A. Prefer <nxt1-edit> over <nxt1-write> whenever the change is < 30%
          of the file. Surgical edits never accidentally rewrite imports
          and are 10–100× cheaper.
  STEP B. If a new dependency is needed, emit a single <nxt1-deps install>
          tag BEFORE the edit that uses it.
  STEP C. Touch only the files you're changing. Do NOT re-emit unrelated
          components "for clarity".

QUALITY BAR
===========
- Premium aesthetic: confident typography, generous spacing, smooth
  micro-interactions, real contextual copy (no Lorem Ipsum), fully
  responsive.
- Prefer dark, cinematic palettes unless the user requested otherwise.
- Use inline SVG icons (sharp, 1.5px stroke) instead of icon fonts/CDNs.
- No external CDNs / unpkg / cdnjs / jsdelivr — bundle everything via the
  project's installed deps.

EXAMPLES
========
Example 1 — edit (smallest change first):

User: "Change the hero title from 'Welcome' to 'Build anything.'"

<nxt1-edit path="src/components/Hero.jsx">
  <search><h1 className="hero-title">Welcome</h1></search>
  <replace><h1 className="hero-title">Build anything.</h1></replace>
</nxt1-edit>
<nxt1-explanation>Updated the hero title to "Build anything."</nxt1-explanation>

Example 2 — add a page on an existing app (route wiring required):

User: "Add a pricing page with three tiers."

<nxt1-write path="src/pages/Pricing.jsx">
import "./Pricing.css";
export default function Pricing() {
  return ( …complete component… );
}
</nxt1-write>
<nxt1-write path="src/pages/Pricing.css">
.pricing { /* complete styles */ }
</nxt1-write>
<nxt1-edit path="src/App.jsx">
  <search><Route path="/" element={<Home/>} /></search>
  <replace><Route path="/" element={<Home/>} />
        <Route path="/pricing" element={<Pricing/>} /></replace>
</nxt1-edit>
<nxt1-explanation>Added a three-tier pricing page and wired up the /pricing route.</nxt1-explanation>

Example 3 — first turn on a fresh scaffold (DO NOT re-emit existing files):

User: "Build a calm focus-timer with ambient backdrops."
(project already has Vite scaffold: src/App.jsx, src/main.jsx, index.html,
vite.config.js, package.json)

<nxt1-write path="src/components/FocusTimer.jsx">
import { useEffect, useState } from "react";
export default function FocusTimer() { …complete UI… }
</nxt1-write>
<nxt1-write path="src/components/AmbientBackdrop.jsx">
export default function AmbientBackdrop() { …complete component… }
</nxt1-write>
<nxt1-edit path="src/App.jsx">
  <search>export default function App() {
  return (
    <div>Welcome to Vite</div>
  );
}</search>
  <replace>import FocusTimer from "./components/FocusTimer";
import AmbientBackdrop from "./components/AmbientBackdrop";
export default function App() {
  return (
    <main className="app">
      <AmbientBackdrop />
      <FocusTimer />
    </main>
  );
}</replace>
</nxt1-edit>
<nxt1-write path="src/App.css">
.app { min-height: 100dvh; background: #0c0c0d; color: #efeae0; }
</nxt1-write>
<nxt1-explanation>Built a focus timer with an ambient backdrop and wired both into App.jsx.</nxt1-explanation>

Example 4 — dependency-aware (deps tag MUST come first):

User: "Add fancy 3D icons throughout the dashboard."

<nxt1-deps action="install">lucide-react</nxt1-deps>
<nxt1-edit path="src/components/StatsCard.jsx">
  <search>import "./StatsCard.css";</search>
  <replace>import "./StatsCard.css";
import { TrendingUp } from "lucide-react";</replace>
</nxt1-edit>
<nxt1-edit path="src/components/StatsCard.jsx">
  <search><span className="stat-label">Revenue</span></search>
  <replace><span className="stat-label"><TrendingUp size={14} strokeWidth={1.5} /> Revenue</span></replace>
</nxt1-edit>
<nxt1-explanation>Added lucide-react and wired a TrendingUp icon into the Revenue stats card.</nxt1-explanation>
"""


# Per-file size threshold beyond which we encourage edits over writes
EDIT_PREFERENCE_BYTES = 5000


def _build_tag_user_prompt(user_message: str,
                            current_files: List[Dict[str, str]],
                            history: List[Dict[str, str]],
                            runtime_ctx: Optional[dict] = None,
                            project_id: Optional[str] = None,
                            active_file: Optional[str] = None) -> str:
    """Compose the user-prompt block fed to the LLM for tag-mode generation.

    For non-trivial projects (>15 files) we ask the project-memory index to
    pick a focused slice of files based on the user's request — this keeps
    the AI context-aware on large codebases without burning the whole token
    budget on the file tree.
    """
    if not current_files:
        files_blob = "(no files yet — start by writing them)"
        context_summary = "context: empty project"
    elif len(current_files) > 15 and project_id:
        # Use the per-project memory index to pick relevant files.
        try:
            from .project_memory_index import select_context_for_prompt
            pack = select_context_for_prompt(
                project_id, current_files, user_message, active_file=active_file,
            )
            context_summary = pack.summary
            parts = []
            for f in pack.files:
                content = f.get("content") or ""
                marker = " (LARGE — use <nxt1-edit>)" if len(content) >= EDIT_PREFERENCE_BYTES else ""
                parts.append(f"=== {f['path']}{marker} ===\n{content}")
            files_blob = "\n\n".join(parts)
            # Hint the model that other files exist outside the window.
            extras = [f["path"] for f in current_files
                       if f["path"] not in pack.chosen_paths][:60]
            if extras:
                files_blob += (
                    "\n\n=== OTHER PROJECT FILES (paths only — not loaded) ===\n"
                    + "\n".join(f"  - {p}" for p in extras)
                )
        except Exception as e:
            logger.warning(f"project-memory index failed (non-fatal): {e}")
            files_blob, context_summary = _format_files_naive(current_files)
    else:
        files_blob, context_summary = _format_files_naive(current_files)

    history_blob = ""
    for m in (history or [])[-6:]:
        c = (m.get("content") or "")
        if len(c) > 500:
            c = c[:500] + "…"
        history_blob += f"\n[{m.get('role')}]: {c}"
    history_blob = history_blob or "(none)"

    runtime_blob = ""
    if runtime_ctx:
        eps = runtime_ctx.get("endpoints") or []
        env_keys = runtime_ctx.get("env_keys") or []
        proxy = runtime_ctx.get("proxy_url") or ""
        deployed_url = runtime_ctx.get("deployed_url") or ""
        runtime_blob = "\n\nRUNTIME CONTEXT (use these when wiring frontend ↔ backend):"
        if proxy:
            runtime_blob += f"\n- Backend proxy URL (frontend should fetch this): {proxy}"
        if eps:
            ep_lines = "\n".join(f"  - {e.get('method', 'GET')} {e.get('path')}" for e in eps)
            runtime_blob += f"\n- Available API routes:\n{ep_lines}"
        if env_keys:
            runtime_blob += f"\n- Backend env vars (already injected): {', '.join(env_keys)}"
        if deployed_url:
            runtime_blob += f"\n- Live deployed URL: {deployed_url}"

    return (
        f"CONTEXT: {context_summary}\n"
        f"CURRENT PROJECT FILES:\n{files_blob}\n\n"
        f"RECENT CONVERSATION:{history_blob}{runtime_blob}\n\n"
        f"USER REQUEST:\n{user_message}\n\n"
        "Respond NOW using NXT1 action tags only. Touch only the files needed. "
        "End with <nxt1-explanation>."
    )


def _format_files_naive(current_files: List[Dict[str, str]]):
    """Fallback file-pack formatter (no memory index)."""
    parts = []
    for f in current_files[:30]:
        content = f.get("content") or ""
        if len(content) > 8000:
            content = content[:8000] + "\n/* …file continues — use <nxt1-edit> for targeted changes… */"
        marker = " (LARGE — use <nxt1-edit>)" if len(content) >= EDIT_PREFERENCE_BYTES else ""
        parts.append(f"=== {f['path']}{marker} ===\n{content}")
    files_blob = "\n\n".join(parts)
    if len(current_files) > 30:
        extra = "\n".join(f"  - {f['path']}" for f in current_files[30:])
        files_blob += f"\n\n=== OTHER PROJECT FILES (paths only) ===\n{extra}"
    return files_blob, f"context: naive (first {min(30, len(current_files))}/{len(current_files)})"


async def generate_project_stream_tag(
    user_message: str,
    current_files: List[Dict[str, str]],
    history: List[Dict[str, str]],
    project_id: str,
    preferred_provider: Optional[str] = None,
    runtime_ctx: Optional[dict] = None,
    cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
):
    """Tag-mode streaming generator. Yields the same envelope as
    `ai_service.generate_project_stream` so the route handler can treat both
    paths uniformly.

    Lifecycle:
      start → phase(Planning) → narration* → phase(Editing) → chunk* +
      tool(action) events (as tags close & apply) → phase(Finalizing) → done.
    """
    provider = get_provider_for_task("code-generation", explicit=preferred_provider)
    session_id = f"proj-{project_id}-tag-{uuid.uuid4().hex[:8]}"
    user_prompt = _build_tag_user_prompt(user_message, current_files, history,
                                          runtime_ctx=runtime_ctx,
                                          project_id=project_id)
    logger.info(f"AI tag-stream via provider={provider.name} model={provider.model}")

    # Throttle cancel checks
    _last_check = [0.0]
    async def _is_cancelled() -> bool:
        if not cancel_check:
            return False
        now = time.monotonic()
        if now - _last_check[0] < 0.5:
            return False
        _last_check[0] = now
        try:
            return bool(await cancel_check())
        except Exception:
            return False

    yield {"type": "start", "provider": provider.name, "model": provider.model,
           "protocol": "tag"}
    yield {"type": "phase", "label": "Planning app structure"}

    try:
        async for line in _stream_narration(user_message, current_files):
            yield {"type": "narration", "line": line}
            if await _is_cancelled():
                yield {"type": "cancelled", "stage": "narration"}
                return
    except Exception as e:
        logger.warning(f"narration error (non-fatal): {e}")

    yield {"type": "phase", "label": "Editing files"}

    # Apply state — starts as a copy of current files so we can resolve edits.
    state = ApplyResult(files=[{"path": f["path"], "content": f.get("content") or ""}
                                for f in (current_files or [])])

    # Build failover chain (mirror JSON path)
    failover_chain = [provider]
    try:
        intent = RouteIntent(routing_mode="auto", task="code-generation",
                              explicit_provider=None)
        seen = {provider.name}
        for alt in _REG.try_chain(intent):
            if alt.name in seen:
                continue
            seen.add(alt.name)
            failover_chain.append(alt)
            if len(failover_chain) >= 3:
                break
    except Exception as e:
        logger.debug(f"failover chain build skipped: {e}")

    parser = TagStreamParser()
    _attempted: List[str] = []
    _last_err: Optional[Exception] = None

    for _i, _p in enumerate(failover_chain):
        provider = _p
        _attempted.append(provider.name)
        if _i > 0:
            yield {"type": "info",
                   "message": f"Provider {failover_chain[_i-1].name} unavailable — switching to {provider.name}…"}
            yield {"type": "phase", "label": "Editing files"}
            # Reset parser between provider attempts so partial state doesn't leak
            parser = TagStreamParser()

        try:
            async for delta in _aiter(provider.generate_stream(
                TAG_SYSTEM_PROMPT, user_prompt,
                session_id + (f"-fb{_i}" if _i else ""),
            )):
                # Emit raw chunk for clients that want a typing indicator
                yield {"type": "chunk", "delta": delta}
                # Feed parser
                for ev in parser.feed(delta):
                    out = _forward_parser_event(ev, state)
                    if out is not None:
                        yield out
                if await _is_cancelled():
                    yield {"type": "cancelled", "stage": "generation"}
                    return
            _last_err = None
            break
        except Exception as e:
            _last_err = e
            msg = str(e)
            transient = any(s in msg for s in (
                "502", "503", "504", "BadGateway", "Service Unavailable",
                "timeout", "TimeoutError", "ProviderUnavailable", "ProviderTimeout",
                "rate_limit", "RateLimit", "InternalServerError",
            ))
            logger.warning(f"tag-mode provider {provider.name} failed "
                            f"(transient={transient}): {e}")
            try:
                _REG.mark_error(provider.name)
            except Exception:
                pass
            if not transient:
                break

    if _last_err is not None:
        em = str(_last_err)
        friendly = (
            "The AI provider is temporarily unavailable. Retry in a moment "
            "or pick a different model from the picker."
            if any(s in em for s in ("502", "503", "504", "BadGateway",
                                       "Service Unavailable", "InternalServerError"))
            else "The model couldn't complete this generation. Retry or pick a different model."
        )
        yield {"type": "error", "message": friendly, "stage": "provider",
               "providers_attempted": _attempted}
        return

    # Final drain of parser
    for ev in parser.finish():
        out = _forward_parser_event(ev, state)
        if out is not None:
            yield out

    yield {"type": "phase", "label": "Validating output"}

    # ── Static validation + self-healing (Phase A.6) ──────────────────────
    # Mirrors ai_service.generate_project_stream. We only re-run the model
    # if validation found errors; the repair pass uses the same tag protocol
    # so changes stay surgical.
    try:
        from .validation_service import (
            diff_paths,
            format_for_repair_prompt,
            validate_files,
        )
        starting_files = [{"path": f["path"], "content": f.get("content") or ""}
                           for f in (current_files or [])]
        changed = diff_paths(starting_files, state.files)
        v_report = validate_files(state.files, only_paths=changed)
        if v_report.issues:
            yield {"type": "validate", "report": v_report.to_dict()}
        if v_report.has_errors:
            yield {"type": "phase", "label": "Self-healing build"}
            repair_user_prompt = (
                f"{user_prompt}\n\n"
                f"=== POST-GENERATION VALIDATION REPORT ===\n"
                f"{format_for_repair_prompt(v_report)}\n\n"
                "Emit ONLY the surgical <nxt1-edit> / <nxt1-write> tags needed "
                "to fix these errors. Do not touch unrelated files. End with "
                "<nxt1-explanation>."
            )
            yield {"type": "info",
                   "message": f"Detected {v_report.error_count} build error(s) — auto-repairing…"}
            try:
                repair_parser = TagStreamParser()
                # Build a fresh ApplyResult seeded from the current state so
                # the model can reference what it just wrote.
                repair_state = ApplyResult(files=[
                    {"path": f["path"], "content": f["content"]} for f in state.files
                ])
                async for delta in _aiter(provider.generate_stream(
                    TAG_SYSTEM_PROMPT, repair_user_prompt, session_id + "-heal",
                )):
                    yield {"type": "chunk", "delta": delta}
                    for ev in repair_parser.feed(delta):
                        out = _forward_parser_event(ev, repair_state)
                        if out is not None:
                            yield out
                for ev in repair_parser.finish():
                    out = _forward_parser_event(ev, repair_state)
                    if out is not None:
                        yield out
                # Re-validate
                repaired_changed = diff_paths(starting_files, repair_state.files)
                v2 = validate_files(repair_state.files, only_paths=repaired_changed)
                if v2.error_count < v_report.error_count:
                    state.files = repair_state.files
                    state.receipts.extend(repair_state.receipts)
                    if repair_state.explanation:
                        state.explanation = (
                            (state.explanation + " | " if state.explanation else "")
                            + repair_state.explanation
                        )
                    yield {"type": "info",
                           "message": f"Repair pass reduced errors {v_report.error_count}\u2192{v2.error_count}."}
                    yield {"type": "validate", "report": v2.to_dict()}
                else:
                    yield {"type": "info",
                           "message": "Repair pass did not improve validation; keeping original."}
            except Exception as e:
                logger.warning(f"tag self-healing repair failed (non-fatal): {e}")
                yield {"type": "info",
                       "message": "Self-healing pass failed; keeping original output."}
    except Exception as e:
        logger.warning(f"tag validation hook failed (non-fatal): {e}")

    yield {"type": "phase", "label": "Finalizing"}

    # ── Apply deps to package.json (Phase B.1.5) ──────────────────────────
    # Any <nxt1-deps action="install"|"uninstall"> tags applied during this
    # build are recorded into state.deps_install / state.deps_uninstall.
    # We translate them into a package.json edit so the change is visible
    # immediately and gets picked up on the next runtime boot / WebContainer
    # mount — no shell execution required from this hot path.
    if state.deps_install or state.deps_uninstall:
        try:
            from .deps_service import apply_deps_to_files
            dr = apply_deps_to_files(
                state.files,
                install=state.deps_install,
                uninstall=state.deps_uninstall,
            )
            if dr.warning:
                yield {"type": "info", "message": dr.warning}
            elif dr.target_path:
                state.files = dr.files
                yield {"type": "tool", "action": "deps-applied",
                       "path": dr.target_path,
                       "installed": dr.installed, "uninstalled": dr.uninstalled}
                # Mirror the file mutation as a "edited" receipt for the
                # build summary so the count is correct.
                state.receipts.append({"action": "edited", "path": dr.target_path})
        except Exception as e:
            logger.warning(f"deps apply failed (non-fatal): {e}")

    # ── Execute shell commands (Phase B.1.6) ──────────────────────────────
    # AI emitted <nxt1-shell> tags. They were applied as intent only — now,
    # if shell exec is enabled by the operator, we actually run them through
    # the ActionRunner with strict guard-rails (denylist, timeout, output
    # cap, sandboxed workdir under /tmp/nxt1-shell/<project_id>/).
    # Output streams as `{type:"tool", action:"shell-output"|"shell-done"}`
    # events the UI already renders.
    if state.shell_commands:
        try:
            from . import shell_service
            from .action_runner import Action, ActionRunner
        except Exception as e:
            logger.warning(f"shell service unavailable: {e}")
            shell_service = None

        if shell_service is not None:
            yield {"type": "phase", "label": "Running build commands"}
            if not shell_service.is_enabled():
                # Surface intent without running.
                for cmd in state.shell_commands:
                    yield {"type": "tool", "action": "shell-recorded",
                           "cmd": cmd,
                           "note": "Shell execution is disabled. Set NXT1_ENABLE_SHELL_EXEC=1 to enable."}
            else:
                # Materialise the latest files to the sandboxed workdir so
                # commands see the AI's most recent output. We pass an
                # async on_line callback that we cannot await from inside
                # the action runner's sync handler — so we run commands
                # directly here instead, recording each as an Action for
                # the timeline.
                runner = ActionRunner(project_id=project_id)
                runner.register("shell", lambda a, _r: None)   # placeholder
                workdir = shell_service.project_workdir(project_id)
                shell_service.materialise_files(workdir, state.files)
                for cmd in state.shell_commands:
                    action = Action(type="shell", payload={"cmd": cmd})
                    await runner.submit(action)
                    yield {"type": "tool", "action": "shell-start", "cmd": cmd,
                           "action_id": action.id}
                    output_lines: List[str] = []
                    async def _on_line(channel: str, line: str, _cmd=cmd):
                        # Truncate to keep SSE payload small
                        output_lines.append(f"[{channel}] {line}")
                    try:
                        result = await shell_service.run_command(
                            workdir, cmd, on_line=_on_line,
                        )
                    except Exception as e:
                        yield {"type": "tool", "action": "shell-done",
                               "cmd": cmd, "exit_code": -1,
                               "error": str(e), "output": "\n".join(output_lines)}
                        continue
                    yield {
                        "type": "tool",
                        "action": "shell-done",
                        "cmd": cmd,
                        "exit_code": result.exit_code,
                        "duration_ms": result.duration_ms,
                        "timed_out": result.timed_out,
                        "truncated": result.truncated,
                        "output": result.output[-4096:] if result.output else "",
                    }
                    # If the command failed and edited files (e.g. `npm install`
                    # generated package-lock.json), sync them back into state.
                    try:
                        lock = workdir / "package-lock.json"
                        if lock.exists():
                            pl_content = lock.read_text(errors="replace")
                            existing = next((f for f in state.files
                                              if f["path"] == "package-lock.json"), None)
                            if existing and existing["content"] != pl_content:
                                existing["content"] = pl_content
                                state.receipts.append({"action": "edited",
                                                       "path": "package-lock.json"})
                            elif not existing:
                                state.files.append({"path": "package-lock.json",
                                                    "content": pl_content})
                                state.receipts.append({"action": "created",
                                                       "path": "package-lock.json"})
                    except Exception as e:
                        logger.debug(f"lockfile sync skipped: {e}")

    # If the AI produced no actions, surface a friendly error.
    if not state.receipts:
        yield {"type": "error",
               "message": "AI did not emit any NXT1 action tags. Retry with a more specific request.",
               "stage": "no_actions"}
        return

    yield {
        "type": "done",
        "files": state.files,
        "receipts": state.receipts,
        "explanation": state.explanation or "Updated files.",
        "notes": state.notes,
        "deps_install": state.deps_install,
        "deps_uninstall": state.deps_uninstall,
        "errors": state.errors,
        "provider": provider.name,
        "model": provider.model,
        "protocol": "tag",
    }


def _forward_parser_event(ev: Dict, state: ApplyResult) -> Optional[Dict]:
    """Translate a parser event into the SSE envelope NXT1 already uses.

    - tag_open(write|edit|rename|delete|deps): emit nothing (waited for close)
    - tag_chunk(write): forward as a "tag_chunk" event so clients can show
      the file being written live (advanced UI may render diffs)
    - tag_close: apply, then emit a "tool" receipt
    - parse_error: forward as info (do not abort)
    - prose: drop (we discourage prose in tag-protocol mode)
    """
    t = ev["type"]
    if t == "tag_chunk":
        return {"type": "tag_chunk", "tag": ev.get("tag"),
                "path": (ev.get("attrs") or {}).get("path"),
                "delta": ev.get("delta")}
    if t == "tag_close":
        try:
            receipt = apply_tag_action(state, ev)
        except TagApplyError as e:
            return {"type": "info", "message": str(e)}
        if not receipt:
            return None
        # Translate apply receipt → existing "tool" event shape so the UI
        # doesn't need to know about the new protocol.
        action = receipt.get("action") or "noop"
        path = receipt.get("path")
        if action.startswith("deps-"):
            return {"type": "tool", "action": action,
                    "packages": receipt.get("packages") or []}
        return {"type": "tool", "action": action, "path": path,
                **({"from": receipt["from"]} if "from" in receipt else {})}
    if t == "parse_error":
        return {"type": "info", "message": ev.get("message", "parse error")}
    if t == "tag_open":
        return None
    if t == "prose":
        # Drop prose — tag mode is no-chatter. But surface non-trivial
        # leading lines as info once (debug aid).
        text = (ev.get("text") or "").strip()
        if text:
            logger.debug(f"tag-mode prose dropped: {text[:120]!r}")
        return None
    return None


__all__ = [
    "TAG_SYSTEM_PROMPT",
    "generate_project_stream_tag",
]
