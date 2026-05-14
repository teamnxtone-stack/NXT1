"""Migration assistant — turn an imported project into a reconnect plan.

Given the files of an imported repo, this service scans for known patterns
(env keys, SDK imports, config files) and emits a structured plan:

    {
        detected: [
            {kind, label, evidence: [file_paths], confidence, action},
            ...
        ],
        missing_env: ["MONGO_URL", "OPENAI_API_KEY", ...],
        provided_env: ["NEXT_PUBLIC_URL", ...],
        steps: [
            {id, title, status, kind, hint, action: {type, payload}},
            ...
        ],
    }

Status semantics on each step:
    "ok"       — already satisfied (env var set, db registered, repo pushed)
    "todo"     — actionable next step the user should run
    "info"     — informational, no action required
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional


# Known integration signatures.
# Each entry: (kind, label, patterns: [re], env_hints: [str], action_hint).
INTEGRATIONS = [
    ("mongodb", "MongoDB / Atlas",
        [r"\bmongo(?:db)?(?:client|\.connect|\+srv://|os\.environ\[\"MONGO)"],
        ["MONGO_URL", "MONGODB_URI", "DB_NAME"],
        "Provision MongoDB Atlas (/admin → Keys → MONGODB_ATLAS_PUBLIC_KEY) "
        "or connect an existing Mongo URL via Tools → Database."),
    ("postgres-neon", "Postgres (Neon-compatible)",
        [r"\bpsycopg2?\b|asyncpg|prisma\.|drizzle|kysely|\.neon\.tech|pg\.connect"],
        ["DATABASE_URL", "POSTGRES_URL", "PG_URL", "NEON_DATABASE_URL"],
        "Provision Neon Postgres in one click from Tools → Database → Provision."),
    ("supabase", "Supabase",
        [r"createClient.*supabase|supabase-js|supabase/auth-helpers|\.supabase\.co"],
        ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
         "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY"],
        "Provision Supabase from Tools → Database (needs SUPABASE_ACCESS_TOKEN "
        "in /admin → Keys)."),
    ("openai", "OpenAI",
        [r"openai\.com|from openai|import openai|new OpenAI\("],
        ["OPENAI_API_KEY", "OPENAI_ORG_ID"],
        "Paste your OpenAI key in /admin → Keys or use the Universal Emergent LLM key."),
    ("anthropic", "Anthropic (Claude)",
        [r"anthropic|claude-3|claude-sonnet|claude-opus|@anthropic-ai"],
        ["ANTHROPIC_API_KEY"],
        "Paste your Anthropic key in /admin → Keys."),
    ("gemini", "Google Gemini",
        [r"gemini|google-generativeai|@google/generative-ai"],
        ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "Paste your Gemini key in /admin → Keys."),
    ("stripe", "Stripe",
        [r"\bstripe\b|@stripe/stripe-js|@stripe/react-stripe-js|stripe\.checkout"],
        ["STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "STRIPE_WEBHOOK_SECRET"],
        "Paste your Stripe live/test keys in /admin → Keys (or this project's Env Vars)."),
    ("r2", "Cloudflare R2 / S3",
        [r"\bs3Client|aws-sdk|@aws-sdk/client-s3|r2\.cloudflarestorage\.com"],
        ["R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ACCOUNT_ID", "R2_BUCKET",
         "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "S3_BUCKET"],
        "Add R2 credentials in /admin → Keys (NXT1 already supports R2 as the "
        "default asset backend)."),
    ("vercel", "Vercel",
        [r"vercel\.json|@vercel/|vercel\.app"],
        ["VERCEL_TOKEN"],
        "Connect your Vercel token in /admin → Keys to enable one-click deploys."),
    ("cloudflare-pages", "Cloudflare Pages / Workers",
        [r"wrangler|cloudflare\.com/workers|@cloudflare/workers-types"],
        ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"],
        "Add Cloudflare token in /admin → Keys; Workers deploys are supported."),
    ("github", "GitHub",
        [r"\.github/workflows|github\.com/|GITHUB_TOKEN"],
        ["GITHUB_TOKEN"],
        "GitHub PAT in /admin → Keys lets NXT1 push/sync back to the source repo."),
    ("supabase-storage", "Supabase Storage",
        [r"\.storage\.from\(|supabase\.storage"],
        [], "Storage routed via Supabase — make sure the storage bucket exists."),
    ("resend", "Resend (email)",
        [r"resend\.|@resend/|resend-node"],
        ["RESEND_API_KEY"], "Add RESEND_API_KEY in /admin → Keys."),
    ("twilio", "Twilio",
        [r"twilio"], ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"],
        "Add Twilio creds in /admin → Keys."),
    ("clerk", "Clerk Auth",
        [r"@clerk/|ClerkProvider"],
        ["CLERK_SECRET_KEY", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"],
        "Add Clerk keys via project Env Vars."),
]

# Env-var name patterns we should pull out of files even if we don't recognise
# the SDK. Helps catch user-defined keys.
ENV_REF_RX = re.compile(r"""(?ix)
    (?:process\.env\.|os\.environ(?:\.get)?\(|os\.getenv\()
    (?:["']?)([A-Z][A-Z0-9_]{2,})
""")


def _scan_files(files: List[dict]) -> List[dict]:
    """Return one dict per file with its lowered content + path for matching."""
    out = []
    for f in files:
        path = f.get("path", "")
        content = f.get("content") or ""
        # Skip enormous files (e.g., bundled JS) — they slow scan + are noisy.
        if len(content) > 200_000:
            content = content[:200_000]
        out.append({"path": path, "content": content})
    return out


def _detect_integrations(scanned: List[dict]) -> List[dict]:
    results: List[dict] = []
    for kind, label, patterns, env_hints, action in INTEGRATIONS:
        evidence: List[str] = []
        for f in scanned:
            text = f["content"]
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
                    evidence.append(f["path"])
                    break
        if not evidence:
            continue
        results.append({
            "kind": kind,
            "label": label,
            "evidence": evidence[:6],          # cap so the response stays small
            "evidence_count": len(evidence),
            "confidence": "high" if len(evidence) >= 3 else "medium" if len(evidence) >= 2 else "low",
            "env_hints": env_hints,
            "action": action,
        })
    return results


def _collect_env_refs(scanned: List[dict]) -> List[str]:
    seen: Dict[str, int] = {}
    for f in scanned:
        for m in ENV_REF_RX.finditer(f["content"]):
            k = m.group(1)
            if not re.match(r"^[A-Z][A-Z0-9_]+$", k):
                continue
            if len(k) > 64:
                continue
            seen[k] = seen.get(k, 0) + 1
    # Filter framework-emitted constants that aren't user envs
    skip = {"NODE_ENV", "VERCEL_ENV", "VERCEL_URL", "NEXT_RUNTIME",
            "PATH", "PYTHONPATH", "PYTHONUNBUFFERED", "PORT", "HOME",
            "USER", "TZ", "LANG", "LC_ALL"}
    out = [k for k in seen.keys() if k not in skip]
    out.sort()
    return out


def build_plan(files: List[dict], project: dict, providers_status: Optional[dict] = None) -> dict:
    """Produce a reconnect plan for an imported project."""
    scanned = _scan_files(files)
    detected = _detect_integrations(scanned)
    env_refs = _collect_env_refs(scanned)

    provided_env = {
        ev.get("key") for ev in (project.get("env_vars") or [])
        if ev.get("key") and ev.get("value")
    }

    # Required env = union of referenced keys + integration hints (deduped)
    required: List[str] = list(env_refs)
    for d in detected:
        for h in d.get("env_hints") or []:
            if h not in required:
                required.append(h)
    missing_env = [k for k in required if k not in provided_env]

    # Build the step list — ordered: infrastructure → integrations → env → deploy
    steps: List[dict] = []

    # 1) GitHub
    gh = project.get("github") or {}
    steps.append({
        "id": "github",
        "title": "GitHub source of truth",
        "kind": "infra",
        "status": "ok" if gh.get("repo_url") else "todo",
        "hint": (
            f"Synced to {gh.get('repo_url')}"
            if gh.get("repo_url")
            else "Push this project to GitHub to lock in the source of truth."
        ),
        "action": {"type": "save_github"} if not gh.get("repo_url") else None,
    })

    # 2) Database — show only if detected
    db_kinds = [d["kind"] for d in detected if d["kind"] in ("mongodb", "postgres-neon", "supabase")]
    if db_kinds:
        registered = bool(project.get("databases"))
        steps.append({
            "id": "database",
            "title": "Database",
            "kind": "infra",
            "status": "ok" if registered else "todo",
            "hint": (
                f"{', '.join(sorted({k.upper() for k in db_kinds}))} detected. "
                + ("Already registered — verify connection in Tools → Database."
                   if registered
                   else "Provision a new DB or connect your existing URL.")
            ),
            "action": {"type": "open_panel", "panel": "database"},
        })

    # 3) Deploy provider
    provider = "vercel" if any(d["kind"] == "vercel" for d in detected) else None
    if not provider:
        provider = "cloudflare-pages" if any(d["kind"] == "cloudflare-pages" for d in detected) else None
    if provider:
        deploys = project.get("deployments") or []
        last_provider = next((d.get("provider") for d in reversed(deploys)
                              if d.get("status") == "deployed"), None)
        steps.append({
            "id": "deploy",
            "title": "Deploy provider",
            "kind": "infra",
            "status": "ok" if last_provider == provider else "todo",
            "hint": f"Detected {provider}. " + (
                f"Last deploy used {last_provider}."
                if last_provider
                else "Click below to deploy this build."
            ),
            "action": {"type": "deploy", "provider": provider},
        })

    # 4) Missing env vars
    if missing_env:
        steps.append({
            "id": "env",
            "title": f"Set {len(missing_env)} env var(s)",
            "kind": "config",
            "status": "todo",
            "hint": (
                "These keys are referenced in code but not set on this project. "
                "Open Tools → Env Vars to add them."
            ),
            "action": {"type": "open_panel", "panel": "env",
                       "payload": {"keys": missing_env}},
            "keys": missing_env[:30],
        })

    # 5) Per-integration reconnect hints
    for d in detected:
        miss = [k for k in (d.get("env_hints") or []) if k not in provided_env]
        if miss:
            steps.append({
                "id": f"int:{d['kind']}",
                "title": d["label"],
                "kind": "integration",
                "status": "todo",
                "hint": d.get("action") or "Reconnect this integration.",
                "missing": miss,
            })

    return {
        "detected": detected,
        "missing_env": missing_env,
        "provided_env": sorted(provided_env),
        "env_refs": env_refs,
        "steps": steps,
        "providers_status": providers_status,
    }
