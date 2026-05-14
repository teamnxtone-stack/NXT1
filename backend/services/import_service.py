"""Project import & analysis service for NXT1 (Phase 6).

Two import surfaces:
1. ZIP upload (multipart) — extract files, filter binary/giant files, build a
   project skeleton.
2. GitHub repo URL — clone via HTTPS shallow (single branch, depth=1).

Plus a project analyser that detects:
  - frameworks (React, Next, Vue, FastAPI, Express, Django, Flask, Rails, …)
  - dependency manifests (package.json, requirements.txt, Pipfile, go.mod, …)
  - api routes (Flask/Express/FastAPI/Django/Next API)
  - env keys referenced (process.env.X, os.environ['X'])
  - frontend/backend split
  - readiness for runtime + deploy

Output is a structured `analysis` dict that goes into the project doc and the
AI prompt (so the AI understands the imported codebase before editing).
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Files we never want to import
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".cache", "__pycache__",
             ".venv", "venv", "env", ".env.dir", "coverage", ".turbo", ".parcel-cache",
             ".idea", ".vscode", "out", "vendor", ".pytest_cache", ".mypy_cache",
             "site-packages"}
SKIP_FILES = {".DS_Store", "Thumbs.db", "*.pyc", "*.pyo", "*.lock", "yarn.lock",
              "package-lock.json", "pnpm-lock.yaml", "poetry.lock"}
TEXT_EXTS = {".html", ".htm", ".css", ".scss", ".sass", ".js", ".jsx", ".ts", ".tsx",
             ".mjs", ".cjs", ".json", ".md", ".mdx", ".py", ".rb", ".go", ".rs",
             ".java", ".kt", ".cs", ".php", ".sh", ".bash", ".zsh", ".yml", ".yaml",
             ".toml", ".ini", ".cfg", ".conf", ".env.example", ".sql", ".graphql",
             ".gql", ".vue", ".svelte", ".astro", ".prisma", ".dockerfile",
             ".gitignore", ".gitattributes", "Dockerfile", "Procfile", "Makefile",
             "vercel.json", "netlify.toml"}
MAX_FILE_BYTES = 1 * 1024 * 1024  # 1 MB per file
MAX_TOTAL_BYTES = 30 * 1024 * 1024  # 30 MB total
MAX_FILES = 1500


def _is_text_file(name: str) -> bool:
    base = os.path.basename(name)
    if base in TEXT_EXTS:
        return True
    # Match suffix
    for ext in TEXT_EXTS:
        if name.lower().endswith(ext):
            return True
    return False


def _path_skip(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    return any(p in SKIP_DIRS for p in parts)


def extract_zip_to_files(zip_bytes: bytes) -> List[dict]:
    """Open a zip in memory, extract eligible text files, return [{path, content}]."""
    files: List[dict] = []
    total = 0
    bio = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(bio) as zf:
        names = zf.namelist()
        # Detect a single top-level dir (common for github archives)
        top_prefix = ""
        if names:
            roots = {n.split("/", 1)[0] for n in names if "/" in n}
            if len(roots) == 1:
                only = next(iter(roots))
                if all(n == only or n.startswith(only + "/") for n in names):
                    top_prefix = only + "/"
        for info in zf.infolist():
            if info.is_dir():
                continue
            if len(files) >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                break
            raw_path = info.filename
            if top_prefix and raw_path.startswith(top_prefix):
                rel = raw_path[len(top_prefix):]
            else:
                rel = raw_path
            if not rel or _path_skip(rel):
                continue
            if not _is_text_file(rel):
                continue
            if info.file_size > MAX_FILE_BYTES:
                continue
            try:
                data = zf.read(info)
            except Exception:
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text = data.decode("latin-1")
                except Exception:
                    continue
            files.append({"path": rel, "content": text})
            total += info.file_size
    return files


def clone_github_repo(repo_url: str, branch: Optional[str] = None) -> List[dict]:
    """Shallow-clone a public GitHub repo and return [{path, content}].
    Uses git CLI (depth=1). Falls back to GitHub codeload archive if git fails.
    """
    import subprocess
    tmp = tempfile.mkdtemp(prefix="nxt1-import-")
    try:
        cmd = ["git", "clone", "--depth", "1", "--single-branch"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [repo_url, tmp]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except Exception:
            # Fallback to codeload archive: only works for github.com
            return _download_github_archive(repo_url, branch)
        return _walk_dir_to_files(Path(tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _download_github_archive(repo_url: str, branch: Optional[str]) -> List[dict]:
    import requests
    m = re.match(r"https?://github\.com/([^/]+)/([^/.]+)(?:\.git)?/?$", repo_url.strip())
    if not m:
        raise ValueError("Only github.com repos are supported in fallback mode")
    owner, repo = m.group(1), m.group(2)
    ref = branch or "main"
    for try_ref in [ref, "master"]:
        url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{try_ref}"
        r = requests.get(url, timeout=60)
        if r.status_code == 200:
            return extract_zip_to_files(r.content)
    raise ValueError(f"Could not fetch {owner}/{repo} (tried main+master)")


def _walk_dir_to_files(root: Path) -> List[dict]:
    files: List[dict] = []
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # prune
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            full = Path(dirpath) / fn
            rel = str(full.relative_to(root)).replace("\\", "/")
            if not _is_text_file(rel) or _path_skip(rel):
                continue
            try:
                size = full.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                continue
            if len(files) >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                break
            try:
                text = full.read_text("utf-8")
            except UnicodeDecodeError:
                try:
                    text = full.read_text("latin-1")
                except Exception:
                    continue
            files.append({"path": rel, "content": text})
            total += size
    return files


# ---------- Analysis ----------
FRAMEWORK_HINTS = {
    # Frontend frameworks
    "next": [r'"next":\s*"', r"from\s+['\"]next/", r"export\s+default\s+function\s+\w+Page"],
    "nuxt": [r'"nuxt":\s*"', r"nuxt\.config\.(js|ts|mjs)"],
    "react": [r"from\s+['\"]react['\"]", r'"react":\s*"'],
    "react-native": [r'"react-native":\s*"', r"from\s+['\"]react-native['\"]"],
    "expo": [r'"expo":\s*"', r"app\.json.*\"expo\"", r"from\s+['\"]expo[/-]"],
    "electron": [r'"electron":\s*"', r"BrowserWindow", r"require\(['\"]electron['\"]\)"],
    "tauri": [r'"@tauri-apps/', r"tauri\.conf\.json"],
    "vue": [r"from\s+['\"]vue['\"]", r'"vue":\s*"', r"<template>"],
    "svelte": [r'"svelte":\s*"', r"<script>\s*export"],
    "sveltekit": [r'"@sveltejs/kit":\s*"', r"svelte\.config\.(js|ts)"],
    "astro": [r'"astro":\s*"', r"---\s*\n", r"astro\.config\.(mjs|js|ts)"],
    "remix": [r'"@remix-run/', r"remix\.config\.(js|ts)"],
    "qwik": [r'"@builder\.io/qwik":\s*"', r"qwik\.config\.(ts|js)"],
    "solidjs": [r'"solid-js":\s*"', r"from\s+['\"]solid-js['\"]"],
    "angular": [r'"@angular/core":\s*"', r"angular\.json"],
    # Browser extensions
    "chrome-extension": [r'"manifest_version":\s*3', r'"manifest_version":\s*2'],
    # Backend
    "express": [r"from\s+['\"]express['\"]", r"require\(['\"]express['\"]\)", r'"express":\s*"'],
    "hono": [r"from\s+['\"]hono['\"]", r'"hono":\s*"'],
    "fastify": [r"from\s+['\"]fastify['\"]", r'"fastify":\s*"'],
    "koa": [r'"koa":\s*"', r"require\(['\"]koa['\"]\)"],
    "fastapi": [r"from\s+fastapi\s+import", r"FastAPI\(\)"],
    "flask": [r"from\s+flask\s+import", r"Flask\(__name__\)"],
    "django": [r"from\s+django", r"INSTALLED_APPS"],
    "rails": [r"Rails\.application", r"config/routes\.rb"],
    "nest": [r"@nestjs/", r"@Module\("],
    "trpc": [r'"@trpc/', r"initTRPC"],
    "graphql": [r'"graphql":\s*"', r"apollo-server"],
    # Tooling / Build
    "tailwind": [r'"tailwindcss":\s*"', r"@tailwind\s"],
    "vite": [r'"vite":\s*"', r"vite\.config\.(js|ts|mjs)"],
    "webpack": [r'"webpack":\s*"', r"webpack\.config\.(js|ts)"],
    "rollup": [r'"rollup":\s*"', r"rollup\.config\.(js|ts|mjs)"],
    "esbuild": [r'"esbuild":\s*"'],
    "turbo": [r'"turbo":\s*"', r"turbo\.json"],
    "nx": [r'"nx":\s*"', r"nx\.json"],
    "typescript": [r'"typescript":\s*"', r"tsconfig\.json"],
    # Databases / ORMs
    "prisma": [r'"prisma":\s*"', r"datasource\s+db", r"schema\.prisma"],
    "drizzle": [r'"drizzle-orm":\s*"', r"from\s+['\"]drizzle-orm"],
    "supabase": [r'"@supabase/supabase-js":\s*"', r"createClient"],
    "mongodb": [r"from\s+motor", r'"mongodb":\s*"', r"MongoClient"],
    "postgres": [r'"pg":\s*"', r"asyncpg"],
    "sqlite": [r'"better-sqlite3":\s*"', r"sqlite3"],
    # Auth
    "next-auth": [r'"next-auth":\s*"'],
    "clerk": [r'"@clerk/', r"useUser\(\)"],
    "firebase": [r'"firebase":\s*"', r"initializeApp\("],
    # Deploy / CI
    "docker": [r"FROM\s+(node|python|ubuntu|alpine|debian)", r"docker-compose\.yml"],
    "vercel": [r"vercel\.json"],
    "netlify": [r"netlify\.toml"],
    "render": [r"render\.yaml"],
    "cloudflare-pages": [r"wrangler\.toml", r"functions/"],
    # Package managers / workspaces
    "pnpm-workspace": [r"pnpm-workspace\.yaml", r"pnpm-lock\.yaml"],
    "yarn-workspace": [r'"workspaces":\s*\['],
    "bun": [r"bun\.lockb", r'"bun-types":\s*"'],
}


def _grep(files: List[dict], pattern: str) -> bool:
    p = re.compile(pattern)
    for f in files:
        if p.search(f["content"]):
            return True
    return False


def detect_frameworks(files: List[dict]) -> List[str]:
    found = []
    for name, pats in FRAMEWORK_HINTS.items():
        for p in pats:
            if _grep(files, p):
                found.append(name)
                break
    return sorted(set(found))


def detect_dependencies(files: List[dict]) -> dict:
    out: dict = {"node": [], "python": [], "ruby": [], "go": []}
    by_path = {f["path"]: f["content"] for f in files}
    if "package.json" in by_path or any(f["path"].endswith("/package.json") for f in files):
        for f in files:
            if f["path"].endswith("package.json"):
                import json
                try:
                    pkg = json.loads(f["content"])
                except Exception:
                    continue
                deps = list((pkg.get("dependencies") or {}).keys()) + \
                       list((pkg.get("devDependencies") or {}).keys())
                out["node"].extend(deps)
    for path, content in by_path.items():
        if path.endswith("requirements.txt"):
            out["python"].extend(
                [ln.split("==")[0].split(">=")[0].strip()
                 for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
            )
        if path.endswith("Pipfile") or path == "pyproject.toml":
            for m in re.finditer(r'^([a-zA-Z0-9_\-]+)\s*=', content, re.M):
                out["python"].append(m.group(1))
        if path == "Gemfile":
            for m in re.finditer(r"gem\s+['\"]([^'\"]+)['\"]", content):
                out["ruby"].append(m.group(1))
        if path == "go.mod":
            for m in re.finditer(r"^\s+([\w./\-]+)\s+v", content, re.M):
                out["go"].append(m.group(1))
    out = {k: sorted(set(v))[:80] for k, v in out.items() if v}
    return out


def detect_routes(files: List[dict]) -> List[dict]:
    routes: List[dict] = []
    seen = set()
    patterns = [
        # FastAPI / Flask / generic Python decorators
        (r'@(?:app|router|api_router|api)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']', "py"),
        # Express
        (r'\b(?:app|router)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']', "node"),
        # Next pages router
        (r'pages/api/([^.]+)\.(?:js|ts)x?$', "next"),
        # Django urls
        (r'path\(\s*["\']([^"\']+)["\']\s*,', "django"),
    ]
    for f in files:
        c = f["content"]
        for pat, kind in patterns:
            for m in re.finditer(pat, c):
                if kind in ("py", "node"):
                    method = m.group(1).upper()
                    path = m.group(2)
                elif kind == "next":
                    method = "ANY"
                    path = "/api/" + m.group(1)
                else:  # django
                    method = "ANY"
                    path = m.group(1)
                key = (method, path, f["path"])
                if key in seen:
                    continue
                seen.add(key)
                routes.append({"method": method, "path": path, "file": f["path"]})
    routes.sort(key=lambda r: (r["path"], r["method"]))
    return routes


def detect_env_keys(files: List[dict]) -> List[str]:
    keys = set()
    for f in files:
        for m in re.finditer(r"process\.env\.([A-Z_][A-Z0-9_]*)", f["content"]):
            keys.add(m.group(1))
        for m in re.finditer(r"os\.environ(?:\.get)?\(\s*['\"]([A-Z_][A-Z0-9_]*)['\"]", f["content"]):
            keys.add(m.group(1))
        for m in re.finditer(r"os\.environ\[\s*['\"]([A-Z_][A-Z0-9_]*)['\"]\s*\]", f["content"]):
            keys.add(m.group(1))
    return sorted(keys)


def detect_split(files: List[dict]) -> dict:
    has_frontend = any(
        f["path"].endswith((".html", ".jsx", ".tsx")) or f["path"] == "index.html"
        or f["path"].startswith("src/") or f["path"].startswith("app/")
        for f in files
    )
    has_backend = any(
        f["path"].startswith("backend/") or f["path"].endswith("server.py")
        or f["path"].endswith("server.js") or "FastAPI(" in f.get("content", "")
        or "express()" in f.get("content", "")
        for f in files
    )
    return {"frontend": has_frontend, "backend": has_backend}


def detect_preview_entry(files: List[dict]) -> dict:
    """Decide the best HTML entry point + preview strategy for a set of files.

    Returns:
        {
            kind: "static-html" | "spa-built" | "spa-source" | "nextjs" | "fastapi" | "unknown",
            entry_path: str | None,    # path inside `files` we should serve as index
            root: str | None,          # the dir we picked (frontend/, src/, …)
            dist_root: str | None,     # path to a built ./dist or ./build if any
            preview_ok: bool,          # safe to render in NXT1's preview iframe
            hint: str,                 # human-readable explanation
        }
    """
    paths = {f.get("path", "") for f in files}

    def has(p: str) -> bool: return p in paths

    def find_first(*candidates: str) -> Optional[str]:
        for c in candidates:
            if has(c):
                return c
        # fallback: any file ending with the trailing segment
        for cand in candidates:
            tail = cand.split("/")[-1]
            for p in paths:
                if p.endswith("/" + tail):
                    return p
        return None

    # 1) Pre-built static output wins — these render cleanly in the iframe.
    # Order matters: most specific paths first. Includes monorepo conventions,
    # Nuxt 3 (.output/public), SvelteKit (.svelte-kit/output/client), Astro
    # (dist with astro.config present), Next static export (out/).
    BUILT_DIST_CANDIDATES = (
        "frontend/dist/index.html",
        "frontend/build/index.html",
        "dist/index.html",
        "build/index.html",
        "out/index.html",
        "public/index.html",  # only when accompanied by a built bundle (handled below)
        ".output/public/index.html",          # Nuxt 3
        ".svelte-kit/output/client/index.html",  # SvelteKit
        "apps/web/dist/index.html",           # Common monorepo
        "apps/frontend/dist/index.html",
        "apps/web/build/index.html",
        "packages/web/dist/index.html",
        "client/dist/index.html",
        "client/build/index.html",
        "web/dist/index.html",
        "web/build/index.html",
    )
    for dist in BUILT_DIST_CANDIDATES:
        if has(dist):
            return {
                "kind": "spa-built",
                "entry_path": dist,
                "root": dist.rsplit("/", 1)[0],
                "dist_root": dist.rsplit("/", 1)[0],
                "preview_ok": True,
                "hint": "Found a pre-built SPA — serving the compiled bundle.",
            }
    # Glob-style fallback: any */dist/index.html anywhere in the tree.
    for p in sorted(paths):
        if p.endswith("/dist/index.html") or p.endswith("/build/index.html"):
            return {
                "kind": "spa-built",
                "entry_path": p,
                "root": p.rsplit("/", 1)[0],
                "dist_root": p.rsplit("/", 1)[0],
                "preview_ok": True,
                "hint": f"Found pre-built SPA at {p.rsplit('/', 1)[0]} — serving the bundle.",
            }

    # 2) Plain static site (only HTML/CSS/JS, no React/Vite/Next).
    plain_index = find_first("index.html", "public/index.html")
    has_any_pkg = any(p.endswith("package.json") for p in paths)
    if plain_index and not has_any_pkg:
        return {
            "kind": "static-html",
            "entry_path": plain_index,
            "root": plain_index.rsplit("/", 1)[0] or ".",
            "dist_root": None,
            "preview_ok": True,
            "hint": "Static HTML site — rendering directly.",
        }

    # 3) Source SPA — React/Vite/CRA/Next. We CAN'T build npm projects in
    #    the preview server, so we surface the source root and recommend
    #    falling back to the live deploy URL.
    next_config = find_first("next.config.js", "next.config.mjs", "next.config.ts",
                             "frontend/next.config.js", "frontend/next.config.mjs",
                             "frontend/next.config.ts")
    if next_config:
        root = next_config.rsplit("/", 1)[0] or "."
        return {
            "kind": "nextjs",
            "entry_path": None,
            "root": root,
            "dist_root": None,
            "preview_ok": False,
            "hint": (
                "Next.js project detected. The preview iframe can't run a Next "
                "server — use Save to GitHub → Vercel deploy, then point preview "
                "at the live URL."
            ),
        }

    pkg_paths = [p for p in paths if p.endswith("package.json")]
    if pkg_paths:
        # Pick the package.json closest to the SPA entry (frontend/* preferred)
        pkg_paths.sort(key=lambda p: (0 if p.startswith("frontend/") else 1, p.count("/")))
        pkg = pkg_paths[0]
        root = pkg.rsplit("/", 1)[0] or "."
        index_html = find_first(
            f"{root}/index.html",
            f"{root}/public/index.html",
            "index.html",
            "public/index.html",
        )
        try:
            content = next((f["content"] for f in files if f["path"] == pkg), "{}")
            pkg_json = json.loads(content)
        except Exception:
            pkg_json = {}
        deps = {**(pkg_json.get("dependencies") or {}), **(pkg_json.get("devDependencies") or {})}
        framework = (
            "vite" if "vite" in deps else
            "cra" if "react-scripts" in deps else
            "react" if "react" in deps else
            "node"
        )
        return {
            "kind": "spa-source",
            "entry_path": index_html,  # may be None — UI falls back to live URL
            "root": root,
            "dist_root": None,
            "framework": framework,
            # If we have an index.html in the source, we can at least render the
            # static shell. JS bundling won't run (no dev server), but a Vite
            # `index.html` with a script tag often shows the loading state and
            # any non-JS content. Mark preview_ok=True for this case so the
            # iframe attempts to render rather than going straight to fallback.
            "preview_ok": bool(index_html),
            "hint": (
                f"{framework.upper()} source detected at {root}/. "
                + ("Rendering the static shell — for full interactivity, "
                   "Save to GitHub → Vercel deploy and the preview will "
                   "auto-redirect to the live URL." if index_html else
                   "No index.html found in source — falling back to live deploy URL.")
            ),
        }

    # 4) FastAPI / pure backend
    has_fastapi = any(p.endswith("requirements.txt") or p == "backend/server.py" for p in paths)
    if has_fastapi:
        return {
            "kind": "fastapi",
            "entry_path": None,
            "root": "backend" if has("backend/server.py") else ".",
            "dist_root": None,
            "preview_ok": False,
            "hint": "Backend-only project. Preview will surface the deploy URL when available.",
        }

    return {
        "kind": "unknown",
        "entry_path": None,
        "root": None,
        "dist_root": None,
        "preview_ok": False,
        "hint": "Couldn't auto-detect a preview root. Add an index.html or build the project to dist/.",
    }


def analyse(files: List[dict]) -> dict:
    frameworks = detect_frameworks(files)
    deps = detect_dependencies(files)
    routes = detect_routes(files)
    env_keys = detect_env_keys(files)
    split = detect_split(files)
    preview_info = detect_preview_entry(files)
    summary_parts = [f"{len(files)} files"]
    if frameworks: summary_parts.append("frameworks: " + ", ".join(frameworks))
    if split.get("frontend"): summary_parts.append("frontend ✓")
    if split.get("backend"): summary_parts.append("backend ✓")
    if routes: summary_parts.append(f"{len(routes)} api routes")
    summary_parts.append(f"preview: {preview_info['kind']}")
    return {
        "files_count": len(files),
        "frameworks": frameworks,
        "dependencies": deps,
        "routes": routes,
        "env_keys": env_keys,
        "split": split,
        "preview_info": preview_info,
        "summary": " · ".join(summary_parts),
    }
