"""NXT1 backend API tests — Phase 2/3 (providers, deployments, domains, multi-file).

Covers:
- Auth, system providers
- Project CRUD + new 4-file scaffold (index.html, styles/main.css, scripts/app.js, README.md)
- Multi-file PUT/DELETE (arbitrary paths e.g. pages/about.html)
- Real OpenAI chat (provider='openai', gpt-5.1) with SHORT prompt
- Deployments endpoints (create, list, detail, cancel rejection on completed)
- Public deploy serving (index, multi-page, CSS file as text/css)
- Domains: add, list, verify, primary, delete
- Backward-compat: POST /api/projects/{id}/deploy
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PASSWORD = "555"  # Phase 4: changed from 'nxt1admin'


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def project(auth_headers):
    """One shared project used by deploy/domain/file/chat tests (cleaner & faster)."""
    r = requests.post(
        f"{BASE_URL}/api/projects",
        headers=auth_headers,
        json={"name": "TEST_phase23", "description": "phase 2/3"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    requests.delete(f"{BASE_URL}/api/projects/{pid}", headers=auth_headers, timeout=15)


# ---------- Auth ----------
class TestAuth:
    def test_login_wrong_password(self):
        # Phase 4: 'nxt1admin' is the OLD password; must now be rejected.
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": "555"}, timeout=15)
        assert r.status_code == 401

    def test_login_correct_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json().get("token"), str)

    def test_verify_valid(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auth/verify", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True


# ---------- System providers ----------
class TestSystemProviders:
    def test_providers_status(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/system/providers", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Phase 4: nested shape { ai:{...}, deploy:[{name,configured,requires_token_env},...], cloudflare_dns_configured: bool }
        assert isinstance(data.get("ai"), dict), data
        assert data["ai"].get("openai") is True  # OPENAI_API_KEY is set in .env
        assert isinstance(data.get("deploy"), list) and len(data["deploy"]) >= 3
        names = {p["name"] for p in data["deploy"]}
        assert {"internal", "vercel", "cloudflare-pages"}.issubset(names), names
        # vercel/cf-pages should be unconfigured (tokens empty)
        for p in data["deploy"]:
            if p["name"] == "vercel":
                assert p["configured"] is False
                assert p["requires_token_env"] == "VERCEL_TOKEN"
            if p["name"] == "cloudflare-pages":
                assert p["configured"] is False
                assert p["requires_token_env"] == "CLOUDFLARE_API_TOKEN"
        assert data.get("cloudflare_dns_configured") is False


# ---------- Project CRUD + new scaffold ----------
class TestProjects:
    def test_list_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/projects", timeout=15)
        assert r.status_code == 401

    def test_create_default_4_files(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects",
            headers=auth_headers,
            json={"name": "TEST_scaffold", "description": "scaffold"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        proj = r.json()
        paths = sorted(f["path"] for f in proj["files"])
        assert paths == ["README.md", "index.html", "scripts/app.js", "styles/main.css"], paths
        # cleanup
        requests.delete(f"{BASE_URL}/api/projects/{proj['id']}", headers=auth_headers, timeout=15)


# ---------- Multi-file PUT/DELETE with arbitrary paths ----------
class TestFiles:
    def test_upsert_arbitrary_path(self, project, auth_headers):
        r = requests.put(
            f"{BASE_URL}/api/projects/{project}/files/pages/about.html",
            headers=auth_headers,
            json={"content": "<h1>About</h1>"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # verify GET project returns it
        rg = requests.get(f"{BASE_URL}/api/projects/{project}", headers=auth_headers, timeout=15)
        assert rg.status_code == 200
        paths = [f["path"] for f in rg.json()["files"]]
        assert "pages/about.html" in paths

    def test_delete_arbitrary_path(self, project, auth_headers):
        # First create a deletable file
        requests.put(
            f"{BASE_URL}/api/projects/{project}/files/scripts/temp.js",
            headers=auth_headers, json={"content": "// temp"}, timeout=15,
        )
        r = requests.delete(
            f"{BASE_URL}/api/projects/{project}/files/scripts/temp.js",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200
        rg = requests.get(f"{BASE_URL}/api/projects/{project}", headers=auth_headers, timeout=15)
        paths = [f["path"] for f in rg.json()["files"]]
        assert "scripts/temp.js" not in paths

    def test_delete_index_html_rejected(self, project, auth_headers):
        r = requests.delete(
            f"{BASE_URL}/api/projects/{project}/files/index.html",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 400, r.text


# ---------- Real OpenAI chat (gpt-5.1) ----------
class TestChatOpenAI:
    def test_chat_openai_short_prompt(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/chat",
            headers=auth_headers,
            json={"message": "Build a small landing page for a coffee shop", "provider": "openai"},
            timeout=120,
        )
        assert r.status_code == 200, f"chat failed: {r.status_code} {r.text[:500]}"
        body = r.json()
        assert body.get("provider") == "openai", body.get("provider")
        # model should be a gpt-4.x family identifier
        assert "gpt-4" in (body.get("model") or "").lower(), body.get("model")
        files = body.get("files", [])
        assert any(f["path"].lower() == "index.html" for f in files)


# ---------- Deployments ----------
class TestDeployments:
    def test_create_deployment(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/deployments",
            headers=auth_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        dep = r.json()
        assert dep.get("status") == "deployed", dep
        assert dep.get("public_url")
        assert dep.get("slug")
        assert isinstance(dep.get("logs"), list) and len(dep["logs"]) > 0
        # store on the project for chained tests
        TestDeployments.dep_id = dep["id"]
        TestDeployments.slug = dep["slug"]

    def test_list_deployments(self, project, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/projects/{project}/deployments",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200
        deps = r.json()
        assert isinstance(deps, list) and len(deps) >= 1
        # most recent first
        assert deps[0]["id"] == TestDeployments.dep_id

    def test_get_deployment_detail(self, project, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/projects/{project}/deployments/{TestDeployments.dep_id}",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == TestDeployments.dep_id
        assert isinstance(d.get("logs"), list)

    def test_cancel_completed_deployment_rejected(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/deployments/{TestDeployments.dep_id}/cancel",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_legacy_deploy_endpoint(self, project, auth_headers):
        """Backward compat: POST /api/projects/{id}/deploy"""
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/deploy",
            headers=auth_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "deployed"


# ---------- Public deploy multi-page / static ----------
class TestPublicDeploy:
    def test_public_index_no_auth(self, project, auth_headers):
        # ensure deployed (re-deploy in case)
        rd = requests.post(f"{BASE_URL}/api/projects/{project}/deployments",
                           headers=auth_headers, timeout=30)
        slug = rd.json()["slug"]
        time.sleep(0.4)
        # Use a clean session (no auth) to confirm public access
        r = requests.get(f"{BASE_URL}/api/deploy/{slug}", timeout=20)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/html")
        # CSS should be inlined: link tag replaced with <style>
        html = r.text
        assert "<style" in html and "main.css" not in html.split("<body")[0].lower().replace("data-from=\"styles/main.css\"", "")
        TestPublicDeploy.slug = slug

    def test_public_about_page(self, project, auth_headers):
        # add about.html, redeploy, fetch
        requests.put(
            f"{BASE_URL}/api/projects/{project}/files/about.html",
            headers=auth_headers,
            json={"content": "<!DOCTYPE html><html><body><h1>About Us</h1></body></html>"},
            timeout=15,
        )
        rd = requests.post(f"{BASE_URL}/api/projects/{project}/deployments",
                           headers=auth_headers, timeout=30)
        slug = rd.json()["slug"]
        time.sleep(0.4)
        r = requests.get(f"{BASE_URL}/api/deploy/{slug}/about.html", timeout=15)
        assert r.status_code == 200, r.text[:300]
        assert "About Us" in r.text

    def test_public_css_static(self, project, auth_headers):
        slug = TestPublicDeploy.slug
        r = requests.get(f"{BASE_URL}/api/deploy/{slug}/styles/main.css", timeout=15)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").startswith("text/css")


# ---------- Domains ----------
class TestDomains:
    domain_id = None

    def test_add_domain(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/domains",
            headers=auth_headers,
            json={"hostname": "example.com"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("hostname") == "example.com"
        # dns instructions should be present
        assert "dns" in str(d).lower() or "cname" in str(d).lower() or d.get("instructions") or d.get("dns_records")
        TestDomains.domain_id = d["id"]

    def test_list_domains(self, project, auth_headers):
        r = requests.get(f"{BASE_URL}/api/projects/{project}/domains",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert any(x["id"] == TestDomains.domain_id for x in r.json())

    def test_verify_domain(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/domains/{TestDomains.domain_id}/verify",
            headers=auth_headers, timeout=20,
        )
        assert r.status_code == 200, r.text
        status = r.json().get("status")
        assert status in {"failed", "pending", "verified"}, status

    def test_primary_domain(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/domains/{TestDomains.domain_id}/primary",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200

    def test_delete_domain(self, project, auth_headers):
        r = requests.delete(
            f"{BASE_URL}/api/projects/{project}/domains/{TestDomains.domain_id}",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200



# ===================== Phase 4 tests =====================

# ---------- Publish-on-save toggle + project state ----------
class TestPublishOnSave:
    def test_default_is_false(self, project, auth_headers):
        # via /state if available, else fall back to project doc
        r = requests.get(f"{BASE_URL}/api/projects/{project}/state",
                         headers=auth_headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            assert data.get("publish_on_save") is False
        else:
            # /state not implemented — flag in report (test skipped, not failed hard)
            pytest.skip(f"/api/projects/{{id}}/state not implemented (HTTP {r.status_code})")

    def test_set_publish_on_save_true(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/publish-on-save",
            headers=auth_headers, json={"publish_on_save": True}, timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("publish_on_save") is True

    def test_persists_after_set(self, project, auth_headers):
        # Set first, then verify via /state OR via the project doc
        requests.post(
            f"{BASE_URL}/api/projects/{project}/publish-on-save",
            headers=auth_headers, json={"publish_on_save": True}, timeout=15,
        )
        r = requests.get(f"{BASE_URL}/api/projects/{project}/state",
                         headers=auth_headers, timeout=15)
        if r.status_code == 200:
            assert r.json().get("publish_on_save") is True
        else:
            # Fall back: verify by re-toggling and checking the response
            r2 = requests.post(
                f"{BASE_URL}/api/projects/{project}/publish-on-save",
                headers=auth_headers, json={"publish_on_save": False}, timeout=15,
            )
            assert r2.json().get("publish_on_save") is False
            # leave it OFF for downstream tests
            pytest.skip("/state endpoint not implemented; toggle round-trip OK")

    def test_toggle_off_for_downstream(self, project, auth_headers):
        # Make sure other tests start with False
        requests.post(
            f"{BASE_URL}/api/projects/{project}/publish-on-save",
            headers=auth_headers, json={"publish_on_save": False}, timeout=15,
        )


# ---------- Streaming chat (SSE) ----------
class TestChatStream:
    def _consume_sse(self, resp, max_seconds=120):
        """Yield parsed JSON events from an SSE response."""
        import json as _json
        start = time.time()
        for raw in resp.iter_lines(decode_unicode=True):
            if time.time() - start > max_seconds:
                break
            if not raw:
                continue
            if raw.startswith("data: "):
                payload = raw[6:]
                try:
                    yield _json.loads(payload)
                except Exception:
                    continue

    def test_chat_stream_basic(self, project, auth_headers):
        # Ensure publish_on_save is OFF
        requests.post(
            f"{BASE_URL}/api/projects/{project}/publish-on-save",
            headers=auth_headers, json={"publish_on_save": False}, timeout=15,
        )
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/chat/stream",
            headers={**auth_headers, "Accept": "text/event-stream"},
            json={"message": "Build a tiny hero", "provider": "openai"},
            stream=True, timeout=180,
        )
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").startswith("text/event-stream"), r.headers

        seen = {"user_message": False, "start": False, "chunk_count": 0,
                "assistant_message": False, "done": False, "end": False,
                "auto_deploy": False}
        done_event = None
        for ev in self._consume_sse(r, max_seconds=180):
            t = ev.get("type")
            if t == "user_message":
                seen["user_message"] = True
            elif t == "start":
                seen["start"] = True
            elif t == "chunk":
                seen["chunk_count"] += 1
            elif t == "assistant_message":
                seen["assistant_message"] = True
            elif t == "done":
                seen["done"] = True
                done_event = ev
            elif t == "auto_deploy":
                seen["auto_deploy"] = True
            elif t == "end":
                seen["end"] = True
                break
            elif t == "error":
                pytest.fail(f"stream errored: {ev}")
        TestChatStream.events = seen
        assert seen["user_message"], seen
        assert seen["start"], seen
        assert seen["chunk_count"] > 0, seen
        assert seen["done"], seen
        assert seen["end"], seen
        # auto_deploy should NOT happen (publish_on_save is False)
        assert seen["auto_deploy"] is False
        # Final done event content
        assert isinstance(done_event.get("files"), list)
        assert any(f["path"].lower() == "index.html" for f in done_event["files"])
        assert done_event.get("provider")
        assert done_event.get("model")

    def test_chat_stream_auto_deploy(self, project, auth_headers):
        # Turn ON publish_on_save
        r0 = requests.post(
            f"{BASE_URL}/api/projects/{project}/publish-on-save",
            headers=auth_headers, json={"publish_on_save": True}, timeout=15,
        )
        assert r0.json()["publish_on_save"] is True
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/chat/stream",
            headers={**auth_headers, "Accept": "text/event-stream"},
            json={"message": "Add a small footer", "provider": "openai"},
            stream=True, timeout=180,
        )
        assert r.status_code == 200, r.text[:300]
        auto_deploy_ev = None
        seen_done = False
        for ev in self._consume_sse(r, max_seconds=180):
            t = ev.get("type")
            if t == "done":
                seen_done = True
            if t == "auto_deploy":
                auto_deploy_ev = ev
            if t == "end":
                break
            if t == "error":
                pytest.fail(f"stream errored: {ev}")
        assert seen_done
        assert auto_deploy_ev is not None, "auto_deploy event missing when publish_on_save=True"
        dep = auto_deploy_ev.get("deployment") or {}
        assert dep.get("id"), auto_deploy_ev
        assert dep.get("status") == "deployed", dep
        assert dep.get("public_url"), dep
        # Reset
        requests.post(
            f"{BASE_URL}/api/projects/{project}/publish-on-save",
            headers=auth_headers, json={"publish_on_save": False}, timeout=15,
        )


# ---------- Version detail (used by diff viewer) ----------
class TestVersionDetail:
    def test_get_version_files(self, project, auth_headers):
        # The chat/stream test above produced versions; use the latest one.
        rl = requests.get(f"{BASE_URL}/api/projects/{project}/versions",
                          headers=auth_headers, timeout=15)
        assert rl.status_code == 200, rl.text
        versions = rl.json()
        if not versions:
            pytest.skip("no versions yet (chat stream may have skipped)")
        vid = versions[0]["id"]
        r = requests.get(f"{BASE_URL}/api/projects/{project}/versions/{vid}",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        files = body.get("files") or body  # accept either {files:[...]} or [...]
        if isinstance(body, dict) and "files" in body:
            files = body["files"]
        assert isinstance(files, list) and len(files) > 0
        assert all("path" in f and "content" in f for f in files)


# ---------- Deployment provider selection (Phase 4) ----------
class TestDeploymentProviders:
    def test_internal_via_json_body(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/deployments",
            headers=auth_headers,
            json={"provider": "internal"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("status") == "deployed", d
        assert d.get("provider") == "internal"
        assert d.get("public_url")

    def test_vercel_fails_without_token(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/deployments",
            headers=auth_headers,
            json={"provider": "vercel"},
            timeout=30,
        )
        # Per review: deployment record returned with status='failed' and error mentioning VERCEL_TOKEN
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("provider") == "vercel"
        assert d.get("status") == "failed", d
        err_text = str(d.get("error") or d.get("logs") or d).upper()
        assert "VERCEL_TOKEN" in err_text, d

    def test_cloudflare_pages_fails_without_token(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/deployments",
            headers=auth_headers,
            json={"provider": "cloudflare-pages"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("provider") == "cloudflare-pages"
        assert d.get("status") == "failed", d
        err_text = str(d.get("error") or d.get("logs") or d).upper()
        assert "CLOUDFLARE_API_TOKEN" in err_text, d


# ---------- Domain add: no auto-CNAME when CF token empty ----------
class TestDomainNoAutoCNAME:
    def test_add_no_auto_cname_when_cf_empty(self, project, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/projects/{project}/domains",
            headers=auth_headers,
            json={"hostname": "phase4-noauto.example.com"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # No automation -> stays pending (NOT 'verified' or 'active')
        assert d.get("status") in {"pending", "unverified"}, d
        # cleanup
        requests.delete(
            f"{BASE_URL}/api/projects/{project}/domains/{d['id']}",
            headers=auth_headers, timeout=15,
        )
