"""Social Media Content Agent routes.

POST   /api/social/generate          → kick off a content-calendar job (returns job_id)
GET    /api/social/posts             → list user's posts (with filters)
GET    /api/social/posts/{id}        → single post detail
PATCH  /api/social/posts/{id}        → update caption/hashtags/status/scheduled_at
DELETE /api/social/posts/{id}        → delete
POST   /api/social/posts/{id}/regenerate → regenerate caption+image
POST   /api/social/profile           → save user's social profile (tone, niche, logo)
GET    /api/social/profile           → get profile
POST   /api/social/profile/logo      → upload logo PNG (multipart)
GET    /api/social/jobs              → user's active+recent social jobs
GET    /api/social/assets/{filename} → static image
"""
import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services import job_service, asset_storage
from services.social_content_service import (
    ASSETS_DIR,
    REF_IMG_DIR,
    run_social_job,
    regenerate_post as _regenerate_post,
)

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.social.routes")

router = APIRouter(prefix="/api/social", tags=["social"])

LOGOS_DIR = Path(__file__).resolve().parent.parent / "static" / "social" / "logos"
LOGOS_DIR.mkdir(parents=True, exist_ok=True)


class GenerateBody(BaseModel):
    brief: str = Field(..., min_length=2, max_length=4000)
    tone: str = Field(default="professional")
    platform: str = Field(default="all")
    platforms: Optional[list[str]] = None
    duration: str = Field(default="this week")
    about: str = Field(default="")
    niche: str = Field(default="")
    reference_image_ids: Optional[list[str]] = None  # IDs from /upload-reference


class ProfileBody(BaseModel):
    tone: str = "professional"
    platforms: list[str] = Field(default_factory=lambda: ["instagram", "linkedin", "twitter"])
    niche: str = ""
    about: str = ""
    logo_path: Optional[str] = None
    connected_accounts: dict = Field(default_factory=dict)


class PostUpdate(BaseModel):
    caption: Optional[str] = None
    hashtags: Optional[list[str]] = None
    status: Optional[str] = None  # draft | approved | scheduled | posted
    scheduled_at: Optional[str] = None


# ------------------------------------------------------------------ profile
@router.get("/profile")
async def get_profile(user_id: str = Depends(verify_token)):
    doc = await db.social_profiles.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        doc = {
            "user_id": user_id,
            "tone": "professional",
            "platforms": ["instagram", "linkedin", "twitter"],
            "niche": "",
            "about": "",
            "logo_path": None,
            "connected_accounts": {},
        }
    return doc


@router.post("/profile")
async def save_profile(body: ProfileBody, user_id: str = Depends(verify_token)):
    payload = body.model_dump()
    payload["user_id"] = user_id
    await db.social_profiles.update_one(
        {"user_id": user_id},
        {"$set": payload},
        upsert=True,
    )
    return {"ok": True, "profile": payload}


@router.post("/profile/logo")
async def upload_logo(
    file: UploadFile = File(...),
    user_id: str = Depends(verify_token),
):
    if not file.filename:
        raise HTTPException(400, "No file")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "Use PNG/JPG/WEBP")
    fn = f"{user_id}-{uuid.uuid4().hex}{suffix}"
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Logo must be <5MB")
    res = asset_storage.put_bytes(folder="social/logos", filename=fn, data=content)
    logo_url = res["url"]
    logo_path_for_overlay = res.get("file_path")  # only present on local backend
    await db.social_profiles.update_one(
        {"user_id": user_id},
        {"$set": {"logo_path": logo_path_for_overlay, "logo_url": logo_url,
                  "logo_storage": res["backend"], "logo_key": res.get("key")}},
        upsert=True,
    )
    return {"logo_path": logo_path_for_overlay, "logo_url": logo_url}


@router.get("/logo/{filename}")
async def get_logo(filename: str):
    p = LOGOS_DIR / filename
    if not p.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(str(p))


# ------------------------------------------------------------------ generation
@router.post("/upload-reference")
async def upload_reference(
    file: UploadFile = File(...),
    user_id: str = Depends(verify_token),
):
    """Attach a reference image to the next /generate request.

    Returns {id, url}. Pass the id back via GenerateBody.reference_image_ids.
    """
    if not file.filename:
        raise HTTPException(400, "No file")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "Use PNG/JPG/WEBP")
    content = await file.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(400, "Max 8MB per reference image")
    rid = uuid.uuid4().hex
    fn = f"{user_id}-{rid}{suffix}"
    res = asset_storage.put_bytes(folder="social/refs", filename=fn, data=content)
    doc = {
        "id": rid,
        "user_id": user_id,
        "filename": fn,
        "file_path": res.get("file_path"),
        "storage_backend": res["backend"],
        "storage_key": res.get("key"),
        "url": res["url"],
        "size_bytes": len(content),
        "created_at": job_service._now(),
    }
    await db.social_references.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/reference/{filename}")
async def get_reference(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Bad filename")
    p = REF_IMG_DIR / filename
    if not p.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(str(p))


@router.post("/generate")
async def generate(body: GenerateBody, user_id: str = Depends(verify_token)):
    """Kick off a background job. Returns job_id immediately.

    The job runs as a detached asyncio.Task — survives request, browser close,
    client disconnect. Progress in `jobs` collection.
    """
    profile = await db.social_profiles.find_one({"user_id": user_id}, {"_id": 0}) or {}
    logo_path = profile.get("logo_path")

    # Resolve reference image IDs → file paths
    ref_paths: list[str] = []
    if body.reference_image_ids:
        cur = db.social_references.find(
            {"user_id": user_id, "id": {"$in": body.reference_image_ids}},
            {"_id": 0, "file_path": 1},
        )
        async for d in cur:
            if d.get("file_path"):
                ref_paths.append(d["file_path"])

    job = await job_service.start(
        db,
        kind="social-content",
        project_id=None,
        actor=user_id,
        initial_logs=[{
            "ts": job_service._now(),
            "level": "info",
            "msg": f"Social content generation started — brief='{body.brief[:80]}'" +
                   (f" + {len(ref_paths)} reference image(s)" if ref_paths else ""),
        }],
    )

    asyncio.create_task(run_social_job(
        db, job["id"],
        user_id=user_id,
        brief=body.brief,
        tone=body.tone,
        platform=body.platform,
        platforms=body.platforms,
        duration=body.duration,
        about=body.about or profile.get("about", ""),
        niche=body.niche or profile.get("niche", ""),
        logo_path=logo_path,
        reference_image_paths=ref_paths or None,
    ))

    return {"job_id": job["id"], "status": "running"}


# ------------------------------------------------------------------ jobs
@router.get("/jobs")
async def list_jobs(limit: int = 20, user_id: str = Depends(verify_token)):
    cur = db.jobs.find(
        {"kind": "social-content", "actor": user_id},
        {"_id": 0},
    ).sort("created_at", -1).limit(max(1, min(int(limit or 20), 50)))
    return {"items": [d async for d in cur]}


# ------------------------------------------------------------------ posts
@router.get("/posts")
async def list_posts(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    job_id: Optional[str] = None,
    limit: int = 100,
    user_id: str = Depends(verify_token),
):
    q: dict = {"user_id": user_id}
    if platform and platform != "all":
        q["platform"] = platform
    if status:
        q["status"] = status
    if job_id:
        q["job_id"] = job_id
    cur = db.social_posts.find(q, {"_id": 0}).sort("scheduled_at", 1).limit(max(1, min(int(limit or 100), 500)))
    return {"items": [d async for d in cur]}


@router.get("/posts/{post_id}")
async def get_post(post_id: str, user_id: str = Depends(verify_token)):
    p = await db.social_posts.find_one({"id": post_id, "user_id": user_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Not found")
    return p


@router.patch("/posts/{post_id}")
async def update_post(
    post_id: str,
    body: PostUpdate,
    user_id: str = Depends(verify_token),
):
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    updates["updated_at"] = job_service._now()
    res = await db.social_posts.update_one({"id": post_id, "user_id": user_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    p = await db.social_posts.find_one({"id": post_id}, {"_id": 0})
    return p


@router.delete("/posts/{post_id}")
async def delete_post(post_id: str, user_id: str = Depends(verify_token)):
    res = await db.social_posts.delete_one({"id": post_id, "user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.post("/posts/{post_id}/regenerate")
async def regenerate_post(post_id: str, user_id: str = Depends(verify_token)):
    try:
        return await _regenerate_post(db, post_id, user_id)
    except ValueError:
        raise HTTPException(404, "Not found")
    except Exception as e:
        logger.exception("regenerate failed")
        raise HTTPException(500, f"Regenerate failed: {e}")


# ------------------------------------------------------------------ static
@router.get("/assets/{filename}")
async def get_asset(filename: str):
    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Bad filename")
    p = ASSETS_DIR / filename
    if not p.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(str(p))
