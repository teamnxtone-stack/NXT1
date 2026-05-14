"""Video Studio service — text-to-video via Fal.ai + uploaded clip management.

Persistent: kicks off as detached asyncio task using job_service.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from services import job_service

logger = logging.getLogger("nxt1.video")

CLIPS_DIR = Path(__file__).resolve().parent.parent / "static" / "video" / "clips"
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

EXPORTS_DIR = Path(__file__).resolve().parent.parent / "static" / "video" / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fal_key() -> str:
    key = os.environ.get("FAL_API_KEY") or os.environ.get("FAL_KEY")
    if not key:
        raise RuntimeError("FAL_API_KEY not configured. Add it to /app/backend/.env")
    return key


STYLE_SUFFIX = {
    "realistic": "photorealistic, cinematic lighting, 4k, highly detailed",
    "animated": "stylized animation, vibrant colors, smooth motion",
    "demo": "clean modern product demo, soft studio lighting, minimal background",
}


def _build_prompt(prompt: str, style: str) -> str:
    suffix = STYLE_SUFFIX.get((style or "realistic").lower(), STYLE_SUFFIX["realistic"])
    return f"{prompt.strip()}. Style: {suffix}."


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


async def run_video_job(
    db,
    job_id: str,
    *,
    user_id: str,
    prompt: str,
    style: str = "realistic",
    duration_s: int = 5,
):
    """Detached background task: generate a clip via Fal.ai CogVideoX."""
    try:
        os.environ["FAL_KEY"] = _fal_key()
        import fal_client

        await job_service.append_log(
            db, job_id, "info",
            f"Submitting prompt to Fal.ai (cogvideox-5b): {prompt[:80]}",
            phase="submitting", progress=0.10,
        )

        full_prompt = _build_prompt(prompt, style)

        loop = asyncio.get_event_loop()

        def _sync_submit():
            return fal_client.subscribe(
                "fal-ai/cogvideox-5b",
                arguments={"prompt": full_prompt},
                with_logs=False,
            )

        await job_service.append_log(db, job_id, "info",
                                     "Generating video (30-90s)…",
                                     phase="generating", progress=0.35)
        result = await loop.run_in_executor(None, _sync_submit)

        video_url = None
        if isinstance(result, dict):
            video_url = (result.get("video") or {}).get("url") if isinstance(result.get("video"), dict) else None
            if not video_url and isinstance(result.get("video"), str):
                video_url = result["video"]
        if not video_url:
            raise RuntimeError(f"Fal.ai returned no video URL. raw={str(result)[:200]}")

        await job_service.append_log(db, job_id, "info", "Downloading video…",
                                     phase="downloading", progress=0.85)
        data = await _download(video_url)

        fn = f"{uuid.uuid4().hex}.mp4"
        out = CLIPS_DIR / fn
        out.write_bytes(data)
        local_url = f"/api/video/clips/{fn}"

        clip = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "job_id": job_id,
            "kind": "ai",
            "prompt": prompt,
            "style": style,
            "duration_s": duration_s,
            "file_path": str(out),
            "url": local_url,
            "remote_url": video_url,
            "size_bytes": len(data),
            "created_at": _now(),
        }
        await db.video_clips.insert_one(dict(clip))
        clip.pop("_id", None)

        await job_service.complete(db, job_id, status="completed",
                                   result={"clip_id": clip["id"], "url": local_url})
        await job_service.append_log(db, job_id, "info",
                                     "✓ Done — clip added.",
                                     phase="completed", progress=1.0)
    except Exception as e:
        logger.exception("video job failed")
        await job_service.fail(db, job_id, f"{type(e).__name__}: {e}")


async def save_uploaded_clip(user_id: str, file_bytes: bytes, filename: str) -> dict:
    suffix = Path(filename).suffix.lower() or ".mp4"
    if suffix not in (".mp4", ".mov", ".webm"):
        raise ValueError("Use mp4 / mov / webm")
    fn = f"{uuid.uuid4().hex}{suffix}"
    out = CLIPS_DIR / fn
    out.write_bytes(file_bytes)
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "kind": "upload",
        "filename": filename,
        "file_path": str(out),
        "url": f"/api/video/clips/{fn}",
        "size_bytes": len(file_bytes),
        "created_at": _now(),
    }
