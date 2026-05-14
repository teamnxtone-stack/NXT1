## 2026-05-14 — Phases F + G shipped

### Phase G — Durable agent_runs worker
- New `services/agent_runs_worker.py` — `execute_run(run_id)` drives a queued run via the shared provider registry (Claude / OpenAI / Emergent / etc.), streams tokens, persists output + assistant message, and emits a bell notification on terminal transition.
- Cooperative cancel: every 10 chunks checks `status == "cancelling"` and bails clean.
- `spawn_run(run_id)` registers each task in `_RUNNING_RUNS` so the recovery sweeper doesn't double-spawn.
- `resume_orphaned_runs()` mirrors `resume_orphaned_workflows` — sweeps Mongo every 5min for `queued`/`running` runs with no live task, re-spawns them, fails anything >24h stale.
- `routes/agent_threads.py` now calls `spawn_run` from `create_thread` (initial message), `create_run`, and `fork_run`.
- `server.py::_workflow_recovery_loop` also calls `resume_orphaned_runs` on each tick.
- Verified: created a thread with `first_message="Say HELLO and only that"` → 8s later run status=completed, output=`HELLO`, logs show start + completion.

### Phase F — Vercel + Coolify + Caddy auto-domain
- New helpers in `services/domain_service.py`:
  - `vercel_attach_domain(project_name, hostname)` → `POST /v10/projects/{name}/domains` with the bearer token; surfaces DNS instructions from `/v6/domains/{name}/config`. 409 (already attached) treated as success.
  - `vercel_remove_domain` — clean teardown on domain delete.
  - `coolify_attach_domain(hostname)` → `POST /api/v1/applications/{uuid}/domains` against `COOLIFY_BASE_URL`.
  - `detect_deploy_host_provider()` returns `vercel | coolify | caddy | manual` based on env config.
- `routes/domains.py::add_domain` now also calls the right platform attach after Cloudflare DNS setup, storing `deploy_provider` and `platform_meta` (vercel verified flag, DNS instructions, errors) on the domain record.
- `routes/domains.py::remove_domain` mirrors removal on Vercel.
- New `GET /api/domains/config` — surfaces `{deploy_provider, vercel, coolify, cloudflare_dns, manual}` so the frontend can render the right "Auto-attach" CTA copy.
- Env vars to set on user's host: `VERCEL_TOKEN` (or `COOLIFY_API_TOKEN` + `COOLIFY_APP_UUID` + optional `COOLIFY_BASE_URL`, or `CADDY_AUTO_HTTPS=1` for self-hosted Caddy auto-HTTPS).

### Verified
- `GET /api/domains/config` returns `{deploy_provider: "manual", vercel: false, coolify: false, ...}` (no keys in preview env — correct).
- Agent run end-to-end: create thread + first_message → poll → output stored.


## 2026-05-14 — Phases A–E shipped (stabilization brief)

### Phase A — Stop the bleeding
- Removed legacy `google-generativeai` from both `requirements.txt` files (kept only `google-genai`).
- Disabled the legacy `useAgentActivityWatcher` that was firing random bottom toasts on every page (now a no-op shim; superseded by the bell-icon Notification Center).
- Mobile fix on `SocialPage.jsx`: parent `h-full min-h-0` → `lg:h-full lg:min-h-0` so mobile lets the page scroll naturally instead of locking columns. Right calendar pane gains `pb-24 lg:pb-7` so the last post isn't covered by the safe-area composer.
- Builder chat: when `autoDeployment.status === "deployed"`, the green "Deploy Now" button swaps to "Connect Domain" + an "Open live" link to the deployed URL. New props: `onConnectDomain`, `deployedUrl` plumbed from `BuilderPage`. data-testid: `chat-connect-domain-button`, `chat-open-live-button`.
- Homepage subhead reworded: founder/MVP-first, dropped enterprise-y "AI-native platform" phrasing.

### Phase B — Notification Center + unified Agent Threads
- **New backend route** `routes/notifications.py` (`/api/notifications/*`) with `emit()` helper. Stored in Mongo collection `notifications` with `{id, user_id, kind, title, body, link, read, created_at}`.
- **Notification emitters wired**: `workflow_service.py` (build_complete, build_failed) and `social_content_service.py` (social_generated).
- **New frontend component** `NotificationCenter.jsx` — bell icon, unread badge, slide-down panel with mark-read / mark-all-read / navigate-to-link. Mounted in `WorkspaceShell` header AND `builder/AppHeader.jsx` so it's reachable from every page. Polls `/list` every 30s.
- **New backend route** `routes/agent_threads.py` (`/api/agents/threads`, `/api/agents/runs`) — durable task threads with message history, status, logs, outputs. Endpoints: create / list / get / patch (rename/pin/archive) / delete; runs: create / list / get / cancel / fork (with parent_run_id + message-history carry-over).

### Phase C — Durable workflows (resume after tab close)
- Added `_workflow_recovery_loop()` to `server.py` startup hooks. Sweeps Mongo every 5min for workflows stuck in `running`/`queued` with no live in-process task and re-spawns them.
- Workflows in `_RUNNING_TASKS` registry — fresh `start_workflow()` calls register their task too so the sweeper doesn't double-spawn.
- 24h stall → auto-fails (so the sweep doesn't churn forever).

### Phase D — Premium UI registry + pipeline discipline
- Verified `data/ui_registry.json` already lists shadcn / Magic UI / Aceternity / Origin UI / framer-motion / R3F — generator pulls from this.
- Verified `services/providers/registry.py` already prioritizes Claude (`anthropic`) first for code-generation / architecture / debug tasks.
- Verified `streamReducer.js` already serializes phases (inferring → foundation → planning → editing → routes → validating → repairing → preview → deploy).
- No code changes here — system was already aligned to the brief's spec.

### Phase E — URL Revamp / Import
- **New service** `services/url_import_service.py` — fetches a live URL (httpx, BeautifulSoup), extracts brand + hero + nav + sections + palette + fonts into a structured `blueprint`.
- **New route** `POST /api/projects/import/url` — creates a project seeded with the blueprint (stored under `analysis.revamp_blueprint`) so the builder can revamp on first chat. Frontend: new "From URL" tab in the Import dialog on `WorkspaceHome`, calls the route with `mode: "revamp"`.

### Verified end-to-end
- `curl /api/notifications/list` → returns list + unread count.
- `curl /api/agents/threads` → create + run lifecycle (queued state persisted).
- `curl /api/projects/import/url` with `example.com` → returns blueprint with hero title "Example Domain", sections extracted.
- Workflow start → 5s later notifications list shows `build_complete` notification with link `/builder/{id}`.
- Screenshot: bell mounts in workspace header, panel opens on click, "Build ready" notification visible inside.


## 2026-05-14 — Clean break from Emergent + UX fixes

### Removed Emergent coupling (per user request — self-hosting with own keys)
- Removed `emergentintegrations==0.1.0` from `requirements.txt` (both root + backend).
- Removed `--extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/` from `render.yaml` build command.
- Removed `EMERGENT_LLM_KEY` entry from `render.yaml` env vars list.
- Refactored `services/social_content_service.py`:
  - Dropped `LlmChat`, `UserMessage`, `ImageContent`, `OpenAIImageGeneration` imports
  - Added local `_claude_chat()` using `litellm` directly with vision support
  - Added local `_openai_image()` using the standard `openai.AsyncOpenAI` SDK
  - Both helpers prefer the user's own `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` and only fall back to the Emergent proxy if neither is set (dead code path on user's server).
- Removed "Emergent universal key" string from job log messages.

### Fixed: Build pipeline "Approve & deploy" popup
- `services/workflow_service.py::node_deployer` now auto-completes (status=`completed`, requires_approval=False) instead of pausing at `waiting`. Builds finish in the background — no intrusive popup.
- Removed `<ResumeWorkflowChip>` mount from `components/builder/ChatPanel.jsx`.

### Fixed: Light mode unreadable text
- `components/premium/ActivityStream.jsx`: swapped hardcoded `rgba(255,255,255,*)` text colors for `var(--nxt-fg)` / `var(--nxt-fg-dim)` / `var(--nxt-fg-faint)` so they theme correctly.
- `components/builder/ChatPanel.jsx::NarrationStream`: replaced Tailwind `text-zinc-200` with `var(--nxt-fg-dim)`.
- Added light-mode safety-net rules in `index.css` that override any remaining hardcoded white text classes (`text-white`, `text-zinc-200/300/400`, `text-white/40-80`) so future regressions can't hide content on cream backgrounds.

### Verified
- `curl /api/workflows/start` → returns `status: completed` immediately, no waiting state.
- Social post generation end-to-end: 17 posts in calendar, all with images, captions, hashtags.
- Builder chat streaming works via `EMERGENT_LLM_KEY` in preview AND would work via real `ANTHROPIC_API_KEY` on user's server.
- Light mode builder screenshot: dark legible text on cream background, no popups.


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
