"""Provider-based AI service for NXT1 with streaming + auto-retry."""
import os
import re
import json
import logging
import uuid
from typing import AsyncIterator, Awaitable, Callable, List, Optional, Tuple

import litellm

# emergentintegrations was a proprietary helper that isn't on PyPI — deploys
# to Render/Vercel/anywhere else fail with "No matching distribution found for
# emergentintegrations==0.1.0". We replaced it with a thin litellm-backed
# helper (`_acomplete`) below. Public API + behaviour are preserved.


def _emergent_proxy_url() -> str:
    """Return the Emergent integration proxy URL (with /llm suffix)."""
    proxy = (
        os.environ.get("INTEGRATION_PROXY_URL")
        or os.environ.get("integration_proxy_url")
        or "https://integrations.emergentagent.com"
    )
    return proxy.rstrip("/") + "/llm"


def _build_litellm_kwargs(
    *,
    provider: str,
    model: str,
    api_key: str,
    messages: list,
    max_tokens: int,
    stream: bool,
    response_format: Optional[dict] = None,
) -> dict:
    """Build litellm kwargs, routing through Emergent proxy when api_key is universal.

    This mirrors what `emergentintegrations.llm.chat.LlmChat` does so the same
    `sk-emergent-*` key works without needing the proprietary helper.
    """
    is_emergent = bool(api_key) and api_key.startswith("sk-emergent-")
    kwargs: dict = {
        "messages":   messages,
        "max_tokens": max_tokens,
        "stream":     stream,
        "api_key":    api_key,
    }
    if is_emergent:
        # Emergent proxy is OpenAI-compatible; pass bare model name.
        # Gemini is the one exception — keep the "gemini/" prefix.
        kwargs["api_base"] = _emergent_proxy_url()
        kwargs["custom_llm_provider"] = "openai"
        if provider == "gemini":
            kwargs["model"] = f"gemini/{model}"
        else:
            kwargs["model"] = model
        # Identify the calling app so the proxy can attribute usage correctly.
        app_id = os.environ.get("APP_URL") or os.environ.get("REACT_APP_BACKEND_URL")
        if app_id:
            kwargs["extra_headers"] = {"X-App-ID": app_id}
    else:
        kwargs["model"] = f"{provider}/{model}"
    if response_format:
        kwargs["response_format"] = response_format
    return kwargs


async def _acomplete(
    *,
    provider: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 12000,
    response_format: Optional[dict] = None,
) -> str:
    """Non-streaming chat completion via litellm. Returns the text body."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
    kwargs = _build_litellm_kwargs(
        provider=provider, model=model, api_key=api_key,
        messages=messages, max_tokens=max_tokens, stream=False,
        response_format=response_format,
    )
    resp = await litellm.acompletion(**kwargs)
    return resp["choices"][0]["message"]["content"] or ""

# Re-export the JSON parsing pipeline + error class from services.parsers.
# Historically these lived inline here (~325 lines of progressive recovery
# logic). They were extracted to keep this file focused on provider routing
# + streaming. Existing imports (`from services.ai_service import
# AIProviderError, parse_ai_response`) keep working unchanged.
from services.parsers import AIProviderError, parse_ai_response  # noqa: F401

logger = logging.getLogger("nxt1.ai")


class BaseAIProvider:
    name: str = "base"
    model: str = ""

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        raise NotImplementedError

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str) -> AsyncIterator[str]:
        raise NotImplementedError


def _litellm_params(provider: str, model: str, api_key: str, system: str, user: str) -> dict:
    return {
        "model": f"{provider}/{model}",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "api_key": api_key,
    }


class OpenAIProvider(BaseAIProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4.1"):
        if not api_key:
            raise AIProviderError("OPENAI_API_KEY missing")
        self.api_key = api_key
        self.model = model

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        return await _acomplete(
            provider="openai",
            model=self.model,
            api_key=self.api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=32000,
            response_format={"type": "json_object"},
        )

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]
        kwargs = _build_litellm_kwargs(
            provider="openai", model=self.model, api_key=self.api_key,
            messages=messages, max_tokens=32000, stream=True,
            response_format={"type": "json_object"},
        )
        response = litellm.completion(**kwargs)
        for chunk in response:
            try:
                delta = chunk.choices[0].delta.content or ""
            except Exception:
                delta = ""
            if delta:
                yield delta


class AnthropicProvider(BaseAIProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        if not api_key:
            raise AIProviderError("ANTHROPIC_API_KEY missing")
        self.api_key = api_key
        self.model = model

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        return await _acomplete(
            provider="anthropic",
            model=self.model,
            api_key=self.api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]
        kwargs = _build_litellm_kwargs(
            provider="anthropic", model=self.model, api_key=self.api_key,
            messages=messages, max_tokens=12000, stream=True,
        )
        response = litellm.completion(**kwargs)
        for chunk in response:
            try:
                delta = chunk.choices[0].delta.content or ""
            except Exception:
                delta = ""
            if delta:
                yield delta


class EmergentProvider(BaseAIProvider):
    name = "emergent"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        if not api_key:
            raise AIProviderError("EMERGENT_LLM_KEY missing")
        self.api_key = api_key
        self.model = model

    def _target_provider(self) -> str:
        if self.model.startswith("gpt") or self.model.startswith("o"):
            return "openai"
        if self.model.startswith("gemini"):
            return "gemini"
        return "anthropic"

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        return await _acomplete(
            provider=self._target_provider(),
            model=self.model,
            api_key=self.api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        # Emergent proxy supports streaming via its OpenAI-compatible endpoint.
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]
        kwargs = _build_litellm_kwargs(
            provider=self._target_provider(), model=self.model, api_key=self.api_key,
            messages=messages, max_tokens=12000, stream=True,
        )
        try:
            response = litellm.completion(**kwargs)
            for chunk in response:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    yield delta
        except Exception as e:
            # If streaming fails, fall back to non-stream so the build doesn't die
            logger.warning(f"emergent streaming failed, falling back to non-stream: {e}")
            text = await self.generate(system_prompt, user_prompt, session_id)
            if text:
                yield text


class GroqProvider(BaseAIProvider):
    """Groq — extremely fast inference, ideal for narration / fast routing.
    Default model: llama-3.3-70b-versatile (good quality + speed)."""
    name = "groq"

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        if not api_key:
            raise AIProviderError("GROQ_API_KEY missing")
        self.api_key = api_key
        self.model = model

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        params = _litellm_params("groq", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 8000, "response_format": {"type": "json_object"}})
        resp = litellm.completion(**params)
        return resp.choices[0].message.content or ""

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        params = _litellm_params("groq", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 8000, "response_format": {"type": "json_object"}, "stream": True})
        response = litellm.completion(**params)
        for chunk in response:
            try:
                delta = chunk.choices[0].delta.content or ""
            except Exception:
                delta = ""
            if delta:
                yield delta


class OpenRouterProvider(BaseAIProvider):
    """OpenRouter — fallback aggregator. Default model: anthropic/claude-3.5-sonnet
    via OpenRouter (works without burning the direct Anthropic quota)."""
    name = "openrouter"

    def __init__(self, api_key: str, model: str = "anthropic/claude-3.5-sonnet"):
        if not api_key:
            raise AIProviderError("OPENROUTER_API_KEY missing")
        self.api_key = api_key
        self.model = model

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        params = _litellm_params("openrouter", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 16000})
        resp = litellm.completion(**params)
        return resp.choices[0].message.content or ""

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        params = _litellm_params("openrouter", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 16000, "stream": True})
        response = litellm.completion(**params)
        for chunk in response:
            try:
                delta = chunk.choices[0].delta.content or ""
            except Exception:
                delta = ""
            if delta:
                yield delta


# ---------- Provider selection (delegated to providers.registry) ----------
# The legacy BaseAIProvider/OpenAIProvider/etc. classes above remain for any
# code that still imports them directly (e.g. older agent modules). New code
# should use `services.providers.registry` and `RouteIntent` instead.
from services.providers import registry as _provider_registry_singleton
from services.providers.base import (  # noqa: F401  (re-exports)
    ProviderError,
    ProviderUnavailable,
    ProviderTimeout,
    ProviderRateLimit,
    ProviderAuthError,
    ProviderBadResponse,
    LatencyTier,
    RouteIntent,
    BaseProvider as _NewBaseProvider,
)


def get_active_provider(preferred: Optional[str] = None) -> "_NewBaseProvider":
    """Resolve a provider via the new registry. Honours an explicit provider id
    if it is configured; otherwise falls back to the auto-routing chain.

    Returns a new-style BaseProvider (from services.providers). All adapters
    expose the same `generate` / `generate_stream` shape as the legacy ones,
    so callers don't need to change.
    """
    requested = (preferred or os.environ.get("AI_PROVIDER", "auto")).lower().strip()
    intent = RouteIntent(
        routing_mode="manual" if requested and requested != "auto" else "auto",
        explicit_provider=requested if (requested and requested != "auto") else None,
    )
    try:
        return _provider_registry_singleton.resolve(intent)
    except ProviderUnavailable as e:
        raise AIProviderError(str(e))


def get_provider_for_task(task: Optional[str], explicit: Optional[str] = None) -> "_NewBaseProvider":
    """Pick the best provider for a task category via the registry.
    Honours explicit override; otherwise routes by task.
    """
    intent = RouteIntent(
        routing_mode="manual" if explicit else "auto",
        explicit_provider=explicit,
        task=(task or None),
    )
    try:
        return _provider_registry_singleton.resolve(intent)
    except ProviderUnavailable as e:
        raise AIProviderError(str(e))


def list_provider_status() -> dict:
    """Legacy shape: { provider_id: bool, ..., preferred }.
    Augmented with new specs/health data under `_registry` for callers that
    want richer info.
    """
    avail = set(_provider_registry_singleton.available())
    out = {
        "openai":     "openai" in avail,
        "anthropic":  "anthropic" in avail,
        "gemini":     "gemini" in avail,
        "xai":        "xai" in avail,
        "groq":       "groq" in avail,
        "deepseek":   "deepseek" in avail,
        "openrouter": "openrouter" in avail,
        "emergent":   "emergent" in avail,
        "preferred":  os.environ.get("AI_PROVIDER", "auto"),
    }
    # Attach richer registry info for new consumers (UI / introspection).
    out["_registry"] = _provider_registry_singleton.health_status()
    return out


def list_provider_specs() -> list:
    """Public helper for the /api/ai/providers endpoint.

    Augments each spec with live `available` (have the required env vars
    been set in the current process?) and `health` (recent error window)
    so the UI can colour the picker accordingly.
    """
    reg = _provider_registry_singleton
    avail = set(reg.available())
    out = []
    for s in reg.list_specs():
        d = s.to_dict()
        d["available"] = s.id in avail
        d["configured"] = s.id in avail  # alias commonly read by UI
        out.append(d)
    return out


def provider_health() -> dict:
    """Health status for ops dashboards."""
    return _provider_registry_singleton.health_status()


# ---------- System prompt ----------
SYSTEM_PROMPT = """You are NXT1, an elite AI app and website builder. You generate REAL, production-quality, multi-file projects from natural-language prompts.

OUTPUT CONTRACT
You MUST respond with a single JSON object and nothing else. No prose outside JSON. No markdown fences. The schema is:
{
  "files": [
    { "path": "<relative path>", "content": "<full file contents>" }
  ],
  "explanation": "<2-3 sentence summary of what changed or was built>",
  "notes": "<optional: dependencies, env vars, follow-ups>"
}

PROJECT STRUCTURE
- Always include `index.html` (the entry page).
- For multi-page websites use additional HTML files (e.g. `about.html`, `pricing.html`, `contact.html`). Reference them via standard `<a href="about.html">`.
- CSS files MUST be referenced via `<link rel="stylesheet" href="<path>">`. Group styles into `styles/main.css` (and additional files if useful).
- JS files MUST be referenced via `<script src="<path>"></script>`. Group scripts under `scripts/`.
- Components / partials go under `components/`.
- Images & uploaded assets are referenced as `assets/<filename>`.
- For backend / API requests, scaffold a `backend/` folder (e.g. `backend/server.py`, `backend/requirements.txt`); the sandbox preview will not execute them, but the user will export them.

QUALITY BAR (extremely important)
- Every output must look like a polished, modern, production-grade product.
- Confident typography, generous spacing, distinctive palette, smooth transitions.
- Real, contextual copy (no Lorem Ipsum).
- Fully responsive (mobile, tablet, desktop) using flex/grid, clamp(), media queries.
- Micro-interactions: hover states, focus rings, transitions.
- Use only inline assets, the user's uploaded `assets/`, or system fonts. NO external CDNs/frameworks unless the user asks.
- Inline SVG icons (sharp, 1.5px stroke) instead of icon fonts.

VARIETY RULE — refuse to repeat the same template (CRITICAL)
- DO NOT default to the same hero pattern every build. Mix it up across builds:
  * left-text / right-text / centered / split-screen / full-image / video-bg / asymmetric
  * single-column long-scroll vs side-rail navigation vs anchor-tab pages
  * grid card galleries vs masonry vs horizontal scroll vs stacked feature blocks
- DO NOT default to the same palette every build. Vary the aesthetic per request:
  * editorial-print (cream / serif), neo-brutalist (high-contrast), glass / aurora,
    monochrome graphite, terminal-green, sunset-coral, midnight-electric, etc.
- Read the user's brief and let the *domain* drive the look: a finance dashboard,
  a coffee shop, a gallery, and a SaaS landing should each feel materially different.
- Generic "dark gradient hero with three feature cards and a CTA at the bottom" is
  the FAILURE MODE — only use it when the user explicitly asks for SaaS-marketing.

QUALITY BAR (continued)
- Prefer dark, cinematic, premium aesthetics by default — but switch tone if the
  user's domain calls for a different mood (e.g. wedding, gallery, kids' app, fintech).

EDITING BEHAVIOR
- When the user asks for a change, output the COMPLETE updated set of files.
- Preserve files that were not changed (re-emit them unchanged).
- If the user reports an error, debug it.
- If asked to add a page/component/API, add it as new files; update navigation.
- If asked for a backend, create files under `backend/`.

PRECISION RULE — surgical edits only (CRITICAL for imported/existing projects)
This is the single most important rule when editing an existing or imported
project. NXT1 users frequently say "just change the navbar color" or "fix the
spacing on the hero" — and they expect EVERYTHING ELSE to be untouched.

- When the user asks for a single specific change (e.g. "change the hero
  title", "add a contact form", "fix the navbar color"), ONLY modify the
  file(s) directly related to that change.
- DO NOT rewrite unrelated files. DO NOT redesign sections the user didn't
  mention. DO NOT remove features. DO NOT change routing/layout/styles
  unless explicitly asked.
- DO NOT reformat code, reorder imports, rename variables, or change
  indentation in files unrelated to the requested change.
- NEVER touch these without an explicit request from the user:
    * `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`
    * `vite.config.*`, `next.config.*`, `astro.config.*`, `nuxt.config.*`,
      `tailwind.config.*`, `postcss.config.*`, `craco.config.*`
    * `tsconfig.json`, `jsconfig.json`, `.eslintrc*`, `.prettierrc*`
    * `.env`, `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`
    * `vercel.json`, `netlify.toml`, `render.yaml`, `wrangler.toml`
    * Anything under `public/`, `static/`, `dist/`, `build/`, `.next/`
    * `README.md` unless the user asks for doc changes
- For imported repos, NEVER move files between `frontend/` and `backend/`,
  NEVER rename directories, NEVER reformat the entire codebase, NEVER
  collapse/refactor unless explicitly asked.
- If a change would touch >5 files, prefer to make smaller follow-up changes
  in separate turns.
- If you're unsure whether a change is "in scope", err on the side of the
  smallest change that satisfies the request.
- Always include a `README.md` only if creating it for the first time on a
  blank project; on imported projects, leave it alone unless asked.

ABSOLUTE RULES
- Output VALID JSON only. No code fences, no commentary outside JSON.
- Do not invent external APIs. Do not ship broken code.
- Every HTML page must `<link>` to the right CSS and `<script>` to the right JS.
"""

RETRY_REINFORCEMENT = (
    "\n\nCRITICAL: Your previous response could not be parsed as valid JSON. "
    "Return ONLY a single JSON object matching the schema. No code fences. "
    "No commentary outside the JSON. Ensure the JSON is COMPLETE and properly closed."
)


# ---------- Precision-editing guardrails ----------
# These paths are NEVER modified unless the user's prompt explicitly mentions
# them. The merge step below restores original content for any protected path
# the AI tried to change but the user didn't ask about.
_PROTECTED_GLOBS = (
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "requirements.txt",
    "Gemfile.lock",
    "vite.config.js", "vite.config.ts", "vite.config.mjs",
    "next.config.js", "next.config.mjs", "next.config.ts",
    "nuxt.config.js", "nuxt.config.ts",
    "astro.config.mjs", "astro.config.js", "astro.config.ts",
    "tailwind.config.js", "tailwind.config.ts",
    "postcss.config.js", "postcss.config.cjs",
    "craco.config.js", "craco.config.ts",
    "tsconfig.json", "jsconfig.json",
    ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.cjs",
    ".prettierrc", ".prettierrc.json", ".prettierrc.js",
    ".gitignore", ".gitattributes",
    ".env", ".env.local", ".env.development", ".env.production",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "vercel.json", "netlify.toml", "render.yaml", "wrangler.toml",
    "Procfile", "Makefile",
)
# Prefix matches — any file under these directories is protected
_PROTECTED_PREFIXES = (
    "public/", "static/",
    "dist/", "build/", ".next/", ".output/", ".svelte-kit/",
    "node_modules/", ".git/", ".cache/",
)


def _is_protected(path: str) -> bool:
    """Decide whether a path is in the no-touch set."""
    if not path:
        return False
    p = path.replace("\\", "/").lower()
    # Glob (exact filename match — anywhere in tree)
    base = p.rsplit("/", 1)[-1]
    if base in {g.lower() for g in _PROTECTED_GLOBS}:
        return True
    # Or full path match (some configs are at root only)
    if p in {g.lower() for g in _PROTECTED_GLOBS}:
        return True
    # Prefix
    for pre in _PROTECTED_PREFIXES:
        if p.startswith(pre) or f"/{pre}" in f"/{p}":
            return True
    return False


def _user_mentioned_path(user_message: str, path: str) -> bool:
    """Return True if the user explicitly mentioned this path in their prompt.
    Matches on full path, filename, and basename-without-extension."""
    if not user_message or not path:
        return False
    msg = user_message.lower()
    p = path.lower()
    base = p.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0]
    return p in msg or base in msg or (len(stem) >= 4 and stem in msg)


def merge_with_protection(
    current_files: List[dict],
    new_files: List[dict],
    user_message: str = "",
    is_imported_project: bool = False,
) -> Tuple[List[dict], List[str]]:
    """Apply precision-editing guardrails to an AI's output.

    For imported projects (and large existing projects in general), the AI
    might "helpfully" rewrite package.json, configs, lockfiles, or move things
    around. This merger restores the original content for any protected path
    the AI tried to change UNLESS the user explicitly mentioned that path.

    Returns (merged_files, reverted_paths) so the caller can surface which
    files were reverted.
    """
    if not new_files:
        return new_files, []
    current_map = {f["path"]: (f.get("content") or "") for f in current_files or []}
    reverted: List[str] = []
    merged: List[dict] = []
    for f in new_files:
        path = f["path"]
        new_content = f.get("content") or ""
        original = current_map.get(path)
        # If a protected path was changed and the user didn't mention it, revert
        if (
            is_imported_project
            and original is not None
            and original != new_content
            and _is_protected(path)
            and not _user_mentioned_path(user_message, path)
        ):
            merged.append({"path": path, "content": original})
            reverted.append(path)
        else:
            merged.append(f)
    # Preserve protected files the AI omitted entirely (e.g. removed package.json)
    out_paths = {m["path"] for m in merged}
    for path, content in current_map.items():
        if path in out_paths:
            continue
        if (
            is_imported_project
            and _is_protected(path)
            and not _user_mentioned_path(user_message, path)
        ):
            merged.append({"path": path, "content": content})
            reverted.append(path)
    return merged, reverted


def is_imported_project(project_doc: dict) -> bool:
    """Heuristic: a project is 'imported' if it has an analysis blob (ZIP/GitHub
    import populated it) or the kind is anything other than blank-start."""
    if not project_doc:
        return False
    analysis = project_doc.get("analysis") or {}
    if not analysis:
        return False
    kind = (analysis.get("preview_info") or {}).get("kind")
    if kind in {"spa-built", "spa-source", "nextjs", "fastapi"}:
        return True
    # Or has a github source pointer (imported from a repo)
    gh = project_doc.get("github") or {}
    if gh.get("source_owner") or gh.get("source_repo_url"):
        return True
    # Or has many files (>30) with mix of frameworks (imported real project)
    if len(project_doc.get("files") or []) > 30:
        return True
    return False


def _select_relevant_files(files: List[dict], user_message: str, max_full: int = 12,
                            max_chars_per_file: int = 8000) -> Tuple[List[dict], List[str]]:
    """Token-saving selection: rank files by simple heuristics against the user
    message and only include the top N with full content; the rest go in as a
    path-only manifest. Heuristics:
      - phrase/term overlap with user message
      - frequently-edited files (index.html, package.json, server.py)
      - files in subdirs the message mentions
    """
    if not files:
        return [], []
    msg = (user_message or "").lower()
    msg_terms = set(re.findall(r"[a-z0-9_]{3,}", msg))
    PRIORITY_PATHS = {"index.html", "package.json", "backend/server.py", "backend/server.js",
                      "src/App.jsx", "src/index.js", "README.md"}

    def score(f: dict) -> float:
        s = 0.0
        path_l = f["path"].lower()
        # Path mention
        if any(t in path_l for t in msg_terms):
            s += 5
        # Priority files always boosted
        if f["path"] in PRIORITY_PATHS:
            s += 3
        # File-content term overlap (cheap)
        c = (f.get("content") or "").lower()
        for t in msg_terms:
            if t in c:
                s += 0.05
        # Slight preference for smaller files (less noise)
        size = len(c) or 1
        s += max(0, 1 - (size / 50000))
        return s

    ranked = sorted(files, key=score, reverse=True)
    top = ranked[:max_full]
    rest_paths = [f["path"] for f in ranked[max_full:]]
    # Truncate the top files
    truncated = []
    for f in top:
        c = f.get("content") or ""
        if len(c) > max_chars_per_file:
            c = c[:max_chars_per_file] + "\n/* ... truncated for prompt ... */"
        truncated.append({"path": f["path"], "content": c})
    return truncated, rest_paths


def build_prompt(
    user_message: str,
    current_files: List[dict],
    history: List[dict],
    runtime_ctx: Optional[dict] = None,
) -> str:
    selected, rest_paths = _select_relevant_files(current_files, user_message)
    files_blob_parts = []
    for f in selected:
        files_blob_parts.append(f"=== {f['path']} ===\n{f['content']}")
    files_blob = "\n\n".join(files_blob_parts) or "(no files yet)"
    if rest_paths:
        files_blob += "\n\n=== OTHER FILES IN THE PROJECT (paths only — request specific files in your response if you need to edit them) ===\n" + "\n".join(f"  - {p}" for p in rest_paths)

    history_blob = ""
    for m in (history or [])[-8:]:
        c = m.get("content", "")
        if len(c) > 600:
            c = c[:600] + "…"
        history_blob += f"\n[{m.get('role')}]: {c}"
    history_blob = history_blob or "(none)"

    runtime_blob = ""
    if runtime_ctx:
        eps = runtime_ctx.get("endpoints") or []
        env_keys = runtime_ctx.get("env_keys") or []
        proxy = runtime_ctx.get("proxy_url") or ""
        deployed_url = runtime_ctx.get("deployed_url") or ""
        runtime_blob = "\n\nRUNTIME CONTEXT (use these when wiring frontend ↔ backend):"
        if proxy:
            runtime_blob += f"\n- Backend proxy URL (frontend should fetch this): {proxy}"
        if eps:
            ep_lines = "\n".join(f"  - {e.get('method', 'GET')} {e.get('path')}" for e in eps)
            runtime_blob += f"\n- Available API routes:\n{ep_lines}"
        if env_keys:
            runtime_blob += f"\n- Backend env vars (already injected): {', '.join(env_keys)}"
        if deployed_url:
            runtime_blob += f"\n- Live deployed URL: {deployed_url}"

    return f"""CURRENT PROJECT FILES:
{files_blob}

RECENT CONVERSATION:
{history_blob}{runtime_blob}

USER REQUEST:
{user_message}

Output the complete updated file set as JSON per the schema. Premium quality. Multi-file structure. Responsive. No external CDNs unless requested. When the project has a backend runtime, frontend fetch() calls MUST target the proxy URL above (not relative paths) so the preview can reach the running backend."""


def _validate_files(files: list, current_files: Optional[list] = None) -> list:
    """Validate and normalise AI-returned files.

    Bug fix iter4 #3: on incremental edits ("Add a footer"), the LLM
    sometimes returns ONLY the changed files. If the project already has
    a valid entry point in current_files, we no longer require the AI
    response to repeat it.
    """
    if not isinstance(files, list) or not files:
        raise AIProviderError("AI returned no files")
    clean = []
    for f in files:
        if not isinstance(f, dict):
            continue
        path = str(f.get("path", "")).strip().lstrip("/")
        content = str(f.get("content", ""))
        if path:
            clean.append({"path": path, "content": content})
    entry_paths = {"index.html", "src/main.jsx", "src/main.tsx", "src/main.js",
                   "app/page.jsx", "app/page.tsx"}
    has_entry_in_response = any(f["path"].lower() in entry_paths for f in clean)
    has_entry_in_current = any(
        (f.get("path") or "").lower() in entry_paths for f in (current_files or [])
    )
    if not has_entry_in_response and not has_entry_in_current:
        raise AIProviderError("AI response missing index.html / app entry point")
    return clean


async def generate_project(
    user_message: str,
    current_files: List[dict],
    history: List[dict],
    project_id: str,
    preferred_provider: Optional[str] = None,
    runtime_ctx: Optional[dict] = None,
) -> dict:
    """Non-streaming generation with one auto-retry on parse failure."""
    provider = get_provider_for_task("code-generation", explicit=preferred_provider)
    session_id = f"proj-{project_id}-{uuid.uuid4().hex[:8]}"
    prompt = build_prompt(user_message, current_files, history, runtime_ctx=runtime_ctx)
    logger.info(f"AI generate via provider={provider.name} model={provider.model}")
    raw = await provider.generate(SYSTEM_PROMPT, prompt, session_id)
    try:
        parsed = parse_ai_response(raw)
    except Exception:
        logger.warning(f"AI parse failed (retry will follow). Length={len(raw)}")
        try:
            raw2 = await provider.generate(SYSTEM_PROMPT + RETRY_REINFORCEMENT, prompt, session_id + "-r")
            parsed = parse_ai_response(raw2)
        except Exception as ee:
            logger.error(f"AI retry also failed: {ee}")
            raise AIProviderError(f"AI parse failed after retry: {ee}")
    files = _validate_files(parsed.get("files") or [], current_files)
    # bug fix iter4 #3: if the AI returned only a subset of files (e.g. on
    # an incremental edit), merge them on top of current_files so unchanged
    # files are preserved.
    if current_files and len(files) < len(current_files):
        by_path = {f["path"]: f for f in current_files}
        for f in files:
            by_path[f["path"]] = f
        files = list(by_path.values())
    return {
        "files": files,
        "explanation": parsed.get("explanation") or "Updated files.",
        "notes": parsed.get("notes"),
        "provider": provider.name,
        "model": provider.model,
    }


# ---------- Commit summary helper ----------
COMMIT_PROMPT = """You are summarising an AI code change for a project's commit history. Given:
- the user's request,
- the AI's explanation of what it built,
- the changed file paths,

output STRICT JSON with exactly two fields:
{ "label": "<5-7 word title, sentence case>", "message": "<1-2 sentence longer description, plain text>" }
No prose outside JSON. No markdown fences."""


async def generate_commit_summary(user_message: str, explanation: str, files: List[dict],
                                   preferred_provider: Optional[str] = None) -> dict:
    """Use the active provider to produce a {label, message} for a version."""
    try:
        provider = get_active_provider(preferred_provider)
    except AIProviderError:
        return {"label": user_message[:60], "message": explanation[:240]}
    paths_blob = ", ".join(f["path"] for f in (files or [])[:30])
    prompt = (
        f"USER REQUEST:\n{user_message[:400]}\n\n"
        f"AI EXPLANATION:\n{explanation[:600]}\n\n"
        f"CHANGED FILES:\n{paths_blob}\n\n"
        "Respond with the JSON now."
    )
    session_id = f"commit-{uuid.uuid4().hex[:8]}"
    try:
        raw = await provider.generate(COMMIT_PROMPT, prompt, session_id)
        parsed = parse_ai_response(raw)
        label = (parsed.get("label") or "")[:120]
        msg = (parsed.get("message") or "")[:600]
        if not label:
            label = user_message[:60]
        if not msg:
            msg = explanation[:240]
        return {"label": label, "message": msg}
    except Exception:
        return {"label": user_message[:60], "message": explanation[:240]}


# ---------- AI debugging ----------
DEBUG_PROMPT = """You are an elite full-stack debugger. The user is seeing an error in a project NXT1 generated. You receive:
  - the error text/log
  - the relevant files
  - the user's note (optional)

Your job: explain the cause, propose a precise fix, and (if obvious) output the corrected file(s).

Return STRICT JSON:
{
  "diagnosis": "<2-4 sentence explanation of root cause>",
  "proposed_fix": "<concrete steps describing the fix>",
  "files": [ { "path": "...", "content": "..." } ]   // optional, only if you confidently know the corrected content
}
No prose outside JSON. No markdown fences."""


async def debug_error(error_text: str, current_files: List[dict], user_note: str = "",
                       preferred_provider: Optional[str] = None) -> dict:
    provider = get_provider_for_task("debug", explicit=preferred_provider)
    files_blob = "\n\n".join(
        [f"=== {f['path']} ===\n{(f.get('content','') or '')[:6000]}" for f in (current_files or [])[:20]]
    ) or "(no files)"
    prompt = (
        f"ERROR / LOG:\n{error_text[:4000]}\n\n"
        f"USER NOTE:\n{user_note[:600]}\n\n"
        f"CURRENT FILES:\n{files_blob}\n\n"
        "Respond with the JSON now."
    )
    session_id = f"debug-{uuid.uuid4().hex[:8]}"
    raw = await provider.generate(DEBUG_PROMPT, prompt, session_id)
    return parse_ai_response(raw)


# ---------- Generate frontend page that calls a backend route ----------
ROUTE_PAGE_PROMPT = """You are NXT1. The user wants a polished frontend page that calls a specific
backend API route through NXT1's runtime proxy. Generate a single, premium-quality file that:
- calls the proxy URL exactly (do NOT use relative paths)
- handles loading, error, and success states
- looks modern (dark theme, sharp typography, generous spacing)
- has zero external dependencies (vanilla HTML+CSS+JS unless target='react')
- uses the right HTTP method
- shows a sample request body editor for non-GET methods
- displays the JSON response in a styled code block
- includes a small header naming the endpoint

Return STRICT JSON:
{
  "path": "<file path inside the project, e.g. 'tools/users.html' for html or 'src/pages/Users.jsx' for react>",
  "content": "<complete file contents>",
  "title": "<short page title shown to user>",
  "explanation": "<one sentence explanation>"
}
No prose outside JSON. No markdown fences."""


async def generate_route_page(method: str, path: str, proxy_url: str,
                              target: str = "html",
                              existing_paths: Optional[List[str]] = None,
                              preferred_provider: Optional[str] = None) -> dict:
    """Use the active AI provider to generate a polished page that calls a route.
    target: 'html' | 'react' | 'auto'.
    """
    provider = get_provider_for_task("route-page", explicit=preferred_provider)
    full_url = f"{proxy_url.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    paths_hint = ", ".join((existing_paths or [])[:30]) or "(empty)"
    user_prompt = (
        f"METHOD: {method}\nROUTE PATH: {path}\nFULL PROXY URL TO CALL: {full_url}\n"
        f"TARGET: {target}\nEXISTING PROJECT FILES: {paths_hint}\n\n"
        "Pick a fresh non-conflicting `path` for the new file. If target=react and project "
        "already uses src/ pick something like `src/pages/<Name>.jsx`. Otherwise place under "
        "`tools/<name>.html`. Keep design tasteful: dark background, white text, generous "
        "spacing, monospace for code, subtle borders. Show response and any error messages. "
        "Respond with the JSON now."
    )
    session_id = f"page-from-route-{uuid.uuid4().hex[:8]}"
    raw = await provider.generate(ROUTE_PAGE_PROMPT, user_prompt, session_id)
    parsed = parse_ai_response(raw)
    if not parsed.get("path") or not parsed.get("content"):
        raise AIProviderError("AI did not return a valid {path, content}")
    # Sanitize path: strip leading slash, keep simple chars
    parsed["path"] = parsed["path"].strip().lstrip("/")
    return {
        "path": parsed["path"],
        "content": parsed["content"],
        "title": parsed.get("title") or f"{method} {path}",
        "explanation": parsed.get("explanation") or "Generated a frontend page for this route.",
        "provider": provider.name,
        "model": provider.model,
    }


async def generate_project_stream(
    user_message: str,
    current_files: List[dict],
    history: List[dict],
    project_id: str,
    preferred_provider: Optional[str] = None,
    runtime_ctx: Optional[dict] = None,
    cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
):
    """Yield SSE chunks: {"type":"chunk","delta":...} and final {"type":"done", ...}.

    Also yields structured phase events the UI uses as the loading state:
        {"type":"phase","label":"Planning app structure"}
        {"type":"phase","label":"Editing files"}
        {"type":"phase","label":"Building preview"}

    Mid-iteration cancellation:
      The optional `cancel_check` is an async callable that should return True
      when the user has requested cancellation (typically: the corresponding
      job's status was flipped to 'cancelled' in MongoDB). When True, the
      generator yields {"type":"cancelled"} and returns cleanly — the calling
      chat.py background task then persists a 'cancelled' assistant message.
      The check is throttled internally so we don't hit the DB on every chunk.
    """
    provider = get_provider_for_task("code-generation", explicit=preferred_provider)
    session_id = f"proj-{project_id}-{uuid.uuid4().hex[:8]}"
    prompt = build_prompt(user_message, current_files, history, runtime_ctx=runtime_ctx)
    logger.info(f"AI stream via provider={provider.name} model={provider.model}")

    # Build a failover chain for transient upstream errors (502/503/timeout/
    # rate-limit/unavailable). We always TRY the primary first, then fall
    # through to the registry's natural priority list. Each fallback gets a
    # fresh session id so prior partial text doesn't pollute its context.
    failover_chain = [provider]
    try:
        from services.providers.types import RouteIntent as _RI
        from services.providers.registry import registry as _REG
        _intent_fallback = _RI(
            routing_mode="auto",
            task="code-generation",
            explicit_provider=None,
        )
        seen_ids = {provider.name}
        for alt in _REG.try_chain(_intent_fallback):
            if alt.name in seen_ids:
                continue
            seen_ids.add(alt.name)
            failover_chain.append(alt)
            if len(failover_chain) >= 3:    # primary + 2 fallbacks max
                break
    except Exception as _e:
        logger.debug(f"failover chain build skipped: {_e}")

    # Throttle cancel checks to ~every 0.5s so we don't hammer Mongo per chunk
    import time as _time
    _last_check = [0.0]
    async def _is_cancelled() -> bool:
        if not cancel_check:
            return False
        now = _time.monotonic()
        if now - _last_check[0] < 0.5:
            return False
        _last_check[0] = now
        try:
            return bool(await cancel_check())
        except Exception:
            return False

    yield {"type": "start", "provider": provider.name, "model": provider.model}
    yield {"type": "phase", "label": "Planning app structure"}

    # Live first-person narration BEFORE the heavy JSON gen so the user sees
    # the agent describing what it's building instead of a static "Thinking".
    try:
        async for line in _stream_narration(user_message, current_files):
            yield {"type": "narration", "line": line}
            if await _is_cancelled():
                yield {"type": "cancelled", "stage": "narration"}
                return
    except Exception as e:  # never block the main build
        logger.warning(f"narration error: {e}")

    yield {"type": "phase", "label": "Editing files"}

    full_text = ""
    # ─── Failover loop ───
    # Try each provider in the chain. If one returns a transient upstream
    # error (502/503/timeout/unavailable), surface a friendly "switching
    # provider" info event and retry on the next one. The user never sees
    # the raw provider trace.
    _last_provider_err = None
    _attempted = []
    for _i, _p in enumerate(failover_chain):
        provider = _p   # rebind so subsequent retry path sees the working one
        _attempted.append(provider.name)
        try:
            if _i > 0:
                yield {
                    "type": "info",
                    "message": f"Provider {failover_chain[_i-1].name} unavailable — switching to {provider.name}…",
                }
                # Re-fire phase so the UI re-activates the editing/coder step.
                yield {"type": "phase", "label": "Editing files"}
            full_text = ""
            async for delta in _aiter(provider.generate_stream(SYSTEM_PROMPT, prompt, session_id + (f"-fb{_i}" if _i else ""))):
                full_text += delta
                yield {"type": "chunk", "delta": delta, "size": len(full_text)}
                if await _is_cancelled():
                    yield {"type": "cancelled", "stage": "generation",
                           "partial_size": len(full_text)}
                    return
            _last_provider_err = None
            break   # success — exit the failover loop
        except Exception as e:
            _last_provider_err = e
            msg = str(e)
            transient = any(s in msg for s in (
                "502", "503", "504", "BadGateway", "Service Unavailable",
                "timeout", "TimeoutError", "ProviderUnavailable", "ProviderTimeout",
                "rate_limit", "RateLimit", "InternalServerError",
            ))
            logger.warning(f"provider {provider.name} failed (transient={transient}): {e}")
            try:
                _REG.mark_error(provider.name)
            except Exception:
                pass
            if not transient:
                # Non-transient (auth, validation, etc) — don't bother with
                # other providers; surface a friendly error and stop.
                break
            # Loop continues to next provider on transient failures.

    if _last_provider_err is not None:
        # Sanitize the message — never expose raw litellm/openai dumps.
        em = str(_last_provider_err)
        friendly = (
            "The AI provider is temporarily unavailable. Retry in a moment "
            "or pick a different model from the picker."
            if any(s in em for s in ("502", "503", "504", "BadGateway", "Service Unavailable", "InternalServerError"))
            else "The model couldn't complete this generation. Retry or pick a different model."
        )
        yield {
            "type": "error",
            "message": friendly,
            # Hide the underlying provider trace from the client. We only keep
            # a short stage hint for the debugger UI.
            "stage": "provider",
            "providers_attempted": _attempted,
        }
        return

    if await _is_cancelled():
        yield {"type": "cancelled", "stage": "post-generation",
               "partial_size": len(full_text)}
        return

    yield {"type": "phase", "label": "Validating output"}

    # Parse with retry-then-repair fallback. Always persist the raw payload
    # on failure so operators can inspect exactly what the model emitted.
    raw_first = full_text
    parsed: Optional[dict] = None
    parse_error: Optional[str] = None

    # Truncation heuristic: streamed text but no closing brace → likely hit
    # max_tokens. Surface as info so user knows to break the task up.
    truncated = bool(full_text) and full_text.count("{") > full_text.count("}")
    if truncated:
        yield {"type": "info", "message": "Output appears truncated (max tokens hit). Attempting recovery…"}

    try:
        parsed = parse_ai_response(full_text)
    except Exception as e:
        parse_error = str(e)
        logger.warning(f"first-parse failed: {e}")
        yield {"type": "info", "message": "Output not valid JSON — retrying with reinforcement…"}
        yield {"type": "phase", "label": "Repairing AI output"}
        try:
            full_text = ""
            async for delta in _aiter(provider.generate_stream(
                SYSTEM_PROMPT + RETRY_REINFORCEMENT, prompt, session_id + "-r"
            )):
                full_text += delta
                yield {"type": "chunk", "delta": delta, "size": len(full_text), "retry": True}
            parsed = parse_ai_response(full_text)
            parse_error = None
        except Exception as e2:
            parse_error = f"{parse_error or 'first parse failed'} → retry parse failed: {e2}"
            logger.warning(f"retry parse failed: {e2}")
            yield {
                "type": "error",
                "message": f"AI returned malformed JSON twice. {e2}",
                "raw_preview": (full_text or raw_first)[-2000:],
                "stage": "parse",
            }
            return

    if not isinstance(parsed, dict):
        yield {"type": "error", "message": "AI response was not a JSON object",
               "raw_preview": (full_text or raw_first)[-2000:], "stage": "parse"}
        return

    # If recovery flag was set during parsing, surface it to the UI so user
    # knows the result was salvaged from a truncated/malformed output.
    if parsed.get("_recovered"):
        yield {"type": "info", "message": "Recovered partial files from a truncated AI response. Review and re-run if anything looks incomplete."}

    try:
        files = _validate_files(parsed.get("files") or [], current_files)
    except Exception as e:
        yield {"type": "error", "message": str(e),
               "raw_preview": (full_text or raw_first)[-2000:], "stage": "validate"}
        return

    # Compute diff against current_files and emit retroactive tool-receipts so
    # the chat can render "Edited `Pricing.jsx` ✓" / "Created `Hero.jsx` ✓"
    # bubbles inline (matches the user's reference UX).
    try:
        existing_map = {f["path"]: f.get("content") or "" for f in current_files}
        new_map = {f["path"]: f.get("content") or "" for f in files}
        # Heuristic: things the model "read" — files mentioned in the user_msg
        # or anywhere in the explanation. Cheap, non-blocking.
        explanation = parsed.get("explanation") or ""
        haystack = f"{user_message}\n{explanation}"
        viewed = [
            p for p in existing_map.keys()
            if (p in haystack or p.split("/")[-1] in haystack)
            and p not in new_map  # if it was edited we'll surface that instead
        ][:3]
        for p in viewed:
            yield {"type": "tool", "action": "viewed", "path": p}
        # Compare current vs new
        for p, content in new_map.items():
            if p not in existing_map:
                yield {"type": "tool", "action": "created", "path": p}
            elif content != existing_map[p]:
                yield {"type": "tool", "action": "edited", "path": p}
        for p in existing_map.keys():
            if p not in new_map:
                yield {"type": "tool", "action": "deleted", "path": p}
    except Exception as e:  # never fail the stream over receipt diffing
        logger.warning(f"tool-receipt diff failed: {e}")

    yield {"type": "phase", "label": "Validating output"}

    # ── Static validation + self-healing (Phase A.6) ──────────────────────
    # Run lightweight syntax/structure checks on the files the AI changed.
    # If errors are found AND we haven't already repaired, kick off ONE
    # repair pass with the error report appended to the prompt. The model
    # gets a chance to surgically fix what it broke without the user
    # having to ask. Tag-mode and JSON-mode share this hook.
    try:
        from services.validation_service import (
            diff_paths,
            format_for_repair_prompt,
            validate_files,
        )
        changed = diff_paths(current_files, files)
        v_report = validate_files(files, only_paths=changed)
        if v_report.issues:
            yield {"type": "validate", "report": v_report.to_dict()}
        if v_report.has_errors:
            yield {"type": "phase", "label": "Self-healing build"}
            repair_user_prompt = (
                f"{prompt}\n\n"
                f"=== POST-GENERATION VALIDATION REPORT ===\n"
                f"{format_for_repair_prompt(v_report)}\n\n"
                "Re-emit ONLY the corrected file set in the same JSON schema. "
                "Keep all unaffected files identical."
            )
            yield {"type": "info",
                   "message": f"Detected {v_report.error_count} build error(s) — auto-repairing…"}
            try:
                repaired_raw = await provider.generate(
                    SYSTEM_PROMPT + RETRY_REINFORCEMENT,
                    repair_user_prompt,
                    session_id + "-heal",
                )
                repaired = parse_ai_response(repaired_raw)
                repaired_files = _validate_files(repaired.get("files") or [])
                # Re-validate; accept the repair only if it improves or holds.
                repaired_changed = diff_paths(current_files, repaired_files)
                v2 = validate_files(repaired_files, only_paths=repaired_changed)
                if v2.error_count < v_report.error_count:
                    files = repaired_files
                    parsed = repaired
                    yield {"type": "info",
                           "message": f"Repair pass reduced errors {v_report.error_count}\u2192{v2.error_count}."}
                    yield {"type": "validate", "report": v2.to_dict()}
                else:
                    yield {"type": "info",
                           "message": "Repair pass did not improve validation; keeping original."}
            except Exception as e:
                logger.warning(f"self-healing repair failed (non-fatal): {e}")
                yield {"type": "info",
                       "message": "Self-healing pass failed; keeping original output."}
    except Exception as e:
        logger.warning(f"validation hook failed (non-fatal): {e}")

    yield {"type": "phase", "label": "Finalizing"}
    yield {
        "type": "done",
        "files": files,
        "explanation": parsed.get("explanation") or "Updated files.",
        "notes": parsed.get("notes"),
        "provider": provider.name,
        "model": provider.model,
    }


async def generate_text_stream(
    *,
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 2400,
    preferred: Optional[str] = None,
) -> AsyncIterator[str]:
    """Generic streaming text generator for arbitrary system+messages
    interactions. Used by the agents-catalog invoke endpoint.

    Resolves a provider via the registry (auto-routes to the first
    available real key, or honours `preferred`/AI_PROVIDER). Yields
    string deltas as they arrive.

    The history is flattened into a single user-prompt buffer for
    providers whose `generate_stream` takes a `(system, user, session)`
    triple. We keep the most recent ~12 turns to bound context.
    """
    import uuid as _uuid
    provider = get_active_provider(preferred=preferred)
    session_id = f"agent-{_uuid.uuid4().hex[:10]}"
    # Flatten chat history into a single user-prompt buffer.
    parts: list[str] = []
    for turn in messages[:-1]:
        role = (turn.get("role") or "").upper()
        content = (turn.get("content") or "").strip()
        if content:
            parts.append(f"[{role}]\n{content}\n")
    last_user = (messages[-1].get("content") if messages else "") or ""
    if parts:
        prompt = "\n".join(parts) + "\n[USER]\n" + last_user
    else:
        prompt = last_user

    try:
        async for chunk in _aiter(provider.generate_stream(
            system_prompt, prompt, session_id,
        )):
            if chunk:
                yield chunk
    except AIProviderError:
        raise
    except Exception as e:
        # Surface as a clean text chunk so the FE shows a readable error,
        # not a 500.
        logger.exception("generate_text_stream failed")
        yield f"\n\n[Provider error: {e}]"


async def _aiter(maybe_async_iter):
    """Adapt a sync or async generator into an async iterator."""
    import inspect
    if inspect.isasyncgen(maybe_async_iter):
        async for item in maybe_async_iter:
            yield item
    else:
        for item in maybe_async_iter:
            yield item


# ---------- Live narration (replaces the silent "Thinking" UX) ----------
NARRATION_SYSTEM = """You are NXT1's narrator. Before the engineering agent
generates files, describe what you are about to build, in 4-7 short, friendly
first-person sentences. One specific action per sentence.

STRICT RULES:
- First-person, conversational ("I'll set up the layout…", "Now I'm wiring up the contact form…").
- Plain prose only. NO JSON. NO markdown. NO code blocks. NO bullet points.
- Each sentence ends with a period and a single space.
- Mention concrete things: the hero, the navigation, the CSS palette, the grid, the
  contact form, the API route, etc. Be specific to the user's request, not generic.
- Do NOT say "I'm thinking" or "Let me think" — describe the actual work.
- Keep it under 80 words total.
"""


def _narration_user_prompt(user_message: str, current_files: list) -> str:
    if current_files:
        existing = ", ".join(f["path"] for f in current_files[:8])
        if len(current_files) > 8:
            existing += f", and {len(current_files) - 8} more"
        ctx = f"Existing project has: {existing}."
    else:
        ctx = "Starting from a blank project."
    return (
        f"USER REQUEST:\n{user_message[:600]}\n\n"
        f"{ctx}\n\n"
        "Narrate the build now in 4-7 first-person sentences."
    )


async def _stream_narration(user_message: str, current_files: list):
    """Yield short narration sentences as plain strings.

    Picks the cheapest streaming-capable provider available so this stays fast:
    OpenAI gpt-4o-mini → Anthropic Haiku → Emergent (Claude Haiku via universal
    key) → silent fallback. Failures are swallowed so the main build is never
    blocked.
    """
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    emergent_key = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    user_prompt = _narration_user_prompt(user_message, current_files)

    # Try Emergent first via litellm if it's the only key available.
    # This makes narration work in environments that only have the universal key.
    if not openai_key and not anthropic_key and emergent_key:
        try:
            text = await _acomplete(
                provider="anthropic",
                model="claude-haiku-4-5-20251001",
                api_key=emergent_key,
                system_prompt=NARRATION_SYSTEM,
                user_prompt=user_prompt,
                max_tokens=220,
            )
            if text:
                for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
                    sent = sent.strip()
                    if sent and len(sent) > 2:
                        yield sent
        except Exception as e:
            logger.warning(f"narration via emergent failed (non-fatal): {e}")
        return

    provider_name, model_name, api_key = None, None, None
    if openai_key:
        provider_name, model_name, api_key = "openai", "gpt-4o-mini", openai_key
    elif anthropic_key:
        provider_name, model_name, api_key = "anthropic", "claude-haiku-4-5-20251001", anthropic_key
    else:
        return  # silent fallback — main build still runs

    params = {
        "model": f"{provider_name}/{model_name}",
        "messages": [
            {"role": "system", "content": NARRATION_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "api_key": api_key,
        "stream": True,
        "max_tokens": 220,
        "temperature": 0.6,
    }
    try:
        response = litellm.completion(**params)
    except Exception as e:
        logger.warning(f"narration setup failed: {e}")
        return

    buf = ""
    sentence_re = re.compile(r"(.+?[.!?])(?:\s+|$)", re.DOTALL)
    try:
        for chunk in response:
            try:
                delta = chunk.choices[0].delta.content or ""
            except Exception:
                delta = ""
            if not delta:
                continue
            buf += delta
            while True:
                m = sentence_re.match(buf)
                if not m:
                    break
                sent = m.group(1).strip()
                buf = buf[m.end():]
                if sent and len(sent) > 2:
                    yield sent
        tail = buf.strip()
        if tail and len(tail) > 2:
            yield tail
    except Exception as e:
        logger.warning(f"narration stream failed (non-fatal): {e}")
