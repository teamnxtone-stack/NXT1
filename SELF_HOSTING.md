# NXT1 — Self-Hosting Guide (AgentOS edition)

## What this gets you
- The full NXT1 builder (prompt → app → preview → deploy → domain → SSL)
- AgentOS dashboard (`/agentos`) with Home / Agents / Jobs / Social / Founders / Resume / Approvals / Chat / Settings
- **5 real autonomous agents** wired and running natively in the pod:
  - **Custom** — research/task runner (Claude + DDG + page fetch)
  - **Job Scout** — JobSpy across LinkedIn / Indeed / Glassdoor / ZipRecruiter
  - **Founders Scout** — Reddit + GitHub cofounder signal scanning
  - **Social Strategist** — Claude → Postiz REST (when configured)
  - **Resume Tailor** — Native ATS keyword scoring + Claude rewrite (no Docker sidecar required)
- Caddy auto-SSL + Cloudflare DNS attach
- Self-healing sandboxed build loop
- 17 premium UI blocks the AI uses to generate apps
- Theme-aware Dashboard — carbon graphite (dark) / warm cream (light) — matches the rest of the app

## Quick start

```bash
# 1. Clone + install
git clone <your-fork> nxt1 && cd nxt1
cd backend && pip install -r requirements.txt && cd ..
cd frontend && yarn install && cd ..

# 2. (Optional) Bring up sidecars (Postiz, Redis, Postgres)
cp .env.example .env  # set OPENAI_API_KEY, POSTGRES_PASSWORD, POSTIZ_SECRET_KEY
docker compose -f docker-compose.agentos.yml up -d

# 3. Configure NXT1 itself — minimum viable config
cat <<EOF >> backend/.env
MONGO_URL=mongodb://localhost:27017
DB_NAME=nxt1
JWT_SECRET=<random 64-char string>
APP_PASSWORD=<your gate password>
ANTHROPIC_API_KEY=<your Anthropic key — preferred>
# OR: EMERGENT_LLM_KEY=<for Emergent-hosted only — skip on self-host>
OPENAI_API_KEY=<optional — for DALL-E 3 image gen>
EOF

cat <<EOF >> frontend/.env
REACT_APP_BACKEND_URL=http://localhost:8001
EOF

# 4. Run
sudo supervisorctl restart backend frontend
# Open http://localhost:3000 — log in with APP_PASSWORD
# AgentOS dashboard at /agentos
```

## Environment variables

| Var                      | Purpose                                                 | Required |
|--------------------------|---------------------------------------------------------|----------|
| `MONGO_URL`              | MongoDB connection string                               | Yes      |
| `DB_NAME`                | Mongo database name                                     | Yes      |
| `JWT_SECRET`             | JWT signing + Cloudflare-token encryption seed          | Yes      |
| `APP_PASSWORD`           | Access-gate password                                    | Yes      |
| `ANTHROPIC_API_KEY`      | Direct Anthropic — preferred path for self-host         | Yes*     |
| `OPENAI_API_KEY`         | Direct OpenAI — for DALL-E 3 + GPT planning             | Optional |
| `GEMINI_API_KEY`         | Direct Gemini — large-context tasks                     | Optional |
| `XAI_API_KEY`            | Grok                                                    | Optional |
| `EMERGENT_LLM_KEY`       | Universal-key fallback (Emergent-hosted only)           | Optional |
| `EMERGENT_BASE_URL`      | Override the Emergent proxy base (defaults to https://integrations.emergentagent.com) | Optional |
| `EMERGENT_STORAGE_URL`   | Override the Emergent object-store URL                  | Optional |
| `AGENTOS_LLM_MODEL`      | Model used by the AgentOS agents (default `claude-sonnet-4-5-20250929`) | Optional |
| `POSTIZ_URL`             | Postiz API base (default http://localhost:5000)         | Optional |
| `POSTIZ_API_KEY`         | Postiz API token (admin → settings)                     | Optional |
| `POSTIZ_SECRET_KEY`      | Postiz JWT secret (docker-compose env)                  | Optional |
| `REDIS_URL`              | Redis for real Celery (when you swap from in-process)   | Optional |
| `CELERY_BROKER_URL`      | Real Celery broker (defaults to in-process runner)      | Optional |
| `CF_TOKEN_KEY`           | Override JWT_SECRET as Cloudflare-token encryption seed | Optional |
| `LIVEKIT_URL`            | LiveKit server (voice agent)                            | Optional |
| `LIVEKIT_API_KEY/SECRET` | LiveKit auth                                            | Optional |
| `DEEPGRAM_API_KEY`       | Voice STT                                               | Optional |
| `CARTESIA_API_KEY`       | Voice TTS                                               | Optional |
| `GITHUB_TOKEN`           | GitHub OAuth / repo import                              | Optional |

\*On self-host, set at least one direct provider key (Anthropic is the simplest — Claude powers AgentOS agents by default). `EMERGENT_LLM_KEY` is the convenience-key system used when deploying to Emergent's preview infra; you can ignore it on your own hardware.

## Removing the Emergent-only dependency

`emergentintegrations==0.1.0` is listed in `backend/requirements.txt` for compatibility with Emergent-hosted preview. **For self-hosting on Render / Fly / Railway / your own VPS, comment this line out** — PyPI doesn't host it, and NXT1 falls back to direct provider SDKs via litellm for app generation, and direct provider HTTP calls for AgentOS agents.

```diff
# backend/requirements.txt
- emergentintegrations==0.1.0
+ # emergentintegrations==0.1.0  # Emergent-hosted only — remove for self-host
```

## AgentOS internals
- **Task runner:** `services/agentos_runner.py` — in-process asyncio queue, MongoDB-persisted, NaN-safe JSON sanitization. Shape-compatible with Celery: swap to real Celery by adding a worker module and pointing `submit_task` at it.
- **Agents:** `services/agentos_agents.py` registers 5 agents via `@register_agent("name")` decorator. Add more by following the pattern.
- **WebSocket:** `/api/agentos/ws/tasks/{task_id}?token=<jwt>` — server pushes step/log/complete events as the agent works.
- **Resume Tailor** runs entirely in-pod — extracts PDF/DOCX via `pdfplumber` + `python-docx`, scores ATS keywords + cosine similarity natively, then calls Claude for the rewrite.

## What's NOT running until you bring up sidecars
- Postiz (Social tab shows config helper until you set `REACT_APP_POSTIZ_URL`)
- LiveKit voice (Voice button is non-functional until you set LIVEKIT_* vars)
- X / LinkedIn outreach (require API keys you provide)

## Production hardening checklist
- [ ] Change `APP_PASSWORD` from `555`
- [ ] Generate a 64-char random `JWT_SECRET`
- [ ] Remove `emergentintegrations` line from `backend/requirements.txt`
- [ ] Set up reverse proxy (Caddy config generator at `/api/hosting/caddy/generate`)
- [ ] Point DNS at your server (use `/api/hosting/cloudflare/connect` if using Cloudflare)
- [ ] Add a real Anthropic + OpenAI key for full multi-model routing
- [ ] Swap in real Celery workers if running >5 concurrent agent tasks

