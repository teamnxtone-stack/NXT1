"""Phase 20 — Four-track backend tests:
A) Premium UI registry
B) Durable LangGraph workflows
C) Caddy + Cloudflare hosting OS
D) Sandboxed self-heal runner
Plus regression checks on /system/ready, /auth/login, /scaffolds, /ai/providers.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
PWD = os.environ.get("APP_PASSWORD", "555")


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PWD}, timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def project_id(auth_headers):
    r = requests.post(
        f"{BASE_URL}/api/projects",
        headers=auth_headers,
        json={"name": f"TEST_phase20_{uuid.uuid4().hex[:6]}", "prompt": "saas dashboard"},
        timeout=20,
    )
    assert r.status_code in (200, 201), r.text
    pid = r.json().get("id") or r.json().get("project_id")
    assert pid, f"no project id: {r.text}"
    return pid


# ---------- Regression ----------
class TestRegression:
    def test_system_ready(self):
        r = requests.get(f"{BASE_URL}/api/system/ready", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ready") is True
        assert d.get("ai_providers", {}).get("total") == 8

    def test_auth_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PWD}, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json().get("token"), str)

    def test_scaffolds_count(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/scaffolds", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("items") or data.get("scaffolds") or []
        assert len(items) >= 10, f"got {len(items)} scaffolds"

    def test_ai_providers(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/ai/providers", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        providers = data if isinstance(data, list) else data.get("providers") or data.get("items") or []
        assert len(providers) == 8, f"got {len(providers)} providers"


# ---------- Track A: UI Registry ----------
class TestTrackA_UIRegistry:
    def test_get_registry_full(self):
        r = requests.get(f"{BASE_URL}/api/ui-registry", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert len(d.get("packs", [])) == 6, f"packs={d.get('packs')}"
        assert d.get("total") == 17, f"total={d.get('total')}"
        assert len(d.get("blocks", [])) == 17

    def test_filter_by_kind(self):
        r = requests.get(f"{BASE_URL}/api/ui-registry", params={"kind": "hero"}, timeout=10)
        assert r.status_code == 200
        blocks = r.json().get("blocks", [])
        assert len(blocks) > 0
        assert all(b.get("kind") == "hero" for b in blocks)

    def test_filter_by_pack(self):
        r = requests.get(f"{BASE_URL}/api/ui-registry", params={"pack": "magicui"}, timeout=10)
        assert r.status_code == 200
        blocks = r.json().get("blocks", [])
        assert len(blocks) > 0
        assert all(b.get("pack") == "magicui" for b in blocks)

    def test_directive(self):
        r = requests.get(f"{BASE_URL}/api/ui-registry/directive", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d.get("directive"), str) and len(d["directive"]) > 0
        assert d.get("block_count") == 17

    def test_get_block_by_id(self):
        r = requests.get(f"{BASE_URL}/api/ui-registry/blocks/hero.aceternity.spotlight", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("id") == "hero.aceternity.spotlight"
        assert d.get("pack") == "aceternity"

    def test_get_block_404(self):
        r = requests.get(f"{BASE_URL}/api/ui-registry/blocks/does.not.exist", timeout=10)
        assert r.status_code == 404


# ---------- Track B: Workflows ----------
class TestTrackB_Workflows:
    def test_start_workflow_404_for_unknown_project(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/workflows/start",
            headers=auth_headers,
            json={"project_id": "nonexistent-xyz", "prompt": "build it"},
            timeout=15,
        )
        assert r.status_code == 404

    def test_start_workflow_and_lifecycle(self, auth_headers, project_id):
        # Start
        r = requests.post(
            f"{BASE_URL}/api/workflows/start",
            headers=auth_headers,
            json={"project_id": project_id, "prompt": "build a saas dashboard"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        wf_id = r.json().get("workflow_id")
        assert wf_id

        # List filtered by project_id
        r = requests.get(
            f"{BASE_URL}/api/workflows/list",
            headers=auth_headers, params={"project_id": project_id}, timeout=10,
        )
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert any(w.get("workflow_id") == wf_id for w in items)

        # Poll until terminal/waiting (max ~60s)
        terminal = {"waiting", "completed", "failed", "cancelled"}
        final = None
        for _ in range(60):
            time.sleep(1)
            g = requests.get(f"{BASE_URL}/api/workflows/{wf_id}", headers=auth_headers, timeout=10)
            assert g.status_code == 200
            final = g.json()
            if final.get("status") in terminal:
                break
        assert final is not None
        assert final.get("status") in terminal, f"stuck at {final.get('status')}"

        # Track history phases
        phases = [h.get("phase") for h in final.get("history", [])]
        # Planner+architect+coder+tester should have run; deployer marks waiting
        assert "planner" in phases
        assert "architect" in phases

        # If status is waiting, requires_approval must be True and we can resume
        if final.get("status") == "waiting":
            assert final.get("requires_approval") is True
            r = requests.post(
                f"{BASE_URL}/api/workflows/{wf_id}/resume",
                headers=auth_headers, json={"approval": True}, timeout=15,
            )
            assert r.status_code == 200, r.text
            assert r.json().get("status") == "completed"

            # verify persistence
            g = requests.get(f"{BASE_URL}/api/workflows/{wf_id}",
                             headers=auth_headers, timeout=10)
            assert g.json().get("status") == "completed"

    def test_cancel_workflow(self, auth_headers, project_id):
        r = requests.post(
            f"{BASE_URL}/api/workflows/start",
            headers=auth_headers,
            json={"project_id": project_id, "prompt": "tmp cancel"},
            timeout=15,
        )
        assert r.status_code == 200
        wf_id = r.json()["workflow_id"]
        # Cancel immediately; should succeed while not terminal
        r = requests.post(f"{BASE_URL}/api/workflows/{wf_id}/cancel",
                          headers=auth_headers, timeout=10)
        # May race with background completion. Accept ok or 400 if already terminal.
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            assert r.json().get("ok") is True


# ---------- Track C: Hosting / Caddy / Cloudflare ----------
class TestTrackC_Hosting:
    def test_readiness(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/hosting/readiness", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "checklist" in d and isinstance(d["checklist"], list)
        assert "caddy_install_available" in d
        keys = {c["key"] for c in d["checklist"]}
        assert {"upstream", "cf_connected", "caddy_guide"}.issubset(keys)

    def test_caddy_generate(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/hosting/caddy/generate",
            headers=auth_headers,
            json={"domains": ["example.com", "www.example.com"], "email": "ops@example.com"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        cf = d.get("caddyfile", "")
        assert "example.com" in cf
        assert "www.example.com" in cf
        assert "Strict-Transport-Security" in cf or "HSTS" in cf or "max-age" in cf
        assert isinstance(d.get("compose_snippet"), str) and len(d["compose_snippet"]) > 0

    def test_caddy_install_guide(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/hosting/caddy/install-guide",
            headers=auth_headers, params={"domain": "example.com"}, timeout=10,
        )
        assert r.status_code == 200
        d = r.json()
        # Should be a steps payload
        as_str = str(d).lower()
        assert "step" in as_str or "domain" in as_str

    def test_cf_status_default(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/hosting/cloudflare/status",
                         headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("connected") is False

    def test_cf_connect_invalid_token(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/hosting/cloudflare/connect",
            headers=auth_headers,
            json={"token": "short"},
            timeout=10,
        )
        assert r.status_code == 400

    def test_cf_connect_invalid_long_token(self, auth_headers):
        # passes length check, fails CF verify
        r = requests.post(
            f"{BASE_URL}/api/hosting/cloudflare/connect",
            headers=auth_headers,
            json={"token": "x" * 60},
            timeout=15,
        )
        assert r.status_code == 400


# ---------- Track D: Runner / Self-heal ----------
class TestTrackD_Runner:
    def test_runner_config(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/runner/config", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("mode") == "subprocess"
        assert "runner_root" in d
        assert "max_attempts_default" in d

    def test_quick_build(self, auth_headers, project_id):
        r = requests.post(
            f"{BASE_URL}/api/runner/projects/{project_id}/quick-build",
            headers=auth_headers, timeout=120,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # ok=true OR skipped permitted, plus an exit_code
        assert "ok" in d or "skipped" in d
        assert "exit_code" in d or "skipped" in d

    def test_self_heal_sse(self, auth_headers, project_id):
        # Use max_attempts=1 to keep this bounded
        with requests.post(
            f"{BASE_URL}/api/runner/projects/{project_id}/self-heal",
            headers=auth_headers,
            json={"max_attempts": 1},
            stream=True,
            timeout=180,
        ) as r:
            assert r.status_code == 200, r.text
            ct = r.headers.get("content-type", "")
            assert "text/event-stream" in ct, f"unexpected ct={ct}"
            got_event = False
            for raw in r.iter_lines(decode_unicode=True):
                if raw and raw.startswith("data:"):
                    got_event = True
                    break
            assert got_event, "no SSE event received"
