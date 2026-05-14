"""NXT1 backend entrypoint (Phase 8 modular).

All endpoints live under /app/backend/routes/. This file is intentionally tiny:
- env loading
- FastAPI app + CORS
- include_router() for every modular package
- startup/shutdown hooks (storage init + runtime idle sweeper)
"""
import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

# Load env before anything else imports os.environ values
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("nxt1")

# Import after env is loaded so modules can read os.environ at import time
from services import runtime_service as rt_svc  # noqa: E402
from services.storage_service import init_storage  # noqa: E402

# Route packages
from routes.access import router as access_router  # noqa: E402
from routes.admin import router as admin_router  # noqa: E402
from routes.admin_domains import router as admin_domains_router  # noqa: E402
from routes.agents import router as agents_router  # noqa: E402
from routes.agents_catalog import router as agents_catalog_router  # noqa: E402
from routes.agentos import router as agentos_router  # noqa: E402
from routes.ai_meta import router as ai_meta_router  # noqa: E402
from routes.assets import router as assets_router  # noqa: E402
from routes.audit import router as audit_router  # noqa: E402
from routes.auth import router as auth_router  # noqa: E402
from routes.autofix import router as autofix_router  # noqa: E402
from routes.chat import router as chat_router  # noqa: E402
from routes.databases import router as databases_router  # noqa: E402
from routes.deployments import router as deployments_router  # noqa: E402
from routes.domains import router as domains_router  # noqa: E402
from routes.env import router as env_router  # noqa: E402
from routes.files import router as files_router  # noqa: E402
from routes.imports import router as imports_router  # noqa: E402
from routes.integrations import router as integrations_router  # noqa: E402
from routes.jobs import router as jobs_router  # noqa: E402
from routes.migration import router as migration_router  # noqa: E402
from routes.oauth import router as oauth_router  # noqa: E402
from routes.preview import router as preview_router  # noqa: E402
from routes.product import router as product_router  # noqa: E402
from routes.project_memory import router as project_memory_router  # noqa: E402
from routes.projects import router as projects_router  # noqa: E402
from routes.public_deploy import router as public_deploy_router  # noqa: E402
from routes.requests import router as requests_router  # noqa: E402
from routes.runtime import router as runtime_router  # noqa: E402
from routes.scaffolds import router as scaffolds_router  # noqa: E402
from routes.site_editor import router as site_editor_router  # noqa: E402
from routes.system import router as system_router  # noqa: E402
from routes.users import router as users_router  # noqa: E402
from routes.versions import router as versions_router  # noqa: E402
# New (2026-01-15): Tracks A/B/C/D
from routes.ui_registry import router as ui_registry_router  # noqa: E402
from routes.workflows import router as workflows_router  # noqa: E402
from routes.hosting import router as hosting_router  # noqa: E402
from routes.runner import router as runner_router  # noqa: E402
# AgentOS v2 (Phase 22 — full dashboard redesign)
from routes.agentos_v2 import router as agentos_v2_router  # noqa: E402
# Social + Video Studio (2026-05-14)
from routes.social import router as social_router  # noqa: E402
from routes.video import router as video_router  # noqa: E402
from routes.social_oauth import router as social_oauth_router  # noqa: E402
from routes.agent_memory import router as agent_memory_router  # noqa: E402
from services.social_scheduler import scheduler_loop as social_scheduler_loop  # noqa: E402
from routes._deps import db as _shared_db  # noqa: E402

app = FastAPI(title="NXT1 API", version="0.6.0")

# Order matters only when paths overlap; our routers don't, but we register
# in a deterministic order grouped by domain.
for r in (
    auth_router,
    projects_router,
    files_router,
    versions_router,
    chat_router,
    assets_router,
    deployments_router,
    domains_router,
    env_router,
    runtime_router,
    imports_router,
    public_deploy_router,
    # advanced / phase-7+
    access_router,
    agents_router,
    agents_catalog_router,
    agentos_router,
    autofix_router,
    product_router,
    requests_router,
    databases_router,
    integrations_router,
    jobs_router,
    migration_router,
    preview_router,
    users_router,
    site_editor_router,
    admin_router,
    admin_domains_router,
    audit_router,
    ai_meta_router,
    oauth_router,
    system_router,
    project_memory_router,
    scaffolds_router,
    # New (2026-01-15): Tracks A/B/C/D
    ui_registry_router,
    workflows_router,
    hosting_router,
    runner_router,
    agentos_v2_router,
    social_router,
    video_router,
    social_oauth_router,
    agent_memory_router,
):
    app.include_router(r)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    init_storage()
    try:
        asyncio.create_task(rt_svc.idle_sweeper())
    except Exception as e:
        logger.warning(f"idle_sweeper not started: {e}")
    try:
        asyncio.create_task(social_scheduler_loop(_shared_db))
        logger.info("social scheduler loop started")
    except Exception as e:
        logger.warning(f"social scheduler not started: {e}")


@app.on_event("shutdown")
async def on_shutdown():
    # Motor client cleanup is handled per-module; nothing to close here.
    pass
