"""Phase 20 — Iteration 2 backend tests.

Validates:
- Vendored UI blocks endpoints: /implemented, /blocks/{id}/source, annotated /blocks/{id}
- Login regression with new APP_PASSWORD=555
- Workflow reconciliation hook via direct service call (avoids LLM dependency)
- Phase 20 regressions: ui-registry, workflows list, hosting/readiness, runner/config,
  caddy/generate (HSTS).
"""
import asyncio
import os
import sys
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
sys.path.insert(0, "/app/backend")


EXPECTED_BLOCK_IDS = {
    "hero.aceternity.spotlight",
    "hero.magicui.bento",
    "hero.aceternity.background-beams",
    "card.magicui.shine-border",
    "card.aceternity.3d-pin",
    "feature.magicui.marquee",
    "feature.magicui.orbiting-circles",
    "feature.aceternity.bento-grid",
    "text.magicui.animated-gradient",
    "text.magicui.typing-animation",
    "background.magicui.dot-pattern",
    "background.aceternity.wavy",
    "background.aceternity.meteors",
    "input.originui.search-with-shortcut",
    "input.originui.password-strength",
    "scene.r3f.particles",
    "scene.r3f.globe",
}


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def token(session):
    r = session.post(f"{BASE_URL}/api/auth/login", json={"password": "555"}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok and isinstance(tok, str) and len(tok) > 20, f"no token in {data}"
    return tok


@pytest.fixture(scope="module")
def auth_session(session, token):
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


# ---------- Login regression ----------
class TestAuth:
    def test_login_with_new_password(self, session):
        r = session.post(f"{BASE_URL}/api/auth/login", json={"password": "555"}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        tok = data.get("token") or data.get("access_token")
        assert tok and len(tok) > 20

    def test_login_with_old_password_fails(self, session):
        r = session.post(f"{BASE_URL}/api/auth/login", json={"password": "nxt1admin"}, timeout=20)
        assert r.status_code in (401, 403), f"old password should not work, got {r.status_code}"


# ---------- Vendored blocks endpoints ----------
class TestVendoredBlocks:
    def test_implemented_list(self, session):
        r = session.get(f"{BASE_URL}/api/ui-registry/implemented", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("count") == 17, f"expected 17 implemented, got {data.get('count')}"
        ids = set(data.get("implemented") or [])
        missing = EXPECTED_BLOCK_IDS - ids
        assert not missing, f"missing block ids: {missing}"

    def test_source_endpoint_spotlight(self, session):
        r = session.get(
            f"{BASE_URL}/api/ui-registry/blocks/hero.aceternity.spotlight/source",
            timeout=20,
        )
        assert r.status_code == 200, r.text
        # content type plain text
        assert "text/plain" in r.headers.get("content-type", "").lower()
        text = r.text
        assert len(text) > 0
        assert "export default function SpotlightHero" in text

    def test_source_404_for_unknown(self, session):
        r = session.get(
            f"{BASE_URL}/api/ui-registry/blocks/nope/source", timeout=20,
        )
        assert r.status_code == 404

    def test_annotated_block_returns_source_url(self, session):
        r = session.get(
            f"{BASE_URL}/api/ui-registry/blocks/hero.aceternity.spotlight", timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("implemented") is True
        assert (
            data.get("source_url")
            == "/api/ui-registry/blocks/hero.aceternity.spotlight/source"
        )

    def test_annotated_unimplemented_or_missing(self, session):
        # request a known registry id but check structure: pick any unimplemented if present
        reg = session.get(f"{BASE_URL}/api/ui-registry", timeout=20).json()
        block_ids = [b["id"] for b in reg.get("blocks", [])]
        # all 17 are implemented now per spec, just sanity check structure on one
        bid = "hero.aceternity.spotlight"
        assert bid in block_ids
        r = session.get(f"{BASE_URL}/api/ui-registry/blocks/{bid}", timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert "implemented" in j and "source_url" in j


# ---------- Regression: Phase 20 tracks still work ----------
class TestPhase20Regression:
    def test_registry_root(self, session):
        r = session.get(f"{BASE_URL}/api/ui-registry", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert len(data.get("packs") or []) == 6, f"packs={len(data.get('packs') or [])}"
        assert len(data.get("blocks") or []) == 17, f"blocks={len(data.get('blocks') or [])}"

    def test_workflows_list(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/workflows/list", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # Accept either {workflows:[...]} or raw list
        assert isinstance(data, (list, dict))

    def test_hosting_readiness(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/hosting/readiness", timeout=20)
        assert r.status_code == 200, r.text

    def test_runner_config(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/runner/config", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("mode") == "subprocess", f"got mode={data.get('mode')}"

    def test_caddy_generate_hsts(self, auth_session):
        payload = {"domains": ["example.com"], "upstream": "http://localhost:8001"}
        r = auth_session.post(
            f"{BASE_URL}/api/hosting/caddy/generate", json=payload, timeout=20
        )
        assert r.status_code == 200, r.text
        data = r.json()
        caddyfile = data.get("caddyfile") or data.get("config") or ""
        if not caddyfile and isinstance(data, dict):
            # try any string val
            for v in data.values():
                if isinstance(v, str) and "Strict-Transport" in v:
                    caddyfile = v
                    break
        assert "Strict-Transport-Security" in caddyfile, (
            f"HSTS missing from caddyfile output: {data}"
        )


# ---------- Workflow reconciliation ----------
class TestWorkflowReconciliation:
    """Validate the reconcile_coder_phase function directly — avoids needing a
    working LLM call. Spec says either path is acceptable.
    """

    def test_reconcile_direct_service_call(self, auth_session):
        # Create a project
        r = auth_session.post(
            f"{BASE_URL}/api/projects",
            json={"name": f"TEST_recon_{uuid.uuid4().hex[:8]}",
                  "description": "reconcile test"},
            timeout=20,
        )
        assert r.status_code in (200, 201), r.text
        proj = r.json()
        project_id = proj.get("id") or proj.get("project_id")
        assert project_id

        # Start a workflow on this project
        r = auth_session.post(
            f"{BASE_URL}/api/workflows/start",
            json={"project_id": project_id, "prompt": "Build a landing page."},
            timeout=20,
        )
        assert r.status_code in (200, 201), r.text
        wf = r.json()
        workflow_id = wf.get("workflow_id")
        assert workflow_id

        # Give the background graph a moment to reach a non-terminal state
        import time as _t
        _t.sleep(3.0)

        # Run all async ops in a single event loop to keep Motor's client bound.
        from services import workflow_service

        async def _do_seed_and_reconcile():
            await workflow_service._db.projects.update_one(
                {"id": project_id},
                {"$set": {"files": [
                    {"path": "index.html", "content": "<html></html>"},
                    {"path": "styles/main.css", "content": "body{}"},
                ]}},
            )
            return await workflow_service.reconcile_coder_phase(
                project_id, files_count=2, explanation="test reconcile"
            )

        result = asyncio.run(_do_seed_and_reconcile())
        assert result is not None, "reconcile returned None (no in-flight wf?)"
        assert result.get("reconciled") is True
        assert result.get("tester_ok") is True
        assert result.get("files_count") == 2

        # Verify workflow doc has reconciliation history entry
        r = auth_session.get(
            f"{BASE_URL}/api/workflows/list?project_id={project_id}", timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        wfs = body if isinstance(body, list) else (body.get("workflows") or body.get("items") or [])
        assert wfs, f"no workflows returned: {body}"
        wf_doc = next((w for w in wfs if w.get("workflow_id") == workflow_id), wfs[0])
        history = wf_doc.get("history") or []
        msgs = [h.get("message", "") for h in history]
        assert any("reconciled from chat stream" in m for m in msgs), (
            f"missing reconcile entry. messages: {msgs}"
        )
        # status should be 'waiting' after deployer phase
        assert wf_doc.get("status") == "waiting", f"status={wf_doc.get('status')}"
        # last deployer entry should be there
        assert any(h.get("phase") == "deployer" for h in history), (
            "no deployer phase in history"
        )
