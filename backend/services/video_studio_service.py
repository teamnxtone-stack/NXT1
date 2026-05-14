"""Video Studio service — Fal.ai multi-model + multi-mode + native ffmpeg export.

Modes:
  • text-to-video  — prompt only
  • image-to-video — prompt + reference image (animate)

Models (selectable from the UI):
  • veo3                  — Google Veo 3.1, premium, t2v / i2v
  • kling-2.5-turbo-pro   — Kling 2.5 Turbo Pro, fast cinematic t2v
  • kling-2.1-master-i2v  — Kling 2.1 Master, premium image-to-video
  • ltx-video             — LTX 2, fast t2v / i2v
  • cogvideox-5b          — Default fast t2v

Persistent: kicks off as detached asyncio task using job_service.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
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
REF_IMG_DIR = Path(__file__).resolve().parent.parent / "static" / "video" / "refs"
REF_IMG_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fal_key() -> str:
    key = os.environ.get("FAL_API_KEY") or os.environ.get("FAL_KEY")
    if not key:
        raise RuntimeError("FAL_API_KEY not configured. Add it to /app/backend/.env")
    return key


# ─────────────────────────────────────────────────────────── model registry
MODEL_REGISTRY: dict[str, dict] = {
    "veo3": {
        "label": "Google Veo 3.1",
        "tier": "premium",
        "t2v": "fal-ai/veo3",
        "i2v": "fal-ai/veo3/image-to-video",
        "duration_choices": [4, 6, 8],
        "notes": "Premium, native audio, multi-shot. ~60-120s.",
    },
    "kling-2.5-turbo-pro": {
        "label": "Kling 2.5 Turbo Pro",
        "tier": "fast-pro",
        "t2v": "fal-ai/kling-video/v2.5-turbo/pro/text-to-video",
        "i2v": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
        "duration_choices": [5, 10],
        "notes": "Cinematic + fast. Director-level camera.",
    },
    "kling-2.1-master": {
        "label": "Kling 2.1 Master",
        "tier": "premium",
        "t2v": "fal-ai/kling-video/v2.1/master/text-to-video",
        "i2v": "fal-ai/kling-video/v2.1/master/image-to-video",
        "duration_choices": [5, 10],
        "notes": "Premium image-to-video. Best motion fluidity.",
    },
    "ltx-video": {
        "label": "LTX Video (fast)",
        "tier": "fast",
        "t2v": "fal-ai/ltx-video",
        "i2v": "fal-ai/ltx-video-13b-distilled/image-to-video",
        "duration_choices": [4, 5],
        "notes": "Very fast, good for iterating.",
    },
    "cogvideox-5b": {
        "label": "CogVideoX 5B",
        "tier": "default",
        "t2v": "fal-ai/cogvideox-5b",
        "i2v": None,
        "duration_choices": [5],
        "notes": "Default fast text-to-video.",
    },
}


def list_models() -> list[dict]:
    return [
        {
            "id": mid,
            "label": m["label"],
            "tier": m["tier"],
            "supports": [k for k in ("t2v", "i2v") if m.get(k)],
            "duration_choices": m["duration_choices"],
            "notes": m["notes"],
        }
        for mid, m in MODEL_REGISTRY.items()
    ]


STYLE_SUFFIX = {
    "realistic": "photorealistic, cinematic lighting, 4k, highly detailed",
    "animated":  "stylized animation, vibrant colors, smooth motion",
    "demo":      "clean modern product demo, soft studio lighting, minimal background",
    "moody":     "moody cinematic, dramatic shadow, film grain, anamorphic",
    "vlog":      "natural daylight, handheld feel, vlog aesthetic, candid",
}


def _build_prompt(prompt: str, style: str) -> str:
    suffix = STYLE_SUFFIX.get((style or "realistic").lower(), STYLE_SUFFIX["realistic"])
    return f"{prompt.strip()}. Style: {suffix}."


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


def _extract_video_url(result: dict) -> Optional[str]:
    """Each fal model returns a slightly different shape. Cover the common ones."""
    if not isinstance(result, dict):
        return None
    # Most: { video: { url } } or { video_url } or { videos: [{ url }] } or { url }
    v = result.get("video")
    if isinstance(v, dict) and v.get("url"):
        return v["url"]
    if isinstance(v, str):
        return v
    if result.get("video_url"):
        return result["video_url"]
    vids = result.get("videos")
    if isinstance(vids, list) and vids:
        first = vids[0]
        if isinstance(first, dict) and first.get("url"):
            return first["url"]
        if isinstance(first, str):
            return first
    if result.get("url"):
        return result["url"]
    return None


async def _fal_upload_image(image_path: str) -> Optional[str]:
    """Upload a local image to fal storage (returns public URL)."""
    try:
        import fal_client
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fal_client.upload_file, image_path)
    except Exception as e:
        logger.error(f"fal upload_file failed: {e}")
        return None


async def run_video_job(
    db,
    job_id: str,
    *,
    user_id: str,
    prompt: str,
    style: str = "realistic",
    duration_s: int = 5,
    model: str = "cogvideox-5b",
    mode: str = "t2v",
    reference_image_path: Optional[str] = None,
):
    """Detached background task. Generates a clip via the selected Fal model."""
    try:
        os.environ["FAL_KEY"] = _fal_key()
        import fal_client

        if model not in MODEL_REGISTRY:
            raise RuntimeError(f"Unknown model '{model}'. Available: {list(MODEL_REGISTRY)}")
        meta = MODEL_REGISTRY[model]
        endpoint = meta.get(mode)
        if not endpoint:
            raise RuntimeError(f"Model '{model}' does not support '{mode}'.")

        full_prompt = _build_prompt(prompt, style)
        await job_service.append_log(
            db, job_id, "info",
            f"Submitting to Fal ({meta['label']} / {mode}): {prompt[:80]}",
            phase="submitting", progress=0.10,
        )

        arguments: dict = {"prompt": full_prompt}
        # Some models accept duration / aspect — pass when sensible
        if duration_s and duration_s in meta["duration_choices"]:
            arguments["duration"] = duration_s

        if mode == "i2v":
            if not reference_image_path:
                raise RuntimeError("Image-to-video requires a reference image.")
            url = await _fal_upload_image(reference_image_path)
            if not url:
                raise RuntimeError("Failed to upload reference image to Fal storage.")
            arguments["image_url"] = url

        await job_service.append_log(db, job_id, "info",
                                     f"Generating with {meta['label']} (this may take 30-180s)…",
                                     phase="generating", progress=0.35)

        loop = asyncio.get_event_loop()

        def _sync_submit():
            return fal_client.subscribe(endpoint, arguments=arguments, with_logs=False)

        result = await loop.run_in_executor(None, _sync_submit)
        video_url = _extract_video_url(result)
        if not video_url:
            raise RuntimeError(f"Fal returned no video URL. raw={str(result)[:300]}")

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
            "model": model,
            "mode": mode,
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
        await job_service.append_log(db, job_id, "info", "✓ Done — clip added.",
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
        "model": None,
        "mode": None,
        "filename": filename,
        "file_path": str(out),
        "url": f"/api/video/clips/{fn}",
        "size_bytes": len(file_bytes),
        "created_at": _now(),
    }


async def save_reference_image(user_id: str, file_bytes: bytes, filename: str) -> dict:
    suffix = Path(filename).suffix.lower() or ".png"
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError("Use png/jpg/webp")
    fn = f"{user_id}-{uuid.uuid4().hex}{suffix}"
    out = REF_IMG_DIR / fn
    out.write_bytes(file_bytes)
    return {
        "id": uuid.uuid4().hex,
        "user_id": user_id,
        "filename": fn,
        "file_path": str(out),
        "url": f"/api/video/refs/{fn}",
        "size_bytes": len(file_bytes),
        "created_at": _now(),
    }


# ─────────────────────────────────────────────────── ffmpeg-based multi-clip export
def _ffmpeg_concat(input_paths: list[str], output_path: str) -> None:
    """Concatenate multiple mp4 clips into one via ffmpeg concat filter.

    Uses the filter_complex re-encode path (safe for differing codecs/resolutions).
    """
    if not input_paths:
        raise RuntimeError("No inputs to concat")
    # Build command: -i in1 -i in2 ... -filter_complex "[0:v:0][0:a:0?][1:v:0][1:a:0?]concat=n=2:v=1:a=1[v][a]" -map "[v]" -map "[a]?" out
    cmd: list[str] = ["ffmpeg", "-y"]
    for p in input_paths:
        cmd += ["-i", p]
    parts = []
    for i in range(len(input_paths)):
        parts.append(f"[{i}:v:0]")
    filter_str = "".join(parts) + f"concat=n={len(input_paths)}:v=1:a=0[v]"
    cmd += [
        "-filter_complex", filter_str,
        "-map", "[v]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg concat failed (rc={proc.returncode}): {proc.stderr.decode(errors='replace')[-400:]}"
        )


async def export_timeline(db, user_id: str, clip_ids: list[str], name: str = "export") -> dict:
    """Server-side stitch of an ordered list of clip IDs. Returns export dict."""
    if not clip_ids:
        raise ValueError("Timeline is empty")
    # Resolve paths preserving order
    docs = []
    async for d in db.video_clips.find(
        {"user_id": user_id, "id": {"$in": clip_ids}}, {"_id": 0, "id": 1, "file_path": 1}
    ):
        docs.append(d)
    by_id = {d["id"]: d for d in docs}
    paths: list[str] = []
    for cid in clip_ids:
        rec = by_id.get(cid)
        if rec and rec.get("file_path") and Path(rec["file_path"]).exists():
            paths.append(rec["file_path"])
    if not paths:
        raise ValueError("No valid clips found for export")

    out_name = f"{uuid.uuid4().hex}.mp4"
    out_path = EXPORTS_DIR / out_name
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _ffmpeg_concat, paths, str(out_path))

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "name": name or "export",
        "clip_ids": clip_ids,
        "file_path": str(out_path),
        "url": f"/api/video/exports/{out_name}",
        "size_bytes": out_path.stat().st_size,
        "created_at": _now(),
    }
    await db.video_exports.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc
