"""3rd-party integrations routes: GitHub Save, Supabase/Neon DB provisioning.

Backed by services/github_service.py (and future supabase_service / neon_service).
Endpoints intentionally never echo the API tokens back to the client.

Reliability improvements:
- Maps github_service.GitHubError.kind → semantic HTTP status (401 auth,
  403 permission, 429 rate-limit, 5xx server, etc.) so the client UI can
  render an actionable message.
- Branch-aware push (default-branch protected, support deploy/preview branches).
- list/create branch endpoints for the branch-based workflow.
"""
import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from services import github_service

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.integrations")

router = APIRouter(prefix="/api", tags=["integrations"])


class GithubSaveIn(BaseModel):
    repo_name: Optional[str] = None
    private: Optional[bool] = True
    branch: Optional[str] = None             # target branch (None → repo default)
    commit_message: Optional[str] = None
    include_deploy_workflow: Optional[bool] = True  # auto-inject .github/workflows/deploy.yml


class GithubBranchIn(BaseModel):
    branch: str
    from_branch: Optional[str] = None  # source (None → default)


def _http_status_for_error(err: github_service.GitHubError) -> int:
    """Map our categorized GitHubError into a meaningful HTTP status."""
    kind = getattr(err, "kind", "unknown")
    if kind == "auth":
        return 401
    if kind == "permission":
        return 403
    if kind == "rate_limit":
        return 429
    if kind == "not_found":
        return 404
    if kind == "validation":
        return 400
    if kind == "network":
        return 503
    if kind == "server":
        return 502
    return 502


@router.post("/projects/{project_id}/github/save")
async def github_save(project_id: str, body: Optional[GithubSaveIn] = Body(None),
                      _: str = Depends(verify_token)):
    """Push the current project's files to a GitHub repo as a single commit.
    Auto-creates the repo on first call. Subsequent calls force-update HEAD
    on the target branch (default: repo's default branch).
    """
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    body = body or GithubSaveIn()
    # Auto-inject GitHub Actions deploy workflow (B.4.5) so a fresh export
    # ships with CI/CD wired up out of the box. We only inject if the
    # project doesn't already carry its own workflow — never overwrite.
    if body.include_deploy_workflow is not False:
        try:
            from services import github_actions_service as ghact
            existing_files = doc.get("files") or []
            wf_path = ".github/workflows/deploy.yml"
            already_has = any((f.get("path") or "").lstrip("/") == wf_path
                              for f in existing_files)
            if not already_has:
                plan = ghact.generate_for_project(existing_files)
                injected = list(existing_files) + [{"path": wf_path, "yaml": plan["yaml"]}]
                # We push as `content` (string) so use that key. Some scaffolds
                # store yaml in `yaml` — normalise:
                injected[-1] = {"path": wf_path, "content": plan["yaml"]}
                doc = dict(doc)
                doc["files"] = injected
                logger.info(
                    f"github_save: injected deploy.yml for project {project_id} "
                    f"target={plan['target']}"
                )
        except Exception as e:
            logger.warning(f"deploy workflow injection skipped: {e}")
    # If the project was imported from GitHub, default to pushing back to the
    # same repo so the loop closes (NXT1 → GitHub → Vercel/CF auto-deploy).
    repo_name = body.repo_name
    if not repo_name:
        gh_meta = (doc.get("github") or {})
        if gh_meta.get("source_name"):
            repo_name = gh_meta["source_name"]
    try:
        result = github_service.save_project_to_github(
            doc,
            repo_name=repo_name,
            private=bool(body.private if body.private is not None else True),
            branch=body.branch,
            commit_message=body.commit_message,
        )
    except github_service.GitHubError as e:
        logger.warning(f"github save failed [{e.kind}]: {e}")
        raise HTTPException(status_code=_http_status_for_error(e), detail=str(e))
    except Exception as e:
        logger.exception("github save unexpected failure")
        raise HTTPException(status_code=500, detail=f"GitHub save failed: {e}")

    # Persist a small marker on the project so we can show "Synced to GitHub" later.
    # Preserve any `source_*` fields so the import-loop pointer survives later saves.
    existing_gh = doc.get("github") or {}
    new_gh = {
        **{k: v for k, v in existing_gh.items() if k.startswith("source_") or k == "imported_at"},
        "repo_url": result["repo_url"],
        "owner": result["owner"],
        "name": result["name"],
        "branch": result.get("branch") or result["default_branch"],
        "default_branch": result["default_branch"],
        "last_commit_sha": result["commit_sha"],
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
        "file_count": result["file_count"],
        "private": result["private"],
    }
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {
            "github": new_gh,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return result


@router.get("/projects/{project_id}/github")
async def github_status(project_id: str, _: str = Depends(verify_token)):
    # Use _id projection alone so we always get a non-empty truthy dict back
    # when the project exists (empty `github` field would otherwise return
    # `{}` which is falsy → false 404).
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "github": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return doc.get("github") or {}


@router.get("/projects/{project_id}/github/branches")
async def github_branches(project_id: str, _: str = Depends(verify_token)):
    """List branches on the project's connected GitHub repo (or imported source)."""
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "github": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not (doc.get("github") or {}).get("owner"):
        raise HTTPException(status_code=404, detail="No GitHub repo connected. Save to GitHub first.")
    gh = doc["github"]
    try:
        branches = github_service.list_branches(gh["owner"], gh["name"])
    except github_service.GitHubError as e:
        raise HTTPException(status_code=_http_status_for_error(e), detail=str(e))
    return {
        "owner": gh["owner"],
        "name": gh["name"],
        "default_branch": gh.get("default_branch") or "main",
        "branches": branches,
    }


@router.post("/projects/{project_id}/github/branch")
async def github_create_branch(project_id: str, body: GithubBranchIn,
                                _: str = Depends(verify_token)):
    """Create a new branch on the connected GitHub repo (off default by default).
    Useful for deploy-preview / branch-preview workflows."""
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "github": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not (doc.get("github") or {}).get("owner"):
        raise HTTPException(status_code=404, detail="No GitHub repo connected. Save to GitHub first.")
    gh = doc["github"]
    branch = (body.branch or "").strip()
    if not branch or "/" in branch or " " in branch:
        raise HTTPException(status_code=400, detail="Invalid branch name (no spaces or slashes).")
    try:
        rec = github_service.create_branch(gh["owner"], gh["name"], branch,
                                           from_branch=body.from_branch)
    except github_service.GitHubError as e:
        raise HTTPException(status_code=_http_status_for_error(e), detail=str(e))
    return rec


@router.get("/projects/{project_id}/github/deploy-workflow")
async def github_preview_deploy_workflow(project_id: str,
                                          _: str = Depends(verify_token)):
    """Preview the `.github/workflows/deploy.yml` that NXT1 will inject on
    the next github/save. Returns target detection, the YAML, and the list
    of secrets the workflow needs in GitHub repo settings.
    """
    doc = await db.projects.find_one({"id": project_id}, {"_id": 0, "files": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Project not found")
    from services import github_actions_service as ghact
    return ghact.generate_for_project(doc.get("files") or [])
