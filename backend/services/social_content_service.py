"""Social Content Agent — Claude (multimodal vision) + OpenAI gpt-image-1 (HQ).

Key behaviors:
  • Uses the user's own ANTHROPIC_API_KEY + OPENAI_API_KEY directly via
    litellm / openai SDK — no proprietary helpers, no managed-key coupling.
  • EMERGENT_LLM_KEY is supported transparently as a fallback proxy when the
    user hasn't yet set their own keys (preview/dev environment).
  • Brief input is multimodal: optional reference image URLs feed both Claude
    (for tone/style understanding) AND OpenAI image gen (the descriptions
    derived from references are appended to image prompts).
  • Auto-loads and auto-writes the user's `agent_memory` so the agent stays
    consistent across sessions.
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

import litellm
from openai import AsyncOpenAI
from PIL import Image

from services import agent_memory, job_service, asset_storage

logger = logging.getLogger("nxt1.social")

ASSETS_DIR = Path(__file__).resolve().parent.parent / "static" / "social"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

REF_IMG_DIR = ASSETS_DIR / "references"
REF_IMG_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_anthropic_key() -> bool:
    return bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip())


def _has_openai_key() -> bool:
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())


def _is_user_openai_key() -> bool:
    return _has_openai_key()


def _emergent_proxy_base() -> Optional[str]:
    """Return Emergent proxy /llm URL when a universal key is present."""
    if not (os.environ.get("EMERGENT_LLM_KEY") or "").strip():
        return None
    base = (
        os.environ.get("INTEGRATION_PROXY_URL")
        or os.environ.get("integration_proxy_url")
        or "https://integrations.emergentagent.com"
    )
    return base.rstrip("/") + "/llm"


async def _claude_chat(
    *,
    system: str,
    user_text: str,
    model: str = "claude-sonnet-4-5-20250929",
    image_b64_list: Optional[list[str]] = None,
    max_tokens: int = 4096,
) -> str:
    """Call Claude with optional vision. Uses ANTHROPIC_API_KEY when set,
    otherwise routes through the Emergent universal-key proxy.
    """
    user_content: list[dict] = [{"type": "text", "text": user_text}]
    for b64 in (image_b64_list or [])[:3]:
        # Detect mime from b64 magic header
        if b64.startswith("/9j/"):
            mime = "image/jpeg"
        elif b64.startswith("R0lGOD"):
            mime = "image/gif"
        elif b64.startswith("UklGR"):
            mime = "image/webp"
        else:
            mime = "image/png"
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    anth_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if anth_key:
        resp = await litellm.acompletion(
            model=f"anthropic/{model}",
            api_key=anth_key,
            messages=messages,
            max_tokens=max_tokens,
        )
        return resp["choices"][0]["message"]["content"] or ""
    # Fallback: Emergent universal-key proxy (OpenAI-compatible)
    em_key = (os.environ.get("EMERGENT_LLM_KEY") or "").strip()
    proxy = _emergent_proxy_base()
    if not em_key or not proxy:
        raise RuntimeError(
            "Claude not configured. Set ANTHROPIC_API_KEY in your environment."
        )
    resp = await litellm.acompletion(
        model=model,  # bare name — proxy figures it out
        api_key=em_key,
        api_base=proxy,
        custom_llm_provider="openai",
        messages=messages,
        max_tokens=max_tokens,
    )
    return resp["choices"][0]["message"]["content"] or ""


async def _openai_image(prompt: str, *, model: str = "gpt-image-1") -> Optional[bytes]:
    """Generate one image via OpenAI gpt-image-1. Returns raw PNG bytes."""
    oa_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if oa_key:
        client = AsyncOpenAI(api_key=oa_key)
    else:
        em_key = (os.environ.get("EMERGENT_LLM_KEY") or "").strip()
        proxy = _emergent_proxy_base()
        if not em_key or not proxy:
            raise RuntimeError(
                "OpenAI image gen not configured. Set OPENAI_API_KEY in your environment."
            )
        client = AsyncOpenAI(api_key=em_key, base_url=proxy)
    resp = await client.images.generate(
        model=model,
        prompt=prompt + " — photorealistic, high detail, professional photography, 4k",
        n=1,
        size="1024x1024",
    )
    if not resp.data:
        return None
    item = resp.data[0]
    if getattr(item, "b64_json", None):
        return base64.b64decode(item.b64_json)
    if getattr(item, "url", None):
        import httpx
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.get(item.url)
            return r.content
    return None



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


def _load_image_b64(path: str) -> Optional[str]:
    try:
        return base64.b64encode(Path(path).read_bytes()).decode()
    except Exception:
        return None


async def _generate_plan(
    db,
    user_id: str,
    brief: str,
    tone: str,
    platforms: list[str],
    count: int,
    about: str,
    niche: str,
    reference_image_paths: Optional[list[str]] = None,
) -> tuple[list[dict], str]:
    """Ask Claude for a structured content calendar.

    Returns (plan_list, reference_visual_summary). The summary describes the
    visual style of any reference images (or "" if none) so it can be appended
    to every image_prompt for cohesive look.
    """
    sys = (
        "You are an elite social media strategist with deep expertise in personal brand. "
        "Output ONLY valid JSON, no prose. JSON is a list of objects, one per day per "
        "platform combination. Each object has fields: day (int 1..N), platform (string), "
        "topic (string), caption (string ready to post), hashtags (array of 5 strings without '#'), "
        "image_prompt (string for DALL-E — visual scene, no text overlays). "
        "Use the user memory and reference images (if provided) to maintain consistency."
    )

    # Auto-load user memory
    mem_block = await agent_memory.build_context_block(db, user_id=user_id, scope="social")

    plat_block = "\n".join(f"- {p}: {PLATFORM_GUIDANCE[p]}" for p in platforms)
    instruction_parts = [
        f"Generate {count} day(s) of social posts for these platforms:\n{plat_block}",
        f"Tone: {tone}",
        f"Niche/Industry: {niche or '(not specified)'}",
        f"About the user: {about or '(not provided)'}",
        f"Brief: {brief}",
        f"Total posts = {count} × {len(platforms)}.",
    ]
    if mem_block:
        instruction_parts.insert(0, mem_block)
    if reference_image_paths:
        instruction_parts.append(
            "Reference images attached — match their visual mood/style in image_prompt."
        )
    instruction_parts.append("Output ONLY the JSON array.")
    instruction = "\n\n".join(instruction_parts)

    # Collect reference images as base64 once for reuse
    ref_b64_list: list[str] = []
    if reference_image_paths:
        for p in reference_image_paths[:3]:
            b64 = _load_image_b64(p)
            if b64:
                ref_b64_list.append(b64)

    resp = await _claude_chat(
        system=sys,
        user_text=instruction,
        image_b64_list=ref_b64_list or None,
        max_tokens=4096,
    )
    text = (resp or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    import json
    plan: list[dict] = []
    try:
        data = json.loads(text)
        plan = data["posts"] if isinstance(data, dict) and "posts" in data else data
        if not isinstance(plan, list):
            raise ValueError("not a list")
    except Exception as e:
        import re
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                plan = json.loads(m.group(0))
            except Exception:
                raise RuntimeError(f"Could not parse content plan: {e}")
        else:
            raise RuntimeError(f"Could not parse content plan: {e}")

    # Build a tiny visual-style summary from reference images via Claude vision
    visual_summary = ""
    if ref_b64_list:
        try:
            visual_summary = (await _claude_chat(
                system="Describe the visual style (mood, palette, composition, subject) of these reference images in 2 sentences for use in DALL-E prompts. No preamble.",
                user_text="Describe these references.",
                image_b64_list=ref_b64_list,
                max_tokens=400,
            )).strip()[:400]
        except Exception as e:
            logger.warning(f"visual summary failed: {e}")

    return plan, visual_summary


def _overlay_logo(image_bytes: bytes, logo_path: Optional[str]) -> bytes:
    if not logo_path or not Path(logo_path).exists():
        return image_bytes
    try:
        base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        logo = Image.open(logo_path).convert("RGBA")
        target_w = max(64, int(base.width * 0.15))
        ratio = target_w / logo.width
        logo = logo.resize((target_w, int(logo.height * ratio)), Image.LANCZOS)
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
    """Generate one HIGH-quality image via OpenAI gpt-image-1. Save and return URL."""
    try:
        raw = await _openai_image(prompt, model="gpt-image-1")
        if not raw:
            return None
        final = _overlay_logo(raw, logo_path)
        fn = f"{uuid.uuid4().hex}.png"
        # Storage facade: R2 if configured, else local disk
        res = asset_storage.put_bytes(folder="social", filename=fn, data=final, content_type="image/png")
        return res["url"]
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
    reference_image_paths: Optional[list[str]] = None,
):
    """Detached background task — survives client disconnect."""
    try:
        plats = _platforms(platform, platforms)
        count = _duration_to_count(duration)
        total = count * len(plats)

        # Auto-write: store the brief itself as a recent example
        try:
            await agent_memory.remember(
                db, user_id=user_id, scope="social", kind="example",
                summary=f"User asked: {brief[:240]}",
                payload={"brief": brief, "tone": tone, "platforms": plats,
                         "duration": duration, "reference_count": len(reference_image_paths or [])},
            )
        except Exception:
            pass

        await job_service.append_log(
            db, job_id, "info",
            f"Loaded user memory + generating {count} day(s) × {len(plats)} platform(s) = {total} posts" +
            (f" with {len(reference_image_paths)} reference image(s)" if reference_image_paths else ""),
            phase="planning", progress=0.05,
        )

        plan, visual_style = await _generate_plan(
            db, user_id, brief, tone, plats, count, about, niche,
            reference_image_paths=reference_image_paths,
        )

        key_kind = "your OpenAI key" if _is_user_openai_key() else "fallback proxy"
        await job_service.append_log(
            db, job_id, "info",
            f"Plan ready ({len(plan)} entries). Generating HQ images via gpt-image-1 ({key_kind})…",
            phase="images", progress=0.20,
        )

        created: list[dict] = []
        for i, entry in enumerate(plan):
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
            base_prompt = entry.get("image_prompt") or f"Stylish branded social image for: {topic}"
            img_prompt = base_prompt + (f" — visual style: {visual_style}" if visual_style else "")

            await job_service.append_log(
                db, job_id, "info",
                f"Day {day} · {plat}: {topic[:60]}",
                phase="generating",
                progress=0.20 + 0.7 * (i / max(len(plan), 1)),
            )

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
                "status": "draft",
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
        await job_service.append_log(
            db, job_id, "info",
            f"Done — {len(created)} posts created.",
            phase="completed", progress=1.0,
        )

        # Auto-write: store a summary so the next run is smarter
        try:
            topics = ", ".join(p.get("topic", "")[:40] for p in created[:3])
            await agent_memory.remember(
                db, user_id=user_id, scope="social", kind="fact",
                summary=f"Generated {len(created)} posts ({tone} tone) — topics: {topics}",
                payload={"job_id": job_id, "platforms": plats, "count": len(created)},
            )
        except Exception:
            pass
    except Exception as e:
        logger.exception("social job failed")
        await job_service.fail(db, job_id, f"{type(e).__name__}: {e}")


async def regenerate_post(db, post_id: str, user_id: str) -> dict:
    """Regenerate caption + image for a single post. Memory-aware."""
    post = await db.social_posts.find_one({"id": post_id, "user_id": user_id}, {"_id": 0})
    if not post:
        raise ValueError("Post not found")

    mem_block = await agent_memory.build_context_block(db, user_id=user_id, scope="social")
    sys = (
        "You are an elite social media strategist. Output ONLY a single JSON object with: "
        "caption (string), hashtags (array of 5 strings without '#'), image_prompt (string). "
        "Use the user memory to keep voice consistent."
    )
    parts = []
    if mem_block:
        parts.append(mem_block)
    parts.append(
        f"Regenerate this post (platform={post['platform']}, topic='{post.get('topic','')}').\n"
        f"Previous caption: {post.get('caption','')[:300]}\nOutput JSON only."
    )
    text = (await _claude_chat(
        system=sys,
        user_text="\n\n".join(parts),
        max_tokens=1500,
    )).strip()
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

    # Memory: note the regeneration as feedback
    try:
        await agent_memory.remember(
            db, user_id=user_id, scope="social", kind="feedback",
            summary=f"Regenerated post on {post['platform']} (topic: {post.get('topic','')[:60]})",
        )
    except Exception:
        pass

    return post
