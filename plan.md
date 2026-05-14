# NXT1 — Unified Cinematic Redesign + Infrastructure Hardening (Updated Plan)

## 1) Objectives
- Deliver a **single cohesive** Carbon-Graphite OS across landing, auth, workspace, builder, preview, deployment, and admin surfaces.
- Enforce **NO pure black** (`#000` / `bg-black`) anywhere; use matte Carbon Graphite surfaces only.
- Ensure **Light Mode is warm + premium** (cream/tan; **never pure white as a base**), with soft graphite typography and clear surface separation.
- Make NXT1 feel like a **premium, cinematic, AI-native operating system** (ChatGPT/Claude/Raycast vibes) — not a developer dashboard.
- Keep the system **portable, self-hostable, production-ready**:
  - **No hardcoded credentials**.
  - Dev environment may use Emergent LLM key as temporary fallback.
  - User-owned keys/tokens (LLM/OAuth/deploy) must cleanly override via env vars.
- Production UX quality bar:
  - **Never show raw backend/provider traces** (LiteLLM, stack traces, JSON dumps, budget errors) to the user.
  - **Never show raw generated-app runtime overlays** in preview; crashes must be masked behind a calm, actionable NXT1 error state.
  - Errors must render as calm, actionable UX with retry paths.
- Evolve the platform as one coordinated pass across:
  - **Track A**: Multi-provider LLM routing + failover + metadata + persistence.
  - **Track B**: Cinematic AI-native UX states (thinking → generating → files → preview → deploy).
  - **Track C**: OAuth (Google/Apple/GitHub) UI + routing logic + account linking readiness (**placeholder-safe until keys**).
  - **Track D**: Intelligent prompt → project inference + scaffolding + internal template catalog.
  - **Track E**: Hosting / Domains OS (Vercel/Railway/Netlify/Custom) architecture + UX (**catalogue + placeholder-safe wiring**).
  - **Track F**: Multi-agent orchestration visibility (planner/builder/tester/deployer) without breaking single-agent flows.
  - **Track G (Phase 11+)**: GitHub import/ZIP ingestion becomes a flagship feature (“drop anything in, NXT1 understands it”).
  - **Track H (Phase 11+)**: Preview system polish + **NXT1-only branding** on all share links.

**Status (as of now)**
- ✅ UI/UX baseline: Landing + Workspace + Builder surfaces cohesive and graphite-compliant.
- ✅ Material system: Carbon Graphite tokens in `index.css`; pure black eradicated.
- ✅ Light Mode foundation: warm cream palette added; no pure white pages.
- ✅ Workspace Home: fullscreen composer only; Recents removed; hamburger-only shell.
- ✅ Cinematic UX: ActivityStream/orchestration patterns shipped and **agent-color-coded**.
- ✅ Provider OS: multi-provider routing + model picker cockpit.
- ✅ OAuth foundation: backend routes exist + frontend states; GitHub OAuth configured.
- ✅ Inference + scaffolding: prompt→framework inference + scaffold injection.
- ✅ BuilderPage / ChatPanel overhaul shipped: Builder light mode fixed; raw provider errors eliminated.
- ✅ Preview iframe runtime error boundary shipped: runtime overlays masked with friendly NXT1 crash UX.
- ✅ Wave 11W3 shipped: mobile builder UX cleanup + agent visibility + template catalog verification.
- ✅ Wave 11W4 shipped: ZIP import progress UI, GitHub OAuth linked-state UX.
- ✅ **Wave 11W5 shipped (Backend reliability + portability foundation):**
  - ✅ xAI/Grok provider adapter (first-class)
  - ✅ Env var alias hydration
  - ✅ Provider availability flags in API
  - ✅ Streaming failover loop for 502/timeout/rate-limit
  - ✅ Public readiness probe `/api/system/ready`
  - ✅ Comprehensive backend e2e test run (15/17)
- ✅ Templates are **internal-only** now (template picker UI hidden from end users per latest direction).

**Known current issues (P0/P1)**
- ❗ Provider upstream instability can still occur (e.g. 502/BadGateway); failover now mitigates transient failures but budget exhaustion remains an external constraint.
- ❗ GitHub import is functional (URL import + OAuth configured), but not “flagship-grade repo browser” yet (queued).
- ❗ Heavy autonomous self-healing build loop + containerized execution runner still deferred (queued, multi-session).
- ❗ ZIP intelligence (monorepo detection, missing package manager hints, dependency reconciliation, auto-fix preflight) not yet fully integrated (queued).
- ❗ Builder mobile layout intent still needs final decision (preview behind ⋯ vs persistent toggle).
- ❗ Stale client caching can cause users to see old UI (needs cache-bust strategy / guidance).

**Testing status**
- ✅ Backend e2e (15/17):
  - system/health, system/ready, system/diagnostics
  - ai/providers (8 incl xAI), ai/models
  - auth/login
  - scaffolds list (12), scaffolds infer
  - projects create, chat stream completes via Emergent fallback, files persisted
  - ZIP import
  - GitHub OAuth status + start redirect
  - Notes: 2 failures were environmental/test-data (budget + octocat repo structure)
- ✅ Frontend build: esbuild bundle OK; component lint OK.
- ✅ Screenshot verification:
  - Landing light mode fixed.
  - Builder (dark + light) at 1440×900 verified.
  - Preview crash overlay light+dark verified; happy path verified.
  - Mobile Builder (390×844 dark) verified: friendly errors, no floating preview pill, no LIVE row, menu + model sheet no clipping.
  - Workspace Home import sheet + drag/drop overlay verified.
  - Workspace Account GitHub linked/configured state verified.

**Incoming focus**
- ⏭️ Next flagship wave: **Import/Migration excellence** (repo browser + ZIP intelligence) + **execution runner** + **heavy self-healing build loop**.

---

## 2) Implementation Steps (Phased)

### Phase 1 — Core POC (Isolation) ✅
- ✅ Multi-provider abstraction + routing primitives.

### Phase 2 — V1 App Development (Cohesive UI System + Command Center) ✅
- ✅ Completed.

### Phase 3 — DeploymentPanel Cinematic Terminal ✅
- ✅ Completed.

### Phase 4 — ChatPanel Mobile + Provider Picker Polish ✅
- ✅ Completed.

### Phase 5 — Backend Multi-Provider Architecture (Full Integration) ✅
- ✅ Completed.

### Phase 6 — Project-Card Glow Refinement ✅
- ✅ Completed.

---

### Phase 7 — AI-Native OS Platform Pass ✅ COMPLETE
- ✅ Provider OS, cinematic UX, OAuth foundation, inference + scaffolding.

---

## 3) Next Actions (Immediate) — Phase 11 (Major Refinement + Infrastructure Pass) ⏭️ ACTIVE
**Principle:** consistency and polish > new UI clutter. Mobile-first. Premium interaction quality.

### Phase 11W1 (Wave 1) — Essentials ✅ COMPLETE
**Shipped:**
- ✅ 11W1-A: Adaptive mode chips on Landing + Workspace.
- ✅ 11W1-B: Bottom-anchored composer in Workspace Home (Claude/ChatGPT feel).
- ✅ 11W1-C: AuthGate refetch hardened.
- ✅ 11W1-D: PublicFooter branding.
- ✅ 11W1-E: SignIn copy simplified.
- ✅ 11W1-F: Light-mode polish.

---

### Phase 11W2 (Wave 2) — Deep Systems ✅ COMPLETE
**Shipped:**
- ✅ Model variants: backend model catalog + UI picker.
- ✅ System diagnostics panel.
- ✅ Project memory API.
- ✅ BuilderPage/ChatPanel light mode + error UX firewall.
- ✅ Preview iframe runtime error boundary + friendly crash overlay.

---

### Phase 11W3 (Wave 3) — Mobile Builder UX Cleanup + Agent Visibility + Template Verification ✅ COMPLETE
**Context:** driven directly by user’s mobile screenshots + performance/clarity feedback.

#### 11W3-A — Mobile Builder UX Cleanup (P0) ✅
**Shipped:**
- ✅ Retroactive raw-error sanitization: historical MongoDB-stored “Generation failed…litellm…” messages render as calm cards.
- ✅ Removed floating mobile Preview oval pill (`bottom-view-preview-bar`).
  - Preview only in composer ⋯ menu.
- ✅ Removed LIVE / Streaming on chrome row under composer.
- ✅ Fixed mobile dropdown clipping:
  - `ComposerActions` menu repositioned `right-0` → `left-0` and width clamped.
  - `ModelPickerCockpit` uses a mobile bottom sheet; trigger restyled for clarity.

#### 11W3-B — Agent Visibility (P1) ✅
**Shipped:**
- ✅ ActivityStream shows agent identity per step with color-coded AgentBadge.
- ✅ `streamReducer.js` assigns agent roles: router, analyst, scaffold, architect, coder, integrator, tester, debugger, preview, devops.

#### 11W3-C — Template Catalog Verification (P1) ✅
- ✅ Backend `/api/scaffolds` returns 12 pre-cached production templates.

---

### Phase 11W4 (Wave 4) — Import UX Progress + OAuth State ✅ COMPLETE

#### 11W4-A — Internal Template-First Speed (P1) ✅
**Shipped:**
- ✅ Template catalog remains **internal** (used by inference/routing).
- ✅ End-user template picker UI removed/hidden (per latest direction).

#### 11W4-B — ZIP Import Progress + Framework Intelligence (P0/P1) ✅ (progress shipped)
**Shipped:**
- ✅ Real upload progress: migrated ZIP import from `fetch` to `XMLHttpRequest` with `upload.onprogress`.
- ✅ Visual progress bar (1.5px jade) + mono caption (`nn% uploaded` / `indexing files…`).
- ✅ Success toast includes detected framework (`Detected react-vite · opening …`).

**Still queued (next wave):**
- ⏭️ Deep parsing intelligence: monorepo detection, missing package manager, dependency reconciliation, safer defaults.

#### 11W4-C — GitHub OAuth UX Linked-State (P0) ✅
**Shipped:**
- ✅ Workspace Account GitHub row now reflects:
  - linked → `GitHub · @username` + jade status dot, tap opens profile
  - configured but not linked → `Connect GitHub` + faint status dot, tap starts OAuth
  - not configured → `GitHub (not configured)` with calm toast
- ✅ Reads provider config from `/api/oauth/status` and linkage from `user.auth_methods.github`.

#### 11W4-D — API Helper Surface (P1) ✅
**Shipped:**
- ✅ `listScaffolds`, `getScaffold`, `inferScaffold` in `frontend/src/lib/api.js`.
- ✅ Import helpers (`importGithub`, `importZipUrl`) and analysis helpers (`getAnalysis`, `refreshAnalysis`).

---

### Phase 11W5 (Wave 5) — Backend Reliability + Portability Foundation ✅ COMPLETE

#### 11W5-A — Gemini + xAI/Grok Providers (P0) ✅
**Shipped:**
- ✅ `XAIProvider` added as first-class adapter (`services/providers/adapters.py`).
  - Models: `grok-4-latest`, `grok-4`, `grok-4-reasoning`, `grok-4-mini`, `grok-4.20-reasoning`, `grok-2-1212`, `grok-beta`.
  - Uses OpenAI-compatible endpoint `https://api.x.ai/v1` via litellm.
  - Streaming + JSON mode + tools/vision flags.
- ✅ Gemini provider remains first-class and uses canonical env var `GEMINI_API_KEY`.

#### 11W5-B — Env-var alias hydration (P0) ✅
**Shipped:**
- ✅ Alias support at registry boot:
  - `GOOGLE_API_KEY` → `GEMINI_API_KEY`
  - `GROK_API_KEY` → `XAI_API_KEY`
  - `CLAUDE_API_KEY` → `ANTHROPIC_API_KEY`
  - `EMERGENT_LLM_API_KEY` → `EMERGENT_LLM_KEY`

#### 11W5-C — Provider availability surface (P0) ✅
**Shipped:**
- ✅ `/api/ai/providers` now returns specs annotated with `available` + `configured` flags.
- ✅ Diagnostics + model selector + readiness can reflect live availability.

#### 11W5-D — Streaming provider failover (P0) ✅
**Shipped:**
- ✅ Failover loop in `ai_service.generate_stream`:
  - 3-deep chain (primary + 2 fallbacks)
  - Retries on transients: 502/503/504, BadGateway, timeout, rate-limit, InternalServerError
  - Emits friendly `info` SSE when switching providers
  - Sanitizes final error (no raw provider traces)

#### 11W5-E — Public readiness probe (P0) ✅
**Shipped:**
- ✅ New `GET /api/system/ready` (no auth):
  - returns `ready` boolean
  - `ai_providers.configured` (IDs only)
  - missing env hints
  - GitHub OAuth config flag
  - safe for uptime monitors

#### 11W5-F — Secret hygiene (P0) ✅
**Shipped:**
- ✅ Removed hallucinated provider keys from `.env`.
- ✅ `.env` now contains empty placeholders for `GEMINI_API_KEY=` and `XAI_API_KEY=` only.

#### 11W5-G — Backend e2e validation (P0) ✅
**Shipped:**
- ✅ Comprehensive backend test run: **15/17 passed**.
  - Remaining 2 failures were environmental/test-data (budget exhausted intermittently; octocat repo content mismatch).

---

### Phase 11W6 (Wave 6) — Flagship Import + ZIP Intelligence + Repo Browser + Heavy Self-Healing + Execution Runner ⏭️ NEXT

#### 11W6-A — GitHub Repo Browser + Import Excellence (P0)
**Goal:** true flagship “bring code in” workflow.
- Repo browser (user/org) + search + pagination.
- Branch selection.
- Import options: shallow clone, subdir import, monorepo detection.
- Post-import: framework detection + dependency reconciliation + preview readiness check.

#### 11W6-B — ZIP Import Intelligence (P0/P1)
**Goal:** “drop anything in” becomes effortless and safe.
- Monorepo detection:
  - detect multiple `package.json` / `pyproject.toml` / `requirements.txt` roots
  - pick best candidate automatically; prompt user only if ambiguous
- Missing build tooling detection:
  - package manager inference (npm/pnpm/yarn/bun)
  - lockfile mismatches and guided fixes
- Dependency reconciliation:
  - ensure required scripts exist (`dev`, `build`, `start`)
  - ensure framework deps exist
- Auto-fix preflight:
  - run lightweight analysis + propose patch before opening Builder

#### 11W6-C — Execution Runner (Containerized) (P1)
**Goal:** production-grade build/run isolation.
- Docker-based runner or sandbox abstraction.
- Deterministic commands per scaffold/framework.
- Capture build logs + runtime logs, persist in project.

#### 11W6-D — Heavy Self-Healing Build Repair Loop (P1)
**Goal:** autonomous loop with guardrails.
- build → detect failure → propose patch → apply → retry (bounded attempts)
- Uses runtime/build logs; leverages existing `/api/projects/{id}/runtime/auto-fix` and deploy auto-fix endpoints.
- UI: agent-coded phases (Tester/Debugger/DevOps) + clear “attempt 1/3” feedback.

---

## 4) Success Criteria
- ✅ Zero pure black across all product surfaces.
- ✅ Workspace remains ultra-minimal (hamburger-only); composer is anchored and operational.
- ✅ Light mode is warm, textured, high-contrast, premium; brand remains visible.
- ✅ Builder: chat composer bottom-anchored; light mode works; CTAs remain prominent.
- ✅ No raw backend/provider errors are rendered in UI — including historical stored messages.
- ✅ No raw preview runtime overlays are shown; iframe crashes render friendly NXT1 overlay.
- ✅ Mobile builder UX: no clipped menus; no noisy “LIVE” chrome; preview accessible via ⋯ menu.
- ✅ Generation feels “alive”: cinematic boot + visible, agent-coded orchestration steps.
- ✅ Backend template catalog exists and is pre-cached (12 templates verified).
- ✅ ZIP import shows real upload progress and transitions to indexing.
- ✅ GitHub OAuth shows configured/linked state and starts real OAuth flow.
- ✅ Providers are portable and self-hostable:
  - Gemini + xAI/Grok supported via canonical env vars + aliases
  - Availability + readiness probes reflect real deployment state
- ⏭️ Next: repo browser import, deeper ZIP intelligence, containerized runner, heavy self-healing loop.

---

## 5) Clarifying Questions (resolved / carried forward)
**Resolved for Phase 11**
- ✅ Dev stability: use Emergent LLM key as dev default; user env keys take precedence.
- ✅ Routing: keep `/access` (invited) and `/admin` separate entry points.
- ✅ Branding: “A product of Jwood Technologies” only in public footer + auth screens.
- ✅ Template selection: templates are internal-only; end-user template picker is hidden.

**Still open / confirm**
1. Builder layout on mobile/tablet: should preview be **only** a full-screen modal from the ⋯ menu, or should there be a persistent preview toggle?
2. Heavy self-healing guardrails: what’s the maximum retry count (default recommendation: 2–3) before asking for user approval?
3. GitHub import UX: should repo browser live in:
   - a) Workspace Home import sheet (as a 3rd tab), or
   - b) a dedicated Workspace → Import page?

---

## Production Environment Variables (for your redeploy)
**Primary/canonical names (recommended):**
- `GEMINI_API_KEY` (Google Gemini)
- `XAI_API_KEY` (xAI Grok)
- `OPENAI_API_KEY` (OpenAI)
- `ANTHROPIC_API_KEY` (Claude)
- `OPENROUTER_API_KEY` (OpenRouter)
- `GROQ_API_KEY` (Groq)
- `DEEPSEEK_API_KEY` (DeepSeek)
- `EMERGENT_LLM_KEY` (optional fallback)

**Accepted aliases (optional):**
- `GOOGLE_API_KEY` → `GEMINI_API_KEY`
- `GROK_API_KEY` → `XAI_API_KEY`
- `CLAUDE_API_KEY` → `ANTHROPIC_API_KEY`
- `EMERGENT_LLM_API_KEY` → `EMERGENT_LLM_KEY`

**OAuth:**
- `OAUTH_GITHUB_CLIENT_ID`
- `OAUTH_GITHUB_CLIENT_SECRET`
- `OAUTH_REDIRECT_BASE` (your backend public origin)
- `FRONTEND_PUBLIC_ORIGIN` (your frontend origin)

**Core:**
- `MONGO_URL`, `DB_NAME`
- `JWT_SECRET`, `APP_PASSWORD`

**Ops probe:**
- `GET /api/system/ready` should return `ready: true` and list your configured providers.
