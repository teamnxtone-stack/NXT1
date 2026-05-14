# NXT1 — Product Requirements Document (PRD)

## Original Problem Statement
"I'm going to send over the file/project as it currently is. For now, please keep everything exactly as-is and do not change or restructure anything yet. I just want you to load it in and preserve the current functionality/UI. After that, we'll make a few targeted edits and refinements step-by-step rather than changing things all at once."

After load-in, the user requested 4 tracks all delivered in one session:
- **A.** Premium UI quality jump (Magic UI / Aceternity / Origin UI retrieval)
- **B.** Durable workflows (LangGraph) with planner→architect→coder→tester→debugger→deployer
- **C.** Deploy + domain OS (Caddy auto-SSL + Cloudflare DNS via user's own token)
- **D.** Self-healing sandboxed build loop with bounded retry

## Architecture & Tech Stack
**Backend:** FastAPI (`/app/backend/server.py`) — 39 modular routers under `/app/backend/routes/`. Mongo via motor. LangGraph for durable workflows. LiteLLM-powered Provider OS routing across Claude / OpenAI / Gemini / xAI / Groq / DeepSeek / OpenRouter / Emergent.

**Frontend:** React 19 + CRACO + Tailwind + shadcn/ui (30+ Radix primitives) + Framer Motion 12 + WebContainers. Routes under `/app/frontend/src/pages/` and shared workspace shell in `/app/frontend/src/components/workspace/`.

**Storage:** MongoDB (motor). LangGraph state persisted in `db.workflows` collection.

**Auth:** JWT (HS256) + `APP_PASSWORD` admin login + per-user (`db.users`) Emergent-managed Google OAuth.

## User Personas
1. **Founder / Builder** (primary) — prompts NXT1 to ship an MVP, runs preview, attaches their domain.
2. **Operator / Self-hoster** — wants to detach from Emergent infra (BYO Cloudflare token, BYO Caddy, BYO provider keys).
3. **Admin** — manages access, secrets, audit, GitHub OAuth.

## Core Requirements (static)
- No pure black backgrounds; warm cream light mode; carbon graphite dark mode.
- All third-party integrations gated by env vars (placeholder-safe).
- No raw provider/runtime traces ever shown in UI.
- Mobile-first builder UX; cinematic agent-coded ActivityStream.
- Provider OS portable: env-var aliases supported, readiness probe at `/api/system/ready`.

## What's Been Implemented (rolling log)

### Pre-load baseline (Phase 1 → 11W5, shipped before this session)
Multi-provider AI routing, scaffolds catalog (12 templates), GitHub OAuth, ZIP import, streaming chat w/ failover, autofix routes, cinematic UI, light+dark theme, workspace shell, project memory, system diagnostics.

### 2026-01-15 — Phase 20: Four-Track Operations Pass ✅
**Track A — Premium UI Registry**
- `/app/backend/data/ui_registry.json` — 6 packs (shadcn / Magic UI / Aceternity / Origin UI / Framer Motion / R3F) and **17 curated blocks** with `ai_hint` annotations.
- `/app/backend/routes/ui_registry.py` — `GET /api/ui-registry?kind=&pack=&tag=`, `/directive`, `/blocks/{id}`.
- `services/agents.py` `FrontendAgent` system prompt now embeds the directive so generations cite block ids.
- Frontend gallery: `components/workspace/UIBlockGallery.jsx` with pack + kind filters.

**Track B — Durable Workflows (LangGraph)**
- `/app/backend/services/workflow_service.py` — StateGraph (planner → architect → coder → tester → debugger → deployer) with Mongo persistence on `db.workflows`, bounded retry on tester failure routing through debugger, human-in-the-loop pause at deployer.
- `/app/backend/routes/workflows.py` — `POST /api/workflows/start`, `GET /list`, `GET /{id}`, `POST /{id}/resume`, `POST /{id}/cancel`.
- Frontend: `components/workspace/WorkflowsPanel.jsx` — status chips, expandable history with agent-coded badges, approve / cancel actions, 4s polling for non-terminal items.

**Track C — Hosting OS (Caddy + Cloudflare)**
- `services/hosting/caddy_service.py` — Caddyfile generator with HSTS / security headers + docker-compose snippet + install steps.
- `services/hosting/cloudflare_user.py` — per-user CF token encrypted at rest with Fernet (key derived from `JWT_SECRET` or `CF_TOKEN_KEY`), verify, list zones, attach DNS record.
- `routes/hosting.py` — `POST /caddy/generate`, `GET /caddy/install-guide`, `POST /cloudflare/connect`, `GET /cloudflare/status`, `GET /cloudflare/zones`, `POST /cloudflare/dns`, `POST /cloudflare/disconnect`, `GET /readiness`.
- Frontend: `components/workspace/HostingOS.jsx` — readiness checklist + Cloudflare connect form + Caddy generator with copyable output.

**Track D — Sandboxed Self-Heal Build Loop**
- `services/runner_service.py` — tmp-dir sandbox (`/tmp/nxt1-runner/...`), `start_sandbox`, `materialize_files` (path-traversal guarded), `run_command`, `detect_build_command` (package.json / requirements.txt / index.html smoke checks), `self_heal_loop` async-generator with bounded retry + DebugAgent patch proposal between attempts, `quick_build` one-shot.
- `routes/runner.py` — `GET /api/runner/config`, `POST /api/runner/projects/{id}/quick-build`, `POST /api/runner/projects/{id}/self-heal` (SSE stream).
- Frontend: `components/workspace/SelfHealPanel.jsx` — attempt counter, agent-coded event log, max-attempts selector.

**Operations page**
- New canonical route `/workspace/operations` with 4 tabs (Premium UI / Workflows / Hosting / Self-Heal) — `pages/workspace/WorkspaceOperations.jsx`.
- Drawer entry "Operations" wired in `WorkspaceShell`.
- `WorkspaceDomains` extended to include `HostingOS` under the existing HostingPicker.

**Operations integration (2026-01-15 evening — combined per user feedback)**
- Password changed to `555`.
- Removed the standalone "Operations" entry from the workspace drawer — the new capabilities are now woven into the existing builder flow.
- `ToolsDrawer` extended with 3 new tools next to Overview / Deploy / Domains / DB:
  - **Build pipeline** — opens `WorkflowsPanel` scoped to the current `projectId`
  - **Self-heal** — opens `SelfHealPanel` scoped to the current `projectId`
  - **Premium UI blocks** — opens `UIBlockGallery`
- `WorkflowsPanel` extended to accept `projectId` prop and auto-filter to that project's workflows.
- `WorkspaceHome.handleSubmit`, `WorkspaceHome.handleStartFromTemplate`, and `DashboardPage.handleBuild` now call `startWorkflow(...)` immediately after `createProject(...)` so the durable pipeline auto-starts whenever a user begins a new app.

**Phase 21 — Chat-stream reconciliation + Vendored block sources (2026-01-15 late)**
- **Workflow reconciliation:** `services/workflow_service.reconcile_coder_phase(project_id, files_count)` looks up the most recent non-terminal workflow for a project, flips the in-flight `coder` phase entry to `done`, appends a "Files reconciled from chat stream" history record, re-runs the tester check against the now-real persisted files, and advances to the deployer phase awaiting approval. Hooked into both `/chat/stream` success path (emits a `workflow_reconciled` SSE event) and the non-streaming `POST /chat` (returns `workflow_reconciled` in the JSON response). Means: as soon as the chat stream finishes generating an app, the Build pipeline panel inside the Builder Tools updates from "Builder handoff complete" → "Build healthy — awaiting deploy approval" without any user action.
- **Physically vendored premium UI block sources** — 8 React files in `/app/frontend/src/components/ui/blocks/` covering all 17 registry block ids:
  - `SpotlightHero.jsx`, `BentoGridHero.jsx`, `BackgroundBeamsHero.jsx`
  - `ShineBorderCard.jsx`, `ThreeDPinCard.jsx`
  - `LogoMarquee.jsx`, `OrbitingCircles.jsx`, `AceternityBento.jsx`
  - `Primitives.jsx` — AnimatedGradientText, TypingAnimation, DotPattern, WavyBackground, Meteors, SearchWithShortcut, PasswordStrengthInput
  - `R3FFallbacks.jsx` — ParticleField, AnimatedGlobe (CSS-only fallbacks; real R3F emitted by AI into generated apps)
  - `index.js` — barrel export + `BLOCK_MAP` + `getBlockComponent(id)` lookup
- New backend endpoints on `routes/ui_registry.py`:
  - `GET /api/ui-registry/implemented` — list of vendored block ids
  - `GET /api/ui-registry/blocks/{id}/source` — returns the raw JSX source as `text/plain` so AI agents can drop the verbatim component into generated apps
  - `GET /api/ui-registry/blocks/{id}` annotated with `implemented: true/false` + `source_url`
- `UIBlockGallery` adds **"Live preview"** button per implemented block opening a full-screen modal that actually renders the component in-page.
- `FrontendAgent` system prompt updated to instruct the AI to copy vendored sources into generated apps' `src/components/ui/blocks/` directory + cite block ids in `// nxt1-block:` comments.

**Phase 22 — AgentOS Command Center (2026-01-15 late) + 5 iter4 bug fixes**

Bug fixes:
- `routes/projects.py` — now persists `prompt` on the project doc + surfaces it on `ProjectFull`; auto-starts the durable workflow on project creation (iter4 #2, #5).
- `services/deployment_service.py` — `InternalProvider` no longer fails on Next.js / React scaffolds; synthesises a static preview shim with a clear "redeploy to Vercel for SSR" warning (iter4 #4).
- `services/ai_service.py` — `_validate_files` accepts incremental edits when current files already have an entry; merges partial responses into existing file set (iter4 #3).
- `services/providers/task_routing.py` — `suggest_for_task` now returns `model_family` + `transport` so the UI shows "anthropic / claude-sonnet-4.5 (via emergent)" instead of just "emergent" (iter4 #1).

AgentOS:
- `services/agentos_runner.py` — in-process Celery-shape task runner with MongoDB persistence, asyncio.Queue WebSocket fan-out, full task lifecycle (queued → running → done/failed/cancelled). Drop-in path to real Celery + Redis (see `docker-compose.agentos.yml`).
- `services/agentos_agents.py` — 4 working agents registered: **custom** (Claude+DDG+web fetch, the OpenHands shape), **job_scout** (JobSpy real install), **founders_scout** (Reddit JSON + GitHub Search), **social_strategist** (Claude → Postiz REST when configured).
- `routes/agentos_v2.py` — REST + WebSocket surface: `/api/agentos/{agents,tasks,tasks/{id},tasks/{id}/cancel,stats}` + `WS /api/agentos/ws/tasks/{id}`.
- `pages/AgentOSDashboard.jsx` — full redesign at `/agentos`: dark navy theme (#0F1117 bg, #1A1D27 cards, #3B82F6 accent), sidebar on desktop, 5-tab bottom nav on mobile, header with approvals bell badge + voice button. 9 pages (Home, Chat, Jobs, Resume, Social, Founders, Agents, Approvals, Settings). Live activity feed polls every 6s. New-task modal with example library. Live WebSocket-driven task detail with step-by-step log + result markdown.
- `docker-compose.agentos.yml` — Postiz + Resume-Matcher + Redis + Postgres sidecars (LiveKit commented out behind env vars).
- `SELF_HOSTING.md` rewritten with full env table + production checklist.
- `_deps.py` — added `verify_token_value()` for WebSocket-auth-via-query.

**End-to-end verified:** Custom agent completed a real 14-step research task ("top agent frameworks") with web search via DDG, page fetching, and Claude synthesis. Produced a polished markdown report. Screenshot confirms the dashboard renders the live log + result in-page.

**Backend test coverage**
- 22/22 pytest pass in `/app/backend/tests/test_phase20_four_tracks.py`.
- All four tracks + regression on `/system/ready`, `/auth/login`, `/scaffolds`, `/ai/providers`.

## Prioritised Backlog

### 2026-05-14 — Phase 23: AgentOS Theme Unification + Resume Tailor + Self-Host Hardening ✅
- **Resume Tailor agent** shipped end-to-end natively (no Docker sidecar): `services/agentos_agents.run_resume_tailor` — pure-Python keyword extraction (frequency + skill-hint regex + bigrams), cosine similarity, 60/40 weighted ATS score, plus 2 Claude calls (tailored rewrite + coach suggestions). PDF / DOCX / TXT upload via `POST /api/agentos/resume/extract` (pdfplumber + python-docx). UI: full Resume tab on the AgentOS dashboard with score gauges, matched/missing keyword pills, tailored markdown preview, copy + .md download.
- **Theme unification.** AgentOS dashboard now uses the same `--nxt-bg / --nxt-surface / --nxt-accent / --hairline / --nxt-fg-*` CSS vars as the rest of NXT1, so it inherits carbon graphite (dark) + warm cream (light) automatically. All 100+ hardcoded `#0F1117 / #1A1D27 / #3B82F6 / rgba(255,255,255,...) / rgba(0,0,0,...)` literals migrated.
- **Prominent back-arrow** at top-left of `/agentos` header (`data-testid="agentos-back"`). Uses smart fallback: `navigate(-1)` if browser history exists, else `/admin`.
- **/agentos wrapped in AuthGate** so the dashboard now requires auth (previously 401'd on initial mount).
- **Hero polish.** Counters strip (running / done-today / all-time / failed) with pulse animation when work is in flight; agent cards got glow-on-hover + `Open →` CTAs; activity feed routes each item to its agent tab.
- **NaN-safe runner.** `agentos_runner._sanitize()` recursively strips `NaN/Infinity/-Infinity` from any task document before it hits the JSON encoder. Was causing `Out of range float values are not JSON compliant` 500s on `GET /api/agentos/tasks` whenever a JobSpy task with `salary_min: NaN` lived in the DB. JobSpy adapter also pre-cleans values now (`_clean()`).
- **Self-host hardening.** `EMERGENT_BASE_URL`, `EMERGENT_STORAGE_URL`, `AGENTOS_LLM_MODEL` env vars now override the previously-hardcoded Emergent endpoints (`agentos_agents._llm_call`, `storage_service.STORAGE_URL`). `SELF_HOSTING.md` rewritten with the 5-agent matrix + diff for removing the `emergentintegrations==0.1.0` pin from `requirements.txt`. `.env.example` added at repo root.
- **Test coverage.** Iter-6 added `/app/backend/tests/test_iter6_agentos_full.py` — 14/14 passing (auth, all 5 agents end-to-end, app-builder create+workflow auto-start, ui-registry regression, resume-extract happy + reject paths). Together with `test_phase20_four_tracks.py` (22/22) and `test_resume_tailor.py`, the regression baseline is solid.

### P1 — next session
- Wire the streaming chat pipeline to **emit `workflow_id` events** so the Workflows panel auto-reconciles the coder phase as the chat completes (currently coder phase records "handoff").
- **Magic UI / Aceternity component packs** physically dropped into `/app/frontend/src/components/ui/blocks/` so the registry resolves to real React components, not just manifest entries.
- Builder page integration: show **SelfHealPanel** as a side drawer when a runtime error is detected.

### P2
- Docker runner mode for `runner_service` (currently `mode=subprocess`).
- Repo browser UI for GitHub import (11W6-A queued from earlier roadmap).
- Real Cloudflare DNS attach button inside `/workspace/domains/{id}` flow that uses the saved user token.
- LangGraph checkpointer migration to an officially supported store (currently using a custom Mongo persistence layer per workflow document).

### P3
- assistant-ui chat-history sidebar (from PDF research doc).
- Master Resume workflow if user picks that vertical.

## Test Credentials
See `/app/memory/test_credentials.md`.

## Next Action Items (post-session handoff)
1. Try the new `/workspace/operations` page in your browser.
2. To enable full premium-UI generation end-to-end: drop a real Anthropic/OpenAI key into `/app/backend/.env` (Emergent key is already there as fallback).
3. To test Cloudflare attach with a real domain: create a token at https://dash.cloudflare.com/profile/api-tokens with Zone:DNS:Edit and paste into the Hosting tab.
