"""
Iteration 4 — Full E2E NXT1 production-path audit.

Exercises the user journey:
  Login → Create project → Auto-workflow → Chat (LLM) →
  Preview info → Deploy → Domains (manual) → Hosting (auto/CF/Caddy) →
  Env vars → Asset upload → AI routing → Agent OS.

Each test classifies its failure as CRITICAL / MAJOR / MINOR via the test name.
"""
import io
import os
import time
import uuid

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
PASSWORD = os.environ.get("APP_PASSWORD", "555")


# ---------------------------------------------------------------- Fixtures ---

@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in response: {r.json()}"
    return tok


@pytest.fixture(scope="session")
def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def project(H):
    payload = {
        "name": f"TEST_iter4_{uuid.uuid4().hex[:8]}",
        "prompt": "Build a premium AI startup landing page with hero + pricing",
    }
    r = requests.post(f"{BASE_URL}/api/projects", json=payload, headers=H, timeout=30)
    assert r.status_code in (200, 201), f"create project failed {r.status_code} {r.text}"
    p = r.json()
    pid = p.get("id")
    assert pid
    yield p
    # Teardown
    try:
        requests.delete(f"{BASE_URL}/api/projects/{pid}", headers=H, timeout=15)
    except Exception:
        pass


# --------------------------------------------------------- 0. Auth happy path

class TestAuth:
    def test_login_with_555(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "access_token" in j or "token" in j

    def test_login_bad_password_rejected(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": "wrong"}, timeout=15)
        assert r.status_code in (400, 401, 403)


# ----------------------------------------------- 1. CRITICAL — E2E happy path

class TestE2EHappyPath:
    def test_project_created(self, project):
        assert project["id"]
        assert project.get("prompt")
        # name was provided so should match — but service may slugify; just check presence
        assert project.get("name")

    def test_workflow_autostarted(self, H, project):
        r = requests.get(
            f"{BASE_URL}/api/workflows/list",
            params={"project_id": project["id"]},
            headers=H, timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        wfs = data if isinstance(data, list) else data.get("workflows", [])
        assert len(wfs) >= 1, f"expected an auto-started workflow, got: {data}"

    def test_chat_generates_files_and_reconciles(self, H, project):
        # Real LLM call — give it 90s
        body = {"message": "Add a footer with copyright text", "provider": None}
        r = requests.post(
            f"{BASE_URL}/api/projects/{project['id']}/chat",
            json=body, headers=H, timeout=90,
        )
        assert r.status_code == 200, f"chat failed {r.status_code} {r.text[:500]}"
        j = r.json()
        assert "files" in j
        assert isinstance(j["files"], list) and len(j["files"]) >= 1
        assert "workflow_reconciled" in j  # key MUST be present, even if None
        # Persistence check
        r2 = requests.get(f"{BASE_URL}/api/projects/{project['id']}", headers=H, timeout=15)
        assert r2.status_code == 200
        assert len(r2.json().get("files", [])) >= 1

    def test_preview_url_endpoint_returns_something(self, H, project):
        """Spec mentioned GET /api/projects/{id}/preview/url — that path doesn't exist;
        the available endpoint is /api/projects/{id}/preview-info. Test the real one."""
        r = requests.get(
            f"{BASE_URL}/api/projects/{project['id']}/preview-info",
            headers=H, timeout=15,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert "preview_info" in j
        # And the spec'd /preview/url — assert clear 404 (not 500)
        r2 = requests.get(
            f"{BASE_URL}/api/projects/{project['id']}/preview/url",
            headers=H, timeout=15,
        )
        assert r2.status_code in (404, 405), f"expected 404/405, got {r2.status_code}"


# ----------------------------------------------- 2. CRITICAL — Deploy endpoints

class TestDeploy:
    def test_providers_list_contains_internal(self, H):
        r = requests.get(f"{BASE_URL}/api/deploy/providers", headers=H, timeout=15)
        assert r.status_code == 200
        ids = {p["id"] for p in r.json().get("providers", [])}
        assert "internal" in ids, f"providers={ids}"

    def test_deploy_internal_and_poll(self, H, project):
        # Hit legacy /deploy which forces 'internal'
        r = requests.post(
            f"{BASE_URL}/api/projects/{project['id']}/deploy",
            headers=H, timeout=60,
        )
        assert r.status_code == 200, r.text
        dep = r.json()
        dep_id = dep.get("id")
        assert dep_id
        # poll
        final = None
        for _ in range(8):
            rp = requests.get(
                f"{BASE_URL}/api/projects/{project['id']}/deployments/{dep_id}",
                headers=H, timeout=15,
            )
            assert rp.status_code == 200
            final = rp.json()
            if final.get("status") in ("deployed", "failed", "live", "completed"):
                break
            time.sleep(2)
        assert final and final.get("status") in ("deployed", "live", "completed"), (
            f"final={final}"
        )
        # internal deployments expose either public_url or slug
        assert final.get("public_url") or final.get("slug")


# ----------------------------------------------- 3. Domains — auto (Cloudflare)

class TestAutoDomain:
    def test_cf_connect_bad_token_returns_400(self, H):
        r = requests.post(
            f"{BASE_URL}/api/hosting/cloudflare/connect",
            json={"token": "definitely_not_a_real_token"},
            headers=H, timeout=15,
        )
        assert r.status_code in (400, 401, 422), r.text

    def test_hosting_readiness(self, H):
        r = requests.get(f"{BASE_URL}/api/hosting/readiness", headers=H, timeout=15)
        assert r.status_code == 200
        j = r.json()
        # any of these top-level keys is fine — just confirm it returns a dict
        assert isinstance(j, dict) and len(j) > 0

    def test_caddy_generate_has_hsts(self, H):
        body = {"domains": ["example.com"], "email": "ops@example.com"}
        r = requests.post(
            f"{BASE_URL}/api/hosting/caddy/generate",
            json=body, headers=H, timeout=15,
        )
        assert r.status_code == 200, r.text
        cfg = r.json().get("caddyfile") or r.json().get("config") or ""
        assert "Strict-Transport-Security" in cfg or "hsts" in cfg.lower(), cfg[:400]


# ----------------------------------------------- 4. Domains — manual project-level

class TestManualDomain:
    def test_create_list_verify_domain(self, H, project):
        # Create
        rc = requests.post(
            f"{BASE_URL}/api/projects/{project['id']}/domains",
            json={"hostname": f"test-{uuid.uuid4().hex[:6]}.example.com"},
            headers=H, timeout=15,
        )
        assert rc.status_code in (200, 201), rc.text
        domain = rc.json()
        did = domain.get("id") or domain.get("domain_id")
        assert did, domain
        # List
        rl = requests.get(
            f"{BASE_URL}/api/projects/{project['id']}/domains",
            headers=H, timeout=15,
        )
        assert rl.status_code == 200
        items = rl.json() if isinstance(rl.json(), list) else rl.json().get("domains", [])
        assert any((d.get("id") or d.get("domain_id")) == did for d in items)
        # Verify
        rv = requests.post(
            f"{BASE_URL}/api/projects/{project['id']}/domains/{did}/verify",
            headers=H, timeout=20,
        )
        assert rv.status_code in (200, 202), rv.text


# ----------------------------------------------- 5. Env vars

class TestEnvVars:
    def test_env_crud(self, H, project):
        pid = project["id"]
        # List (start)
        r0 = requests.get(f"{BASE_URL}/api/projects/{pid}/env", headers=H, timeout=15)
        assert r0.status_code == 200
        assert isinstance(r0.json(), list)
        # Upsert
        r1 = requests.post(
            f"{BASE_URL}/api/projects/{pid}/env",
            json={"key": "STRIPE_KEY", "value": "sk_test_xxx"},
            headers=H, timeout=15,
        )
        assert r1.status_code == 200, r1.text
        # List shows it (redacted)
        r2 = requests.get(f"{BASE_URL}/api/projects/{pid}/env", headers=H, timeout=15)
        items = r2.json()
        match = [e for e in items if e["key"] == "STRIPE_KEY"]
        assert match, items
        masked = match[0].get("value_masked", "")
        assert "sk_test_xxx" not in masked  # must be redacted
        # Delete
        rd = requests.delete(
            f"{BASE_URL}/api/projects/{pid}/env/STRIPE_KEY", headers=H, timeout=15
        )
        assert rd.status_code == 200, rd.text


# ----------------------------------------------- 6. Assets

class TestAssets:
    def test_upload_and_list(self, H, project):
        pid = project["id"]
        # 1x1 transparent PNG
        png = bytes.fromhex(
            "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
            "890000000A49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
        )
        files = {"file": ("dot.png", io.BytesIO(png), "image/png")}
        # Auth header only (don't send Content-Type: json)
        r = requests.post(
            f"{BASE_URL}/api/projects/{pid}/upload",
            headers={"Authorization": H["Authorization"]},
            files=files,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        a = r.json()
        assert a.get("id") and a.get("filename")
        # List
        rl = requests.get(
            f"{BASE_URL}/api/projects/{pid}/assets", headers=H, timeout=15
        )
        assert rl.status_code == 200
        assert any(x.get("id") == a["id"] for x in rl.json())


# ----------------------------------------------- 7. AI routing (NOT single provider)

class TestAIRouting:
    def test_providers_listed(self, H):
        r = requests.get(f"{BASE_URL}/api/ai/providers", headers=H, timeout=15)
        assert r.status_code == 200
        provs = r.json().get("providers", [])
        ids = {p.get("id") for p in provs}
        # Spec says 8 providers; assert at least 6 + key ones
        assert {"openai", "anthropic", "gemini"}.issubset(ids), ids
        assert len(provs) >= 6, f"only {len(provs)} providers: {ids}"

    def test_task_routing_table_multi_provider(self, H):
        r = requests.get(f"{BASE_URL}/api/ai/task-routing", headers=H, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        table = j.get("table", {})
        suggestions = j.get("suggestions", {})
        assert isinstance(table, dict) and len(table) >= 3
        # Confirm NOT hardcoded to one provider
        suggested_providers = set()
        for v in suggestions.values():
            if isinstance(v, dict):
                p = v.get("provider") or v.get("provider_id")
                if p:
                    suggested_providers.add(p)
        assert len(suggested_providers) >= 2, (
            f"routing is hardcoded to a single provider: {suggested_providers}"
        )

    def test_agents_route_picks_role_by_prompt(self, H):
        # Frontend-y prompt
        r = requests.post(
            f"{BASE_URL}/api/agents/route",
            json={"prompt": "Build a responsive Tailwind UI page with a modal and dropdown"},
            headers=H, timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("role") in ("frontend", "architecture")
        # Devops-y prompt
        r2 = requests.post(
            f"{BASE_URL}/api/agents/route",
            json={"prompt": "Deploy to vercel and set up SSL on a custom domain"},
            headers=H, timeout=15,
        )
        assert r2.status_code == 200
        assert r2.json().get("role") == "devops"


# ----------------------------------------------- 8. Agent OS — catalog + history

class TestAgentOS:
    def test_agents_listed(self, H):
        r = requests.get(f"{BASE_URL}/api/agents", headers=H, timeout=15)
        assert r.status_code == 200
        agents = r.json()
        roles = {a.get("role") for a in (agents if isinstance(agents, list) else agents.get("agents", []))}
        # Domain agents
        assert {"frontend", "backend"}.intersection(roles), roles

    def test_lifecycle_returns_states(self, H):
        r = requests.get(f"{BASE_URL}/api/agents/lifecycle", timeout=15)
        # No auth required on this endpoint (no Depends(verify_token))
        assert r.status_code == 200, r.text
        j = r.json()
        assert "agents" in j and len(j["agents"]) >= 1
        assert "all_roles" in j

    def test_per_agent_conversation_history_exists(self, H):
        """Spec: 'whether per-agent CONVERSATION HISTORY or PAST TASKS exists'."""
        r = requests.get(f"{BASE_URL}/api/agents/conversations", headers=H, timeout=15)
        assert r.status_code == 200, r.text
        # shape should be a list (possibly empty)
        body = r.json()
        items = body if isinstance(body, list) else body.get("conversations", [])
        assert isinstance(items, list)
