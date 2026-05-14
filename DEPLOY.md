# NXT1 — Deployment Guide

This is the end-to-end checklist for exporting NXT1 from Emergent back to
your own GitHub repo and re-deploying on **Vercel (frontend) + Render
(backend) + MongoDB Atlas (database)** with your own provider keys.

The platform is fully env-driven — no hardcoded URLs, keys, or domains.
Drop in your variables on Vercel/Render and everything reconnects.

---

## 1. Architecture at a glance

```
  ┌────────────────────────┐     HTTPS      ┌────────────────────────┐
  │  Vercel — frontend     │  ───────────▶  │  Render — backend      │
  │  React (Vite/CRA)      │   /api/*       │  FastAPI + uvicorn     │
  │  REACT_APP_BACKEND_URL │                │  MongoDB Atlas         │
  └────────────────────────┘                │  + provider keys       │
                                            └────────────────────────┘
```

All backend API routes are prefixed `/api/*`. The frontend ONLY hits

> **2026-05-13 deploy-blocker fix.** `emergentintegrations==0.1.0` was
> removed from `requirements.txt` — it isn't published to PyPI so deploys
> on Render / Vercel / fresh boxes failed with
> `No matching distribution found for emergentintegrations==0.1.0`. The
> backend now routes ALL LLM calls through `litellm` (already a dep).
> No code changes needed on your side; just drop in a real provider key
> (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`,
> etc.) and NXT1 auto-picks it on boot.

`process.env.REACT_APP_BACKEND_URL` — never `localhost`, never a
hardcoded preview URL.

---

## 2. Required environment variables

### Backend (`Render` → Environment)

| Variable                | Required | Purpose |
|-------------------------|----------|---------|
| `MONGO_URL`             | **Yes**  | MongoDB Atlas connection string. e.g. `mongodb+srv://user:pwd@cluster.mongodb.net/?retryWrites=true&w=majority` |
| `DB_NAME`               | **Yes**  | Mongo database name. e.g. `nxt1_prod` |
| `APP_PASSWORD`          | **Yes**  | Workspace passkey (admin login at `/access`) |
| `JWT_SECRET`            | **Yes**  | HS256 signing secret. Generate with `openssl rand -hex 32` |
| `CORS_ORIGINS`          | Yes      | Comma-separated. e.g. `https://nxt1.yourdomain.com,https://www.nxt1.yourdomain.com` |
| `AI_PROVIDER`           | Optional | `auto` (default) — auto-picks first available real key on boot. Override with `anthropic`, `openai`, `gemini`, `xai`, `groq`, `deepseek`, `openrouter`, `emergent` |

### Provider keys (drop in whichever you actually use)

NXT1 auto-detects which providers are configured. **You don't need to
set them all** — drop in just the ones you'll use.

| Variable               | Aliases accepted          | Provider          |
|------------------------|---------------------------|-------------------|
| `ANTHROPIC_API_KEY`    | `CLAUDE_API_KEY`          | Claude (Sonnet 4.5 / Opus 4.1 / Haiku 4.5) |
| `OPENAI_API_KEY`       | —                         | GPT-4.1 / GPT-4o / o4-mini |
| `GEMINI_API_KEY`       | `GOOGLE_API_KEY`, `GOOGLE_GEMINI_API_KEY` | Gemini 2.0 Flash / 1.5 Pro |
| `XAI_API_KEY`          | `GROK_API_KEY`, `XAI_GROK_API_KEY` | Grok 4 / Reasoning / mini |
| `GROQ_API_KEY`         | —                         | Llama 3.3 70B / Mixtral 8x7B |
| `DEEPSEEK_API_KEY`     | —                         | DeepSeek Chat / Reasoner |
| `OPENROUTER_API_KEY`   | —                         | OpenRouter passthrough |
| `EMERGENT_LLM_KEY`     | `EMERGENT_LLM_API_KEY`    | Emergent universal (managed). NOTE: this only works inside Emergent's own preview pods where the proxy is reachable. For your own Render/Vercel deploys, use a real first-party key (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` / etc.). |

When NXT1 boots, it logs `AI_PROVIDER auto-set to <id>` so you can
confirm which provider was selected. Set `AI_PROVIDER=auto` to keep the
failover chain enabled across all configured providers.

### Optional deployment integrations

| Variable             | Purpose |
|----------------------|---------|
| `VERCEL_TOKEN`       | Lets NXT1 deploy generated apps to your Vercel account |
| `RENDER_API_KEY`     | Lets NXT1 deploy generated apps to your Render account |
| `GITHUB_TOKEN`       | Required for "Save to GitHub" + import-repo flows |

### Frontend (`Vercel` → Environment)

| Variable                  | Required | Purpose |
|---------------------------|----------|---------|
| `REACT_APP_BACKEND_URL`   | **Yes**  | e.g. `https://nxt1-api.onrender.com` (NO trailing slash, NO `/api`) |

---

## 3. Step-by-step deployment

### 3.1 Export from Emergent
1. In Emergent, click **Save to GitHub** in the chat composer.
2. Choose your own repo. Two folders: `backend/` and `frontend/`.

### 3.2 MongoDB Atlas
1. Create a free Atlas cluster.
2. Whitelist `0.0.0.0/0` (or specifically Render's IP range for production).
3. Create a DB user.
4. Copy the SRV connection string → use as `MONGO_URL`.

### 3.3 Render — backend
1. Connect your GitHub repo.
2. Choose **Web Service**.
3. Build command: `pip install -r backend/requirements.txt`
4. Start command: `cd backend && uvicorn server:app --host 0.0.0.0 --port $PORT`
5. Environment variables: drop in the table above.
6. Health check path: `/api/auth/login` (will 422 without a body — that's fine; means the server is up).

### 3.4 Vercel — frontend
1. Connect your GitHub repo.
2. Root directory: `frontend`
3. Framework preset: Create React App (or Vite — match your repo).
4. Build command: `yarn build`
5. Output directory: `build` (CRA) or `dist` (Vite).
6. Environment variable: `REACT_APP_BACKEND_URL` → your Render URL.

### 3.5 Custom domain
- Add your domain on Vercel (frontend).
- Add a subdomain like `api.yourdomain.com` on Render (backend).
- Update `CORS_ORIGINS` on Render to include your frontend domain.
- Update `REACT_APP_BACKEND_URL` on Vercel to point to your API domain.

---

## 4. Post-deploy smoke checks

After the first deploy:

```bash
# 1. Backend health
curl -i https://api.yourdomain.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password":"<APP_PASSWORD>"}'
# → 200 + { token, expires_at }

# 2. Provider detection
curl https://api.yourdomain.com/api/ai/providers \
  -H "Authorization: Bearer <token>"
# → Each provider id should have `available: true` for keys you set.

# 3. Project create (uses snapshot)
curl https://api.yourdomain.com/api/projects \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Smoke test","prompt":"Build a pricing page","mode":"website"}'
# → Returns project with N files, plus `bootstrap.source: "snapshot"`.
```

---

## 5. What auto-works after redeploy

- **Snapshot bootstrap** — pre-baked scaffolds load in <5ms.
- **Provider failover** — drop in 1 or 5 keys, NXT1 routes intelligently.
- **WebContainer previews** — runs entirely in the browser; nothing
  for you to configure on the backend.
- **GitHub Actions deploys** — works once `GITHUB_TOKEN` is set.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Login failed` | `APP_PASSWORD` not set on Render | Set it, then `Render → Manual Deploy → Restart` |
| Empty model picker | No provider keys configured | Add at least one of `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` / `XAI_API_KEY` |
| CORS errors in browser | `CORS_ORIGINS` missing your frontend domain | Add and restart backend |
| Build hangs on "Editing files…" | Provider is timing out / 502 | Switch to a different provider via Model picker, OR set `AI_PROVIDER=<provider_id>` for explicit routing |
| WebContainer preview fails to boot | Missing COOP/COEP headers | Vercel adds them automatically via `frontend/public/coi-serviceworker.js`. Ensure the file is in your build output. |
| 502 from Emergent gateway | Upstream issue with Emergent's managed key | Add your own `ANTHROPIC_API_KEY` (etc.) — NXT1 will auto-prefer it on next boot |

---

## 7. What NOT to do

- ❌ Do not set `AI_PROVIDER` to a value you don't have a key for.
- ❌ Do not hardcode your provider keys in code. Use env vars only.
- ❌ Do not bypass `/api/*` — every backend route is namespaced under it.
- ❌ Do not put trailing slashes on `REACT_APP_BACKEND_URL`.
- ❌ Do not commit your `.env` files. `.gitignore` already excludes them.

---

## 8. Useful endpoints for ops

| Endpoint | What it tells you |
|---|---|
| `GET /api/ai/providers` | Per-provider availability + health |
| `GET /api/ai/models` | Full model variant catalogue |
| `GET /api/projects` | All projects (paginated) |
| `GET /api/scaffolds` | Available scaffold packs |

---

**Maintained by Jwood Technologies. NXT1 is an AI-native build, host, and deploy platform.**
