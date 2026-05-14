"""Phase 19 — Migration assistant + precision-editing + preview live fallback."""
import os
import sys
import requests
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE_URL}/api"
PASSWORD = os.environ.get("APP_PASSWORD", "555")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"password": PASSWORD}, timeout=10)
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- migration_service unit ----------
def test_migration_plan_detects_mongo_and_openai():
    from services.migration_service import build_plan
    files = [
        {"path": "backend/server.py", "content":
            "from motor.motor_asyncio import AsyncIOMotorClient\n"
            "import os\n"
            "client = AsyncIOMotorClient(os.environ['MONGO_URL'])\n"
            "from openai import OpenAI\n"
            "ai = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))\n"},
        {"path": "backend/requirements.txt", "content": "motor\nopenai\nfastapi"},
    ]
    plan = build_plan(files, project={"env_vars": []})
    kinds = {d["kind"] for d in plan["detected"]}
    assert "mongodb" in kinds
    assert "openai" in kinds
    missing = set(plan["missing_env"])
    assert "MONGO_URL" in missing
    assert "OPENAI_API_KEY" in missing


def test_migration_plan_detects_supabase_and_stripe():
    from services.migration_service import build_plan
    files = [
        {"path": "frontend/src/lib/supabase.js", "content":
            "import { createClient } from '@supabase/supabase-js';\n"
            "export const supabase = createClient(\n"
            "  process.env.NEXT_PUBLIC_SUPABASE_URL,\n"
            "  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,\n"
            ");"},
        {"path": "frontend/src/lib/checkout.js", "content":
            "import { loadStripe } from '@stripe/stripe-js';\n"
            "export const stripe = loadStripe(process.env.STRIPE_PUBLISHABLE_KEY);"},
    ]
    plan = build_plan(files, project={"env_vars": []})
    kinds = {d["kind"] for d in plan["detected"]}
    assert "supabase" in kinds
    assert "stripe" in kinds


def test_migration_plan_marks_step_ok_when_env_present():
    from services.migration_service import build_plan
    files = [
        {"path": "backend/server.py", "content":
            "import os\nmongo = os.environ['MONGO_URL']\n"},
    ]
    plan = build_plan(files, project={"env_vars": [
        {"key": "MONGO_URL", "value": "mongodb://..."},
    ]})
    assert "MONGO_URL" not in plan["missing_env"]


def test_migration_plan_endpoint_returns_correct_shape(auth_headers):
    pr = requests.get(f"{API}/projects", headers=auth_headers, timeout=10).json()
    if not pr:
        pytest.skip("No projects")
    pid = pr[0]["id"]
    r = requests.get(f"{API}/projects/{pid}/migration-plan",
                     headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    for k in ("detected", "missing_env", "provided_env", "env_refs", "steps"):
        assert k in body, f"missing {k}"
    assert isinstance(body["detected"], list)
    assert isinstance(body["steps"], list)


def test_migration_plan_requires_auth():
    pr = requests.get(f"{API}/projects", timeout=10)
    # Some projects endpoints accept anon; the migration endpoint must not.
    r = requests.get(f"{API}/projects/anyid/migration-plan", timeout=10)
    assert r.status_code in (401, 403)


def test_migration_plan_404_for_unknown(auth_headers):
    r = requests.get(f"{API}/projects/no-such-id/migration-plan",
                     headers=auth_headers, timeout=10)
    assert r.status_code == 404


# ---------- AI system-prompt sanity ----------
def test_system_prompt_includes_precision_rule():
    from services.ai_service import SYSTEM_PROMPT
    assert "PRECISION RULE" in SYSTEM_PROMPT
    assert "surgical" in SYSTEM_PROMPT.lower()
    assert "imported repos" in SYSTEM_PROMPT.lower()


# ---------- preview-info live URL surfacing ----------
def test_preview_info_surfaces_live_url_field(auth_headers):
    pr = requests.get(f"{API}/projects", headers=auth_headers, timeout=10).json()
    if not pr:
        pytest.skip("No projects")
    pid = pr[0]["id"]
    r = requests.get(f"{API}/projects/{pid}/preview-info",
                     headers=auth_headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "live_url" in body  # may be None — shape must exist
    assert "preview_info" in body
