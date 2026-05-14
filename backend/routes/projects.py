"""Project CRUD + state + memory + publish-on-save (Phase 8 modular refactor).

Robustness note (Phase B.5 hardening — Feb 2026)
================================================
ALL string-typed fields on these models use `field_validator(mode="before")`
to coerce `None` / numbers / oddly-typed inputs into safe strings. This
protects every endpoint from the FE accidentally sending `null` or omitting
a field (Pydantic 2 default = 422 with "Input should be a valid string"),
AND protects response serialisation from legacy DB documents that may have
`name: None` from earlier builds. The builder pipeline is the highest-
churn entry point — we never want it to fail on a name mishap.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from ._deps import db, verify_token

router = APIRouter(prefix="/api", tags=["projects"])


def _coerce_name(v) -> str:
    """Normalize `name`-style fields. Accept None / numbers / weird strings,
    emit a clean non-empty title.

    Special case (2026-05-13 — frontend bug): callers occasionally passed
    a whole payload object as `name` (e.g. `createProject({...})` against
    the old positional helper). Without this fallback, `str(v)` rendered
    the whole dict as `"{'name': '…', 'prompt': '…'}"` and poisoned the
    dashboard. Recover the inner name when we see it.
    """
    if v is None:
        return "Untitled project"
    if isinstance(v, dict):
        # Best-effort: pull the most likely human-readable field out.
        for k in ("name", "title", "label"):
            inner = v.get(k)
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
        # Fall back to prompt → first 60 chars as title.
        p = v.get("prompt")
        if isinstance(p, str) and p.strip():
            return p.strip()[:60]
        return "Untitled project"
    s = str(v).strip()
    return s or "Untitled project"


def _coerce_str_or_empty(v) -> str:
    if v is None:
        return ""
    return str(v)


# ---------- Models ----------
class FileItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str
    content: str = ""

    @field_validator("path", mode="before")
    @classmethod
    def _v_path(cls, v):
        s = _coerce_str_or_empty(v).lstrip("/")
        return s or "untitled.txt"

    @field_validator("content", mode="before")
    @classmethod
    def _v_content(cls, v):
        return _coerce_str_or_empty(v)


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # Accept anything: the validator below normalises to a friendly default.
    name: Optional[str] = None
    description: Optional[str] = ""
    # Legacy + new template hint keys. We accept ALL of them and pick the
    # first usable one, so the FE can keep evolving without breaking the BE
    # contract.
    template: Optional[str] = None          # NXT1 scaffold kind ("react-vite", ...)
    scaffold_id: Optional[str] = None       # FE alias for `template`
    framework: Optional[str] = None         # FE: "react", "next", "static", …
    prompt: Optional[str] = None            # initial user prompt (used to infer scaffold)
    mode: Optional[str] = None              # FE: "app", "website", "fullstack"

    @field_validator("name", mode="before")
    @classmethod
    def _v_name(cls, v):
        return _coerce_name(v)

    @field_validator("description", "template", "scaffold_id", "framework",
                      "prompt", "mode", mode="before")
    @classmethod
    def _v_str(cls, v):
        if v is None:
            return None if cls.__name__ == "_unused" else ""
        return str(v)

    def resolve_scaffold_kind(self) -> Optional[str]:
        """Pick the best NXT1 scaffold kind from whatever the FE sent.

        Priority:
          1. `template` (explicit)
          2. `scaffold_id` (FE alias) — may be a NXT1 kind or a friendly id
          3. `framework` heuristic
          4. `prompt` keyword inference (lazy import to avoid cycles)
        """
        # Normalise FE scaffold_id (kebab) into NXT1 kind set.
        FE_TO_KIND = {
            "react-vite": "react-vite",
            "next": "nextjs-tailwind",
            "nextjs": "nextjs-tailwind",
            "nextjs-tailwind": "nextjs-tailwind",
            "expo": "expo-rn",
            "expo-rn": "expo-rn",
            "extension": "browser-extension",
            "browser-extension": "browser-extension",
            "chat": "ai-chat-streaming",
            "ai-chat-streaming": "ai-chat-streaming",
            "static": "web-static",
            "html": "web-static",
            "web-static": "web-static",
        }
        if self.template and self.template in FE_TO_KIND:
            return FE_TO_KIND[self.template]
        if self.template:
            return self.template   # caller does its own fallback
        if self.scaffold_id and self.scaffold_id in FE_TO_KIND:
            return FE_TO_KIND[self.scaffold_id]
        fw = (self.framework or "").lower()
        if fw in FE_TO_KIND:
            return FE_TO_KIND[fw]
        # Prompt-driven inference (best-effort; never raises)
        if self.prompt:
            try:
                from services.inference_service import infer_project_kind
                r = infer_project_kind(self.prompt)
                # `infer_project_kind` may return an `InferenceResult`
                # dataclass or a plain string depending on the version.
                kind = getattr(r, "kind", r)
                return kind if isinstance(kind, str) else None
            except Exception:
                return None
        return None


class ProjectMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    description: str = ""
    created_at: str
    updated_at: str
    deployed: bool = False
    deploy_slug: Optional[str] = None

    @field_validator("name", mode="before")
    @classmethod
    def _v_name(cls, v):
        return _coerce_name(v)

    @field_validator("description", mode="before")
    @classmethod
    def _v_desc(cls, v):
        return _coerce_str_or_empty(v)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _v_ts(cls, v):
        if v is None:
            return datetime.now(timezone.utc).isoformat()
        return str(v)


class ProjectFull(ProjectMeta):
    files: List[FileItem] = []
    github: Optional[dict] = None
    prompt: Optional[str] = ""  # bug fix iter4 #5: surface initial prompt


class PublishToggle(BaseModel):
    publish_on_save: bool


# ---------- Default scaffold ----------
DEFAULT_INDEX_HTML = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"/>
  <title>New NXT1 Project</title>
  <link rel=\"stylesheet\" href=\"styles/main.css\" />
</head>
<body>
  <main class=\"hero\">
    <div class=\"badge\">NXT1 / NEW BUILD</div>
    <h1>Describe what to build.</h1>
    <p>Open the chat panel and tell NXT1 what you want. It will generate the code, render the preview, and let you deploy.</p>
  </main>
  <script src=\"scripts/app.js\"></script>
</body>
</html>
"""

DEFAULT_STYLES_CSS = """:root { --bg:#0a0a0a; --fg:#fff; --muted:#a1a1aa; --accent:#ff8a3d; --accent2:#3ec5b9; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--fg);
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px;
}
.hero { max-width: 720px; text-align: left; }
.badge {
  display: inline-block;
  font: 600 11px/1 monospace;
  letter-spacing: 0.22em;
  padding: 6px 10px;
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 2px;
  color: var(--muted);
  margin-bottom: 24px;
}
h1 {
  font-size: clamp(40px, 6vw, 72px);
  letter-spacing: -0.03em;
  line-height: 1;
  background: linear-gradient(120deg, var(--accent2), var(--accent));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  margin-bottom: 18px;
}
p { color: var(--muted); font-size: 18px; line-height: 1.6; max-width: 56ch; }
"""

DEFAULT_SCRIPT_JS = "// Your project scripts go here.\nconsole.log('NXT1 project ready');\n"

DEFAULT_README = """# NXT1 Project

This project was scaffolded by NXT1.

## Files
- `index.html` — entry page
- `styles/main.css` — global styles
- `scripts/app.js` — JS entry point

## Run locally
Open `index.html` directly, or serve the folder with `python3 -m http.server`.

## Deploy
Click **Deploy** in NXT1 to publish to a public URL. Add a custom domain via the **Domains** panel.
"""


def default_files() -> List[dict]:
    return [
        {"path": "index.html", "content": DEFAULT_INDEX_HTML},
        {"path": "styles/main.css", "content": DEFAULT_STYLES_CSS},
        {"path": "scripts/app.js", "content": DEFAULT_SCRIPT_JS},
        {"path": "README.md", "content": DEFAULT_README},
    ]


# ---------- Routes ----------
@router.get("/projects", response_model=List[ProjectMeta])
async def list_projects(_: str = Depends(verify_token)):
    docs = await db.projects.find(
        {}, {"_id": 0, "files": 0, "messages": 0, "versions": 0,
             "deployments": 0, "domains": 0},
    ).sort("updated_at", -1).to_list(500)
    return [ProjectMeta(**d) for d in docs]


@router.post("/projects", response_model=ProjectFull)
async def create_project(body: ProjectCreate, _: str = Depends(verify_token)):
    """Create a project. Chef-style template-first reliability:
    we ALWAYS seed from a real scaffold when we can infer one (from the
    explicit `template`/`scaffold_id`/`framework` hints OR from the
    initial `prompt` via inference_service), so the very first chat turn
    starts from working code instead of an empty skeleton — the largest
    single reliability lever for builder-pipeline success.
    """
    now = datetime.now(timezone.utc).isoformat()
    pid = str(uuid.uuid4())
    # Guard: when the FE omits `name` entirely, Pydantic doesn't run the
    # before-validator on the missing field (it just uses the default None).
    # Normalize here so scaffolds + responses never see None.
    safe_name = _coerce_name(body.name)
    files = None
    bootstrap_info: dict = {}
    kind = body.resolve_scaffold_kind()

    import time as _time
    t_bootstrap = _time.perf_counter()

    # 1) Prefer pre-baked snapshot (sub-ms warm load, ~5ms cold).
    if kind:
        try:
            from services.scaffold_snapshot_service import (
                snapshot_path, load_snapshot,
            )
            if snapshot_path(kind) is not None:
                files, snap_info = load_snapshot(kind, project_name=safe_name)
                bootstrap_info = {**snap_info, "kind": kind}
        except Exception as e:
            import logging
            logging.getLogger("nxt1.projects").warning(
                f"snapshot {kind!r} failed, falling back to live pack: {e}")
            files = None

    # 2) Fall back to the live pack (re-runs the python generator).
    if not files and kind:
        try:
            from services import scaffolds as scaffolds_pack
            files = scaffolds_pack.build_scaffold(kind, project_name=safe_name)
            bootstrap_info = {"kind": kind, "source": "live-pack",
                              "file_count": len(files)}
        except Exception as e:
            import logging
            logging.getLogger("nxt1.projects").warning(
                f"scaffold {kind!r} failed, falling back to default: {e}")
            files = None

    # 3) Final fallback: minimal hand-rolled skeleton.
    if not files:
        files = default_files()
        bootstrap_info = {"kind": None, "source": "default-skeleton",
                          "file_count": len(files)}

    bootstrap_info["t_to_first_file_ms"] = round(
        (_time.perf_counter() - t_bootstrap) * 1000, 3)
    import logging
    logging.getLogger("nxt1.projects").info(
        "project bootstrap: kind=%s source=%s files=%d t=%sms",
        bootstrap_info.get("kind"), bootstrap_info.get("source"),
        bootstrap_info.get("file_count"),
        bootstrap_info.get("t_to_first_file_ms"),
    )

    doc = {
        "id": pid,
        "name": safe_name,
        "description": body.description or "",
        "scaffold_kind": kind,                 # for telemetry / later context
        "bootstrap": bootstrap_info,           # source, file_count, t_ms
        "created_at": now,
        "updated_at": now,
        "deployed": False,
        "deploy_slug": None,
        "publish_on_save": False,
        "files": files,
        "messages": [],
        "versions": [],
        "deployments": [],
        "assets": [],
        "domains": [],
        "prompt": (body.prompt or "")[:8000],  # bug fix iter4 #5: persist
    }
    await db.projects.insert_one(doc)
    # bug fix iter4 #2: auto-start the durable workflow alongside project create
    # so the Build pipeline tab populates immediately instead of staying empty.
    if body.prompt:
        try:
            from services.workflow_service import start_workflow
            await start_workflow(pid, body.prompt, "admin", "internal")
        except Exception:
            pass  # best-effort — never break project creation on workflow issues
    return ProjectFull(
        id=pid, name=safe_name, description=body.description or "",
        created_at=now, updated_at=now, deployed=False, deploy_slug=None,
        files=[FileItem(**f) for f in files],
        prompt=doc["prompt"],
    )


@router.get("/projects/{project_id}", response_model=ProjectFull)
async def get_project(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectFull(
        id=doc["id"], name=doc["name"], description=doc.get("description", ""),
        created_at=doc["created_at"], updated_at=doc["updated_at"],
        deployed=doc.get("deployed", False), deploy_slug=doc.get("deploy_slug"),
        files=[FileItem(**f) for f in doc.get("files", [])],
        prompt=doc.get("prompt", ""),
    )


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, _: str = Depends(verify_token)):
    result = await db.projects.delete_one({"id": project_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True}


@router.get("/projects/{project_id}/state")
async def get_project_state(project_id: str, _: str = Depends(verify_token)):
    doc = await db.projects.find_one(
        {"id": project_id},
        {"_id": 0, "id": 1, "publish_on_save": 1, "deployed": 1, "deploy_slug": 1,
         "last_deployed_at": 1, "deployments": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    deps = doc.get("deployments") or []
    latest = deps[-1] if deps else None
    summary = None
    if latest:
        summary = {
            "id": latest.get("id"),
            "status": latest.get("status"),
            "provider": latest.get("provider"),
            "public_url": latest.get("public_url"),
            "started_at": latest.get("started_at"),
            "completed_at": latest.get("completed_at"),
        }
    return {
        "id": doc["id"],
        "publish_on_save": bool(doc.get("publish_on_save")),
        "deployed": bool(doc.get("deployed")),
        "deploy_slug": doc.get("deploy_slug"),
        "last_deployed_at": doc.get("last_deployed_at"),
        "latest_deployment": summary,
    }


@router.post("/projects/{project_id}/publish-on-save")
async def set_publish_on_save(project_id: str, body: PublishToggle,
                              _: str = Depends(verify_token)):
    res = await db.projects.update_one(
        {"id": project_id},
        {"$set": {"publish_on_save": body.publish_on_save,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True, "publish_on_save": body.publish_on_save}


@router.get("/projects/{project_id}/memory")
async def get_memory(project_id: str, _: str = Depends(verify_token)):
    from services.memory_service import build_index, quick_summary
    doc = await db.projects.find_one(
        {"id": project_id}, {"_id": 0, "files": 1, "memory": 1},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    cached = doc.get("memory") or {}
    files = doc.get("files", [])
    return {
        "summary": cached.get("summary") or quick_summary(files),
        "index": build_index(files),
        "updated_at": cached.get("updated_at"),
        "ai_summary_present": bool(cached.get("summary")),
    }
