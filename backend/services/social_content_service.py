"""Social Content Agent — generates a calendar of social media posts.

Uses Claude (via Emergent universal key) for content + OpenAI DALL-E for images.
Persistent: jobs are tracked in MongoDB via job_service so closing the browser
does not stop the build.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration
from PIL import Image

from services import job_service

logger = logging.getLogger("nxt1.social")

ASSETS_DIR = Path(__file__).resolve().parent.parent / "static" / "social"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _api_key() -> str:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")
    return key


PLATFORM_GUIDANCE = {
    "instagram": "Highly visual. Caption: 1-3 short paragraphs + emojis sparingly. Hashtags: 8-12 niche+broad mix.",
    "linkedin":  "Professional tone. First-person founder voice. Caption: 3-6 short paragraphs, line-broken. Hashtags: 3-5 industry tags.",
    "twitter":   "Concise. Hook + payoff in 250 chars or a 3-tweet micro-thread. Hashtags: 1-3 only.",
}


def _duration_to_count(duration: str) -> int:
    d = (duration or "").lower()
    if "today" in d:
        return 1
    if "week" in d:
        return 7
    # "daily for 30" -> 30
    digits = "".join(c for c in d if c.isdigit())
    if digits:
        try:
            return max(1, min(int(digits), 30))
        except Exception:
            pass
    return 7


def _platforms(platform: Optional[str], explicit: Optional[list]) -> list[str]:
    if explicit:
        return [p for p in explicit if p in PLATFORM_GUIDANCE]
    p = (platform or "all").lower()
    if p == "all":
        return ["instagram", "linkedin", "twitter"]
    return [p] if p in PLATFORM_GUIDANCE else ["linkedin"]


async def _generate_plan(brief: str, tone: str, platforms: list[str], count: int,
                         about: str, niche: str) -> list[dict]:
    """Ask Claude for a structured content calendar (JSON list)."""
    sys = (
        "You are an elite social media strategist. Output ONLY valid JSON, no prose. "
        "JSON is a list of objects, one per day per platform combination. "
        "Each object has fields: day (int 1..N), platform (string), topic (string), "
        "caption (string ready to post), hashtags (array of 5 strings without '#'), "
        "image_prompt (string for DALL-E - visual scene, no text overlays)."
    )
    plat_block = "\n".join(f"- {p}: {PLATFORM_GUIDANCE[p]}" for p in platforms)
    instruction = (
        f"Generate {count} day(s) of social posts for these platforms:\n{plat_block}\n\n"
        f"Tone: {tone}\n"
        f"Niche/Industry: {niche or 'general business'}\n"
        f"About the user: {about or '(not provided)'}\n"
        f"Brief: {brief}\n\n"
        f"Total posts = {count} × {len(platforms)}. "
        "Output ONLY the JSON array."
    )
    chat = LlmChat(
        api_key=_api_key(),
        session_id=f"social-plan-{uuid.uuid4()}",
        system_message=sys,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    resp = await chat.send_message(UserMessage(text=instruction))
    # Strip fences
    text = (resp or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    import json
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "posts" in data:
            data = data["posts"]
        if not isinstance(data, list):
            raise ValueError("not a list")
        return data
    except Exception as e:
        # Try to extract array
        import re
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        logger.error(f"Plan parse failed: {e}; raw={text[:400]}")
        raise RuntimeError(f"Could not parse content plan from AI: {e}")


def _overlay_logo(image_bytes: bytes, logo_path: Optional[str]) -> bytes:
    if not logo_path or not Path(logo_path).exists():
        return image_bytes
    try:
        base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        logo = Image.open(logo_path).convert("RGBA")
        # Resize logo to ~15% of image width
        target_w = max(64, int(base.width * 0.15))
        ratio = target_w / logo.width
        logo = logo.resize((target_w, int(logo.height * ratio)), Image.LANCZOS)
        # Bottom-right with padding
        pad = int(base.width * 0.03)
        pos = (base.width - logo.width - pad, base.height - logo.height - pad)
        base.alpha_composite(logo, pos)
        out = io.BytesIO()
        base.convert("RGB").save(out, format="PNG")
        return out.getvalue()
    except Exception as e:
        logger.warning(f"logo overlay failed: {e}")
        return image_bytes


async def _generate_image(prompt: str, logo_path: Optional[str]) -> Optional[str]:
    """Generate a single image and save to disk; return relative path."""
    try:
        img_gen = OpenAIImageGeneration(api_key=_api_key())
        images = await img_gen.generate_images(
            prompt=prompt,
            model="gpt-image-1",
            number_of_images=1,
        )
        if not images:
            return None
        raw = images[0]
        # If returned as dict {image_base64: ...}
        if isinstance(raw, dict) and "image_base64" in raw:
            raw = base64.b64decode(raw["image_base64"])
        elif isinstance(raw, str):
            raw = base64.b64decode(raw)
        final = _overlay_logo(raw, logo_path)
        fn = f"{uuid.uuid4().hex}.png"
        out = ASSETS_DIR / fn
        out.write_bytes(final)
        return f"/api/social/assets/{fn}"
    except Exception as e:
        logger.error(f"image gen failed: {e}")
        return None


async def run_social_job(
    db,
    job_id: str,
    *,
    user_id: str,
    brief: str,
    tone: str,
    platform: str,
    platforms: Optional[list],
    duration: str,
    about: str,
    niche: str,
    logo_path: Optional[str],
):
    """Detached background task — survives client disconnect.

    Writes:
      jobs[job_id] progress + logs (via job_service)
      social_posts entries (one per generated post)
    """
    try:
        plats = _platforms(platform, platforms)
        count = _duration_to_count(duration)
        total = count * len(plats)

        await job_service.append_log(db, job_id, "info",
                                     f"Generating {count} day(s) × {len(plats)} platform(s) = {total} posts",
                                     phase="planning", progress=0.05)

        plan = await _generate_plan(brief, tone, plats, count, about, niche)
        await job_service.append_log(db, job_id, "info",
                                     f"Plan ready with {len(plan)} entries. Generating images…",
                                     phase="images", progress=0.20)

        created: list[dict] = []
        for i, entry in enumerate(plan):
            # Check cancellation
            cur = await db.jobs.find_one({"id": job_id}, {"status": 1})
            if cur and cur.get("status") == "cancelled":
                await job_service.append_log(db, job_id, "warn", "Cancelled by user", phase="cancelled")
                return

            day = entry.get("day") or (i // max(len(plats), 1)) + 1
            plat = (entry.get("platform") or plats[0]).lower()
            caption = entry.get("caption") or ""
            hashtags = entry.get("hashtags") or []
            if isinstance(hashtags, str):
                hashtags = [h.strip().lstrip("#") for h in hashtags.split() if h.strip()]
            topic = entry.get("topic") or ""
            img_prompt = entry.get("image_prompt") or f"Stylish branded social image for: {topic}"

            await job_service.append_log(db, job_id, "info",
                                         f"Day {day} · {plat}: {topic[:60]}",
                                         phase="generating",
                                         progress=0.20 + 0.7 * (i / max(len(plan), 1)))

            image_url = await _generate_image(img_prompt, logo_path)

            scheduled_at = (datetime.now(timezone.utc) + timedelta(days=int(day) - 1)).isoformat()

            post = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "job_id": job_id,
                "day": int(day),
                "platform": plat,
                "topic": topic,
                "caption": caption,
                "hashtags": hashtags,
                "image_url": image_url,
                "image_prompt": img_prompt,
                "status": "draft",  # draft | approved | scheduled | posted
                "scheduled_at": scheduled_at,
                "created_at": _now(),
                "updated_at": _now(),
            }
            await db.social_posts.insert_one(dict(post))
            post.pop("_id", None)
            created.append(post)

        await job_service.complete(
            db, job_id,
            status="completed",
            result={"posts_created": len(created), "post_ids": [p["id"] for p in created]},
        )
        await job_service.append_log(db, job_id, "info",
                                     f"Done — {len(created)} posts created.",
                                     phase="completed", progress=1.0)
    except Exception as e:
        logger.exception("social job failed")
        await job_service.fail(db, job_id, f"{type(e).__name__}: {e}")


async def regenerate_post(db, post_id: str, user_id: str) -> dict:
    """Regenerate caption + image for a single post."""
    post = await db.social_posts.find_one({"id": post_id, "user_id": user_id}, {"_id": 0})
    if not post:
        raise ValueError("Post not found")

    sys = (
        "You are an elite social media strategist. Output ONLY a single JSON object with: "
        "caption (string), hashtags (array of 5 strings without '#'), image_prompt (string)."
    )
    instruction = (
        f"Regenerate this post (keep platform={post['platform']}, topic similar to '{post.get('topic','')}'):\n"
        f"Previous caption: {post.get('caption','')[:300]}\n"
        "Output JSON only."
    )
    chat = LlmChat(
        api_key=_api_key(),
        session_id=f"regen-{uuid.uuid4()}",
        system_message=sys,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    text = (await chat.send_message(UserMessage(text=instruction))).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    import json
    try:
        new = json.loads(text)
    except Exception:
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        new = json.loads(m.group(0)) if m else {}

    image_url = await _generate_image(new.get("image_prompt") or post.get("image_prompt"), None)

    updates = {
        "caption": new.get("caption") or post["caption"],
        "hashtags": new.get("hashtags") or post["hashtags"],
        "image_prompt": new.get("image_prompt") or post["image_prompt"],
        "image_url": image_url or post.get("image_url"),
        "updated_at": _now(),
    }
    await db.social_posts.update_one({"id": post_id}, {"$set": updates})
    post.update(updates)
    return post
