# NXT1 Upgrade Plan — Learning from Dyad & Chef

> Living document. Updated as we ship improvements.
>
> Goal: make NXT1's backend / orchestration significantly more powerful by
> absorbing the best ideas from `dyad` (Electron desktop builder, Apache 2.0)
> and `chef` (Convex's bolt.diy fork, web builder). Preserve NXT1 identity,
> hosted multi-tenant architecture, MongoDB, design, and route surface.

---

## 1. What NXT1 already does well (DO NOT regress)

| Capability | Status in NXT1 |
|---|---|
| Multi-provider AI routing (anthropic/openai/xai/gemini/groq/deepseek/openrouter/emergent) with task & tier hints | ✅ `services/providers/registry.py` |
| Streaming generation with phase events, narration, tool-receipt diffing | ✅ `ai_service.generate_project_stream` |
| Multi-level JSON recovery (strict → ctrl-char normalize → json_repair → regex salvage) | ✅ `ai_service.parse_ai_response` |
| Precision-editing guardrails (protect package.json/configs/lockfiles on imports) | ✅ `ai_service.merge_with_protection` |
| MongoDB persistence (hosted multi-tenant) | ✅ |
| 135-route control plane (projects, files, versions, chat, deployments, domains, env, runtime, imports, integrations, jobs, migration, preview, users, site_editor, admin, audit, ai_meta, oauth, system, project_memory, scaffolds, public_deploy, etc.) | ✅ |
| Autofix / debug agents | ✅ `routes/autofix.py`, `services/agents.py` |
| Modular scaffolds (`react_vite`, `nextjs_tailwind`, `expo_rn`, `browser_extension`, `web_static`, `ai_chat_streaming`) | ✅ `services/scaffolds/` |
| GitHub, Vercel, Cloudflare, Neon, Supabase, R2 integrations | ✅ |

**These are competitive moats. Neither dyad nor chef has a hosted multi-tenant control plane.**

---

## 2. What dyad / chef do that NXT1 should adopt

### 2.1 Tag-protocol for AI output (HIGH IMPACT — Phase A)

Both reference builders abandon the single-JSON-blob protocol in favour of
**inline streaming tags**:

- Dyad emits `<dyad-write path="…">…</dyad-write>`, `<dyad-rename from="…" to="…" />`,
  `<dyad-delete path="…" />`, `<dyad-search-replace path="…"><search>…</search><replace>…</replace></dyad-search-replace>`,
  `<dyad-add-dependency packages="react-icons lucide" />`, `<dyad-execute-sql>…</dyad-execute-sql>`.
- Chef emits `<boltArtifact id="…"><boltAction type="file" filePath="…">…</boltAction>
  <boltAction type="shell">npm install …</boltAction>…</boltArtifact>`.

**Why this is dramatically better than NXT1's current `"files":[...]` JSON blob:**

1. **Token efficiency** — an "edit Hero color" turns into ~50 tokens
   (`<nxt1-edit><search>…</search><replace>…</replace></nxt1-edit>`) instead
   of re-emitting every file (~5–50k tokens). 10–100× cost reduction on
   incremental edits.
2. **Streaming-applicable** — tag close events trigger immediate file
   mutation. The user sees "Edited Hero.jsx ✓" mid-stream instead of waiting
   for the full JSON to arrive and parse.
3. **Action diversity** — rename / delete / deps-install / sql-exec are
   first-class instead of being shoe-horned into `files[]`.
4. **Resilient to truncation** — if the model hits max_tokens partway, the
   tags that did close are already applied; only the in-flight tag is lost.
   JSON blobs are all-or-nothing.

**Plan:** Implement `nxt1-*` tags alongside (not replacing) the JSON path.
Feature-flagged: per-request `?protocol=tag` query param + per-project default
preference. JSON path stays as fallback.

→ **Phase A.1 (this iteration):** `services/tag_protocol.py` parser + apply
  layer, `services/ai_service_tag.py` streaming generator + tag system prompt,
  `routes/chat.py` plumbing behind `?protocol=tag` query param, unit tests.

### 2.2 Streaming message parser as a state machine (HIGH IMPACT — Phase A)

Chef's `StreamingMessageParser` is a clean state machine that fires
`onActionOpen`, `onActionStream`, `onActionClose`, `onArtifactOpen`,
`onArtifactClose` callbacks as bytes arrive. NXT1 currently buffers and parses
JSON in one shot at the end. Adopting this pattern (for the tag-protocol path)
enables real-time apply, real-time tool receipts, real-time file-tree update,
real-time terminal output.

→ Bundled into Phase A.1 above.

### 2.3 Post-generation validation worker (HIGH IMPACT — Phase A.2)

Dyad runs `tsc.ts` in a worker thread after each generation, returning a
`ProblemReport` of TypeScript / lint errors. NXT1 has the autofix route but it
must be triggered manually. Pattern to adopt:

- After every successful generation, run a fast syntax/lint check on changed
  files (no full `npm run build`, no docker).
- If errors detected, stream `{type:"validate", errors:[…]}` to the client and
  auto-queue one repair pass with the error report in the user prompt.
- One repair max → stop loop to avoid infinite token-burn.

→ **Phase A.2 (next iteration):** `services/validation_service.py` (esprima
  for JS, py-compile for Python, html5lib for HTML). Hook into
  `generate_project_stream` after the `done` event.

### 2.4 Robust dependency installer with error pattern detection (Phase A.3)

Dyad's `executeAddDependency.ts` has:
- pattern matching for `npm err! …`, `blocked`, `timed out`, `denied`,
  `ETIMEDOUT`, `E[A-Z][A-Z0-9_]{2,}`
- noise filtering (`progress:`, `npm notice`, …)
- timeout enforcement
- summary extraction so the AI sees only the relevant line

NXT1's runtime_service has dep install but doesn't have this surfacing
quality. The repair loop will be MUCH more effective with clean dep errors.

### 2.5 Action runner with abort + per-action status (Phase A.4)

Chef's `ActionRunner` keeps a `MapStore<ActionState>` with
`pending|running|complete|aborted|failed`, supports abort signals, aggregates
terminal output per action. Cleaner than NXT1's `response_processor` which
applies everything synchronously. With the tag-protocol path we'll need this.

### 2.6 In-browser preview via WebContainer (Phase B — opt-in)

Chef uses `@webcontainer/api` (StackBlitz) to run Node/npm in the browser.
Pros: zero-latency preview, no server cost, full dev-server experience.
Cons: requires `crossOriginIsolated` (COOP/COEP headers), only some apps work
(no native deps, limited node binaries), browser-only. NXT1 should add this as
an **opt-in alternative preview mode** for SPA-style projects (Vite/CRA/Next
static), keeping the server-side preview as the default for full-stack apps.

→ Phase B (later): `frontend/src/lib/webcontainer/` + opt-in toggle in the
  builder preview panel.

### 2.7 MCP tool registry (Phase B)

Dyad's `mcp_manager.ts` + `mcp_consent.ts` integrate Model Context Protocol
servers (custom tools the user plugs in: Linear, Sentry, Postgres, etc.). NXT1
has none. Stage later — needs a tool-consent UX.

### 2.8 Snapshot bootstrap (Phase B)

Chef's `make-bootstrap-snapshot.js` builds a precompressed snapshot of the
template so a new project boots instantly inside WebContainer. NXT1 should
ship snapshots for each scaffold (zstd-compressed file list + manifest) so
scaffold creation is one Mongo write instead of recursive file copy.

### 2.9 Chat / message compaction (Phase B)

Both projects compact long conversations. Chef uses LZ4 on stored messages
(`compressMessages.ts`, `lz4.ts`). Dyad has an explicit `compactedAt` field
and a `compaction_system_prompt.ts`. NXT1 has chat-summarisation for version
labels but stores full message text. For long projects this becomes
problematic (>500 messages). Add background compaction job.

### 2.10 Rate limiter (HIGH IMPACT — Phase A.5)

Chef has a built-in Convex `rateLimiter`. NXT1 has no per-user / per-project
rate limit on AI generation → cost runaway risk. Add a token-bucket limiter
keyed by `(user_id, route)`. Mongo collection `rate_limits` with TTL.

→ **Phase A.5 (this iteration):** `services/rate_limit_service.py` +
  apply to `POST /projects/{id}/chat/stream`.

### 2.11 Eval harness (Phase A.6 — light, Phase B — heavy)

Chef's `test-kitchen/` runs fixture tasks against the live builder and grades
outputs (`chefScorer.ts`). NXT1 has unit tests but no end-to-end eval. Skeleton
now (4–6 fixtures), expand later.

### 2.12 Framework auto-detection (Phase A — small)

Dyad's `framework_utils.detectFrameworkType()` returns `nextjs | vite |
vite-nitro | other`. NXT1 has `inference_service.infer_project_kind` which is
similar; we can extend it with dyad's signals (nitro detection, vite-config
presence as separate signal from `vite` dep).

### 2.13 AI rules patcher (Phase B)

Dyad's `ai_rules_patcher.ts` writes/updates an `AI_RULES.md` at the project
root with detected framework rules, used as context. NXT1's project_memory
already gives us 80% — extend to auto-emit `AI_RULES.md` on import.

---

## 3. What NXT1 should NOT adopt

- **Drizzle + SQLite** (dyad). NXT1 is hosted multi-tenant; SQLite per-user is
  Electron-only.
- **Convex as the source of truth** (chef). Vendor lock-in conflicts with
  NXT1's "host anything anywhere" strategy.
- **Electron IPC handler architecture** (dyad). NXT1 is a web app; FastAPI
  routers are the right surface.
- **WebContainer as the ONLY preview mode** (chef). It can't run full-stack
  Python/Go/Rust backends. Keep server-side preview as default.
- **`<dialog>` and OS file-pickers** (dyad). NXT1 uploads/imports are
  browser-based (POST multipart).
- **bolt-style monolithic system prompt** (chef). NXT1's modular prompt
  (system_prompt + framework prompt + theme + supabase/neon context) is
  already more sophisticated.

---

## 4. Implementation phases

### Phase A — Tag protocol + safety (this work, additive, feature-flagged)
- [x] A.0 — Analysis + plan (this doc)
- [x] A.1 — Streaming tag-protocol parser + apply (`services/tag_protocol.py`)
- [x] A.2 — Tag-mode streaming generator + system prompt (`services/ai_service_tag.py`)
- [x] A.3 — Wire into `/projects/{id}/chat/stream?protocol=tag`
- [x] A.4 — Unit tests for parser + apply
- [ ] A.5 — Rate limiter middleware (next iteration)
- [ ] A.6 — Post-gen validation hook (next iteration)
- [ ] A.7 — Eval harness skeleton (next iteration)

### Phase B — Power features (next sprint)
- [ ] B.1 — Action runner abstraction (per-action status + abort)
- [ ] B.2 — Dep installer error-pattern surfacer
- [ ] B.3 — WebContainer preview mode (opt-in, SPA only)
- [ ] B.4 — Snapshot bootstrap for scaffolds
- [ ] B.5 — Chat compaction background job
- [ ] B.6 — `AI_RULES.md` auto-patcher
- [ ] B.7 — Framework detection enrichment

### Phase C — Platform features (later)
- [ ] C.1 — MCP tool registry
- [ ] C.2 — Socket firewall for sandbox
- [ ] C.3 — Cloud sandbox provider (alt to local exec)
- [ ] C.4 — PTY command runner (terminal in builder)
- [ ] C.5 — Full eval harness with scorer
- [ ] C.6 — Migration plan store (versioned schema migrations for user apps)

---

## 5. Tag protocol — formal spec (Phase A.1)

```
<nxt1-write path="src/App.jsx">
…complete file contents…
</nxt1-write>

<nxt1-edit path="src/App.jsx">
  <search>const title = "Old"</search>
  <replace>const title = "New"</replace>
</nxt1-edit>

<nxt1-rename from="src/Old.jsx" to="src/New.jsx" />
<nxt1-delete path="src/Unused.jsx" />

<nxt1-deps action="install">react-icons lucide-react</nxt1-deps>
<nxt1-deps action="uninstall">moment</nxt1-deps>

<nxt1-explanation>Refactored hero with stickier nav.</nxt1-explanation>
<nxt1-notes>Run `yarn add` after.</nxt1-notes>
```

Rules:
- Each tag is independent. Order = application order.
- `<nxt1-write>` replaces the whole file (creates if missing).
- `<nxt1-edit>` requires `<search>` to match exactly once in current content.
- `<nxt1-rename>` and `<nxt1-delete>` are self-closing.
- Tag content is plain text (not HTML-escaped). Inner `<` is fine as long as
  the literal closing tag string doesn't appear inside the content.
- Stream events emitted by the parser:
  - `{type:"tag_open", tag, attrs}`
  - `{type:"tag_stream", tag, delta}` (only for `write`)
  - `{type:"tag_close", tag, attrs, content}` → triggers apply

---

## 6. Open questions / decisions still pending

- Whether to mandate `<nxt1-edit>` for files >5kb (saves tokens) or leave the
  model to choose between `<nxt1-write>` and `<nxt1-edit>`. **Decision: leave
  to the model in v1, instrument and tune in v2.**
- Whether tag-protocol should be the default for repeat edits on existing
  projects. **Decision: not yet — opt-in for now via query param, gather
  data, flip default later.**
- WebContainer auth/COOP requirements need a serverless edge function or
  custom headers on the preview origin. **Decision: defer to Phase B once
  Phase A is validated.**
