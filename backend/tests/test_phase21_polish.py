"""Phase 21 polish pass — Iteration 3 backend tests.

Validates the 4 follow-ups from the polish pass:
- /implemented returns manifest + source_of_truth keys
- /source endpoint sets Cache-Control: public, max-age=3600, immutable + X-NXT1-* headers
- /blocks/{id} now annotates named_export + file fields
- _has_entry helper is shared between node_tester and reconcile_coder_phase
- Workflow lifecycle still reaches status='waiting'
- Regression on all Phase 20 endpoints
"""
import asyncio
import inspect
import os
import sys
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
# Cache-Control is overridden to "no-store, no-cache" by the K8s/Cloudflare
# ingress for the public preview URL, so to verify the backend's own header
# emission we hit localhost:8001 directly for that test only.
LOCAL_URL = "http://localhost:8001"
sys.path.insert(0, "/app/backend")


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


# ---------- /implemented manifest exposure ----------
class TestImplementedManifest:
    def test_count_and_keys(self, session):
        r = session.get(f"{BASE_URL}/api/ui-registry/implemented", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("count") == 17, f"expected 17, got {data.get('count')}"
        # New keys from polish pass
        assert "manifest" in data, f"'manifest' key missing: {list(data.keys())}"
        manifest_path = data["manifest"]
        assert "block_sources.json" in manifest_path, f"unexpected manifest path: {manifest_path}"
        assert "source_of_truth" in data, f"'source_of_truth' key missing: {list(data.keys())}"
        sot = data["source_of_truth"]
        assert "BLOCK_MAP" in sot, f"unexpected source_of_truth: {sot}"
        assert "index.js" in sot, f"unexpected source_of_truth: {sot}"


# ---------- /source cache headers ----------
class TestSourceCacheHeaders:
    def test_spotlight_source_cache_and_xheaders(self, session):
        bid = "hero.aceternity.spotlight"
        # Hit backend directly — ingress overrides Cache-Control for the
        # public preview domain (Cloudflare strips public/immutable).
        r = session.get(
            f"{LOCAL_URL}/api/ui-registry/blocks/{bid}/source", timeout=20,
        )
        assert r.status_code == 200, r.text
        cc = r.headers.get("Cache-Control", "")
        assert "public" in cc and "max-age=3600" in cc and "immutable" in cc, (
            f"Cache-Control missing expected directives: '{cc}'"
        )
        assert r.headers.get("X-NXT1-Block-Id") == bid, (
            f"X-NXT1-Block-Id mismatch: {r.headers.get('X-NXT1-Block-Id')}"
        )
        assert r.headers.get("X-NXT1-Block-File") == "SpotlightHero.jsx", (
            f"X-NXT1-Block-File mismatch: {r.headers.get('X-NXT1-Block-File')}"
        )
        # Also verify X-* headers pass through the public ingress
        r2 = session.get(
            f"{BASE_URL}/api/ui-registry/blocks/{bid}/source", timeout=20,
        )
        assert r2.status_code == 200
        assert r2.headers.get("X-NXT1-Block-Id") == bid
        assert r2.headers.get("X-NXT1-Block-File") == "SpotlightHero.jsx"

    def test_primitives_source_xheader_file(self, session):
        bid = "text.magicui.animated-gradient"
        r = session.get(
            f"{LOCAL_URL}/api/ui-registry/blocks/{bid}/source", timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.headers.get("X-NXT1-Block-File") == "Primitives.jsx"
        assert r.headers.get("X-NXT1-Block-Id") == bid
        # named-export header for primitive-style blocks
        assert r.headers.get("X-NXT1-Named-Export") == "AnimatedGradientText"
        cc = r.headers.get("Cache-Control", "")
        assert "immutable" in cc and "max-age=3600" in cc


# ---------- /blocks/{id} annotation (named_export + file) ----------
class TestBlockAnnotation:
    def test_primitive_named_export(self, session):
        r = session.get(
            f"{BASE_URL}/api/ui-registry/blocks/text.magicui.animated-gradient",
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("named_export") == "AnimatedGradientText", (
            f"named_export wrong: {data.get('named_export')}"
        )
        assert data.get("file") == "Primitives.jsx", f"file wrong: {data.get('file')}"
        assert data.get("implemented") is True

    def test_default_export_block(self, session):
        r = session.get(
            f"{BASE_URL}/api/ui-registry/blocks/hero.aceternity.spotlight",
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("named_export") is None, (
            f"expected null named_export, got {data.get('named_export')}"
        )
        assert data.get("file") == "SpotlightHero.jsx", f"file wrong: {data.get('file')}"


# ---------- _has_entry shared helper ----------
class TestHasEntryHelper:
    def test_helper_exists_and_is_used(self):
        from services import workflow_service

        assert hasattr(workflow_service, "_has_entry"), (
            "workflow_service._has_entry helper missing"
        )
        # Function semantics
        assert workflow_service._has_entry([{"path": "index.html"}]) is True
        assert workflow_service._has_entry([{"path": "src/main.tsx"}]) is True
        assert workflow_service._has_entry([{"path": "app/page.jsx"}]) is True
        assert workflow_service._has_entry([{"path": "README.md"}]) is False
        assert workflow_service._has_entry([]) is False
        assert workflow_service._has_entry(None) is False  # robust to None

        # Make sure both call sites use the helper (no inline duplication of
        # the entry-paths set).
        node_tester_src = inspect.getsource(workflow_service.node_tester)
        reconcile_src = inspect.getsource(workflow_service.reconcile_coder_phase)
        assert "_has_entry(" in node_tester_src, (
            "node_tester does not call _has_entry"
        )
        assert "_has_entry(" in reconcile_src, (
            "reconcile_coder_phase does not call _has_entry"
        )

    def test_tester_records_has_entry_false_for_empty_files(self, auth_session):
        # Create project with NO files seeded
        r = auth_session.post(
            f"{BASE_URL}/api/projects",
            json={"name": f"TEST_p21_noentry_{uuid.uuid4().hex[:8]}",
                  "description": "no entry test"},
            timeout=20,
        )
        assert r.status_code in (200, 201), r.text
        project_id = r.json().get("id") or r.json().get("project_id")
        assert project_id

        # Ensure files list is empty (overwrite any defaults).
        # Use a fresh Motor client bound to this event loop.
        async def _clear():
            from motor.motor_asyncio import AsyncIOMotorClient
            from services import workflow_service as ws

            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            ws._client = client
            ws._db = db
            ws.COL = db.workflows
            await db.projects.update_one(
                {"id": project_id}, {"$set": {"files": []}},
            )
        asyncio.run(_clear())

        # Start workflow
        r = auth_session.post(
            f"{BASE_URL}/api/workflows/start",
            json={"project_id": project_id, "prompt": "Build something."},
            timeout=20,
        )
        assert r.status_code in (200, 201), r.text
        workflow_id = r.json().get("workflow_id")
        assert workflow_id

        # Wait for the background graph to walk through tester
        import time as _t
        _t.sleep(4.0)

        r = auth_session.get(
            f"{BASE_URL}/api/workflows/list?project_id={project_id}", timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        wfs = body if isinstance(body, list) else (body.get("workflows") or body.get("items") or [])
        wf = next((w for w in wfs if w.get("workflow_id") == workflow_id), None)
        assert wf, f"workflow not found in list: {body}"
        test_results = wf.get("test_results") or {}
        # Either test_results has_entry=False or a tester history entry recorded failed
        history = wf.get("history") or []
        tester_entries = [h for h in history if h.get("phase") == "tester"]
        assert tester_entries, "no tester history entries"
        # Could be has_entry=False on test_results or last tester status=failed
        assert (test_results.get("has_entry") is False) or any(
            h.get("status") == "failed" for h in tester_entries
        ), f"tester did not record has_entry=False: test_results={test_results}, tester={tester_entries}"


# ---------- Workflow lifecycle reaches waiting via reconcile ----------
class TestWorkflowLifecycle:
    def test_start_and_reconcile_to_waiting(self, auth_session):
        r = auth_session.post(
            f"{BASE_URL}/api/projects",
            json={"name": f"TEST_p21_lifecycle_{uuid.uuid4().hex[:8]}",
                  "description": "lifecycle"},
            timeout=20,
        )
        assert r.status_code in (200, 201), r.text
        project_id = r.json().get("id") or r.json().get("project_id")

        r = auth_session.post(
            f"{BASE_URL}/api/workflows/start",
            json={"project_id": project_id, "prompt": "Landing page."},
            timeout=20,
        )
        assert r.status_code in (200, 201), r.text
        workflow_id = r.json().get("workflow_id")
        assert workflow_id

        import time as _t
        _t.sleep(3.0)

        async def _seed_and_reconcile():
            # Fresh Motor client bound to this event loop — module-level
            # client in workflow_service was bound to an earlier (now-closed)
            # loop from the previous test's asyncio.run().
            from motor.motor_asyncio import AsyncIOMotorClient
            from services import workflow_service as ws

            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            ws._client = client
            ws._db = db
            ws.COL = db.workflows

            await db.projects.update_one(
                {"id": project_id},
                {"$set": {"files": [
                    {"path": "index.html", "content": "<html></html>"},
                ]}},
            )
            return await ws.reconcile_coder_phase(
                project_id, files_count=1, explanation="lifecycle test"
            )

        result = asyncio.run(_seed_and_reconcile())
        assert result is not None, "reconcile returned None"
        assert result.get("tester_ok") is True

        r = auth_session.get(
            f"{BASE_URL}/api/workflows/list?project_id={project_id}", timeout=20,
        )
        body = r.json()
        wfs = body if isinstance(body, list) else (body.get("workflows") or body.get("items") or [])
        wf = next((w for w in wfs if w.get("workflow_id") == workflow_id), None)
        assert wf, "workflow not found"
        assert wf.get("status") == "waiting", f"status={wf.get('status')}"
        history = wf.get("history") or []
        assert any(h.get("phase") == "deployer" and h.get("status") == "waiting"
                   for h in history), "no deployer waiting entry"


# ---------- Phase 20 regression ----------
class TestPhase20Regression:
    def test_login(self, session):
        r = session.post(f"{BASE_URL}/api/auth/login", json={"password": "555"}, timeout=20)
        assert r.status_code == 200

    def test_ui_registry_root(self, session):
        r = session.get(f"{BASE_URL}/api/ui-registry", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert len(data.get("blocks") or []) == 17
        assert len(data.get("packs") or []) == 6

    def test_workflows_list(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/workflows/list", timeout=20)
        assert r.status_code == 200

    def test_hosting_readiness(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/hosting/readiness", timeout=20)
        assert r.status_code == 200

    def test_runner_config(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/runner/config", timeout=20)
        assert r.status_code == 200
        assert r.json().get("mode") == "subprocess"

    def test_caddy_generate(self, auth_session):
        payload = {"domains": ["example.com"], "upstream": "http://localhost:8001"}
        r = auth_session.post(
            f"{BASE_URL}/api/hosting/caddy/generate", json=payload, timeout=20
        )
        assert r.status_code == 200
        data = r.json()
        body = data.get("caddyfile") or data.get("config") or ""
        if not body and isinstance(data, dict):
            for v in data.values():
                if isinstance(v, str) and "Strict-Transport" in v:
                    body = v
                    break
        assert "Strict-Transport-Security" in body
