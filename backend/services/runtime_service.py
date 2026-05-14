"""Backend runtime sandbox for NXT1.

This module manages subprocess-based execution of generated backends (FastAPI
first, Node/Express adapter ready). It is NOT a container-grade isolation
layer — it runs each project's backend as a child process in the same pod with:
  - separate working directory under /tmp/nxt1-runtimes/<project_id>/
  - restricted env (only the project's env_vars + a safe baseline)
  - resource limits via resource.RLIMIT_AS (memory cap) and RLIMIT_NPROC
  - idle auto-stop after RUNTIME_IDLE_TIMEOUT seconds with no proxy hits
  - log capture into a ring buffer per project

The proxy `/api/runtime/{project_id}/{path}` forwards requests to the running
process's localhost port. The frontend iframe preview can call its own backend
through this proxy.

For real production-grade isolation we'd want Docker / Firecracker / gVisor;
that requires a container runtime outside this pod and is left for Phase 6.
"""
import os
import re
import sys
import time
import uuid
import shutil
import signal
import asyncio
import logging
import resource
import subprocess
from datetime import datetime, timezone
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Deque

logger = logging.getLogger("nxt1.runtime")

RUNTIME_ROOT = Path("/tmp/nxt1-runtimes")
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

PORT_RANGE_START = 19000
PORT_RANGE_END = 19999
LOG_RING_SIZE = 1500
RUNTIME_IDLE_TIMEOUT = 15 * 60  # seconds
RUNTIME_STARTUP_GRACE = 4.0  # seconds before reporting status
MEMORY_CAP_BYTES = 512 * 1024 * 1024  # 512 MB
PROC_LIMIT = 64

# In-memory registry: project_id -> RuntimeHandle
_RUNTIMES: Dict[str, "RuntimeHandle"] = {}
_PORTS_IN_USE: set = set()
_lock = asyncio.Lock()


def _alloc_port() -> int:
    for p in range(PORT_RANGE_START, PORT_RANGE_END):
        if p not in _PORTS_IN_USE:
            _PORTS_IN_USE.add(p)
            return p
    raise RuntimeError("No free runtime ports available")


def _free_port(p: int):
    _PORTS_IN_USE.discard(p)


def _safe_env(custom: Dict[str, str]) -> Dict[str, str]:
    """Build a minimal env dict for the runtime subprocess."""
    base = {
        "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "NODE_ENV": "production",
        "HOME": str(RUNTIME_ROOT),
    }
    # Strip sensitive platform vars; only inject project env_vars
    for k, v in (custom or {}).items():
        if k.startswith(("AWS_", "K8S_", "KUBE", "MONGO_URL", "JWT_SECRET", "OPENAI_API_KEY",
                         "ANTHROPIC_API_KEY", "EMERGENT_LLM_KEY", "VERCEL_TOKEN", "CLOUDFLARE_")):
            # Only allow these if the user explicitly set them via env_vars (the user's project env)
            pass
        base[k] = str(v) if v is not None else ""
    return base


def _detect_runtime_type(files: List[dict]) -> Optional[dict]:
    """Heuristically pick how to run the backend.
    Returns: { 'kind': 'python'|'node', 'entry': str, 'cmd': [...], 'requirements': [...] } or None.
    """
    paths = {f["path"]: f["content"] for f in files or []}
    backend_files = {p: c for p, c in paths.items() if p.startswith("backend/")}
    # Python
    py_entry_candidates = ["backend/server.py", "backend/main.py", "backend/app.py", "backend/api.py"]
    for entry in py_entry_candidates:
        if entry in backend_files:
            req = backend_files.get("backend/requirements.txt", "")
            return {
                "kind": "python",
                "entry": entry,
                "cmd": [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "{port}"]
                       if entry.endswith("server.py") else
                       [sys.executable, entry.split("/", 1)[1]],
                "requirements": [l.strip() for l in req.splitlines() if l.strip() and not l.startswith("#")],
            }
    # Node
    node_entry_candidates = ["backend/server.js", "backend/index.js", "backend/app.js"]
    for entry in node_entry_candidates:
        if entry in backend_files:
            has_pkg = "backend/package.json" in backend_files
            return {
                "kind": "node",
                "entry": entry,
                "cmd": ["node", entry.split("/", 1)[1]],
                "requirements": [],
                "needs_npm_install": has_pkg,
            }
    return None


def _materialize(project_id: str, files: List[dict]) -> Path:
    """Write the project's backend/ files to a fresh runtime workspace."""
    work = RUNTIME_ROOT / project_id
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for f in files:
        if not f["path"].startswith("backend/"):
            continue
        rel = f["path"].split("/", 1)[1]
        target = work / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"])
    return work


def _apply_limits():
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_CAP_BYTES, MEMORY_CAP_BYTES))
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (PROC_LIMIT, PROC_LIMIT))
    except Exception:
        pass
    # New session so we can kill the whole group
    try:
        os.setsid()
    except Exception:
        pass


class RuntimeHandle:
    def __init__(self, project_id: str, kind: str, entry: str, port: int, work_dir: Path):
        self.project_id = project_id
        self.kind = kind
        self.entry = entry
        self.port = port
        self.work_dir = work_dir
        self.process: Optional[subprocess.Popen] = None
        self.started_at: Optional[str] = None
        self.last_proxy_at: float = time.time()
        self.logs: Deque[dict] = deque(maxlen=LOG_RING_SIZE)
        self.endpoints: List[str] = []
        self.endpoints_full: List[dict] = []
        self._reader_task: Optional[asyncio.Task] = None
        self.stopped: bool = False
        self.error: Optional[str] = None
        self.health_status: Optional[dict] = None  # { ok, status_code, ts }

    def status_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "kind": self.kind,
            "entry": self.entry,
            "port": self.port,
            "started_at": self.started_at,
            "last_active": datetime.fromtimestamp(self.last_proxy_at, tz=timezone.utc).isoformat(),
            "alive": self.is_alive(),
            "stopped": self.stopped,
            "error": self.error,
            "endpoints": self.endpoints,
            "endpoints_full": self.endpoints_full,
            "health": self.health_status,
            "log_count": len(self.logs),
        }

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None and not self.stopped

    def append_log(self, level: str, msg: str):
        self.logs.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "msg": msg.rstrip(),
        })

    async def _read_stream(self, stream, level: str):
        loop = asyncio.get_event_loop()
        while not self.stopped:
            line = await loop.run_in_executor(None, stream.readline)
            if not line:
                break
            text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
            self.append_log(level, text)

    async def start_readers(self):
        if not self.process:
            return
        # We started with text=False, so readline returns bytes
        async def _drain(stream, level):
            try:
                await self._read_stream(stream, level)
            except Exception as e:  # noqa: BLE001
                self.append_log("error", f"reader error: {e}")
        asyncio.create_task(_drain(self.process.stdout, "stdout"))
        asyncio.create_task(_drain(self.process.stderr, "stderr"))


async def _install_python_deps(handle: RuntimeHandle, requirements: List[str]):
    if not requirements:
        return
    handle.append_log("info", f"› installing {len(requirements)} python packages…")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir", *requirements,
        cwd=str(handle.work_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        handle.append_log("error", f"pip install failed: {err.decode(errors='replace')[:500]}")
        raise RuntimeError(f"pip install failed: {err.decode(errors='replace')[:200]}")
    handle.append_log("info", "✓ dependencies installed")


async def _install_node_deps(handle: RuntimeHandle):
    """Run `npm install --no-audit --no-fund --silent` if backend/package.json exists."""
    pkg_path = handle.work_dir / "package.json"
    if not pkg_path.exists():
        return
    handle.append_log("info", "› npm install…")
    proc = await asyncio.create_subprocess_exec(
        "npm", "install", "--no-audit", "--no-fund", "--silent",
        cwd=str(handle.work_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        handle.append_log("error", f"npm install failed: {err.decode(errors='replace')[:500]}")
        raise RuntimeError(f"npm install failed: {err.decode(errors='replace')[:200]}")
    handle.append_log("info", "✓ node modules installed")


def _detect_endpoints(files: List[dict]) -> List[str]:
    """Return path strings only (legacy)."""
    return [e["path"] for e in _detect_endpoints_full(files)]


def _detect_endpoints_full(files: List[dict]) -> List[dict]:
    """Return rich endpoints: [{ method, path, file, line }]."""
    out: List[dict] = []
    seen = set()
    for f in files or []:
        if not f["path"].startswith("backend/"):
            continue
        content = f["content"]
        # Python: @app.get("/p"), @api_router.post("/p"), etc.
        for m in re.finditer(
            r'@(?:app|router|api_router)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']',
            content, re.IGNORECASE,
        ):
            method = m.group(1).upper()
            path = m.group(2)
            line = content[:m.start()].count("\n") + 1
            key = (method, path)
            if key not in seen:
                seen.add(key)
                out.append({"method": method, "path": path, "file": f["path"], "line": line})
        # Express: app.get("/p", ...), router.post("/p")
        for m in re.finditer(
            r'\b(?:app|router)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']',
            content, re.IGNORECASE,
        ):
            method = m.group(1).upper()
            path = m.group(2)
            line = content[:m.start()].count("\n") + 1
            key = (method, path)
            if key not in seen:
                seen.add(key)
                out.append({"method": method, "path": path, "file": f["path"], "line": line})
    out.sort(key=lambda e: (e["path"], e["method"]))
    return out


async def start_runtime(project_id: str, files: List[dict], env_vars: Dict[str, str]) -> RuntimeHandle:
    async with _lock:
        existing = _RUNTIMES.get(project_id)
        if existing and existing.is_alive():
            existing.append_log("info", "↺ stop existing runtime before re-start")
            await stop_runtime(project_id, hold_lock=True)

        rt = _detect_runtime_type(files)
        if not rt:
            raise RuntimeError("No backend entry found. Add `backend/server.py` (FastAPI) or `backend/server.js` (Node).")

        port = _alloc_port()
        work = _materialize(project_id, files)
        handle = RuntimeHandle(project_id, rt["kind"], rt["entry"], port, work)
        handle.endpoints = _detect_endpoints(files)
        handle.endpoints_full = _detect_endpoints_full(files)
        _RUNTIMES[project_id] = handle

        try:
            if rt["kind"] == "python" and rt["requirements"]:
                # Best-effort install with a 60s cap
                try:
                    await asyncio.wait_for(_install_python_deps(handle, rt["requirements"]), timeout=60)
                except asyncio.TimeoutError:
                    handle.append_log("warn", "× pip install timed out after 60s — starting anyway")
                except Exception as e:  # noqa: BLE001
                    handle.append_log("error", f"× dep install error: {e}")
            elif rt["kind"] == "node" and rt.get("needs_npm_install"):
                try:
                    await asyncio.wait_for(_install_node_deps(handle), timeout=120)
                except asyncio.TimeoutError:
                    handle.append_log("warn", "× npm install timed out after 120s — starting anyway")
                except Exception as e:  # noqa: BLE001
                    handle.append_log("error", f"× npm install error: {e}")

            cmd = [c.replace("{port}", str(port)) if isinstance(c, str) else c for c in rt["cmd"]]
            handle.append_log("info", f"› launching: {' '.join(cmd)} (port {port})")

            env = _safe_env(env_vars or {})
            env["PORT"] = str(port)

            proc = subprocess.Popen(
                cmd,
                cwd=str(work),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=_apply_limits,
                bufsize=1,
            )
            handle.process = proc
            handle.started_at = datetime.now(timezone.utc).isoformat()
            await handle.start_readers()

            # Brief grace to surface immediate errors
            await asyncio.sleep(RUNTIME_STARTUP_GRACE)
            if not handle.is_alive():
                code = handle.process.returncode if handle.process else None
                handle.error = f"Process exited (code={code}) shortly after start. See logs."
                _free_port(port)
                raise RuntimeError(handle.error)

            handle.append_log("info", f"✓ runtime ready at http://127.0.0.1:{port}")
            return handle
        except Exception:
            _free_port(port)
            raise


async def stop_runtime(project_id: str, hold_lock: bool = False) -> bool:
    async def _do():
        handle = _RUNTIMES.get(project_id)
        if not handle:
            return False
        handle.stopped = True
        if handle.process and handle.process.poll() is None:
            try:
                # Kill the whole process group
                os.killpg(os.getpgid(handle.process.pid), signal.SIGTERM)
            except Exception:
                try: handle.process.terminate()
                except Exception: pass
            try:
                handle.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(os.getpgid(handle.process.pid), signal.SIGKILL)
                except Exception: pass
        handle.append_log("info", "› stopped")
        _free_port(handle.port)
        return True

    if hold_lock:
        return await _do()
    async with _lock:
        return await _do()


async def restart_runtime(project_id: str, files: List[dict], env_vars: Dict[str, str]) -> RuntimeHandle:
    await stop_runtime(project_id)
    return await start_runtime(project_id, files, env_vars)


def get_handle(project_id: str) -> Optional[RuntimeHandle]:
    return _RUNTIMES.get(project_id)


# --- error detection for autonomous debugging ----------------------------
ERROR_HINTS = (
    "Traceback (most recent call last):",
    "Error:",
    "TypeError",
    "ValueError",
    "ImportError",
    "ModuleNotFoundError",
    "SyntaxError",
    "RuntimeError",
    "AttributeError",
    "NameError",
    "FileNotFoundError",
    "exception",
    "Cannot find module",
    "Unhandled rejection",
    "EADDRINUSE",
    "ECONNREFUSED",
    "uncaughtException",
    "ECONNRESET",
)


def extract_recent_errors(project_id: str, max_lines: int = 80) -> dict:
    """Return {has_errors, error_text, recent_logs[]} from a runtime's recent log buffer."""
    handle = _RUNTIMES.get(project_id)
    if not handle:
        return {"has_errors": False, "error_text": "", "recent_logs": []}
    logs = list(handle.logs)[-max_lines:]
    error_lines = []
    for line in logs:
        msg = (line.get("msg") or "")
        lvl = line.get("level", "")
        if lvl in ("error", "stderr") or any(h in msg for h in ERROR_HINTS):
            error_lines.append(f"[{lvl}] {msg}")
    has_errors = bool(error_lines) or (handle.error and not handle.is_alive())
    error_text = ""
    if handle.error and not handle.is_alive():
        error_text = f"Runtime exited: {handle.error}\n\n"
    error_text += "\n".join(error_lines[-30:])
    if not error_text.strip():
        error_text = "\n".join(f"[{l.get('level','info')}] {l.get('msg','')}" for l in logs[-30:])
    return {
        "has_errors": bool(has_errors),
        "error_text": error_text[:6000],
        "recent_logs": logs,
        "alive": handle.is_alive(),
        "runtime_error": handle.error,
    }


def list_all_status() -> List[dict]:
    return [h.status_dict() for h in _RUNTIMES.values()]


async def idle_sweeper():
    """Stop runtimes that have been idle past RUNTIME_IDLE_TIMEOUT."""
    while True:
        try:
            now = time.time()
            for pid, h in list(_RUNTIMES.items()):
                if not h.is_alive():
                    continue
                if now - h.last_proxy_at > RUNTIME_IDLE_TIMEOUT:
                    logger.info(f"idle sweep: stopping {pid}")
                    h.append_log("info", "› idle timeout — auto-stopping")
                    await stop_runtime(pid)
        except Exception as e:  # noqa: BLE001
            logger.error(f"idle sweeper: {e}")
        await asyncio.sleep(60)


# ---------- Proxy support ----------
import httpx  # noqa: E402

_proxy_client: Optional[httpx.AsyncClient] = None


def _proxy() -> httpx.AsyncClient:
    global _proxy_client
    if _proxy_client is None:
        _proxy_client = httpx.AsyncClient(timeout=30.0, follow_redirects=False)
    return _proxy_client


async def proxy_request(project_id: str, method: str, path: str, headers: dict, body: bytes,
                        query: str) -> tuple[int, dict, bytes]:
    handle = _RUNTIMES.get(project_id)
    if not handle or not handle.is_alive():
        return 503, {"content-type": "application/json"}, b'{"error":"runtime not running"}'
    handle.last_proxy_at = time.time()
    url = f"http://127.0.0.1:{handle.port}/{path.lstrip('/')}"
    if query:
        url += f"?{query}"
    # Strip hop-by-hop headers
    fwd_headers = {k: v for k, v in headers.items() if k.lower() not in
                   ("host", "content-length", "authorization", "cookie", "connection")}
    try:
        resp = await _proxy().request(method, url, content=body, headers=fwd_headers)
        out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in
                       ("transfer-encoding", "content-encoding", "content-length", "connection")}
        return resp.status_code, out_headers, resp.content
    except Exception as e:  # noqa: BLE001
        handle.append_log("error", f"proxy: {e}")
        return 502, {"content-type": "application/json"}, f'{{"error":"proxy: {e}"}}'.encode()


async def health_probe(project_id: str, path: str = "/api/health") -> dict:
    """Hit the runtime's health endpoint directly (not through proxy logging)."""
    handle = _RUNTIMES.get(project_id)
    if not handle or not handle.is_alive():
        return {"ok": False, "alive": False, "ts": datetime.now(timezone.utc).isoformat()}
    url = f"http://127.0.0.1:{handle.port}{path if path.startswith('/') else '/' + path}"
    try:
        resp = await _proxy().get(url, timeout=3.0)
        result = {
            "ok": 200 <= resp.status_code < 300,
            "status_code": resp.status_code,
            "alive": True,
            "ts": datetime.now(timezone.utc).isoformat(),
            "body_preview": resp.text[:200],
        }
    except Exception as e:  # noqa: BLE001
        result = {"ok": False, "alive": True, "error": str(e),
                  "ts": datetime.now(timezone.utc).isoformat()}
    handle.health_status = result
    return result
