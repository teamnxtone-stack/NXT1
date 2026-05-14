# NXT1 — Product Requirements Document

## Original problem statement (verbatim)
> Install my existing app, then add (per nxt1_social_video_render_prompt.pdf): Render deploy fix, AI Social Media Content Agent, Video Studio. Builders/agents must keep running even if browser closed. Workspace login password is 555. Build the full OAuth + posting infrastructure now (I'll paste platform creds later — auto-posting should just work the moment I add them).

## Architecture
- **Backend** — FastAPI + uvicorn (8001) + MongoDB via motor. Modular routers under `/app/backend/routes/*`, services under `/app/backend/services/*`.
- **Frontend** — React 19 + CRACO + Tailwind + framer-motion (port 3000). API calls via `REACT_APP_BACKEND_URL`.
- **Persistent execution** — `services/job_service.py` records every long task in Mongo `jobs`. New work is launched as detached `asyncio.create_task` so the job survives request lifecycle, browser close, client disconnect. UI re-attaches via `useJobProgress` (poll + localStorage recall).
- **Background scheduler** — `services/social_scheduler.py` runs forever on the FastAPI event loop (started in `on_startup`). Every 60 s it (a) publishes posts whose `scheduled_at <= now` if a connection exists, (b) fires weekly auto-pilot for users whose enabled + day-of-week + hour match.
- **OAuth** — `services/social_publishing_service.py` builds platform-specific authorize URLs, exchanges codes for tokens (Meta Graph v21, LinkedIn OIDC, X OAuth 2.0 + PKCE), and publishes (IG Graph media+media_publish, LinkedIn UGC, X v2 tweets). All gated by env-var presence; no platform code runs until creds are pasted.
- **Render deploy** — `render.yaml` at root, `.python-version` at root, mirrored `requirements.txt` at root.

## What's been implemented (2026-05-14)

### Foundation
- Installed existing NXT1 zip, preserved `.env`s, fixed missing `eslint-config-react-app@7.0.1`. Backend + frontend run clean via supervisor.

### Render deploy fix
- `/app/render.yaml`, `/app/.python-version`, `/app/requirements.txt` (root mirror), `backend/runtime.txt` typo fix.

### Workspace auth
- `APP_PASSWORD=555` (admin/legacy gate at `/access`).
- `JWT_SECRET` pinned (no more dev default).

### Social Content Agent
- **Backend**: `routes/social.py`, `services/social_content_service.py` — Claude `claude-sonnet-4-5-20250929` plan JSON + OpenAI `gpt-image-1` images + Pillow logo overlay. Mongo `social_posts`, `social_profiles`.
- **Frontend**: `pages/workspace/SocialPage.jsx` — chat brief + tone/platforms/duration chips + profile drawer + native post calendar with **Regenerate / Approve / Schedule / Post Now / Delete** actions per card. Persistent job progress with localStorage re-attach.

### Social OAuth + posting infrastructure (NEW)
- **Backend**: `routes/social_oauth.py`, `services/social_publishing_service.py`
  - `GET /api/social/oauth/status` — what's configured server-side
  - `GET /api/social/oauth/{platform}/start` — auth URL (with PKCE for X)
  - `GET /api/social/oauth/{platform}/callback` — browser-redirect; exchanges code → stores token in `social_connections`
  - `GET /api/social/connections`, `POST /api/social/connections/{platform}/disconnect`
  - `POST /api/social/posts/{id}/publish` (now) and `/schedule`
- **Frontend**: `components/social/ConnectionsAndAutopilot.jsx` — Connect/Disconnect rows + "Server creds not configured" hint when env vars missing.

### Weekly Auto-pilot (NEW)
- **Backend**: `services/social_scheduler.py` — async loop, ticks every 60 s. Reads `social_autopilot` docs (enabled + cadence_day + cadence_hour + brief). On match (and last_run > 6 days ago), kicks off the same detached generation job used by `/api/social/generate`.
- `GET / POST /api/social/autopilot` to read / write the config.
- **Frontend**: Autopilot toggle + brief + day + hour in the Social page brand drawer.

### Video Studio
- **Backend**: `routes/video.py`, `services/video_studio_service.py` — Fal.ai `cogvideox-5b` text-to-video (detached job), mp4/mov/webm upload, clip CRUD, timeline save, post-to-social handoff.
- **Frontend**: `pages/workspace/StudioPage.jsx` — header (Upload / AI Generate / Export MP4), video player, timeline strip, library, AI Generate drawer, Post-to-Social modal.

### Sidebar
- `WorkspaceShell.jsx`: Home / Apps / **Social** / **Studio** / Agents / AgentOS / Account.

### Mobile polish
- Verified responsive at 390 px. Social: stacked single column; chips wrap; PostCard's 5-button action row uses 44 px touch targets via `IconBtn`. Studio: header buttons wrap; player + timeline + library stack.

## Testing
- **Iter 6** — 32/32 PASS (Social + Video core, detached jobs, regenerate, FAL gating, persistence across restart).
- **Iter 7** — 30/30 PASS (password 555, OAuth status/start/callback gating, connections, autopilot CRUD, scheduler safety with no connection).

## Next Action Items
- **P0 — Push to GitHub** via the "Save to GitHub" button. Render auto-deploys via `render.yaml`. Set these env vars on Render: `MONGO_URL`, `DB_NAME`, `EMERGENT_LLM_KEY`, `APP_PASSWORD`, `JWT_SECRET`, `PUBLIC_BACKEND_URL` (your Render URL), and the platform creds below.
- **P0 — Paste platform credentials** into `/app/backend/.env` (and Render env) — full list in `/app/memory/test_credentials.md`. The moment any pair is set + backend restarts, the corresponding Connect button activates.
- **P1 — Multi-clip MP4 stitching** in Studio export (currently downloads active clip). Needs ffmpeg.wasm or a server-side ffmpeg endpoint.
- **P1 — LinkedIn image posting** — current UGC post is text-only; for image uploads we need the `assets?action=registerUpload` flow (deferred).
- **P1 — Instagram Reels / X video** posting via /media + /media_publish — currently only image posting wired for IG; X is text-only.
- **P2 — WebSocket push** instead of 1.5 s polling for progress.
- **P2 — Logo overlay controls** (size / position / opacity).
- **P2 — Refresh-token rotation** for X (refresh tokens issued but not yet auto-rotated).

## Personas
- **Founder operator** — weekly content + product demos without a marketing team.
- **Solo developer / indie hacker** — Studio for demos, Social for build-in-public.

## Environment
- Backend `.env`: `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `EMERGENT_LLM_KEY` (set), `APP_PASSWORD=555`, `JWT_SECRET`, `PUBLIC_BACKEND_URL`, plus empty placeholders for: `FAL_API_KEY`, `META_APP_ID`, `META_APP_SECRET`, `X_CLIENT_ID`, `X_CLIENT_SECRET`, `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`.
- Frontend `.env`: `REACT_APP_BACKEND_URL`, `WDS_SOCKET_PORT=443`, `ENABLE_HEALTH_CHECK=false`.
