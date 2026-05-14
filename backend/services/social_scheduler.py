"""Social scheduler — background loop.

Runs every 60 s on the FastAPI event loop. Two responsibilities:

  1. Publish-when-due:
     For every post where status="scheduled" AND scheduled_at <= now AND the
     user has a connection for that platform → publish via
     social_publishing_service.publish_post, mark posted (or capture error).

  2. Auto-pilot:
     For every social_autopilot doc where enabled=True AND it's the configured
     weekday/hour AND last_run_at < (now - 6 days) → kick off a fresh
     content-generation job (same flow as POST /api/social/generate).

The loop is launched in server.py's `on_startup` so it survives the same way
every other detached task does — restart = restart loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from services import job_service, social_publishing_service as pub
from services.social_content_service import run_social_job

logger = logging.getLogger("nxt1.social.scheduler")

TICK_SECONDS = 60


def _now():
    return datetime.now(timezone.utc)


async def _publish_due_posts(db) -> int:
    """Find posts that should go out now. Returns count posted."""
    now_iso = _now().isoformat()
    cursor = db.social_posts.find(
        {"status": "scheduled", "scheduled_at": {"$lte": now_iso}},
        {"_id": 0},
    ).limit(20)
    sent = 0
    async for post in cursor:
        try:
            conn = await db.social_connections.find_one(
                {"user_id": post["user_id"], "platform": post["platform"]},
                {"_id": 0},
            )
            if not conn:
                # No connection yet — skip silently; user will see it stay scheduled.
                continue
            media_abs = None
            if post.get("image_url"):
                media_abs = (pub._public_base() + post["image_url"]
                             if post["image_url"].startswith("/") else post["image_url"])
            result = await pub.publish_post(conn, post, media_url=media_abs)
            await db.social_posts.update_one(
                {"id": post["id"]},
                {"$set": {
                    "status": "posted",
                    "platform_post_id": result.get("platform_post_id"),
                    "platform_url": result.get("url"),
                    "posted_at": _now().isoformat(),
                    "last_publish_error": None,
                    "updated_at": _now().isoformat(),
                }},
            )
            sent += 1
        except Exception as e:
            logger.warning(f"scheduler publish failed (post={post.get('id')}): {e}")
            await db.social_posts.update_one(
                {"id": post["id"]},
                {"$set": {
                    "last_publish_error": str(e)[:300],
                    "updated_at": _now().isoformat(),
                }},
            )
    return sent


async def _fire_autopilots(db) -> int:
    now = _now()
    cursor = db.social_autopilot.find({"enabled": True}, {"_id": 0})
    fired = 0
    async for ap in cursor:
        try:
            cad_day = int(ap.get("cadence_day", 1))   # 0=Mon..6=Sun
            cad_hour = int(ap.get("cadence_hour", 9))
            if now.weekday() != cad_day or now.hour != cad_hour:
                continue
            last = ap.get("last_run_at")
            if last:
                try:
                    last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                except Exception:
                    last_dt = None
                if last_dt and (now - last_dt) < timedelta(days=6):
                    continue
            brief = (ap.get("brief") or "").strip()
            if not brief:
                continue
            # Kick off a detached generation job for this user
            job = await job_service.start(
                db,
                kind="social-content",
                project_id=None,
                actor=ap["user_id"],
                initial_logs=[{
                    "ts": now.isoformat(),
                    "level": "info",
                    "msg": f"[Auto-pilot] {brief[:80]}",
                }],
            )
            asyncio.create_task(run_social_job(
                db, job["id"],
                user_id=ap["user_id"],
                brief=brief,
                tone=ap.get("tone", "professional"),
                platform="all",
                platforms=ap.get("platforms") or ["linkedin", "twitter"],
                duration=ap.get("duration", "this week"),
                about=ap.get("about", ""),
                niche=ap.get("niche", ""),
                logo_path=None,
            ))
            await db.social_autopilot.update_one(
                {"user_id": ap["user_id"]},
                {"$set": {
                    "last_run_at": now.isoformat(),
                    "last_job_id": job["id"],
                }},
            )
            fired += 1
        except Exception as e:
            logger.warning(f"autopilot fire failed (user={ap.get('user_id')}): {e}")
    return fired


async def scheduler_loop(db):
    logger.info("Social scheduler loop started (tick=%ss)", TICK_SECONDS)
    while True:
        try:
            n_pub = await _publish_due_posts(db)
            n_ap = await _fire_autopilots(db)
            if n_pub or n_ap:
                logger.info("scheduler tick: published=%d autopilots_fired=%d", n_pub, n_ap)
        except Exception as e:
            logger.exception(f"scheduler tick error: {e}")
        await asyncio.sleep(TICK_SECONDS)
