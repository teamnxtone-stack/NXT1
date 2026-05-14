# NXT1 — Product Requirements Document

## Original problem statement (verbatim)
> I'm sending you my current app that file don't change anything I want you to install it and then we're gonna make a couple of changes and adjustments.
> 
> Follow-up: Implement the changes outlined in `nxt1_social_video_render_prompt.pdf` (Render deploy fix, AI Social Media Content Agent, Video Studio page). Builders/agents must keep running even if the browser is closed.

## Architecture
- **Backend** — FastAPI on uvicorn (port 8001), modular routers under `/app/backend/routes/*`, business logic under `/app/backend/services/*`, MongoDB via motor (`MONGO_URL`, `DB_NAME` from env).
- **Frontend** — React 19 + CRACO + Tailwind + framer-motion, served at port 3000. All API calls go through `REACT_APP_BACKEND_URL`.
- **Persistent background jobs** — `services/job_service.py` records every long-running task in the `jobs` Mongo collection (status, progress, phase, logs[], result, error). New work (`run_social_job`, `run_video_job`) is launched as **detached `asyncio.create_task`** from the route handler so the job survives the request lifecycle, browser close, and client disconnect. The UI re-attaches by polling `GET /api/jobs/{id}` (1.5 s) via `useJobProgress` and recalls the last in-flight `job_id` from localStorage. On mount, pages also query their `/jobs` list for any `queued|running` jobs to resume display.
- **Render deploy** — `render.yaml` at root, `.python-version` at root, `requirements.txt` mirrored at root, `backend/runtime.txt` fixed (`python-3.11.9`).

## What's been implemented (2026-05-14)
- **Existing codebase installed** — preserved `.env`s, ran `pip install -r requirements.txt`, `yarn install`, added missing `eslint-config-react-app@7.0.1` (was blocking webpack), services running clean via supervisor.
- **Render deploy fix**
  - `/app/render.yaml` — web service, rootDir=backend, build/start cmds, envVars stub.
  - `/app/.python-version` — `3.11.9`.
  - `/app/requirements.txt` — mirrored from backend/.
  - `backend/runtime.txt` — fixed typo (`pyhon` → `python-3.11.9`).
- **Social Content Agent (backend)**
  - `routes/social.py` (15 endpoints): generate (detached job), posts list/get/patch/delete/regenerate, profile get/save, logo upload+serve, jobs list, assets serve.
  - `services/social_content_service.py` — Claude `claude-sonnet-4-5-20250929` for structured plan JSON, OpenAI `gpt-image-1` for images, Pillow logo overlay (15% width, bottom-right), MongoDB `social_posts` collection.
- **Video Studio (backend)**
  - `routes/video.py` (12 endpoints): generate (Fal.ai detached job), upload mp4/mov/webm, clips list/delete/serve, jobs, timeline save/list/get, post-to-social.
  - `services/video_studio_service.py` — `fal-ai/cogvideox-5b` via `fal_client`. Downloads result mp4, stores under `backend/static/video/clips/`.
- **Social Page** (`pages/workspace/SocialPage.jsx`)
  - 40/60 desktop split → stacked mobile. Chat-style brief input, platform/duration/tone chips, profile drawer (niche, about, logo upload), live progress with logs, native post-calendar grid with Regenerate / Approve / Delete actions. Re-attaches to any in-flight job on mount.
- **Studio Page** (`pages/workspace/StudioPage.jsx`)
  - Header (Upload / AI Generate / Export MP4) + main video player + timeline strip + clip library sidebar. AI Generate drawer (prompt + style + duration). Post-to-Social modal creates a social_posts draft. Re-attaches to in-flight AI video jobs.
- **Sidebar nav** — added Social (Megaphone) + Studio (Film) items in `WorkspaceShell.jsx`.
- **Routes** — `/workspace/social` + `/workspace/studio` registered in `App.js`.
- **API helpers** — full social + video clients in `lib/api.js`; `useJobProgress` hook with persistent localStorage re-attach.
- **Testing** — 32/32 backend tests PASSED (iteration_6.json). Includes persistent-jobs survives-backend-restart verification.

## Verified end-to-end flows
- Social: generate "founder LinkedIn post" → Claude plan (10 s) → DALL-E image (15 s) → post visible in calendar with image, caption, hashtags; Regenerate produces fresh image+caption; Approve flips status.
- Studio: upload .mp4 → appears in Library → Add to Timeline → plays in player → Post to Social creates a social_post draft.
- Persistence: closing the tab during generation does NOT stop the job; reopening the page resumes progress display via localStorage recall + `/jobs` fallback.

## Next Action Items (P0 → P2)
- **P0 — User to push to GitHub** via the in-app "Save to Github" button. Render auto-deploy will then pick up `render.yaml`.
- **P0 — Add FAL_API_KEY** to `/app/backend/.env` to enable AI text-to-video (currently UI shows a clear "FAL_API_KEY not configured" notice in the AI Generate drawer).
- **P1 — Postiz native replacement** (per user choice: A. native build, no docker sidecars). Currently we schedule into MongoDB; auto-posting to Instagram/X/LinkedIn requires each platform's OAuth + Graph API tokens. Add `INSTAGRAM_ACCESS_TOKEN`, `LINKEDIN_ACCESS_TOKEN`, `TWITTER_*` envs + posting workers when user is ready.
- **P1 — Multi-clip MP4 stitching in Studio export** (currently exports the active clip directly). Browser-side: integrate `ffmpeg.wasm`; server-side: add a `routes/video.py` `/export` endpoint that uses system ffmpeg.
- **P1 — Mobile polish** at 390 px width — already responsive via tailwind `lg:` breakpoints but needs a swipe test on real device.
- **P2 — WebSocket push** instead of 1.5 s polling for progress (lower latency, lower load). Backend `chat_router` already has WS pattern to copy.
- **P2 — Logo position / size / opacity controls** for social image overlay.

## Personas
- **Founder operator** — wants weekly content + product demo videos without a marketing team.
- **Solo developer / indie hacker** — uses Studio for demo clips, Social for build-in-public posts.

## Environment
- Backend `.env`: `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `EMERGENT_LLM_KEY` (set), `FAL_API_KEY` (empty — user-supplied).
- Frontend `.env`: `REACT_APP_BACKEND_URL`, `WDS_SOCKET_PORT=443`, `ENABLE_HEALTH_CHECK=false`.
