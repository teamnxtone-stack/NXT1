## 2026-05-15 — Deep bolt.diy integration (single integrated app, not nested)

### Problem
After the iter9 migration the `/builder` page felt like two stacked products: NXT1's header on top, then bolt.diy's *whole* intro screen (logo + sidebar + "Where ideas begin" + "Guest User" + provider dropdown + its own chat composer) underneath. User demanded one unified app: NXT1 chat composer on the LEFT, bolt's Workbench (preview/code/terminal) on the RIGHT, no bolt chrome anywhere.

### What shipped
**Bolt sidecar — runs as a headless engine when `?headless=1`:**
- `app/components/header/Header.tsx` — adds `data-nxt1-bolt-header` so SCSS can hide it.
- `app/components/sidebar/Menu.client.tsx` — root motion.div gets `data-nxt1-bolt-menu` so it can be hidden.
- `app/styles/index.scss` — adds an `html[data-nxt1-headless='1']` block that hides `[data-nxt1-bolt-header]`, `[data-nxt1-bolt-menu]`, `#intro` (the welcome splash); sets `--header-height: 0px` so the Workbench fills the iframe edge-to-edge; transparent body so NXT1 chrome shows through.
- `app/root.tsx` — inline theme script flips `data-nxt1-headless='1'` when `URLSearchParams.get('headless')==='1'`.
- `app/components/chat/Chat.client.tsx` — in headless mode forces `chatStore.showChat=false`, `chatStore.started=true`, `setChatStarted(true)`, `workbenchStore.showWorkbench.set(true)` so the Workbench mounts immediately. Locks provider to Anthropic + model to `claude-sonnet-4-20250514`. Installs `window.__nxt1BoltBridge = { ready, append, stop, getMessages, getIsLoading, subscribe }` and posts `{type:'nxt1-bolt-messages', messages, isLoading}` to `window.parent` on every store update.
- `app/utils/constants.ts` — `DEFAULT_MODEL = 'claude-sonnet-4-20250514'`, `DEFAULT_PROVIDER` pinned to Anthropic.
- `app/lib/modules/llm/providers/anthropic.ts` — claude-sonnet-4-20250514 added as first static model.

**NXT1 — owns the entire left panel + drives bolt through the bridge:**
- `frontend/src/pages/BuilderPage.jsx` — full rewrite. Split layout: 46% (max 540px) chat panel left, flex-1 bolt iframe right. NXT1 chat panel has its own header (Workspace back, NXT1 wordmark, bell, "New tab" link), message bubble list, and composer (textarea, attach button, send arrow, "Claude Sonnet 4 · locked" caption). Bolt iframe loads `/api/bolt-engine/?headless=1&project={id}` without the `credentialless` attribute (it's same-origin; credentialless under COI would 403 module fetches). On mount calls `ensureCoiServiceWorker()` and shows a "Reload to enable terminal" pill if the SW just installed.
- Bridge polling + postMessage listener mirror bolt's message stream into NXT1 bubbles; new messages get auto-persisted via PUT to `/api/v1/builder/chat/{projectId}`.
- `stripBoltMetaHeaders()` cleans bolt's `[Model: …]\n\n[Provider: …]\n\n` prefix off user bubbles so they look native.

**Backend — Mongo-backed chat history:**
- `routes/builder_chat.py` — GET / POST / PUT / DELETE `/api/v1/builder/chat/{project_id}`. Collection `builder_chats: {project_id, messages:[{id,role,content,ts}], updated_at}`. Pydantic-validated, _id excluded.

### Verified via testing_agent iter10 (and re-verified after the credentialless fix)
- Backend persistence: 7/7 pytest pass (`/app/backend/tests/test_iter10_builder_chat.py`).
- Bolt proxy isolation regression-clean: COEP credentialless + COOP same-origin still set on both `/api/bolt-engine/` and `/api/bolt-engine/?headless=1`.
- Inside iframe: `window.crossOriginIsolated === true`, `window.__nxt1BoltBridge` is an object with `ready:true`, Workbench mounts (Code/Diff/Preview tabs, Files sidebar, Bolt Terminal with `~/project` prompt), `[data-nxt1-bolt-header]` is `display:none`, `#intro` is gone.
- Composer is enabled, "Claude Sonnet 4 · locked" caption shown.
- Workspace / Social / Studio / Memory / Leads / Notifications / Landing + chat bubble all unchanged.

### Critical fix found during iter10 testing
- Removed `credentialless="true"` from the iframe element in `BuilderPage.jsx`. The iframe is **same-origin** with the parent; once the COI service worker activates the parent, a credentialless attribute on a same-origin iframe causes sub-resource fetches to drop credentials and the proxy 403s the JS module chunks. Without the attribute the iframe inherits its isolation context from the COI-isolated parent and module loading works.

### Known follow-ups (deferred — explicitly told user)
- Full WebContainer filesystem snapshot round-trip to Mongo so a returning user gets the exact file state across devices. Today bolt persists in-browser IndexedDB; files survive within a tab + cross-reload but not cross-device.
- Replay persisted user prompts back into bolt's chat store on reopen (we currently only restore the bubbles in NXT1's panel — re-running bolt's pipeline on every reopen would burn the user's Anthropic budget, so by design we don't auto-resend).
- Silence remaining cosmetic console errors from bolt (HMR wss probe; `fetchConfiguredProviders` 404). Non-functional.

### Required for full end-to-end app generation
- The user must set `ANTHROPIC_API_KEY=...` in `/app/backend/.env` and restart `bolt-engine` (bolt reads it from `process.env`). Without it, sending a prompt installs the user bubble fine but bolt's `/api/chat` returns no completion.



## 2026-05-15 — Full bolt.diy builder migration (replaces native builder)

### What shipped
- Native builder UI (`ChatPanel`, `PreviewPanel`, `FileExplorer`, `BoltDiyOverlay`, …) **deleted**. Only `SheetOverlay.jsx` remains in `/app/frontend/src/components/builder/` (used by `SettingsSheet`).
- New `BuilderPage.jsx` is a single fullscreen iframe pointing at `/api/bolt-engine/` with `credentialless="true"` so the WebContainer can boot inside it without the parent page needing cross-origin-isolation.
- New `routes/bolt_proxy.py` reverse-proxies `/api/bolt-engine/{path}` → `http://127.0.0.1:5173/api/bolt-engine/{path}`. Forces `Cross-Origin-Embedder-Policy: credentialless` + `Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Resource-Policy: cross-origin` on every response so WebContainers boot through the public ingress even when CF strips bolt's own headers.
- Uses `httpx.AsyncClient.send(req, stream=True)` (the previous `client.request(...)` then `aiter_raw()` was the StreamConsumed bug surfaced in the handoff).

### bolt.diy sidecar changes (in `/app/services/bolt-engine/`)
- `vite.config.ts` — added `base: '/api/bolt-engine/'`, `remixVitePlugin({ basename: '/api/bolt-engine/' })`, and `server.hmr: false` (proxy doesn't tunnel WebSockets).
- `app/entry.client.tsx` — installs a global `window.fetch` interceptor that rewrites any same-origin URL starting with `/api/…` (other than already-prefixed `/api/bolt-engine/…`) to live under `/api/bolt-engine`. Without this every bolt-internal API call leaked into NXT1's FastAPI backend.
- `app/lib/stores/theme.ts` — `DEFAULT_THEME = 'dark'`.
- `app/root.tsx` — inline theme script defaults to `'dark'` instead of OS preference; favicon points at `/api/bolt-engine/favicon.svg`.
- `app/components/header/Header.tsx` — logo points at `/api/bolt-engine/logo.svg`.
- `app/styles/variables.scss` — dark-theme palette overridden: `--bolt-elements-bg-depth-1: #0F1117`, `--bolt-elements-bg-depth-2: #1A1D27`, `--bolt-elements-bg-depth-3: #232634`. Accent stays at `#3B82F6` (already `colors.accent.500` in `uno.config.ts`).
- `public/favicon.svg` + `public/logo.svg` — replaced with NXT1-branded SVGs (NXT badge + BUILDER wordmark).

### Verified via testing agent (iter9, 15/15 backend tests + Playwright)
- COEP/COOP headers survive the public Cloudflare ingress.
- Iframe boots end-to-end: `data-theme="dark"`, body bg = `rgb(15, 17, 23)`, NXT1 logo top-left, "Where ideas begin" welcome screen renders.
- Zero 5xx from NXT1 backend during the run.
- Regression-clean across `/workspace`, `/workspace/social`, `/workspace/studio`, `/workspace/memory`, `/workspace/leads`, public landing + chat bubble.

### Known cosmetic warnings (LOW; tracked but not blocking)
- Bolt's `fetchConfiguredProviders()` → 404 (its remix /api/* routes aren't all reachable through the proxy). Renders fine; user can still enter an API key via the UI.
- HMR ws probe shows two 403s per iframe load even with `hmr:false`. No functional impact.
- Pre-existing nested-button hydration warning in `NotificationCenter` (unrelated to this migration).

### Operational note
The bolt-engine supervisor entry can race when restarted — the parent `pnpm` exits but child `remix vite:dev` survives and holds port 5173, so the next start lands on 5174/5175 and the proxy 502s. Recovery: `sudo supervisorctl stop bolt-engine && pkill -9 -f "remix vite" && pkill -9 -f workerd && pkill -9 -f esbuild && sudo supervisorctl start bolt-engine`.



## 2026-05-15 — Platform polish pass (Phase H)

### Conversational chat gate (most critical fix)
- New `classify_intent(message, has_prior_messages)` in `routes/chat.py` — fast, deterministic classifier returning `build | edit | chat | ambiguous`. Greeting + question patterns short-circuit before the build pipeline ever fires.
- New `_conversational_reply_stream()` — small SSE stream that uses the provider chain to send a natural conversational reply, persists it as a normal assistant message, and signals `complete` with `intent: "chat"`.
- Frontend (`ChatPanel.jsx`): handles `start { mode: "chat" }`, accumulates `chunk { delta }` into a streaming assistant bubble, and finalises on `complete`.
- Verified: `"hi"` / `"thanks"` / `"can you explain how this works?"` all reply conversationally; `"build me a landing page..."` still drives the full build.

### Builder uploads — Photos vs Files (always visible)
- `ChatPanel.jsx`: two separate buttons + hidden inputs.
  - Photos: `accept="image/*"` (`Image` icon) — `data-testid="chat-photo-button"` / `chat-photo-input`.
  - Files: `accept="video/*,.pdf,.doc,.docx,.csv,.json,.txt,.md,.rtf,.xls,.xlsx,.ppt,.pptx,.zip"` (`Paperclip` icon) — `data-testid="chat-upload-button"` / `chat-file-input`.
  - Both buttons always rendered regardless of whether the user has typed.
- `routes/assets.py::upload_asset`: 8MB ceiling → 64MB; adds `kind` field on the asset record (`image | video | audio | pdf | document | data | archive | file`) so downstream pipelines can branch on type.

### Custom preview hostname (kill Emergent branding)
- `services/preview_service.py::public_origin()` default now `https://nxtone.ai` (was `nxtone.tech`).
- `build_url(slug, custom_host=...)` supports per-project custom hosts. Strips `http(s)://` and trailing `/` properly (previous `lstrip` was buggy).
- `make_initial()` / `refresh()` carry `custom_host` through.
- New `PreviewIn.custom_host` field in `routes/preview.py` — POST `/api/projects/{id}/preview` accepts `{"custom_host": "preview.client.com"}` and returns a URL rooted on that host.
- Verified: `preview.client.com` → `https://preview.client.com/p/{slug}`; `https://demo.brand.io` → normalised to `demo.brand.io`.

### Template variation (less repetitive AI output)
- Added a VARIETY RULE block to `services/ai_service.py` system prompt:
  - Forbids defaulting to the same hero pattern every build (lists alternates: left/right/center/split/full-image/video-bg/asymmetric).
  - Lists palette options (editorial-print, neo-brutalist, glass/aurora, monochrome graphite, terminal-green, sunset-coral, midnight-electric).
  - Instructs the model to let domain drive aesthetics; flags "dark gradient hero + 3 feature cards + CTA" as the failure mode.

### Homepage — Jwood positioning
- `LandingPage.jsx` subhead reworked to founder/private-platform tone.
- Added "No credits. No tokens. Just build." line under the subhead.
- Existing "A product of Jwood Technologies" signature preserved.

### Deferred (will need a follow-up phase)
- Light-mode pass is partial — added safety-net CSS earlier (overrides `text-white`, `text-zinc-*` Tailwind classes) but a per-component spacing/loading audit is still pending.
- Full mobile-builder reformat: only the side-menu + bottom overflow patches are done; a dedicated mobile layout (collapsible panels, no broken overflow) requires deeper component work.
- Web-asset pulling during generation (image search, font lookup, real demo content): not yet wired — would require a tool-call layer on top of the LLM.
- Auto-fill empty input boxes with starter content across the entire app: only the workspace prompt suggestions chip-bar exists today; pulling generated defaults into every empty composer needs a separate pass.
- Frontend page for agent threads (`/workspace/agents`): backend is durable + verified, but no React surface yet.


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
