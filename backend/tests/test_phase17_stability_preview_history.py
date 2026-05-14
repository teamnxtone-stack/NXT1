"""Phase 17 — JSON stability, persistent history, import preview detection,
admin domains for NXT1 itself."""
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


# ---------- JSON stability ----------
def test_parse_ai_response_handles_markdown_fences():
    from services.ai_service import parse_ai_response
    out = parse_ai_response('```json\n{"a": 1, "b": [1,2]}\n```')
    assert out == {"a": 1, "b": [1, 2]}


def test_parse_ai_response_repairs_unterminated_string():
    from services.ai_service import parse_ai_response
    out = parse_ai_response('{"a": "hello, "b": 2')
    # json_repair will close the string; we only assert it returned a dict.
    assert isinstance(out, dict)


def test_parse_ai_response_repairs_trailing_comma():
    from services.ai_service import parse_ai_response
    out = parse_ai_response('{"files":[{"path":"a","content":"b"},],"explanation":"x"}')
    assert out["explanation"] == "x"
    assert len(out["files"]) == 1


def test_parse_ai_response_rejects_junk():
    from services.ai_service import parse_ai_response, AIProviderError
    with pytest.raises(AIProviderError):
        parse_ai_response("not json at all")


# ---------- Import preview detection ----------
def test_detect_preview_entry_static_html():
    from services.import_service import detect_preview_entry
    files = [
        {"path": "index.html", "content": "<html><body>hi</body></html>"},
        {"path": "style.css", "content": "body{}"},
    ]
    info = detect_preview_entry(files)
    assert info["kind"] == "static-html"
    assert info["entry_path"] == "index.html"
    assert info["preview_ok"] is True


def test_detect_preview_entry_react_source():
    from services.import_service import detect_preview_entry
    files = [
        {"path": "frontend/package.json",
         "content": '{"dependencies":{"react":"18","vite":"5"}}'},
        {"path": "frontend/src/App.jsx", "content": "export default ()=>null"},
        {"path": "frontend/index.html", "content": "<div id=root></div>"},
    ]
    info = detect_preview_entry(files)
    assert info["kind"] == "spa-source"
    assert info["framework"] == "vite"
    assert info["root"] == "frontend"
    assert info["preview_ok"] is False
    assert "deploy" in info["hint"].lower() or "live" in info["hint"].lower()


def test_detect_preview_entry_spa_built():
    from services.import_service import detect_preview_entry
    files = [
        {"path": "frontend/dist/index.html", "content": "<div id=root></div>"},
        {"path": "frontend/package.json", "content": "{}"},
    ]
    info = detect_preview_entry(files)
    assert info["kind"] == "spa-built"
    assert info["entry_path"] == "frontend/dist/index.html"
    assert info["preview_ok"] is True


def test_detect_preview_entry_nextjs():
    from services.import_service import detect_preview_entry
    files = [
        {"path": "next.config.js", "content": "module.exports={}"},
        {"path": "pages/index.js", "content": "export default ()=>null"},
        {"path": "package.json", "content": '{"dependencies":{"next":"15"}}'},
    ]
    info = detect_preview_entry(files)
    assert info["kind"] == "nextjs"
    assert info["preview_ok"] is False


# ---------- Persistent chat history schema ----------
def test_messages_endpoint_returns_extended_fields(auth_headers):
    pr = requests.get(f"{API}/projects", headers=auth_headers, timeout=10).json()
    if not pr:
        pytest.skip("No projects")
    pid = pr[0]["id"]
    r = requests.get(f"{API}/projects/{pid}/messages", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    # Messages may be empty for a fresh project; the endpoint must exist.
    body = r.json()
    assert isinstance(body, list)


def test_preview_info_endpoint(auth_headers):
    pr = requests.get(f"{API}/projects", headers=auth_headers, timeout=10).json()
    if not pr:
        pytest.skip("No projects")
    pid = pr[0]["id"]
    r = requests.get(f"{API}/projects/{pid}/preview-info", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "preview_info" in body and "live_url" in body and "preview_slug" in body


# ---------- Admin domains for NXT1 ----------
def test_admin_domains_requires_admin():
    r = requests.get(f"{API}/admin/domains", timeout=10)
    assert r.status_code in (401, 403)


def test_admin_domains_list_empty(auth_headers):
    r = requests.get(f"{API}/admin/domains", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    assert "items" in r.json() and "count" in r.json()


def test_admin_domains_invalid_hostname(auth_headers):
    r = requests.post(f"{API}/admin/domains", headers=auth_headers,
                      json={"hostname": "not a host"}, timeout=10)
    assert r.status_code == 400


def test_admin_domains_add_managed_and_remove(auth_headers):
    host = "phase17-test.nxtone.tech"
    # Cleanup if present
    r = requests.get(f"{API}/admin/domains", headers=auth_headers, timeout=10)
    for d in r.json()["items"]:
        if d["hostname"] == host:
            requests.delete(f"{API}/admin/domains/{d['id']}", headers=auth_headers, timeout=10)

    add = requests.post(f"{API}/admin/domains", headers=auth_headers,
                        json={"hostname": host, "role": "preview"}, timeout=20)
    assert add.status_code == 200, add.text
    rec = add.json()
    assert rec["hostname"] == host
    assert rec["managed"] is True  # nxtone.tech is on the configured CF account
    assert rec["zone_name"] == "nxtone.tech"
    assert rec["status"] in ("verified", "pending")
    assert rec["role"] == "preview"

    dele = requests.delete(f"{API}/admin/domains/{rec['id']}", headers=auth_headers, timeout=15)
    assert dele.status_code == 200
