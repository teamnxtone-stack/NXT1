"""NXT1 Phase 7 R1 — Autonomous Debugging Loop + Multi-agent foundation tests.

Covers:
- GET /api/agents (lists 5 agents with role+label)
- POST /api/projects/{id}/runtime/auto-fix when no errors → ok=true, has_errors=false
- POST /api/agents/run with role='debug' (small prompt) → 200
- POST /api/agents/run with role='unknown' → 400
- End-to-end auto-fix loop on fresh project (ONE real OpenAI call):
    create project → write broken backend → start runtime → /api/broken=500
    → auto-fix proposes fix → apply → /api/broken=200 → version snapshot exists
    → cleanup
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PASSWORD = "555"


# -------- Fixtures --------
@pytest.fixture(scope="session")
def auth_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# -------- Multi-agent foundation --------
class TestAgents:
    def test_list_agents(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/agents", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # accept either {agents:[...]} or list
        agents = data.get("agents") if isinstance(data, dict) else data
        assert isinstance(agents, list), data
        assert len(agents) >= 5, f"expected >=5 agents, got {len(agents)}"
        roles = {a.get("role") for a in agents}
        assert {"architecture", "frontend", "backend", "debug", "devops"}.issubset(roles), roles
        for a in agents:
            assert a.get("role"), a
            assert a.get("label"), a

    def test_run_agent_unknown_role(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/agents/run",
            headers=auth_headers,
            json={"role": "unknown", "prompt": "x"},
            timeout=30,
        )
        assert r.status_code == 400, r.text
        body = r.json()
        msg = (body.get("detail") or body.get("message") or str(body)).lower()
        assert "unknown" in msg and "unknown agent" in msg or "unknown agent role" in msg, body

    def test_run_agent_debug_small_prompt(self, auth_headers):
        # tiny prompt to limit tokens
        r = requests.post(
            f"{BASE_URL}/api/agents/run",
            headers=auth_headers,
            json={"role": "debug", "prompt": "Diagnose: NameError x is not defined."},
            timeout=120,
        )
        assert r.status_code == 200, r.text[:500]
        body = r.json()
        # text always present, parsed may be None
        assert "text" in body, body
        assert isinstance(body.get("text"), str) and len(body["text"]) > 0


# -------- Auto-fix: no-errors path --------
class TestAutoFixNoErrors:
    def test_auto_fix_returns_ok_when_no_errors(self, auth_headers):
        # Create a fresh project (no runtime started, no errors)
        rc = requests.post(
            f"{BASE_URL}/api/projects",
            headers=auth_headers,
            json={"name": "TEST_phase7_noerr", "description": "no-err"},
            timeout=20,
        )
        assert rc.status_code == 200
        pid = rc.json()["id"]
        try:
            # Empty body: omit json entirely so FastAPI sees no body and uses None
            r = requests.post(
                f"{BASE_URL}/api/projects/{pid}/runtime/auto-fix",
                headers=auth_headers, timeout=30,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("ok") is True, body
            assert body.get("has_errors") is False, body
            assert body.get("fix_id") is None, body
            assert body.get("files") == [], body
        finally:
            requests.delete(f"{BASE_URL}/api/projects/{pid}", headers=auth_headers, timeout=15)


# -------- End-to-end autonomous fix loop (ONE real OpenAI call) --------
@pytest.mark.e2e
class TestAutoFixE2E:
    def test_autonomous_fix_loop(self, auth_headers):
        # 1) create project
        rc = requests.post(
            f"{BASE_URL}/api/projects",
            headers=auth_headers,
            json={"name": "TEST_phase7_autofix", "description": "autofix"},
            timeout=20,
        )
        assert rc.status_code == 200, rc.text
        pid = rc.json()["id"]

        try:
            broken_server = (
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                "@app.get('/api/broken')\n"
                "def broken():\n"
                "    return {'value': undefined_var}\n"
            )
            requirements = "fastapi\nuvicorn\n"

            # 2) write broken server.py + requirements.txt
            r1 = requests.put(
                f"{BASE_URL}/api/projects/{pid}/files/backend/server.py",
                headers=auth_headers, json={"content": broken_server}, timeout=15,
            )
            assert r1.status_code == 200, r1.text
            r2 = requests.put(
                f"{BASE_URL}/api/projects/{pid}/files/backend/requirements.txt",
                headers=auth_headers, json={"content": requirements}, timeout=15,
            )
            assert r2.status_code == 200, r2.text

            # 3) start runtime
            rs = requests.post(
                f"{BASE_URL}/api/projects/{pid}/runtime/start",
                headers=auth_headers, json={}, timeout=90,
            )
            assert rs.status_code == 200, rs.text[:500]
            # wait for runtime to come alive
            alive = False
            for _ in range(30):
                time.sleep(1)
                rh = requests.get(
                    f"{BASE_URL}/api/projects/{pid}/runtime",
                    headers=auth_headers, timeout=15,
                )
                if rh.status_code == 200 and rh.json().get("alive"):
                    alive = True
                    break
            assert alive, "runtime did not become alive within 30s"

            # 4) try-it on /api/broken → 500
            rt = requests.post(
                f"{BASE_URL}/api/projects/{pid}/runtime/try",
                headers=auth_headers,
                json={"method": "GET", "path": "/api/broken"},
                timeout=30,
            )
            assert rt.status_code == 200, rt.text
            try_body = rt.json()
            # status of upstream is in body (status / status_code)
            upstream_status = try_body.get("status") or try_body.get("status_code") or try_body.get("response", {}).get("status")
            assert upstream_status == 500, f"expected 500 from /api/broken, got {upstream_status}: {try_body}"

            # 5) auto-fix proposal — empty body (use runtime error buffer)
            raf = requests.post(
                f"{BASE_URL}/api/projects/{pid}/runtime/auto-fix",
                headers=auth_headers, timeout=180,
            )
            assert raf.status_code == 200, raf.text[:500]
            fix = raf.json()
            assert fix.get("has_errors") is True, fix
            assert fix.get("confidence") in {"high", "medium", "low"}, fix
            files = fix.get("files") or []
            assert len(files) >= 1, fix
            f0 = files[0]
            assert f0.get("path") == "backend/server.py", f0
            after = f0.get("after") or ""
            # The AI may mention "undefined_var" in a code comment, but it must
            # not be referenced as an identifier any more. Strip line-comments first.
            after_no_comments = "\n".join(
                line.split("#", 1)[0] for line in after.splitlines()
            )
            assert "undefined_var" not in after_no_comments, f"undefined_var still in after code: {after[:300]}"
            diff = f0.get("diff") or {}
            added = diff.get("added", diff.get("additions"))
            removed = diff.get("removed", diff.get("removals"))
            assert added is not None and removed is not None, diff
            # post_fix_action
            assert fix.get("post_fix_action") == "restart_runtime", fix

            # 6) apply
            apply_payload = {
                "fix_id": fix.get("fix_id"),
                "files": [{"path": f["path"], "after": f["after"]} for f in files],
                "restart_runtime": True,
                "fix_summary": fix.get("fix_summary") or "auto-fix",
                "diagnosis": fix.get("diagnosis") or "",
            }
            ra = requests.post(
                f"{BASE_URL}/api/projects/{pid}/runtime/auto-fix/apply",
                headers=auth_headers, json=apply_payload, timeout=120,
            )
            assert ra.status_code == 200, ra.text[:500]
            ab = ra.json()
            assert ab.get("restarted") is True, ab
            runtime_obj = ab.get("runtime") or {}
            assert runtime_obj.get("alive") is True, ab

            # wait for runtime to settle after restart
            time.sleep(3)
            for _ in range(20):
                rh = requests.get(
                    f"{BASE_URL}/api/projects/{pid}/runtime",
                    headers=auth_headers, timeout=15,
                )
                if rh.status_code == 200 and rh.json().get("alive"):
                    break
                time.sleep(1)

            # 7) try again /api/broken → 200
            rt2 = requests.post(
                f"{BASE_URL}/api/projects/{pid}/runtime/try",
                headers=auth_headers,
                json={"method": "GET", "path": "/api/broken"},
                timeout=30,
            )
            assert rt2.status_code == 200, rt2.text
            try_body2 = rt2.json()
            upstream_status2 = try_body2.get("status") or try_body2.get("status_code") or try_body2.get("response", {}).get("status")
            assert upstream_status2 == 200, f"expected 200 after fix, got {upstream_status2}: {try_body2}"

            # 8) /commits → version snapshot of type 'auto-fix' should be present
            rg = requests.get(
                f"{BASE_URL}/api/projects/{pid}/commits",
                headers=auth_headers, timeout=15,
            )
            assert rg.status_code == 200
            commits = rg.json() or []
            types = [c.get("type") for c in commits]
            assert "auto-fix" in types, types

        finally:
            # 9) cleanup: stop runtime + delete project
            try:
                requests.post(f"{BASE_URL}/api/projects/{pid}/runtime/stop",
                              headers=auth_headers, timeout=30)
            except Exception:
                pass
            requests.delete(f"{BASE_URL}/api/projects/{pid}",
                            headers=auth_headers, timeout=15)
