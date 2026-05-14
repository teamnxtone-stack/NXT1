"""Job control routes: list active, get details, cancel.

Until this phase, jobs only ended via natural completion or generation error.
With the new background-task build flow (Phase 9 Fix #4), users may want to
proactively stop a build (e.g. they realize the prompt was wrong, the build is
far too large, or the AI is going in a bad direction).

This route surfaces:
  GET   /api/projects/{pid}/jobs/active    — list jobs still in flight
  GET   /api/jobs/{job_id}                 — single job detail (logs included)
  POST  /api/projects/{pid}/jobs/{job_id}/cancel — mark job cancelled

The cancel marker is read by the background task on its next iteration to bail
early. State that's already been written stays put (consistent with how the
rest of the platform handles interrupts).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from services import job_service

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.jobs")

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/projects/{project_id}/jobs/active")
async def list_active_jobs(project_id: str, _: str = Depends(verify_token)):
    """All jobs for this project that are still running."""
    items = await db.jobs.find(
        {
            "project_id": project_id,
            "status": {"$in": ["queued", "running"]},
        },
        {"_id": 0},
    ).sort("started_at", -1).to_list(length=20)
    return {"items": items, "count": len(items)}


@router.get("/projects/{project_id}/jobs")
async def list_recent_jobs(
    project_id: str,
    limit: int = 20,
    _: str = Depends(verify_token),
):
    """Recent jobs (active + completed + failed). Used to show task history."""
    items = await db.jobs.find(
        {"project_id": project_id},
        {"_id": 0},
    ).sort("started_at", -1).to_list(length=max(1, min(100, int(limit or 20))))
    return {"items": items, "count": len(items)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, _: str = Depends(verify_token)):
    """Full job detail including phase log / progress / result."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/projects/{project_id}/jobs/{job_id}/cancel")
async def cancel_job(project_id: str, job_id: str,
                     _: str = Depends(verify_token)):
    """Mark a running job as cancelled.

    The background task watches for `status=cancelled` between iterations and
    bails early on the next event. Already-persisted partial state survives.
    """
    job = await db.jobs.find_one({"id": job_id, "project_id": project_id},
                                 {"_id": 0})
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") not in ("queued", "running"):
        return {"id": job_id, "status": job.get("status"), "already_done": True}
    now = datetime.now(timezone.utc).isoformat()
    await db.jobs.update_one(
        {"id": job_id},
        {
            "$set": {
                "status": "cancelled",
                "finished_at": now,
                "cancel_requested_at": now,
                "updated_at": now,
            },
            "$push": {
                "logs": {
                    "ts": now,
                    "level": "warn",
                    "msg": "Job cancelled by user",
                },
            },
        },
    )
    return {"id": job_id, "status": "cancelled"}
