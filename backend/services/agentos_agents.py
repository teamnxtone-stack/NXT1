"""AgentOS — Custom Agent (the heart of the dashboard).

A lightweight Claude-driven task runner that fills the role of OpenHands
in this environment (OpenHands SDK has dependency conflicts that prevent
clean install in our pod).

The loop:
  1. Receive a free-form task ("Research the top 10 VC firms...").
  2. Ask Claude to break it into steps.
  3. For each step, decide which tool to use (web search via DDG, then
     summarisation) and execute.
  4. Stream live logs + step updates to subscribers via agentos_runner.
  5. Produce a final markdown result.

This is intentionally narrow — no terminal/file-editor tools yet (those
require sandbox isolation). Web research + summarisation covers ~70%
of the user-asked examples ("research top tools", "summarise YC S25",
"find 20 potential customers").

For full OpenHands-grade tooling (terminal, file editor, code exec),
self-hosters can swap in real OpenHands by setting OPENHANDS_URL.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Dict, List

import requests

from services.agentos_runner import (
    push_step, push_log, register_agent,
)

logger = logging.getLogger("nxt1.agentos.custom")


# Self-host friendly defaults. Override either of these via env to point
# at your own proxy or to opt out of the Emergent universal-key transport.
_EMERGENT_BASE_DEFAULT = "https://integrations.emergentagent.com"
_AGENTOS_MODEL_DEFAULT = "claude-sonnet-4-5-20250929"


# ─── Tools ───────────────────────────────────────────────────────────────
async def _web_search(query: str, task_id: str, limit: int = 5) -> List[Dict]:
    """DuckDuckGo lite search — no API key required."""
    await push_log(task_id, f"  > Searching DuckDuckGo for: {query!r}")
    try:
        r = await asyncio.to_thread(
            requests.get,
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "NXT1-AgentOS/1.0"},
            timeout=15,
        )
        if r.status_code != 200:
            return []
        # Naive HTML scrape — fine for a lightweight research loop.
        results: List[Dict] = []
        for m in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>',
            r.text,
        ):
            url, title = m.group(1), m.group(2).strip()
            # DDG wraps redirect URLs; strip prefix
            if "uddg=" in url:
                m2 = re.search(r"uddg=([^&]+)", url)
                if m2:
                    from urllib.parse import unquote
                    url = unquote(m2.group(1))
            results.append({"title": title, "url": url})
            if len(results) >= limit:
                break
        await push_log(task_id, f"  > {len(results)} result(s)")
        return results
    except Exception as e:  # noqa: BLE001
        await push_log(task_id, f"  ! search failed: {e}", level="warn")
        return []


async def _fetch_page(url: str, task_id: str, max_chars: int = 6000) -> str:
    """Fetch + strip HTML to plain text (lightweight)."""
    try:
        r = await asyncio.to_thread(
            requests.get, url,
            headers={"User-Agent": "NXT1-AgentOS/1.0"},
            timeout=15,
        )
        if r.status_code != 200:
            return ""
        text = re.sub(r"<script[^>]*>.*?</script>", "", r.text, flags=re.S)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception:
        return ""


# ─── LLM ────────────────────────────────────────────────────────────────
async def _llm_call(prompt: str, system: str = "") -> str:
    """Universal Emergent key → Claude Sonnet 4.5 by default.

    Honours user-supplied ANTHROPIC_API_KEY if set; otherwise falls back
    to the Emergent universal-key transport. Self-hosters can override
    the proxy via env `EMERGENT_BASE_URL=https://your-proxy.example`.
    """
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    model = os.environ.get("AGENTOS_LLM_MODEL", _AGENTOS_MODEL_DEFAULT)
    api_key = anthropic_key or emergent_key
    if not api_key:
        return "(no LLM key configured — set ANTHROPIC_API_KEY or EMERGENT_LLM_KEY)"
    emergent_base = os.environ.get("EMERGENT_BASE_URL", _EMERGENT_BASE_DEFAULT)
    try:
        r = await asyncio.to_thread(
            requests.post,
            f"{emergent_base}/llm/v1/chat/completions"
            if not anthropic_key else "https://api.anthropic.com/v1/messages",
            headers=(
                {"Authorization": f"Bearer {api_key}",
                 "Content-Type":  "application/json"}
                if not anthropic_key else
                {"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"}
            ),
            json=(
                {"model": model,
                 "messages": [{"role": "system", "content": system},
                              {"role": "user",   "content": prompt}],
                 "max_tokens": 2000}
                if not anthropic_key else
                {"model": model,
                 "system": system,
                 "messages": [{"role": "user", "content": prompt}],
                 "max_tokens": 2000}
            ),
            timeout=60,
        )
        data = r.json()
        if anthropic_key:
            return (data.get("content") or [{}])[0].get("text", "")
        return ((data.get("choices") or [{}])[0].get("message") or {}).get(
            "content", ""
        ) or json.dumps(data)[:400]
    except Exception as e:  # noqa: BLE001
        return f"(LLM error: {e})"


# ─── Agent: custom (free-form research/task runner) ───────────────────
@register_agent("custom")
async def run_custom(task: Dict) -> Dict:
    payload = task.get("payload") or {}
    task_id = task["task_id"]
    user_prompt = (payload.get("prompt") or payload.get("title") or "").strip()
    if not user_prompt:
        raise ValueError("Custom agent: 'prompt' is required.")

    await push_step(task_id, "Breaking task into subtasks", status="running")
    plan = await _llm_call(
        prompt=(
            f"Task: {user_prompt}\n\n"
            "Break this into 3-5 concrete research steps. Output ONLY a numbered "
            "list, one step per line, no preamble."
        ),
        system=(
            "You are NXT1 AgentOS. Plan research tasks crisply. Each step "
            "must be a concrete, atomic web-research action."
        ),
    )
    steps = [s.strip(" 0123456789.-") for s in plan.splitlines() if s.strip()][:5]
    if not steps:
        steps = [f"Research: {user_prompt}"]
    await push_step(task_id, f"Plan: {len(steps)} step(s)", status="done",
                    detail="\n".join(steps))

    # Execute each step
    findings: List[Dict] = []
    for i, step in enumerate(steps, 1):
        await push_step(task_id, f"Step {i}/{len(steps)}: {step}",
                         status="running")
        results = await _web_search(step, task_id, limit=3)
        for res in results[:2]:
            page = await _fetch_page(res["url"], task_id, max_chars=4000)
            if page:
                findings.append({
                    "step":   step,
                    "title":  res["title"],
                    "url":    res["url"],
                    "excerpt": page[:1200],
                })
        await push_step(task_id, f"Step {i} complete", status="done",
                         detail=f"{len(results)} source(s) gathered")

    # Synthesize
    await push_step(task_id, "Synthesizing final answer", status="running")
    findings_text = "\n\n".join([
        f"### {f['title']}\nURL: {f['url']}\nStep: {f['step']}\n\n{f['excerpt']}"
        for f in findings
    ]) or "(no sources gathered — knowledge-only response)"
    final = await _llm_call(
        prompt=(
            f"Original task: {user_prompt}\n\n"
            f"Research findings:\n{findings_text}\n\n"
            "Write a polished, well-structured markdown report answering the original "
            "task. Use headings, bullets, citations like [1] referencing the URLs you used."
        ),
        system=(
            "You are NXT1 AgentOS. Produce concise, founder-grade reports. "
            "Cite sources inline. Never invent URLs."
        ),
    )
    await push_step(task_id, "Done", status="done")
    return {
        "report":   final,
        "findings": findings,
        "sources":  [f["url"] for f in findings],
    }


# ─── Agent: job_scout (JobSpy-backed) ────────────────────────────────
@register_agent("job_scout")
async def run_job_scout(task: Dict) -> Dict:
    payload = task.get("payload") or {}
    task_id = task["task_id"]
    titles = payload.get("titles") or ["Product Manager"]
    location = payload.get("location") or "Remote"
    sites = payload.get("sites") or ["linkedin", "indeed", "glassdoor", "zip_recruiter"]
    results_wanted = int(payload.get("results_wanted") or 20)

    await push_step(task_id, "Searching job boards", status="running",
                     detail=f"titles={titles}, location={location}, sites={sites}")
    try:
        from jobspy import scrape_jobs  # type: ignore
        await push_log(task_id, "› JobSpy: scraping...")
        df = await asyncio.to_thread(
            scrape_jobs,
            site_name=sites,
            search_term=titles[0] if isinstance(titles, list) else titles,
            location=location,
            results_wanted=results_wanted,
            hours_old=72,
        )
        jobs = []
        if df is not None and not df.empty:
            import math
            def _clean(v):
                """Strip pandas NaN / NaT / inf so Mongo + JSON encoders cope."""
                if v is None:
                    return None
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    return None
                # pandas Timestamp / NaT
                if hasattr(v, "isoformat"):
                    try:
                        return v.isoformat()
                    except Exception:
                        return str(v)
                return v
            for row in df.head(results_wanted).to_dict(orient="records"):
                jobs.append({
                    "platform":   _clean(row.get("site")),
                    "title":      _clean(row.get("title")),
                    "company":    _clean(row.get("company")),
                    "location":   _clean(row.get("location")),
                    "url":        _clean(row.get("job_url")),
                    "salary_min": _clean(row.get("min_amount")),
                    "salary_max": _clean(row.get("max_amount")),
                    "posted":     _clean(row.get("date_posted")) or "",
                    "description": (_clean(row.get("description")) or "")[:500],
                })
        await push_step(task_id, f"Found {len(jobs)} job(s)", status="done")
        return {"jobs": jobs, "count": len(jobs)}
    except Exception as e:  # noqa: BLE001
        await push_log(task_id, f"JobSpy error: {e}", level="error")
        raise


# ─── Agent: founders_scout (X + Reddit + GitHub) ──────────────────────
@register_agent("founders_scout")
async def run_founders_scout(task: Dict) -> Dict:
    payload = task.get("payload") or {}
    task_id = task["task_id"]
    keywords = payload.get("keywords") or [
        "looking for technical cofounder",
        "need a CTO",
        "seeking technical cofounder",
    ]
    leads: List[Dict] = []
    # Reddit (no auth required)
    for kw in keywords[:3]:
        await push_step(task_id, f"Reddit: {kw}", status="running")
        try:
            r = await asyncio.to_thread(
                requests.get,
                f"https://www.reddit.com/search.json?q={kw}&sort=new&limit=10",
                headers={"User-Agent": "NXT1-AgentOS/1.0"},
                timeout=15,
            )
            data = r.json()
            for child in (data.get("data") or {}).get("children") or []:
                p = child.get("data") or {}
                leads.append({
                    "platform": "reddit",
                    "author":   p.get("author"),
                    "title":    p.get("title"),
                    "url":      "https://reddit.com" + (p.get("permalink") or ""),
                    "subreddit": p.get("subreddit"),
                    "snippet":  (p.get("selftext") or "")[:300],
                    "keyword":  kw,
                })
            await push_step(task_id, f"Reddit: {kw}", status="done",
                             detail=f"{len(leads)} cumulative leads")
        except Exception as e:  # noqa: BLE001
            await push_log(task_id, f"Reddit error: {e}", level="warn")
    # GitHub (no auth = 60 req/hr)
    await push_step(task_id, "GitHub bio scan", status="running")
    try:
        r = await asyncio.to_thread(
            requests.get,
            "https://api.github.com/search/users",
            params={"q": "looking for cofounder in:bio", "per_page": 10},
            timeout=15,
        )
        for u in (r.json().get("items") or []):
            leads.append({
                "platform": "github",
                "author":   u.get("login"),
                "url":      u.get("html_url"),
                "snippet":  "GitHub user with cofounder signal in bio",
                "keyword":  "github bio scan",
            })
        await push_step(task_id, "GitHub bio scan", status="done")
    except Exception as e:  # noqa: BLE001
        await push_log(task_id, f"GitHub error: {e}", level="warn")
    return {"leads": leads, "count": len(leads)}


# ─── Agent: social_strategist (Postiz-bound content generator) ───────
@register_agent("social_strategist")
async def run_social_strategist(task: Dict) -> Dict:
    payload = task.get("payload") or {}
    task_id = task["task_id"]
    industry = payload.get("industry") or "AI / startups"
    tone     = payload.get("tone") or "founder"
    days     = int(payload.get("days") or 7)

    await push_step(task_id, "Generating content strategy", status="running")
    plan = await _llm_call(
        prompt=(
            f"Generate a {days}-day social media content plan for an {industry} "
            f"audience in a {tone} tone. For each day output JSON with keys: "
            "day, topic, caption, hashtags (array, 5-7), image_prompt, "
            "best_time (HH:MM). Output a JSON array, no preamble."
        ),
        system="You are NXT1's social content strategist. Output STRICT JSON only.",
    )
    await push_step(task_id, "Strategy ready", status="done", detail=plan[:400])

    # Try Postiz REST push if configured
    postiz_url = os.environ.get("POSTIZ_URL")
    postiz_key = os.environ.get("POSTIZ_API_KEY")
    pushed = 0
    if postiz_url and postiz_key:
        await push_step(task_id, "Pushing drafts to Postiz", status="running")
        try:
            items = json.loads(plan)
            for it in items[:days]:
                try:
                    await asyncio.to_thread(
                        requests.post,
                        f"{postiz_url}/api/posts",
                        headers={"Authorization": f"Bearer {postiz_key}",
                                 "Content-Type": "application/json"},
                        json={
                            "content":  it.get("caption"),
                            "hashtags": it.get("hashtags"),
                            "scheduled_at": it.get("best_time"),
                        },
                        timeout=10,
                    )
                    pushed += 1
                except Exception as e:  # noqa: BLE001
                    await push_log(task_id, f"Postiz push failed: {e}", level="warn")
            await push_step(task_id, f"Pushed {pushed} to Postiz", status="done")
        except Exception as e:  # noqa: BLE001
            await push_log(task_id, f"Plan parse failed: {e}", level="warn")
    else:
        await push_log(task_id, "Postiz not configured — drafts saved locally only.",
                       level="info")
    return {"plan": plan, "pushed_to_postiz": pushed}


# ─── Agent: resume_tailor (native ATS scoring + LLM tailoring) ──────────
_STOPWORDS = {
    "a","an","and","are","as","at","be","by","for","from","has","have","he",
    "in","is","it","its","of","on","or","such","that","the","their","then",
    "there","these","they","this","to","was","will","with","you","your",
    "we","our","i","my","me","us","but","if","not","do","does","did","so",
    "can","also","into","more","than","over","via","etc","using","use","used",
    "should","would","could","may","might","must","like","just","very","ever",
    "any","all","each","some","most","new","old","up","out","off","across",
    "while","when","where","what","who","how","why","whose","whom","been","were",
    "had","being","am","because","both","few","many","much","other","others",
    "no","yes","one","two","three","first","second","including","includes",
    "year","years","work","worked","working","role","roles","team","teams",
}
_SKILL_HINTS_RE = re.compile(
    r"\b("
    r"python|java|javascript|typescript|react|node|vue|angular|svelte|next\.?js|"
    r"django|flask|fastapi|spring|express|rails|laravel|"
    r"aws|gcp|azure|kubernetes|docker|terraform|ansible|jenkins|github actions|"
    r"sql|postgres(ql)?|mysql|mongodb|redis|elasticsearch|kafka|rabbitmq|"
    r"pytorch|tensorflow|keras|scikit-?learn|pandas|numpy|spark|hadoop|airflow|"
    r"figma|sketch|adobe|photoshop|illustrator|"
    r"agile|scrum|kanban|jira|confluence|"
    r"saas|b2b|b2c|api|rest|graphql|grpc|microservices|"
    r"machine learning|deep learning|nlp|llm|ai|ml|computer vision|"
    r"product management|product strategy|roadmap|stakeholder|kpi|okr"
    r")\b",
    re.IGNORECASE,
)


def _tokenize(text: str) -> List[str]:
    """Lowercase token list, stripped of stopwords & punctuation."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9+#.\- ]+", " ", text)
    toks = [t.strip(".-") for t in text.split() if t.strip(".-")]
    return [t for t in toks if len(t) > 2 and t not in _STOPWORDS]


def _keyword_extract(text: str, top_n: int = 30) -> List[str]:
    """Frequency + skill-hint extraction. No sklearn needed."""
    toks = _tokenize(text)
    freq: Dict[str, int] = {}
    for t in toks:
        freq[t] = freq.get(t, 0) + 1
    # Boost explicit skill hints
    for m in _SKILL_HINTS_RE.finditer(text or ""):
        kw = m.group(1).lower()
        freq[kw] = freq.get(kw, 0) + 5
    # Bigrams for multi-word phrases (e.g., "product manager")
    for i in range(len(toks) - 1):
        bg = f"{toks[i]} {toks[i+1]}"
        if all(len(p) > 2 for p in bg.split()):
            freq[bg] = freq.get(bg, 0) + 1
    ordered = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [kw for kw, _c in ordered[:top_n]]


def _cosine_score(a: str, b: str) -> float:
    """Pure-python cosine similarity on bag-of-words. Returns 0..1."""
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    from collections import Counter
    va, vb = Counter(ta), Counter(tb)
    common = set(va) & set(vb)
    dot = sum(va[t] * vb[t] for t in common)
    import math
    na = math.sqrt(sum(v * v for v in va.values()))
    nb = math.sqrt(sum(v * v for v in vb.values()))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


@register_agent("resume_tailor")
async def run_resume_tailor(task: Dict) -> Dict:
    payload = task.get("payload") or {}
    task_id = task["task_id"]
    resume_text = (payload.get("resume_text") or "").strip()
    jd_text     = (payload.get("job_description") or "").strip()
    job_title   = (payload.get("job_title") or "").strip() or "the role"
    if not resume_text:
        raise ValueError("Resume Tailor: 'resume_text' is required.")
    if not jd_text:
        raise ValueError("Resume Tailor: 'job_description' is required.")

    await push_step(task_id, "Extracting keywords from job description",
                     status="running")
    jd_keywords     = _keyword_extract(jd_text, top_n=30)
    resume_keywords = set(_keyword_extract(resume_text, top_n=80))
    matched = [k for k in jd_keywords if k in resume_keywords or
               any(part in resume_keywords for part in k.split())]
    missing = [k for k in jd_keywords if k not in matched]
    await push_step(task_id, "Keyword extraction complete", status="done",
                     detail=f"{len(jd_keywords)} JD keywords · {len(matched)} matched · {len(missing)} missing")

    await push_step(task_id, "Computing ATS similarity score", status="running")
    cos = _cosine_score(resume_text, jd_text)
    kw_coverage = len(matched) / max(1, len(jd_keywords))
    # Weighted: 60% keyword coverage, 40% cosine similarity → 0..100
    ats_score = round((0.6 * kw_coverage + 0.4 * cos) * 100, 1)
    await push_step(task_id, f"ATS score: {ats_score}/100", status="done",
                     detail=f"keyword coverage {round(kw_coverage*100)}% · cosine {round(cos*100)}%")

    await push_step(task_id, "Generating tailored resume", status="running")
    missing_str = ", ".join(missing[:15]) or "(none — strong baseline match)"
    tailored = await _llm_call(
        prompt=(
            f"You are tailoring a resume for **{job_title}**.\n\n"
            f"=== JOB DESCRIPTION ===\n{jd_text[:4000]}\n\n"
            f"=== CURRENT RESUME ===\n{resume_text[:6000]}\n\n"
            f"=== KEYWORDS MISSING FROM RESUME (from JD) ===\n{missing_str}\n\n"
            "Rewrite the resume in clean markdown to maximise ATS keyword density "
            "while staying TRUTHFUL — never invent experience the candidate doesn't have. "
            "Where their existing work plausibly relates to a missing keyword, surface that "
            "match in the bullet (e.g. if JD wants 'Kubernetes' and they list 'containers', "
            "expand to 'Kubernetes / Docker'). Keep tone professional, use action verbs, "
            "and preserve all dates, companies, and titles exactly. "
            "Output ONLY the rewritten resume in markdown — no preamble, no postscript."
        ),
        system=(
            "You are NXT1's Resume Tailor. Truthful, ATS-aware, founder-grade. "
            "Never fabricate experience. Output clean markdown only."
        ),
    )
    await push_step(task_id, "Tailored resume ready", status="done")

    await push_step(task_id, "Writing improvement suggestions", status="running")
    suggestions = await _llm_call(
        prompt=(
            f"Job: {job_title}\n"
            f"Missing JD keywords: {missing_str}\n"
            f"ATS score: {ats_score}/100\n\n"
            "Write 4-6 short, actionable bullets the candidate could do to genuinely "
            "raise this score (skills to learn, side projects to ship, certifications). "
            "Output as a markdown bullet list only."
        ),
        system="You are NXT1's career coach. Crisp, actionable bullets only.",
    )
    await push_step(task_id, "Done", status="done")

    return {
        "ats_score":       ats_score,
        "keyword_coverage": round(kw_coverage * 100, 1),
        "cosine_similarity": round(cos * 100, 1),
        "jd_keywords":     jd_keywords,
        "matched":         matched,
        "missing":         missing,
        "tailored_resume": tailored,
        "suggestions":     suggestions,
        "report":          (
            f"# Resume tailored for **{job_title}**\n\n"
            f"**ATS score:** {ats_score}/100  ·  Keyword coverage {round(kw_coverage*100)}%  ·  Cosine {round(cos*100)}%\n\n"
            f"## Tailored resume\n\n{tailored}\n\n"
            f"## Coach's suggestions\n\n{suggestions}\n\n"
            f"## Missing keywords ({len(missing)})\n\n"
            + (", ".join(missing[:20]) or "_none — strong baseline_")
        ),
    }
