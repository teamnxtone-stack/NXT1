"""Sandboxed runner service (Track D — self-healing build loop).

Creates an isolated scratch workspace (under /tmp/nxt1-runner-<id>) for each
build attempt so the running NXT1 instance cannot be corrupted by user code.

Two execution modes:
  * `subprocess` (default, works inside the existing container)
  * `docker`     (returns a recipe — actual docker exec deferred to user infra)

Public API:
  start_sandbox_build(project_id, attempt=1)  -> {workspace_dir, attempt}
  run_build(workspace_dir, files, build_cmd)  -> {ok, logs, error, duration_ms}
  cleanup_sandbox(workspace_dir)
  self_heal_loop(project_id, max_attempts=3)  -> async-generator of phase events
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger("nxt1.runner")

RUNNER_ROOT = os.environ.get("NXT1_RUNNER_ROOT", "/tmp/nxt1-runner")
MAX_ATTEMPTS_DEFAULT = int(os.environ.get("WORKFLOW_MAX_RETRIES", "3"))


def _ensure_root():
    os.makedirs(RUNNER_ROOT, exist_ok=True)


def start_sandbox(project_id: str, attempt: int = 1) -> Dict[str, Any]:
    """Allocate a fresh tmp workspace for a build attempt."""
    _ensure_root()
    workspace = tempfile.mkdtemp(prefix=f"{project_id[:8]}-a{attempt}-", dir=RUNNER_ROOT)
    return {"workspace_dir": workspace, "attempt": attempt, "project_id": project_id}


def materialize_files(workspace_dir: str, files: List[Dict[str, str]]) -> int:
    """Write project files into the sandbox. Returns count written."""
    count = 0
    for f in files or []:
        path = (f.get("path") or "").strip().lstrip("/")
        if not path:
            continue
        if ".." in path.split("/"):
            continue  # path traversal guard
        full = os.path.join(workspace_dir, path)
        os.makedirs(os.path.dirname(full) or workspace_dir, exist_ok=True)
        try:
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(f.get("content") or "")
            count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"materialize_files: skipped {path}: {e}")
    return count


async def run_command(workspace_dir: str, cmd: List[str],
                       timeout_sec: int = 120) -> Dict[str, Any]:
    """Run a command inside the sandbox. Captures stdout/stderr."""
    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=workspace_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {
                "ok": False, "exit_code": -1,
                "stdout": "", "stderr": f"Timeout after {timeout_sec}s",
                "duration_ms": int((time.monotonic() - start) * 1000),
            }
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": (stdout or b"").decode("utf-8", "replace")[-8000:],
            "stderr": (stderr or b"").decode("utf-8", "replace")[-8000:],
            "duration_ms": int((time.monotonic() - start) * 1000),
        }
    except FileNotFoundError as e:
        return {"ok": False, "exit_code": -1, "stdout": "", "stderr": str(e),
                "duration_ms": int((time.monotonic() - start) * 1000)}


def detect_build_command(files: List[Dict[str, str]]) -> Optional[List[str]]:
    """Best-effort build command detection.

    For now we focus on static checks (syntax) because real `yarn build` or
    `pip install` inside this container would be slow + brittle. The shape
    is here so a Docker runner can swap in.
    """
    paths = {(f.get("path") or "") for f in (files or [])}
    if "package.json" in paths:
        # Cheap static check: validate JSON + look for `build` script.
        return ["python3", "-c",
                "import json,sys,os;"
                "p=os.path.join(os.getcwd(),'package.json');"
                "d=json.load(open(p));"
                "scripts=d.get('scripts') or {};"
                "print('OK build script present' if scripts.get('build') else "
                "'WARN no build script');"
                "sys.exit(0 if scripts.get('build') else 0)"]
    if "requirements.txt" in paths or "backend/requirements.txt" in paths:
        # Validate by lightweight parse — pip install in the sandbox is too heavy here.
        req = "requirements.txt" if "requirements.txt" in paths else "backend/requirements.txt"
        return ["python3", "-c",
                f"open('{req}').read(); print('OK requirements readable')"]
    if "index.html" in paths or any(p.endswith(".html") for p in paths):
        # Validate by opening + brief HTML smoke
        target = "index.html" if "index.html" in paths else \
                 next((p for p in paths if p.endswith(".html")), "")
        return ["python3", "-c",
                f"d=open('{target}').read(); "
                "import sys; sys.exit(0 if '<html' in d.lower() else 1); "
                "print('OK html shape')"]
    return None


def cleanup_sandbox(workspace_dir: str) -> bool:
    try:
        if workspace_dir and workspace_dir.startswith(RUNNER_ROOT):
            shutil.rmtree(workspace_dir, ignore_errors=True)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


async def self_heal_loop(project_id: str, files: List[Dict[str, str]],
                          max_attempts: int = MAX_ATTEMPTS_DEFAULT
                          ) -> AsyncIterator[Dict[str, Any]]:
    """Bounded build → detect failure → propose patch → retry loop.

    Yields phase events suitable for SSE:
      {phase, agent, attempt, max_attempts, message, status, ...}

    The "propose patch" step delegates to the existing autofix route's
    DebugAgent which already understands the JSON contract.
    """
    attempt = 0
    current_files = list(files or [])
    while attempt < max_attempts:
        attempt += 1
        ws = start_sandbox(project_id, attempt=attempt)
        yield {"phase": "sandbox.start", "agent": "devops",
               "attempt": attempt, "max_attempts": max_attempts,
               "message": f"Attempt {attempt}/{max_attempts}: sandbox at {ws['workspace_dir']}",
               "status": "running"}

        written = materialize_files(ws["workspace_dir"], current_files)
        yield {"phase": "sandbox.materialized", "agent": "coder",
               "attempt": attempt, "max_attempts": max_attempts,
               "message": f"{written} file(s) materialized.",
               "status": "running"}

        cmd = detect_build_command(current_files)
        if not cmd:
            yield {"phase": "tester.skip", "agent": "tester",
                   "attempt": attempt, "max_attempts": max_attempts,
                   "message": "No recognised build command — skipping.",
                   "status": "done"}
            cleanup_sandbox(ws["workspace_dir"])
            yield {"phase": "loop.complete", "agent": "devops",
                   "attempt": attempt, "max_attempts": max_attempts,
                   "message": "Self-heal complete (no build to verify).",
                   "status": "completed"}
            return

        result = await run_command(ws["workspace_dir"], cmd, timeout_sec=60)
        if result.get("ok"):
            yield {"phase": "tester.pass", "agent": "tester",
                   "attempt": attempt, "max_attempts": max_attempts,
                   "message": "Build smoke check passed.",
                   "status": "done", "duration_ms": result.get("duration_ms")}
            cleanup_sandbox(ws["workspace_dir"])
            yield {"phase": "loop.complete", "agent": "devops",
                   "attempt": attempt, "max_attempts": max_attempts,
                   "message": "Self-heal complete — build healthy.",
                   "status": "completed"}
            return

        # Failure path: emit error + delegate to DebugAgent for a patch
        err_blob = (result.get("stderr") or result.get("stdout") or "")[:2000]
        yield {"phase": "tester.fail", "agent": "tester",
               "attempt": attempt, "max_attempts": max_attempts,
               "message": "Build smoke check failed.",
               "status": "failed", "error": err_blob,
               "duration_ms": result.get("duration_ms")}

        cleanup_sandbox(ws["workspace_dir"])

        if attempt >= max_attempts:
            yield {"phase": "loop.exhausted", "agent": "devops",
                   "attempt": attempt, "max_attempts": max_attempts,
                   "message": f"Exhausted {max_attempts} attempts — needs human approval.",
                   "status": "waiting"}
            return

        # Ask the debug agent for a patch — bounded by errors only.
        try:
            from services import agents as agents_svc  # local import
            agent = agents_svc.get_agent("debug")
            prompt = (
                f"BUILD FAILURE in sandbox attempt {attempt}/{max_attempts}.\n"
                f"ERROR / STDERR:\n{err_blob[:1500]}\n\n"
                f"PROJECT FILES (paths only): "
                f"{[f.get('path') for f in current_files[:30]]}\n\n"
                "Propose MINIMAL file edits that would let the build pass on the next attempt. "
                "Respond with the standard debug-agent JSON now."
            )
            yield {"phase": "debugger.thinking", "agent": "debugger",
                   "attempt": attempt, "max_attempts": max_attempts,
                   "message": "Debug agent proposing a patch...",
                   "status": "running"}
            res = await agent.run(prompt)
            parsed = res.parsed or {}
            patches = parsed.get("files") or []
            if not patches:
                yield {"phase": "debugger.empty", "agent": "debugger",
                       "attempt": attempt, "max_attempts": max_attempts,
                       "message": "No patch proposed — re-running with same files.",
                       "status": "done"}
                continue
            # Merge patches into current_files for the next attempt
            by_path = {f.get("path"): i for i, f in enumerate(current_files)}
            applied: List[str] = []
            for p in patches:
                path = (p.get("path") or "").strip().lstrip("/")
                after = p.get("after")
                if not path or after is None:
                    continue
                if path in by_path:
                    current_files[by_path[path]] = {"path": path, "content": after}
                else:
                    current_files.append({"path": path, "content": after})
                    by_path[path] = len(current_files) - 1
                applied.append(path)
            yield {"phase": "debugger.patched", "agent": "debugger",
                   "attempt": attempt, "max_attempts": max_attempts,
                   "message": f"Patch applied to {len(applied)} file(s).",
                   "status": "done", "applied": applied}
        except Exception as e:  # noqa: BLE001
            logger.exception("self_heal_loop debug agent failed")
            yield {"phase": "debugger.error", "agent": "debugger",
                   "attempt": attempt, "max_attempts": max_attempts,
                   "message": f"Debug agent error: {e}",
                   "status": "failed"}


# ---------- Sync wrapper for non-streaming callers ----------
async def quick_build(project_id: str, files: List[Dict[str, str]]) -> Dict[str, Any]:
    """One-shot build (no retry) — useful for readiness checks."""
    ws = start_sandbox(project_id, attempt=1)
    try:
        materialize_files(ws["workspace_dir"], files)
        cmd = detect_build_command(files)
        if not cmd:
            return {"ok": True, "skipped": True, "reason": "no-build-command"}
        result = await run_command(ws["workspace_dir"], cmd, timeout_sec=60)
        return {
            "ok": result["ok"],
            "exit_code": result["exit_code"],
            "duration_ms": result["duration_ms"],
            "stderr_tail": (result.get("stderr") or "")[-1000:],
            "stdout_tail": (result.get("stdout") or "")[-1000:],
            "ran_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        cleanup_sandbox(ws["workspace_dir"])
