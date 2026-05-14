"""NXT1 — Scaffold + import routes (Phase 11 W4 Tracks 1 + 4).

Exposes the scaffold catalogue + a ZIP/manifest inspection endpoint.

  GET  /api/scaffolds                  — catalogue (no file bodies)
  GET  /api/scaffolds/{id}             — full scaffold (with file bodies)
  POST /api/scaffolds/infer            — prompt -> picked scaffold preview
  POST /api/imports/inspect            — inspect a project manifest payload
                                          (package.json / requirements.txt /
                                          pyproject / app.json / manifest.json)
                                          and report the detected framework,
                                          package manager, scripts, env vars.

Note: actual ZIP file extraction is handled in services/github_service.py
which already accepts uploads. /imports/inspect is a *lightweight*
introspection endpoint that lets the UI preview what will be detected
before committing to a full import.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.scaffolds import list_scaffolds, get_scaffold, pick_scaffold, enrich_kind_with_scaffold
from services.inference_service import infer_project_kind

from ._deps import verify_token

router = APIRouter(prefix="/api", tags=["scaffolds"])


# ============================================================
#   Scaffolds catalogue
# ============================================================
@router.get("/scaffolds")
async def scaffolds_index(_: str = Depends(verify_token)):
    return {"scaffolds": list_scaffolds()}


@router.get("/scaffolds/{scaffold_id}")
async def scaffolds_get(scaffold_id: str, _: str = Depends(verify_token)):
    s = get_scaffold(scaffold_id)
    if not s:
        raise HTTPException(status_code=404, detail="Scaffold not found")
    return s


class _InferIn(BaseModel):
    prompt: str


@router.post("/scaffolds/infer")
async def scaffolds_infer(body: _InferIn, _: str = Depends(verify_token)):
    """Run the full inference -> scaffold-pick chain on a prompt."""
    inf = infer_project_kind(body.prompt or "")
    s_summary = enrich_kind_with_scaffold(inf.kind)
    return {
        "inference": inf.to_dict(),
        "scaffold":  s_summary,
        "will_load": bool(s_summary),
    }


# ============================================================
#   Import inspector  (Track 4)
# ============================================================
class _ImportIn(BaseModel):
    files:     Optional[Dict[str, str]] = None   # path -> small text content
    file_tree: Optional[List[str]]      = None   # just the file paths (when content too large)


def _detect_pkg_manager(files: Dict[str, str], tree: List[str]) -> str:
    if "pnpm-lock.yaml" in tree:
        return "pnpm"
    if "yarn.lock" in tree:
        return "yarn"
    if "bun.lockb" in tree:
        return "bun"
    if "package-lock.json" in tree:
        return "npm"
    if "poetry.lock" in tree:
        return "poetry"
    if "Pipfile.lock" in tree:
        return "pipenv"
    if "requirements.txt" in tree:
        return "pip"
    if "package.json" in tree:
        return "npm"
    if "pyproject.toml" in tree:
        return "pip"
    return "unknown"


def _safe_json(s: str) -> Optional[Dict]:
    try:
        return json.loads(s)
    except Exception:
        return None


def _detect_framework(files: Dict[str, str], tree: List[str]) -> Dict:
    """Best-effort framework + entry detection."""
    out: Dict = {"framework": "unknown", "flavor": None}
    pkg_raw = files.get("package.json") or files.get("frontend/package.json")
    pkg = _safe_json(pkg_raw or "") or {}
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}

    if "next" in deps:
        out["framework"] = "nextjs"
        out["flavor"] = "app-router" if ("app/page.tsx" in tree or "app/page.jsx" in tree or "app/layout.tsx" in tree) else "pages-router"
    elif "vite" in deps:
        out["framework"] = "vite"
        out["flavor"] = "react" if "react" in deps else None
    elif "expo" in deps or "app.json" in tree:
        out["framework"] = "expo"
    elif "@tauri-apps/api" in deps or any(p.startswith("src-tauri/") for p in tree):
        out["framework"] = "tauri"
    elif "turbo" in deps or "turbo.json" in tree:
        out["framework"] = "turborepo"
    elif "express" in deps:
        out["framework"] = "express"
    elif "react" in deps:
        out["framework"] = "react-spa"

    # Python
    if any(p.endswith("requirements.txt") or p == "pyproject.toml" for p in tree):
        if "main.py" in tree or "app.py" in tree or "server.py" in tree:
            reqs = (files.get("requirements.txt") or files.get("backend/requirements.txt") or "")
            if "fastapi" in reqs.lower():
                out["backend_framework"] = "fastapi"
            elif "flask" in reqs.lower():
                out["backend_framework"] = "flask"
            elif "django" in reqs.lower():
                out["backend_framework"] = "django"

    # Browser extension
    if "manifest.json" in tree:
        man = _safe_json(files.get("manifest.json") or "") or {}
        if man.get("manifest_version") in (2, 3):
            out["framework"] = "browser-extension"
            out["flavor"] = f"mv{man['manifest_version']}"

    return out


def _extract_scripts(files: Dict[str, str]) -> Dict[str, str]:
    pkg = _safe_json(files.get("package.json") or "") or {}
    return dict(pkg.get("scripts") or {})


ENV_PATTERN = re.compile(r"^\s*([A-Z][A-Z0-9_]+)\s*=", re.MULTILINE)
CODE_ENV_PATTERN = re.compile(r"(?:process\.env|os\.environ)\.(?:get\(['\"]|)([A-Z][A-Z0-9_]+)", re.MULTILINE)


def _detect_env_vars(files: Dict[str, str]) -> List[str]:
    out = set()
    for path, body in (files or {}).items():
        lower = path.lower()
        if lower.endswith(".env") or lower.endswith(".env.example") or lower.endswith(".env.local"):
            for m in ENV_PATTERN.finditer(body or ""):
                out.add(m.group(1))
        elif lower.endswith((".js", ".jsx", ".ts", ".tsx", ".py")):
            for m in CODE_ENV_PATTERN.finditer(body or ""):
                out.add(m.group(1))
    return sorted(out)


@router.post("/imports/inspect")
async def imports_inspect(body: _ImportIn, _: str = Depends(verify_token)):
    """Inspect a (sampled) project payload + return detected framework,
    package manager, scripts, env vars, build/start commands, and a
    suggested matching scaffold id. Used by the GitHub/ZIP import UI to
    preview what NXT1 will infer before committing to a full import.
    """
    files = body.files or {}
    tree  = body.file_tree or list(files.keys())
    fw    = _detect_framework(files, tree)
    pm    = _detect_pkg_manager(files, tree)
    scripts = _extract_scripts(files)
    env_vars = _detect_env_vars(files)

    # Suggest a matching scaffold by framework.
    fw_id = (fw.get("framework") or "").lower()
    fw_map = {
        "nextjs":            "nextjs-tailwind",
        "vite":              "react-vite",
        "react-spa":         "react-vite",
        "expo":              "expo-rn",
        "tauri":             "tauri-desktop",
        "turborepo":         "turborepo-monorepo",
        "express":           "express-backend",
        "browser-extension": "browser-extension",
    }
    bk_map = {
        "fastapi": "fastapi-backend",
    }
    suggested_id = fw_map.get(fw_id) or bk_map.get(fw.get("backend_framework") or "") or ""

    suggested = pick_scaffold(suggested_id) if suggested_id else None
    if suggested:
        suggested = {k: v for k, v in suggested.items() if k != "files"}

    return {
        "detected": {
            "framework":         fw.get("framework"),
            "flavor":            fw.get("flavor"),
            "backend_framework": fw.get("backend_framework"),
            "package_manager":   pm,
            "scripts":           scripts,
            "env_vars":          env_vars,
            "build_command":     scripts.get("build")  or "",
            "start_command":     scripts.get("start")  or scripts.get("dev") or "",
            "dev_command":       scripts.get("dev")    or scripts.get("start") or "",
        },
        "suggested_scaffold": suggested,
    }
