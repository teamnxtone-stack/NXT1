"""AgentOS — personal AI agent suite (Phase B.13, 2026-05-13).

Workspace-only routes powering the AgentOS dashboard:

  Profile (Settings):
    GET    /api/v1/agentos/profile
    PUT    /api/v1/agentos/profile

  Job discovery (Agent 2):
    POST   /api/v1/agentos/jobs/scan        — kick off a fresh scan
    GET    /api/v1/agentos/jobs             — list, filter by status/platform
    POST   /api/v1/agentos/jobs/{id}/approve
    POST   /api/v1/agentos/jobs/{id}/reject

  Resume (Agent 4):
    GET    /api/v1/agentos/resume/master
    PUT    /api/v1/agentos/resume/master
    POST   /api/v1/agentos/resume/tailor    — tailor master to a job
    GET    /api/v1/agentos/resume/tailored  — list tailored versions

  Outreach (Agent 5):
    GET    /api/v1/agentos/leads
    POST   /api/v1/agentos/leads/draft      — draft a message for one lead
    POST   /api/v1/agentos/leads/{id}/approve
    POST   /api/v1/agentos/leads/{id}/reject

  Approvals queue:
    GET    /api/v1/agentos/approvals
    POST   /api/v1/agentos/approvals/{id}/approve
    POST   /api/v1/agentos/approvals/{id}/reject

  System:
    GET    /api/v1/agentos/system/keys      — which provider/integration
                                              keys are actually configured

The Browser Agent, Voice Agent, and live-send outreach are NOT wired here —
they require infrastructure (Playwright sandbox, LiveKit Cloud, OAuth tokens)
that doesn't fit the single-pod environment. The FE shows clear "Coming next
— set $KEY to enable" cards for those.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ._deps import db, verify_token

logger = logging.getLogger("nxt1.agentos")

router = APIRouter(prefix="/api/v1/agentos", tags=["agentos"])


# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------
COL_PROFILE = "agentos_profiles"
COL_JOBS = "agentos_jobs"
COL_LEADS = "agentos_leads"
COL_APPROVALS = "agentos_approvals"
COL_RESUMES = "agentos_resumes"
COL_SOCIAL = "agentos_social_strategies"
COL_FOUNDERS = "agentos_founders_config"

DEFAULT_PROFILE = {
    "name": "", "current_role": "", "target_roles": [],
    "bio": "", "years_experience": 0,
    "location": "", "remote_only": True,
    "min_salary": None,
    "target_titles": ["Senior Software Engineer", "Staff Engineer"],
    "target_locations": ["Remote"],
    "exclude_companies": [],
    "job_scan_freq_hours": 6,
    "outreach_scan_freq_hours": 12,
    "daily_application_limit": 20,
    "daily_outreach_limit": 15,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "_id"}


async def _get_profile_or_default(user: str) -> dict:
    doc = await db[COL_PROFILE].find_one({"user": user}, {"_id": 0})
    if not doc:
        doc = {"user": user, **DEFAULT_PROFILE, "created_at": _now(), "updated_at": _now()}
        await db[COL_PROFILE].insert_one(dict(doc))
        doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# Profile / Settings
# ---------------------------------------------------------------------------
class ProfileBody(BaseModel):
    name: Optional[str] = None
    current_role: Optional[str] = None
    target_roles: Optional[list[str]] = None
    bio: Optional[str] = None
    years_experience: Optional[int] = None
    location: Optional[str] = None
    remote_only: Optional[bool] = None
    min_salary: Optional[int] = None
    target_titles: Optional[list[str]] = None
    target_locations: Optional[list[str]] = None
    exclude_companies: Optional[list[str]] = None
    job_scan_freq_hours: Optional[int] = Field(None, ge=1, le=72)
    outreach_scan_freq_hours: Optional[int] = Field(None, ge=1, le=72)
    daily_application_limit: Optional[int] = Field(None, ge=0, le=200)
    daily_outreach_limit: Optional[int] = Field(None, ge=0, le=200)


@router.get("/profile")
async def get_profile(user: str = Depends(verify_token)):
    return await _get_profile_or_default(user)


@router.put("/profile")
async def update_profile(body: ProfileBody, user: str = Depends(verify_token)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    patch["updated_at"] = _now()
    await _get_profile_or_default(user)  # ensure row exists
    await db[COL_PROFILE].update_one({"user": user}, {"$set": patch})
    return await _get_profile_or_default(user)


# ---------------------------------------------------------------------------
# Job discovery (Agent 2 — real, via jobspy)
# ---------------------------------------------------------------------------
class JobScanBody(BaseModel):
    sites: Optional[list[str]] = Field(default=None,
        description="One or more of: linkedin, indeed, glassdoor, zip_recruiter, google")
    search_terms: Optional[list[str]] = None
    location: Optional[str] = None
    results_wanted: int = Field(20, ge=5, le=100)
    is_remote: Optional[bool] = None
    hours_old: int = Field(72, ge=1, le=720)


def _job_url_hash(j: dict) -> str:
    """Stable dedup key — prefers `job_url`, falls back to (site,title,company)."""
    return (j.get("job_url") or
            f"{j.get('site','?')}::{j.get('title','?')}::{j.get('company','?')}")


def _safe_num(v):
    """pandas returns NaN for missing numeric fields; FastAPI's JSON serializer
    chokes on it ("Out of range float values are not JSON compliant"). Coerce."""
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:  # NaN check
            return None
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


def _normalize_job(raw: dict, user: str) -> dict:
    return {
        "id":          str(uuid.uuid4()),
        "user":        user,
        "url_hash":    _job_url_hash(raw),
        "site":        raw.get("site") or raw.get("source"),
        "title":       raw.get("title"),
        "company":     raw.get("company"),
        "location":    raw.get("location"),
        "is_remote":   bool(raw.get("is_remote")) if raw.get("is_remote") is not None else False,
        "job_url":     raw.get("job_url"),
        "description": (raw.get("description") or "")[:6000] if isinstance(raw.get("description"), str) else "",
        "min_amount":  _safe_num(raw.get("min_amount")),
        "max_amount":  _safe_num(raw.get("max_amount")),
        "currency":    raw.get("currency") or "USD",
        "date_posted": str(raw.get("date_posted") or ""),
        "status":      "new",
        "log":         [],
        "created_at":  _now(),
        "updated_at":  _now(),
    }


async def _scan_jobs(user: str, body: JobScanBody) -> dict:
    """Run a single jobspy scrape, dedup vs Mongo, insert new ones."""
    profile = await _get_profile_or_default(user)
    sites = body.sites or ["linkedin", "indeed", "zip_recruiter"]
    search_terms = body.search_terms or profile.get("target_titles") or ["Software Engineer"]
    location = body.location or (profile.get("target_locations") or [""])[0] or "Remote"
    is_remote = body.is_remote if body.is_remote is not None else profile.get("remote_only", True)

    from jobspy import scrape_jobs

    def _scrape():
        # jobspy is synchronous + does HTTP; run off the event loop.
        try:
            return scrape_jobs(
                site_name=sites,
                search_term=", ".join(search_terms[:3]),
                location=location,
                results_wanted=body.results_wanted,
                hours_old=body.hours_old,
                is_remote=is_remote,
                country_indeed="USA",
            )
        except Exception as e:
            logger.exception("jobspy scrape failed")
            return e

    df = await asyncio.to_thread(_scrape)
    if isinstance(df, Exception):
        raise HTTPException(status_code=502, detail=f"Job board scrape failed: {df}")

    new_count = 0
    if df is not None and not df.empty:
        # Pandas' to_dict() leaves NaN floats in place; FastAPI's JSON
        # serializer rejects them. Replace NaN with None up front.
        try:
            import math
            def _clean(v):
                if isinstance(v, float) and math.isnan(v):
                    return None
                return v
        except Exception:
            def _clean(v): return v  # noqa

        existing = await db[COL_JOBS].find(
            {"user": user}, {"_id": 0, "url_hash": 1}
        ).to_list(length=5000)
        seen = {d["url_hash"] for d in existing}
        to_insert: list[dict] = []
        for _, row in df.iterrows():
            raw = {k: _clean(v) for k, v in row.to_dict().items()}
            doc = _normalize_job(raw, user)
            if doc["url_hash"] in seen:
                continue
            seen.add(doc["url_hash"])
            to_insert.append(doc)
        if to_insert:
            await db[COL_JOBS].insert_many(to_insert)
            new_count = len(to_insert)

    return {"scanned_at": _now(), "new_jobs": new_count,
            "total_returned": int(getattr(df, "shape", [0])[0] or 0)}


@router.post("/jobs/scan")
async def jobs_scan(body: JobScanBody, user: str = Depends(verify_token)):
    return await _scan_jobs(user, body)


@router.get("/jobs")
async def jobs_list(
    status: Optional[str] = None,
    site: Optional[str] = None,
    limit: int = 100,
    user: str = Depends(verify_token),
):
    q: dict = {"user": user}
    if status:
        q["status"] = status
    if site:
        q["site"] = site
    cur = db[COL_JOBS].find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cur.to_list(length=limit)


@router.post("/jobs/{job_id}/approve")
async def jobs_approve(job_id: str, user: str = Depends(verify_token)):
    job = await db[COL_JOBS].find_one({"id": job_id, "user": user}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await db[COL_JOBS].update_one(
        {"id": job_id, "user": user},
        {"$set": {"status": "approved", "updated_at": _now()}},
    )
    # Enqueue an approval item so the user explicitly confirms the auto-apply.
    approval = {
        "id": str(uuid.uuid4()), "user": user, "kind": "apply_job",
        "title": f"Apply to {job['title']} @ {job['company']}",
        "preview": {"job": job},
        "status": "pending",
        "created_at": _now(),
    }
    await db[COL_APPROVALS].insert_one(dict(approval))
    return {"ok": True}


@router.post("/jobs/{job_id}/reject")
async def jobs_reject(job_id: str, user: str = Depends(verify_token)):
    r = await db[COL_JOBS].update_one(
        {"id": job_id, "user": user},
        {"$set": {"status": "rejected", "updated_at": _now()}},
    )
    if not r.modified_count:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Resume (Agent 4)
# ---------------------------------------------------------------------------
class MasterResumeBody(BaseModel):
    plain_text: str = Field(..., min_length=20, max_length=80000)


@router.get("/resume/master")
async def resume_master_get(user: str = Depends(verify_token)):
    doc = await db[COL_RESUMES].find_one({"user": user, "kind": "master"}, {"_id": 0})
    return doc or {"user": user, "kind": "master", "plain_text": ""}


@router.put("/resume/master")
async def resume_master_put(body: MasterResumeBody, user: str = Depends(verify_token)):
    await db[COL_RESUMES].update_one(
        {"user": user, "kind": "master"},
        {"$set": {
            "user": user, "kind": "master",
            "plain_text": body.plain_text,
            "updated_at": _now(),
        }},
        upsert=True,
    )
    return {"ok": True}


class TailorBody(BaseModel):
    job_id: str


@router.post("/resume/tailor")
async def resume_tailor(body: TailorBody, user: str = Depends(verify_token)):
    """Rewrite the master resume for one job via litellm. Returns the
    tailored markdown text. (PDF export → Phase B.14 — needs reportlab
    install pass.)"""
    master = await db[COL_RESUMES].find_one({"user": user, "kind": "master"}, {"_id": 0})
    if not master or not (master.get("plain_text") or "").strip():
        raise HTTPException(status_code=400, detail="Master resume not set yet")
    job = await db[COL_JOBS].find_one({"id": body.job_id, "user": user}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from services.ai_service import generate_text_stream
    system = (
        "You are an elite resume tailor. Rewrite the provided MASTER RESUME "
        "to match the JOB DESCRIPTION while staying strictly factual — never "
        "invent skills or experience that aren't in the master. Adjust bullet "
        "ordering, emphasise relevant keywords, trim irrelevant sections, "
        "preserve dates and titles. Output a single markdown document, no "
        "preamble."
    )
    user_msg = (
        f"# MASTER RESUME\n\n{master['plain_text']}\n\n"
        f"# JOB DESCRIPTION\n\n"
        f"Title: {job['title']}\nCompany: {job['company']}\nLocation: {job.get('location','')}\n\n"
        f"{job.get('description','')[:3000]}\n\n"
        f"# OUTPUT\nReturn ONLY the tailored resume in markdown."
    )
    chunks: list[str] = []
    async for ch in generate_text_stream(
        system_prompt=system,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=2400,
    ):
        chunks.append(ch)
    tailored = "".join(chunks).strip()
    if not tailored:
        raise HTTPException(status_code=502, detail="LLM returned no content")

    tdoc = {
        "id":         str(uuid.uuid4()),
        "user":       user,
        "kind":       "tailored",
        "job_id":     body.job_id,
        "job_title":  job["title"],
        "company":    job["company"],
        "markdown":   tailored,
        "created_at": _now(),
    }
    await db[COL_RESUMES].insert_one(dict(tdoc))
    return _public(tdoc)


@router.get("/resume/tailored")
async def resume_tailored_list(user: str = Depends(verify_token)):
    cur = db[COL_RESUMES].find(
        {"user": user, "kind": "tailored"}, {"_id": 0}
    ).sort("created_at", -1).limit(50)
    return await cur.to_list(length=50)


# ---------------------------------------------------------------------------
# Outreach (Agent 5 — draft only, no real send yet)
# ---------------------------------------------------------------------------
class DraftLeadBody(BaseModel):
    platform: str = Field(..., description="linkedin | x")
    name: str
    snippet: str = Field(..., description="The lead's post content / bio")
    profile_url: Optional[str] = None


@router.get("/leads")
async def leads_list(status: Optional[str] = None, user: str = Depends(verify_token)):
    q: dict = {"user": user}
    if status:
        q["status"] = status
    cur = db[COL_LEADS].find(q, {"_id": 0}).sort("created_at", -1).limit(200)
    return await cur.to_list(length=200)


@router.post("/leads/draft")
async def leads_draft(body: DraftLeadBody, user: str = Depends(verify_token)):
    """Save a new lead + ask the LLM to draft a personalised message."""
    profile = await _get_profile_or_default(user)
    from services.ai_service import generate_text_stream

    system = (
        "You craft short, sincere outreach messages. Tone: human, specific, "
        "no marketing fluff. Max 4 sentences. Reference their snippet "
        "naturally. Sign off with the sender's first name only."
    )
    user_msg = (
        f"# SENDER BIO\n{profile.get('bio') or profile.get('current_role') or 'Engineer'}\n"
        f"Name: {profile.get('name') or 'Me'}\n\n"
        f"# LEAD\nPlatform: {body.platform}\nName: {body.name}\n\n"
        f"# THEIR POST\n{body.snippet[:1500]}\n\n"
        f"# OUTPUT\nReturn ONLY the message text — no quotation marks, no preamble."
    )
    chunks: list[str] = []
    async for ch in generate_text_stream(
        system_prompt=system,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=320,
    ):
        chunks.append(ch)
    drafted = "".join(chunks).strip()

    lead = {
        "id":           str(uuid.uuid4()),
        "user":         user,
        "platform":     body.platform,
        "name":         body.name,
        "snippet":      body.snippet[:2000],
        "profile_url":  body.profile_url,
        "draft":        drafted,
        "status":       "drafted",
        "created_at":   _now(),
    }
    await db[COL_LEADS].insert_one(dict(lead))
    return _public(lead)


class EditLeadBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


@router.post("/leads/{lead_id}/approve")
async def leads_approve(lead_id: str, body: Optional[EditLeadBody] = None,
                         user: str = Depends(verify_token)):
    lead = await db[COL_LEADS].find_one({"id": lead_id, "user": user}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    # Rate-limit check.
    profile = await _get_profile_or_default(user)
    cap = profile.get("daily_outreach_limit", 15)
    midnight_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = await db[COL_LEADS].count_documents({
        "user": user, "status": "queued",
        "approved_at": {"$gte": midnight_utc.isoformat()},
    })
    if sent_today >= cap:
        raise HTTPException(status_code=429, detail=f"Daily outreach limit ({cap}) reached")
    final_message = body.message if body and body.message else lead.get("draft", "")
    await db[COL_LEADS].update_one(
        {"id": lead_id, "user": user},
        {"$set": {
            "status": "queued",
            "approved_at": _now(),
            "final_message": final_message,
        }},
    )
    return {"ok": True, "note": "Queued — real send pending Browser Agent infra"}


@router.post("/leads/{lead_id}/reject")
async def leads_reject(lead_id: str, user: str = Depends(verify_token)):
    r = await db[COL_LEADS].update_one(
        {"id": lead_id, "user": user},
        {"$set": {"status": "rejected", "rejected_at": _now()}},
    )
    if not r.modified_count:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Approvals queue
# ---------------------------------------------------------------------------
@router.get("/approvals")
async def approvals_list(user: str = Depends(verify_token)):
    cur = db[COL_APPROVALS].find(
        {"user": user, "status": "pending"}, {"_id": 0}
    ).sort("created_at", -1).limit(200)
    return await cur.to_list(length=200)


@router.post("/approvals/{aid}/approve")
async def approvals_approve(aid: str, user: str = Depends(verify_token)):
    r = await db[COL_APPROVALS].update_one(
        {"id": aid, "user": user, "status": "pending"},
        {"$set": {"status": "approved", "decided_at": _now()}},
    )
    if not r.modified_count:
        raise HTTPException(status_code=404, detail="Approval not found / already decided")
    return {"ok": True}


@router.post("/approvals/{aid}/reject")
async def approvals_reject(aid: str, user: str = Depends(verify_token)):
    r = await db[COL_APPROVALS].update_one(
        {"id": aid, "user": user, "status": "pending"},
        {"$set": {"status": "rejected", "decided_at": _now()}},
    )
    if not r.modified_count:
        raise HTTPException(status_code=404, detail="Approval not found / already decided")
    return {"ok": True}


# ---------------------------------------------------------------------------
# System — which keys are wired
# ---------------------------------------------------------------------------
@router.get("/system/keys")
async def system_keys(_: str = Depends(verify_token)):
    """Report which integration keys are configured. Used by the FE
    Settings page to render "Configured ✓" / "Set $KEY to enable" badges.
    Never returns the actual key values."""
    def _has(k: str) -> bool:
        return bool(os.environ.get(k))
    return {
        "llm": {
            "anthropic":   _has("ANTHROPIC_API_KEY"),
            "openai":      _has("OPENAI_API_KEY"),
            "gemini":      _has("GEMINI_API_KEY") or _has("GOOGLE_API_KEY"),
            "xai":         _has("XAI_API_KEY") or _has("GROK_API_KEY"),
            "emergent":    _has("EMERGENT_LLM_KEY"),
        },
        "voice": {
            "deepgram":    _has("DEEPGRAM_API_KEY"),
            "cartesia":    _has("CARTESIA_API_KEY"),
            "livekit":     _has("LIVEKIT_URL") and _has("LIVEKIT_API_KEY") and _has("LIVEKIT_API_SECRET"),
        },
        "platforms": {
            "linkedin":    _has("LINKEDIN_SESSION_COOKIE"),
            "x":           _has("X_SESSION_COOKIE"),
        },
        "encryption":      _has("ENCRYPTION_KEY"),
    }



# ---------------------------------------------------------------------------
# Social — Postiz integration stubs + content-strategy generation
# ---------------------------------------------------------------------------
_POSTIZ_URL = os.environ.get("POSTIZ_URL", "http://localhost:5000")
_BOLT_URL   = os.environ.get("BOLT_DIY_URL", "http://localhost:5173")


async def _probe_url(url: str, timeout: float = 3.0) -> bool:
    """Lightweight liveness probe — used by Social/Builder tabs to decide
    whether to render the iframe or a "boot it" notice. Never raises."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            r = await client.get(url)
            return r.status_code < 500
    except Exception:
        return False


@router.get("/social/status")
async def social_status(_: str = Depends(verify_token)):
    """Returns whether the Postiz sidecar is reachable + the iframe URL."""
    return {
        "service": "postiz",
        "url": _POSTIZ_URL,
        "reachable": await _probe_url(_POSTIZ_URL),
        "boot_hint": "docker compose --profile social up -d",
    }


class SocialStrategyBody(BaseModel):
    goals: Optional[str] = Field(None, max_length=500,
        description="Free-text goals for this week's content")
    platforms: Optional[list[str]] = Field(
        default=None,
        description="Target platforms — defaults to ['linkedin','x']")
    cadence_per_week: int = Field(5, ge=1, le=21)


@router.post("/social/strategy")
async def social_strategy(body: SocialStrategyBody, user: str = Depends(verify_token)):
    """Generate a 1-week content calendar using the user's profile +
    goals. Returns structured day-by-day post drafts ready to schedule
    in Postiz."""
    profile = await _get_profile_or_default(user)
    platforms = body.platforms or ["linkedin", "x"]

    from services.ai_service import generate_text_stream
    system = (
        "You are a social-content strategist. Generate a 1-week content "
        "calendar tailored to the sender's bio and goals. Tone: authentic, "
        "human, specific. No hashtag stuffing. Each post stands alone — no "
        "thread cliffhangers. Output MUST be valid JSON of shape: "
        '{"posts":[{"day":"Mon","platform":"linkedin","hook":"…","body":"…","why":"…"}]}'
    )
    user_msg = (
        f"# SENDER\n"
        f"Name: {profile.get('name') or 'Operator'}\n"
        f"Role: {profile.get('current_role') or 'Founder'}\n"
        f"Bio: {profile.get('bio') or '—'}\n\n"
        f"# GOALS\n{body.goals or 'Build audience, share authentic build notes.'}\n\n"
        f"# CONSTRAINTS\nPlatforms: {', '.join(platforms)}\n"
        f"Cadence: {body.cadence_per_week} posts spread across the week.\n\n"
        f"# OUTPUT\nReturn ONLY the JSON object — no preamble, no markdown fences."
    )
    chunks: list[str] = []
    async for ch in generate_text_stream(
        system_prompt=system,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=1800,
    ):
        chunks.append(ch)
    raw = "".join(chunks).strip()
    if not raw:
        raise HTTPException(status_code=502, detail="LLM returned no content")

    # Parse — be forgiving of code fences.
    import json
    import re
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
        posts = parsed.get("posts") if isinstance(parsed, dict) else None
        if not isinstance(posts, list):
            posts = []
    except Exception:
        posts = [{"day": "Mon", "platform": platforms[0], "hook": raw[:120],
                  "body": raw, "why": "raw output (LLM did not return JSON)"}]

    strat = {
        "id":         str(uuid.uuid4()),
        "user":       user,
        "goals":      body.goals,
        "platforms":  platforms,
        "posts":      posts,
        "created_at": _now(),
    }
    await db[COL_SOCIAL].insert_one(dict(strat))
    return _public(strat)


@router.get("/social/strategies")
async def social_strategies(user: str = Depends(verify_token)):
    cur = db[COL_SOCIAL].find({"user": user}, {"_id": 0}).sort("created_at", -1).limit(20)
    return await cur.to_list(length=20)


# ---------------------------------------------------------------------------
# Founders — warm-lead config (the Outreach UI now lives under this tab)
# ---------------------------------------------------------------------------
DEFAULT_FOUNDERS_CONFIG = {
    "stages":      ["seed", "series-a"],
    "industries":  ["AI", "Developer Tools", "SaaS"],
    "geographies": ["United States", "Remote"],
    "ticket_size_min": None,
    "ticket_size_max": None,
    "keywords":    ["founder", "ceo", "building"],
    "exclude_keywords": ["recruiter", "hiring"],
}


class FoundersConfigBody(BaseModel):
    stages:           Optional[list[str]] = None
    industries:       Optional[list[str]] = None
    geographies:      Optional[list[str]] = None
    ticket_size_min:  Optional[int] = None
    ticket_size_max:  Optional[int] = None
    keywords:         Optional[list[str]] = None
    exclude_keywords: Optional[list[str]] = None


@router.get("/founders/config")
async def founders_config_get(user: str = Depends(verify_token)):
    doc = await db[COL_FOUNDERS].find_one({"user": user}, {"_id": 0})
    if not doc:
        doc = {"user": user, **DEFAULT_FOUNDERS_CONFIG,
               "created_at": _now(), "updated_at": _now()}
        await db[COL_FOUNDERS].insert_one(dict(doc))
        doc.pop("_id", None)
    return doc


@router.put("/founders/config")
async def founders_config_put(body: FoundersConfigBody, user: str = Depends(verify_token)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    patch["updated_at"] = _now()
    await founders_config_get(user)  # ensure row exists
    await db[COL_FOUNDERS].update_one({"user": user}, {"$set": patch})
    return await founders_config_get(user)


@router.get("/founders/stats")
async def founders_stats(user: str = Depends(verify_token)):
    """Quick counts for the Founders tab top-strip."""
    rows = await db[COL_LEADS].find(
        {"user": user}, {"_id": 0, "status": 1}
    ).to_list(length=5000)
    by_status: dict = {}
    for doc in rows:
        s = doc.get("status") or "unknown"
        by_status[s] = by_status.get(s, 0) + 1
    return {
        "drafted":  by_status.get("drafted",  0),
        "queued":   by_status.get("queued",   0),
        "sent":     by_status.get("sent",     0),
        "rejected": by_status.get("rejected", 0),
        "total":    sum(by_status.values()),
    }


# ---------------------------------------------------------------------------
# Builder — bolt.diy sidecar liveness probe (UI uses iframe directly)
# ---------------------------------------------------------------------------
@router.get("/builder/status")
async def builder_status(_: str = Depends(verify_token)):
    return {
        "service": "bolt.diy",
        "url": _BOLT_URL,
        "reachable": await _probe_url(_BOLT_URL),
        "boot_hint": "supervisorctl start bolt-engine",
    }


# ---------------------------------------------------------------------------
# Studio — OpenReel sidecar liveness probe
# ---------------------------------------------------------------------------
_STUDIO_URL = os.environ.get("STUDIO_URL", "http://localhost:5174")


@router.get("/studio/status")
async def studio_status(_: str = Depends(verify_token)):
    return {
        "service": "openreel",
        "url": _STUDIO_URL,
        "reachable": await _probe_url(_STUDIO_URL),
        "boot_hint": "supervisorctl start video-studio",
    }


@router.get("/storage/status")
async def storage_status(_: str = Depends(verify_token)):
    from services import asset_storage
    return asset_storage.status()
