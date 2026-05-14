## 2026-05-14 — AI generation restored via Emergent universal key

### Root cause
Previous agent had:
1. Stripped `emergentintegrations` usage from `ai_service.py` and replaced it with a litellm shim that called the Emergent proxy at the wrong URL (missing `/llm` suffix) and with the wrong model format (`{provider}/{model}` instead of bare model + `custom_llm_provider=openai`).
2. **Removed `EmergentProvider` entirely from `ALL_ADAPTERS`** in `services/providers/adapters.py`, so `registry.available()` returned `[]` — every builder request returned *"No AI provider is configured"*.
3. Used model id `claude-haiku-4-5-20251001` which is valid; the previous catalog mistakenly had `claude-haiku-4-5-20250929`.

### Fix applied
- Added `_build_litellm_kwargs(...)` helper in `services/ai_service.py` that detects `sk-emergent-*` keys and routes to `https://integrations.emergentagent.com/llm` with `custom_llm_provider="openai"` (matches the official `LlmChat._execute_completion` logic from the `emergentintegrations` package).
- Wired all three first-party adapters (`OpenAIProvider`, `AnthropicProvider`, `EmergentProvider`) and their `generate_stream` variants through the same helper so `EMERGENT_LLM_KEY` works for both blocking and streaming calls.
- Re-added `EmergentProvider` to `ALL_ADAPTERS`; re-enabled its `generate/generate_stream` by delegating to the new `ai_service.EmergentProvider`.
- Flipped its `streaming=True` (it actually does stream now via the OpenAI-compatible proxy) and updated the model id to `claude-haiku-4-5-20251001`.

### Verified
- `curl /api/projects/{id}/chat/stream` → returns `start`/`narration`/`chunk` SSE events (Claude Sonnet 4.5 via emergent). End-to-end build succeeds.
- `LlmChat` direct call (used by `social_content_service`) → returns OK.
- Registry `available()` → `['emergent']` when only `EMERGENT_LLM_KEY` is set.


# NXT1 — Product Requirements Document

## Latest user direction (May 14, 2026)
- Builder/Studio black-screen fixed: BoltDiyOverlay + OpenReelOverlay only iframe when the configured URL is a **public https** URL. Localhost = native UI stays primary. No more blank pages.
- **17 Premium UI Blocks** hidden from frontend (Tools drawer + Operations tab). Registry still lives at `/api/ui/registry` and is auto-consumed by the build agent when matching user briefs → templates.
- **Cloudflare R2 storage facade** (`services/asset_storage.py`) — every social/video upload routes through it. R2 when keys are set, local disk fallback otherwise.
- **AI provider failures** ("Generation failed at 0%") root cause: **Emergent universal key budget exhausted** ($2.06 / $2.00 cap). The fix is on the user side: paste your own `OPENAI_API_KEY` + `ANTHROPIC_API_KEY` (already wired everywhere — picked up automatically).

## Architecture
- **Backend** — FastAPI/uvicorn (8001), MongoDB via motor.
- **Frontend** — React 19 + CRACO + Tailwind + framer-motion (3000).
- **Sidecars**:
  - `bolt-engine` (bolt.diy app builder, port 5173) — supervisor-managed
  - `video-studio` (OpenReel, port 5174) — supervisor-managed
  - Both fronted by overlay components that only activate when reachable at a **public https URL**. In preview/dev → native UI primary.
- **Storage** — `services/asset_storage.py` (R2 first, local disk fallback). Wraps existing `services/r2_service.py`.
- **Persistent jobs** — `services/job_service.py` writes to Mongo; long tasks are detached `asyncio.create_task`. UI re-attaches via `useJobProgress` + localStorage.
- **Agent Memory** — `services/agent_memory.py` per-user shared context, auto-loaded into every social run, page UI at `/workspace/memory`.

## What's been implemented
- Social Content Agent (Claude + DALL-E + memory + autopilot + OAuth IG/X/LinkedIn).
- Native Video Studio (5 Fal.ai models: Veo 3.1, Kling 2.5 Turbo Pro, Kling 2.1 Master, LTX, CogVideoX; t2v + i2v; reference images; server-side ffmpeg multi-clip MP4 export via imageio-ffmpeg).
- Agent Memory page (`/workspace/memory`) — pin/edit/delete with scope+kind tags.
- Cloudflare R2 storage facade — all uploads route through it.
- bolt.diy + OpenReel sidecars installed + supervisor-managed; overlay components hand off automatically when public URL is set.
- Render deploy fix: `render.yaml`, root `requirements.txt`, root `.python-version`, `--extra-index-url` for `emergentintegrations`, `imageio-ffmpeg` for Render-safe ffmpeg.
- 17 Premium UI Blocks moved to backend-only catalog.

## What the user must paste on Render
**Required to get past the "AI provider temporarily unavailable" error:**
- `ANTHROPIC_API_KEY` — your own Claude key (replaces exhausted Emergent budget for chat).
- `OPENAI_API_KEY` — your own OpenAI key (replaces Emergent for images + chat fallback).

**Required for everything else:**
- `MONGO_URL`, `DB_NAME` — your MongoDB Atlas URI + DB name.
- `APP_PASSWORD=555` — workspace gate.
- `JWT_SECRET` — any 32+ char random string.
- `PUBLIC_BACKEND_URL` — your Render https URL.
- **Cloudflare R2** (durable storage; replaces ephemeral Render disk):
  - `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_BASE`.
- **Fal.ai video**: `FAL_API_KEY`.
- **OAuth (auto-posting)**: `META_APP_ID/SECRET`, `X_CLIENT_ID/SECRET`, `LINKEDIN_CLIENT_ID/SECRET`. Register callback `{PUBLIC_BACKEND_URL}/api/social/oauth/{platform}/callback` in each platform's dev console.
- **Sidecars (optional)**: `BOLT_DIY_URL`, `STUDIO_URL` — point to your bolt.diy + OpenReel deployments. When unset or pointing at localhost, native NXT1 UI stays primary.

## Render deploy known fixes
- `requirements.txt` has `emergentintegrations==0.1.0` + `fal-client==1.0.0` pinned.
- `render.yaml` build cmd uses `--extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/` so Render finds `emergentintegrations`.
- `imageio-ffmpeg` ships a static ffmpeg binary inside the Python wheel — Render's Python runtime gets ffmpeg automatically (system ffmpeg not required).

## Next action items
- **P0 (user)**: Paste keys on Render (above). Push and redeploy.
- **P1**: When R2 keys present + verify a video clip upload lands in your bucket.
- **P1**: Connect Instagram/LinkedIn/X in Social → Brand · Identity once `*_CLIENT_ID/SECRET` are set.
- **P2**: Wire AI provider preference UI so user can pick "always use my own key first".
- **P2**: Memory UI panel for global pinned brand facts (already exists at `/workspace/memory`).
