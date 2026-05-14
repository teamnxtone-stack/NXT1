# NXT1 — Product Requirements Document

## Original problem statement (verbatim, latest)
> With the social media content creator, hook it up to my OpenAI key — I want OpenAI making those photos, and I want them really really good. Add a way the chat box accepts images (like attaching photos to give context). Throughout the entire app, the agent needs to **store memory** — memories are really important. Make sure everything is ready to push and works on Render — strip any blockers. I'll add the other API keys on Render so it syncs.

## Architecture
- **Backend** — FastAPI + uvicorn (8001), MongoDB via motor.
- **Frontend** — React 19 + CRACO + Tailwind + framer-motion.
- **Persistent jobs** — `services/job_service.py` writes every long task to Mongo `jobs`. Work is `asyncio.create_task`'d → survives browser/request lifecycle. UI re-attaches via `useJobProgress` + localStorage.
- **Agent Memory** — `services/agent_memory.py` provides per-user, scope-tagged persistent context (`global` | `social` | `studio` | `agents`). Auto-loaded into prompts as a `=== USER MEMORY ===` block (pinned first, max 2.2 KB). Auto-written by the social agent on every generate / regenerate.
- **Background scheduler** — `services/social_scheduler.py` ticks every 60 s; publishes due posts + fires weekly auto-pilot.
- **OAuth + posting** — `services/social_publishing_service.py` for Meta/IG, LinkedIn, X. Gated by env-var presence; activates automatically when creds are pasted.
- **Render deploy** — `render.yaml` at root, `.python-version` at root, mirrored `requirements.txt` at root.

## What's been implemented (2026-05-14)

### Foundation
- Installed user's NXT1 zip; preserved `.env`s; fixed missing `eslint-config-react-app@7.0.1`.
- Render deploy files: `render.yaml`, `.python-version`, root `requirements.txt`, fixed `backend/runtime.txt`.
- Workspace gate password = `555` via `APP_PASSWORD`.

### Social Content Agent (v2 — memory + multimodal + HQ images)
- **OpenAI image gen prefers user's `OPENAI_API_KEY`** for top-quality `gpt-image-1`. Falls back to `EMERGENT_LLM_KEY` only if blank. Append `"— photorealistic, high detail, professional photography, 4k"` to every prompt.
- **Multimodal brief** — chat input accepts reference images (paperclip button). Backend route `POST /api/social/upload-reference` (max 8 MB, png/jpg/webp). The agent passes them as `ImageContent` to Claude (vision) for tone/style understanding AND derives a `visual_style` summary that's appended to every image_prompt for visual cohesion across the calendar.
- **Auto-memory** — every generation auto-loads `agent_memory(scope=social)` into the Claude prompt AND auto-writes a `fact` ("Generated N posts (founder tone) — topics: …") + `example` ("User asked: …") so the next run is smarter. Regenerate writes a `feedback` entry.
- **Post actions**: Regenerate · Approve · Schedule · Post now · Delete (44 px touch targets, mobile-safe).

### Agent Memory system (NEW, NXT1-wide)
- `services/agent_memory.py` + `routes/agent_memory.py` (`/api/memory`).
- Kinds: `fact | preference | example | feedback | image | system`. Scopes: `global | social | studio | agents`.
- `build_context_block` returns a ready-to-inject prompt snippet, pinned first, capped at 2200 chars.
- Endpoints: list, add, patch (summary/pin), delete, `/context?scope=…`.

### Video Studio
- `routes/video.py` + `services/video_studio_service.py` — Fal.ai `cogvideox-5b` (detached job), mp4/mov/webm upload, clip CRUD, timeline save, post-to-social.
- AI Generate drawer + Post-to-Social modal in `pages/workspace/StudioPage.jsx`.

### Social OAuth + posting + autopilot
- `routes/social_oauth.py`, `services/social_publishing_service.py` — Meta Graph v21 (IG via page→business-account discovery → media + media_publish), LinkedIn UGC, X OAuth 2.0 + PKCE + v2 tweets.
- `services/social_scheduler.py` — 60 s loop; publishes due posts AND fires weekly autopilots. Safe when no connection exists (just leaves posts scheduled).
- `components/social/ConnectionsAndAutopilot.jsx` — Connect / Disconnect UI + Autopilot day/hour/brief toggle inside the Brand · Identity drawer.

### Sidebar / routes
- `/workspace/social`, `/workspace/studio`, plus existing Home / Apps / Agents / AgentOS / Account.

## Testing (cumulative)
- Iter 6 — 32/32 PASS · Social + Video core + persistence.
- Iter 7 — 30/30 PASS · Workspace password 555 + OAuth + connections + autopilot + scheduler safety.
- Iter 8 — 28/28 PASS · Agent Memory CRUD + reference-image upload + memory-aware generate + Render readiness + regression smoke.

## Render readiness checklist (all green)
- ✅ `render.yaml` lists every needed envVar (`sync: false` so they're set per-environment).
- ✅ `requirements.txt` at root and at `backend/` (pinned).
- ✅ `.python-version` at root = `3.11.9`.
- ✅ `backend/runtime.txt` = `python-3.11.9`.
- ✅ No hardcoded localhost in backend; all URLs via env (`MONGO_URL`, `PUBLIC_BACKEND_URL`).
- ✅ Frontend reads `REACT_APP_BACKEND_URL` only; no API URL hardcoding.
- ✅ Backend boots fresh — confirmed after multiple `supervisorctl restart`.
- ✅ Scheduler safe when no connection exists.
- ✅ Image gen falls back gracefully when `OPENAI_API_KEY` is blank.

## Next Action Items
- **P0 — Push to GitHub** (Save to GitHub button). Render auto-deploys.
- **P0 — Set these env vars on Render**: `MONGO_URL`, `DB_NAME`, `APP_PASSWORD=555`, `JWT_SECRET` (any 32+ char random string), `PUBLIC_BACKEND_URL` (your Render URL), `EMERGENT_LLM_KEY`, **`OPENAI_API_KEY` (yours, for top-quality images)**, plus the platform creds you have: `FAL_API_KEY`, `META_APP_ID/SECRET`, `X_CLIENT_ID/SECRET`, `LINKEDIN_CLIENT_ID/SECRET`.
- **P0 — Register OAuth callback URLs** in each platform's developer console: `{PUBLIC_BACKEND_URL}/api/social/oauth/{instagram|linkedin|twitter}/callback`.
- **P1 — Multi-clip MP4 stitching** in Studio Export (ffmpeg.wasm or server ffmpeg endpoint).
- **P1 — Image upload for LinkedIn + X** publishing (currently text-only on those two; IG is image-only).
- **P1 — Memory UI** — list/pin/edit memory items in a dedicated panel (currently auto-only).
- **P2 — WebSocket push** instead of 1.5 s polling.
- **P2 — Refresh-token rotation** for X.

## Personas
- **Founder operator** — weekly content + product demos without a marketing team.
- **Solo developer / indie hacker** — Studio for demos, Social for build-in-public.

## Env vars (final)
- Required at runtime: `MONGO_URL`, `DB_NAME`.
- AI: `EMERGENT_LLM_KEY` (fallback for everything) + `OPENAI_API_KEY` (user's; preferred for images) + optional `ANTHROPIC_API_KEY` (user's; preferred for Claude).
- Auth: `APP_PASSWORD`, `JWT_SECRET`.
- OAuth: `PUBLIC_BACKEND_URL`, `META_APP_ID`, `META_APP_SECRET`, `X_CLIENT_ID`, `X_CLIENT_SECRET`, `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`.
- Video: `FAL_API_KEY`.
