"""Video Studio routes.

GET  /api/video/models             → list available Fal models + capabilities
POST /api/video/upload-reference   → upload a still (png/jpg/webp) for image-to-video
GET  /api/video/refs/{filename}    → serve reference image

POST /api/video/generate           → AI gen via Fal (model + mode + optional ref image)
POST /api/video/upload             → upload mp4/mov clip
GET  /api/video/clips              → list clips
GET  /api/video/clips/{filename}   → serve clip
DELETE /api/video/clips/{id}       → delete clip
GET  /api/video/jobs               → list video jobs

POST /api/video/timeline           → save timeline
GET  /api/video/timelines          → list
GET  /api/video/timeline/{id}      → load

POST /api/video/export             → server-side ffmpeg stitch → mp4
GET  /api/video/exports/{filename} → serve stitched mp4
GET  /api/video/exports            → list user's exports

POST /api/video/post-to-social     → drop into Social calendar as draft
"""
import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services import job_service
from services.video_studio_service import (
    CLIPS_DIR, EXPORTS_DIR, REF_IMG_DIR,
    MODEL_REGISTRY, list_models,
    run_video_job, save_uploaded_clip, save_reference_image,
    export_timeline,
)

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.video.routes")
router = APIRouter(prefix="/api/video", tags=["video"])


class GenerateBody(BaseModel):
    prompt: str = Field(..., min_length=2, max_length=2000)
    style: str = Field(default="realistic")     # realistic | animated | demo | moody | vlog
    duration_s: int = Field(default=5, ge=2, le=15)
    model: str = Field(default="cogvideox-5b")
    mode: str = Field(default="t2v")            # t2v | i2v
    reference_image_id: Optional[str] = None    # required when mode=i2v


class TimelineBody(BaseModel):
    name: str = Field(default="Untitled")
    tracks: list = Field(default_factory=list)
    aspect: str = Field(default="16:9")
    duration_s: float = Field(default=10.0)


class ExportBody(BaseModel):
    clip_ids: list[str]
    name: str = "export"


class PostToSocialBody(BaseModel):
    clip_id: str
    caption: Optional[str] = ""
    platforms: list[str] = Field(default_factory=lambda: ["instagram"])
    scheduled_at: Optional[str] = None


@router.get("/health")
async def health(_user: str = Depends(verify_token)):
    return {
        "fal_configured": bool(os.environ.get("FAL_API_KEY")),
        "ffmpeg_available": bool(os.popen("which ffmpeg").read().strip()),
        "ok": True,
    }


@router.get("/models")
async def get_models(_user: str = Depends(verify_token)):
    return {"items": list_models()}


# ─────────────────────────────────────────────────── reference images
@router.post("/upload-reference")
async def upload_reference(
    file: UploadFile = File(...),
    user_id: str = Depends(verify_token),
):
    if not file.filename:
        raise HTTPException(400, "No file")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Max 10MB")
    try:
        doc = await save_reference_image(user_id, content, file.filename)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await db.video_references.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/refs/{filename}")
async def get_ref(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Bad filename")
    p = REF_IMG_DIR / filename
    if not p.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(str(p))


# ─────────────────────────────────────────────────── generate
@router.post("/generate")
async def generate(body: GenerateBody, user_id: str = Depends(verify_token)):
    if not os.environ.get("FAL_API_KEY"):
        raise HTTPException(400, "FAL_API_KEY is not configured. Add it via Settings → Integrations.")
    if body.model not in MODEL_REGISTRY:
        raise HTTPException(400, f"Unknown model. Available: {list(MODEL_REGISTRY)}")
    meta = MODEL_REGISTRY[body.model]
    if not meta.get(body.mode):
        raise HTTPException(400, f"Model '{body.model}' does not support '{body.mode}'.")

    ref_path = None
    if body.mode == "i2v":
        if not body.reference_image_id:
            raise HTTPException(400, "Image-to-video requires reference_image_id.")
        ref = await db.video_references.find_one(
            {"user_id": user_id, "id": body.reference_image_id}, {"_id": 0}
        )
        if not ref:
            raise HTTPException(404, "Reference image not found.")
        ref_path = ref["file_path"]

    job = await job_service.start(
        db,
        kind="video-generate",
        project_id=None,
        actor=user_id,
        initial_logs=[{
            "ts": job_service._now(),
            "level": "info",
            "msg": f"AI video queued: model={body.model} mode={body.mode} prompt={body.prompt[:60]}",
        }],
    )
    asyncio.create_task(run_video_job(
        db, job["id"],
        user_id=user_id,
        prompt=body.prompt,
        style=body.style,
        duration_s=body.duration_s,
        model=body.model,
        mode=body.mode,
        reference_image_path=ref_path,
    ))
    return {"job_id": job["id"], "status": "running"}


# ─────────────────────────────────────────────────── upload + clips
@router.post("/upload")
async def upload_clip(file: UploadFile = File(...), user_id: str = Depends(verify_token)):
    if not file.filename:
        raise HTTPException(400, "No file")
    content = await file.read()
    if len(content) > 200 * 1024 * 1024:
        raise HTTPException(400, "Max 200MB")
    try:
        clip = await save_uploaded_clip(user_id, content, file.filename)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await db.video_clips.insert_one(dict(clip))
    clip.pop("_id", None)
    return clip


@router.get("/clips")
async def list_clips(limit: int = 100, user_id: str = Depends(verify_token)):
    cur = db.video_clips.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(
        max(1, min(int(limit or 100), 500))
    )
    return {"items": [d async for d in cur]}


@router.get("/clips/{filename}")
async def get_clip_file(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Bad filename")
    p = CLIPS_DIR / filename
    if not p.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(str(p), media_type="video/mp4")


@router.delete("/clips/{clip_id}")
async def delete_clip(clip_id: str, user_id: str = Depends(verify_token)):
    doc = await db.video_clips.find_one({"id": clip_id, "user_id": user_id})
    if not doc:
        raise HTTPException(404, "Not found")
    try:
        Path(doc.get("file_path", "")).unlink(missing_ok=True)
    except Exception:
        pass
    await db.video_clips.delete_one({"id": clip_id})
    return {"ok": True}


# ─────────────────────────────────────────────────── jobs
@router.get("/jobs")
async def list_jobs(limit: int = 20, user_id: str = Depends(verify_token)):
    cur = db.jobs.find(
        {"kind": "video-generate", "actor": user_id},
        {"_id": 0},
    ).sort("created_at", -1).limit(max(1, min(int(limit or 20), 50)))
    return {"items": [d async for d in cur]}


# ─────────────────────────────────────────────────── timeline
@router.post("/timeline")
async def save_timeline(body: TimelineBody, user_id: str = Depends(verify_token)):
    tid = str(uuid.uuid4())
    doc = {
        "id": tid, "user_id": user_id, "name": body.name, "tracks": body.tracks,
        "aspect": body.aspect, "duration_s": body.duration_s,
        "created_at": job_service._now(), "updated_at": job_service._now(),
    }
    await db.video_timelines.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/timelines")
async def list_timelines(user_id: str = Depends(verify_token)):
    cur = db.video_timelines.find({"user_id": user_id}, {"_id": 0}).sort("updated_at", -1).limit(100)
    return {"items": [d async for d in cur]}


@router.get("/timeline/{tid}")
async def get_timeline(tid: str, user_id: str = Depends(verify_token)):
    doc = await db.video_timelines.find_one({"id": tid, "user_id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Not found")
    return doc


# ─────────────────────────────────────────────────── server-side export
@router.post("/export")
async def export(body: ExportBody, user_id: str = Depends(verify_token)):
    try:
        doc = await export_timeline(db, user_id, body.clip_ids, name=body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("export failed")
        raise HTTPException(500, f"Export failed: {e}")
    return doc


@router.get("/exports")
async def list_exports(user_id: str = Depends(verify_token)):
    cur = db.video_exports.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(50)
    return {"items": [d async for d in cur]}


@router.get("/exports/{filename}")
async def get_export(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Bad filename")
    p = EXPORTS_DIR / filename
    if not p.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(str(p), media_type="video/mp4",
                        filename=f"nxt1-studio-{filename}")


# ─────────────────────────────────────────────────── post to social
@router.post("/post-to-social")
async def post_to_social(body: PostToSocialBody, user_id: str = Depends(verify_token)):
    clip = await db.video_clips.find_one({"id": body.clip_id, "user_id": user_id}, {"_id": 0})
    if not clip:
        raise HTTPException(404, "Clip not found")

    drafts = []
    for plat in body.platforms:
        post = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "platform": plat,
            "caption": body.caption or "",
            "hashtags": [],
            "video_url": clip.get("url"),
            "image_url": None,
            "kind": "video",
            "status": "draft",
            "scheduled_at": body.scheduled_at or job_service._now(),
            "created_at": job_service._now(),
            "updated_at": job_service._now(),
        }
        await db.social_posts.insert_one(dict(post))
        post.pop("_id", None)
        drafts.append(post)
    return {"items": drafts, "count": len(drafts)}
