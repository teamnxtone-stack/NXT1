"""NXT1 shell-execution service for tag-mode <nxt1-shell> actions.

What this lets the AI do
========================
When the model emits

    <nxt1-shell>npm run build</nxt1-shell>

we route the command through this service. It materialises the project files
to a per-project workdir, runs the command with strict guard-rails, captures
stdout/stderr, and surfaces them as streamed tool events back to the UI.

Safety
======
Generated shell is powerful and easy to abuse. Defaults are deliberately
conservative:

  • Off by default. Set NXT1_ENABLE_SHELL_EXEC=1 to opt in.
  • Per-command timeout: NXT1_SHELL_TIMEOUT (default 90s).
  • Combined-output cap: 64KB per command (truncated tail surfaced).
  • Denylist of catastrophic patterns (`rm -rf /`, fork-bombs, `sudo`,
    `mkfs`, raw `curl … | sh`).
  • Working directory is a per-project sandbox under
    /tmp/nxt1-shell/<project_id>/. We never run inside /app.
  • The subprocess runs with HOME pointed at the workdir to avoid touching
    the user's real shell history / npm cache.
  • Network access is permitted (so `npm install` / `git clone` work) but
    the subprocess does not inherit our env beyond a minimal allowlist.

Lifecycle
=========
  ensure_workdir(project_id, files)  → materialise files to disk
  run_command(workdir, cmd, on_line) → async run with streaming output
                                       returns CompletedCommand

The ActionRunner (services.action_runner) is the orchestration layer that
sequences a list of shell actions for a single build turn.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("nxt1.shell")


# ─── policy ────────────────────────────────────────────────────────────────

SHELL_ROOT = Path(os.environ.get("NXT1_SHELL_ROOT", "/tmp/nxt1-shell"))
DEFAULT_TIMEOUT_S = float(os.environ.get("NXT1_SHELL_TIMEOUT", "90"))
MAX_OUTPUT_BYTES = int(os.environ.get("NXT1_SHELL_MAX_OUTPUT", str(64 * 1024)))

# Surface-level deny patterns. Caller still needs to opt-in via the env flag.
_DENY_PATTERNS = [
    re.compile(r"\brm\s+-[a-z]*r[a-z]*f?\s+/+\s*($|\s)"),   # rm -rf /
    re.compile(r":\(\)\s*\{\s*:\|\s*:\s*&\s*\}"),            # fork bomb
    re.compile(r"\bsudo\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"\bcurl\s+[^|;&]*\|\s*(sh|bash|zsh|fish)\b"),
    re.compile(r"\bwget\s+[^|;&]*\|\s*(sh|bash|zsh|fish)\b"),
    re.compile(r"/etc/passwd"),
    # block shutdown / reboot
    re.compile(r"\b(shutdown|reboot|halt|poweroff)\b"),
]

# Minimal env passed to the subprocess. Anything not listed is stripped.
_ENV_ALLOW = (
    "PATH", "LANG", "LC_ALL", "TZ", "TERM",
    "npm_config_cache", "NODE_OPTIONS",
)


def is_enabled() -> bool:
    """Master switch — shell execution is OFF by default."""
    v = (os.environ.get("NXT1_ENABLE_SHELL_EXEC") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def is_command_safe(cmd: str) -> Optional[str]:
    """Return None if the command passes the deny-list; else a reason string."""
    if not (cmd or "").strip():
        return "empty command"
    for pat in _DENY_PATTERNS:
        if pat.search(cmd):
            return f"denied by safety policy ({pat.pattern!r})"
    return None


# ─── workdir management ────────────────────────────────────────────────────

def project_workdir(project_id: str) -> Path:
    p = SHELL_ROOT / str(project_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def materialise_files(workdir: Path, files: List[Dict[str, str]]) -> None:
    """Write the NXT1 file list to `workdir`. We DELIBERATELY don't delete
    files we haven't been told about — incremental edits stay incremental,
    and a previous run's `node_modules` stays cached between commands.
    """
    for f in files or []:
        rel = (f.get("path") or "").strip().lstrip("/")
        if not rel:
            continue
        # Refuse paths that try to escape the workdir.
        if ".." in Path(rel).parts:
            logger.warning(f"shell: skipping escape path {rel!r}")
            continue
        out = workdir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f.get("content") or "")


def reset_workdir(project_id: str) -> None:
    """Wipe a project's sandbox. Caller controls when (rarely; we prefer
    persistent caches between turns for fast `npm install`)."""
    p = SHELL_ROOT / str(project_id)
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)


# ─── execution ────────────────────────────────────────────────────────────

@dataclass
class CompletedCommand:
    cmd: str
    exit_code: int
    output: str
    duration_ms: int
    timed_out: bool = False
    truncated: bool = False
    reason: Optional[str] = None       # for refusals
    workdir: Optional[str] = None


def _subprocess_env(workdir: Path) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOW}
    # Reasonable defaults
    env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    env["HOME"] = str(workdir)
    env["TMPDIR"] = str(workdir / ".tmp")
    Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    # Make node tools quieter by default
    env.setdefault("NPM_CONFIG_FUND", "false")
    env.setdefault("NPM_CONFIG_AUDIT", "false")
    env.setdefault("CI", "true")
    return env


async def run_command(
    workdir: Path,
    cmd: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    on_line: Optional[Callable[[str, str], Awaitable[None]]] = None,
) -> CompletedCommand:
    """Run `cmd` under bash -lc inside `workdir`. Streams every line of
    output through `on_line(channel, line)` where channel is "stdout" or
    "stderr"; the same content is also returned in the combined `output`.
    """
    deny = is_command_safe(cmd)
    if deny:
        return CompletedCommand(cmd=cmd, exit_code=126, output=f"[refused] {deny}\n",
                                  duration_ms=0, reason=deny,
                                  workdir=str(workdir))

    env = _subprocess_env(workdir)
    started = time.monotonic()
    output_parts: List[str] = []
    output_bytes = 0
    truncated = False

    proc = await asyncio.create_subprocess_exec(
        "/bin/bash", "-lc", cmd,
        cwd=str(workdir),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def _drain(stream, channel: str):
        nonlocal output_bytes, truncated
        if not stream:
            return
        async for raw in stream:
            try:
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
            except Exception:
                continue
            chunk = f"[{channel}] {line}\n"
            if output_bytes + len(chunk) > MAX_OUTPUT_BYTES:
                truncated = True
                continue
            output_parts.append(chunk)
            output_bytes += len(chunk)
            if on_line:
                try:
                    await on_line(channel, line)
                except Exception:
                    logger.exception("on_line callback raised (suppressed)")

    try:
        stdout_task = asyncio.create_task(_drain(proc.stdout, "stdout"))
        stderr_task = asyncio.create_task(_drain(proc.stderr, "stderr"))
        try:
            exit_code = await asyncio.wait_for(proc.wait(), timeout=timeout)
            timed_out = False
        except asyncio.TimeoutError:
            timed_out = True
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
            exit_code = proc.returncode if proc.returncode is not None else 124
        # Make sure drains finish
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
    except asyncio.CancelledError:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        raise

    return CompletedCommand(
        cmd=cmd,
        exit_code=int(exit_code or 0),
        output="".join(output_parts),
        duration_ms=int((time.monotonic() - started) * 1000),
        timed_out=timed_out,
        truncated=truncated,
        workdir=str(workdir),
    )


# Convenience helper for the chat layer
async def run_in_project(
    project_id: str,
    files: List[Dict[str, str]],
    cmd: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    on_line: Optional[Callable[[str, str], Awaitable[None]]] = None,
) -> CompletedCommand:
    workdir = project_workdir(project_id)
    materialise_files(workdir, files)
    return await run_command(workdir, cmd, timeout=timeout, on_line=on_line)


__all__ = [
    "is_enabled",
    "is_command_safe",
    "CompletedCommand",
    "run_command",
    "run_in_project",
    "project_workdir",
    "materialise_files",
    "reset_workdir",
    "SHELL_ROOT",
    "DEFAULT_TIMEOUT_S",
    "MAX_OUTPUT_BYTES",
]
