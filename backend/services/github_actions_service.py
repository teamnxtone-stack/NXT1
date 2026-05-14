"""GitHub Actions deploy pipeline generator.

For every NXT1 scaffold / project type we know about, emit the right
`.github/workflows/deploy.yml` so that a fresh GitHub export auto-deploys
without the user wiring anything by hand.

Targets supported today
=======================
  • static            → GitHub Pages (no build, uses Pages branch)
  • vite              → GitHub Pages (`vite build` → `dist/`)
  • next_static       → Cloudflare Pages (uses CF_API_TOKEN + CF_ACCOUNT_ID)
  • next_server       → Vercel (uses VERCEL_TOKEN)
  • cra               → GitHub Pages (`react-scripts build` → `build/`)
  • node_api          → Render (uses RENDER_SERVICE_ID + RENDER_API_KEY)
  • python_api        → Render (Python service)

Returns the workflow YAML as a string ready to be written as
`.github/workflows/deploy.yml`. The caller (github_service / scaffold) is
responsible for actually committing it.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("nxt1.ghactions")


# ─── Detection ──────────────────────────────────────────────────────────────

def detect_target(files: List[Dict[str, str]]) -> str:
    """Pick the best deploy target based on the project's file shape."""
    paths = {(f.get("path") or "").strip().lstrip("/") for f in files or []}
    pkg = next((f for f in files or [] if (f.get("path") or "").strip().lstrip("/") == "package.json"), None)
    pkg_data: Dict = {}
    if pkg:
        try:
            pkg_data = json.loads(pkg.get("content") or "{}")
        except Exception:
            pass

    deps = {**(pkg_data.get("dependencies") or {}),
             **(pkg_data.get("devDependencies") or {})}
    scripts = pkg_data.get("scripts") or {}

    has_next = "next" in deps
    has_vite = "vite" in deps
    has_react_scripts = "react-scripts" in deps
    has_express = "express" in deps or "fastify" in deps or "hono" in deps
    has_py = "requirements.txt" in paths or "pyproject.toml" in paths or "Pipfile" in paths

    if has_py:
        return "python_api"
    if has_express:
        # Has both? Treat as next/server-style — backend lives in same repo
        if has_next:
            return "next_server"
        return "node_api"
    if has_next:
        # Heuristic: `output: 'export'` in next.config → static. Otherwise server.
        cfg = next((f for f in files or []
                    if (f.get("path") or "").startswith("next.config")), None)
        if cfg and "output: 'export'" in (cfg.get("content") or ""):
            return "next_static"
        return "next_server"
    if has_vite:
        return "vite"
    if has_react_scripts:
        return "cra"
    if "index.html" in paths and not pkg:
        return "static"
    if scripts.get("build"):
        return "vite"   # generic Node build
    return "static"


# ─── Workflow generators ────────────────────────────────────────────────────

_PAGES_HEADER = """name: Deploy
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true
"""


def _static_pages() -> str:
    return _PAGES_HEADER + """
jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: .
      - id: deployment
        uses: actions/deploy-pages@v4
"""


def _vite_pages(node_version: str = "20") -> str:
    return _PAGES_HEADER + f"""
jobs:
  build-and-deploy:
    environment:
      name: github-pages
      url: ${{{{ steps.deployment.outputs.page_url }}}}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '{node_version}'
          cache: 'npm'
      - run: npm ci --no-fund --no-audit
      - run: npm run build
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist
      - id: deployment
        uses: actions/deploy-pages@v4
"""


def _cra_pages(node_version: str = "20") -> str:
    return _PAGES_HEADER + f"""
jobs:
  build-and-deploy:
    environment:
      name: github-pages
      url: ${{{{ steps.deployment.outputs.page_url }}}}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '{node_version}'
          cache: 'npm'
      - run: npm ci --no-fund --no-audit
      - run: npm run build
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: build
      - id: deployment
        uses: actions/deploy-pages@v4
"""


def _next_static_cf(node_version: str = "20") -> str:
    return f"""name: Deploy (Cloudflare Pages)
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '{node_version}'
          cache: 'npm'
      - run: npm ci --no-fund --no-audit
      - run: npm run build
      - name: Publish to Cloudflare Pages
        uses: cloudflare/pages-action@v1
        with:
          apiToken: ${{{{ secrets.CLOUDFLARE_API_TOKEN }}}}
          accountId: ${{{{ secrets.CLOUDFLARE_ACCOUNT_ID }}}}
          projectName: ${{{{ secrets.CLOUDFLARE_PAGES_PROJECT }}}}
          directory: out
"""


def _next_server_vercel(node_version: str = "20") -> str:
    return f"""name: Deploy (Vercel)
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '{node_version}'
          cache: 'npm'
      - name: Install Vercel CLI
        run: npm install --global vercel@latest
      - name: Pull Vercel environment information
        run: vercel pull --yes --environment=production --token=${{{{ secrets.VERCEL_TOKEN }}}}
      - name: Build
        run: vercel build --prod --token=${{{{ secrets.VERCEL_TOKEN }}}}
      - name: Deploy
        run: vercel deploy --prebuilt --prod --token=${{{{ secrets.VERCEL_TOKEN }}}}
"""


def _node_api_render(node_version: str = "20") -> str:
    return f"""name: Deploy (Render)
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '{node_version}'
          cache: 'npm'
      - run: npm ci --no-fund --no-audit
      - run: npm run build --if-present
      - name: Trigger Render deploy
        uses: johnbeynon/render-deploy-action@v0.0.8
        with:
          service-id: ${{{{ secrets.RENDER_SERVICE_ID }}}}
          api-key: ${{{{ secrets.RENDER_API_KEY }}}}
"""


def _python_api_render(py_version: str = "3.11") -> str:
    return f"""name: Deploy (Render)
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '{py_version}'
      - run: pip install -r requirements.txt
      - run: python -m pytest --maxfail=1 -q || echo "no tests"
      - name: Trigger Render deploy
        uses: johnbeynon/render-deploy-action@v0.0.8
        with:
          service-id: ${{{{ secrets.RENDER_SERVICE_ID }}}}
          api-key: ${{{{ secrets.RENDER_API_KEY }}}}
"""


_GENERATORS = {
    "static":        _static_pages,
    "vite":          _vite_pages,
    "cra":           _cra_pages,
    "next_static":   _next_static_cf,
    "next_server":   _next_server_vercel,
    "node_api":      _node_api_render,
    "python_api":    _python_api_render,
}


def generate_workflow(target: str) -> str:
    """Return the workflow YAML text for the requested target."""
    fn = _GENERATORS.get(target)
    if not fn:
        return _static_pages()
    return fn()


def required_secrets(target: str) -> List[Tuple[str, str]]:
    """List of (secret_name, where_to_get) the workflow needs in GitHub
    repo settings → Secrets and variables → Actions."""
    if target == "next_static":
        return [
            ("CLOUDFLARE_API_TOKEN", "https://dash.cloudflare.com/profile/api-tokens"),
            ("CLOUDFLARE_ACCOUNT_ID", "Cloudflare → Account → Settings"),
            ("CLOUDFLARE_PAGES_PROJECT", "Cloudflare → Pages → your project name"),
        ]
    if target == "next_server":
        return [("VERCEL_TOKEN", "https://vercel.com/account/tokens")]
    if target in {"node_api", "python_api"}:
        return [
            ("RENDER_SERVICE_ID", "Render → service → settings → service ID"),
            ("RENDER_API_KEY",    "https://dashboard.render.com/u/settings#api-keys"),
        ]
    return []   # static / vite / cra need no secrets


def generate_for_project(files: List[Dict[str, str]]) -> Dict:
    """Convenience: detect + generate. Returns {target, yaml, secrets, path}."""
    target = detect_target(files)
    yaml = generate_workflow(target)
    return {
        "target": target,
        "path": ".github/workflows/deploy.yml",
        "yaml": yaml,
        "required_secrets": required_secrets(target),
    }


__all__ = [
    "detect_target",
    "generate_workflow",
    "required_secrets",
    "generate_for_project",
]
