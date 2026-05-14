"""
Phase 6 R3 + Phase 7 tests:
- POST /api/projects/{id}/generate-page-from-route (ONE live LLM call only — html target)
- 404 path on non-existent project
- Inline env edit (upsert in place, no duplicate)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://nxt-studio.preview.emergentagent.com").rstrip("/")
PASSWORD = "555"
EXISTING_PROJECT_ID = "ed2736da-9f17-4525-8e3b-e0f1ccfad4e2"
PROXY_SUBSTRING = "nxt-studio.preview.emergentagent.com/api/runtime/"


@pytest.fixture(scope="module")
def auth_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_client(auth_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"})
    return s


# -------- Project existence sanity --------
def test_existing_project_loads(auth_client):
    r = auth_client.get(f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}", timeout=15)
    assert r.status_code == 200, f"Project not found: {r.text}"
    data = r.json()
    assert data.get("id") == EXISTING_PROJECT_ID
    assert isinstance(data.get("files"), list)


# -------- 404 on missing project --------
def test_generate_page_404_on_missing_project(auth_client):
    r = auth_client.post(
        f"{BASE_URL}/api/projects/does-not-exist-xxx/generate-page-from-route",
        json={"method": "GET", "path": "/api/x"},
        timeout=15,
    )
    assert r.status_code == 404
    assert "not found" in r.text.lower()


# -------- Live LLM happy path: html target (RUN ONCE) --------
def test_generate_page_from_route_html(auth_client):
    payload = {"method": "GET", "path": "/api/users", "target": "html"}
    r = auth_client.post(
        f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/generate-page-from-route",
        json=payload,
        timeout=120,
    )
    assert r.status_code == 200, f"Generate failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("ok") is True
    assert isinstance(data.get("path"), str) and data["path"].startswith("tools/"), f"Bad path: {data.get('path')}"
    assert data.get("title") and isinstance(data["title"], str)
    assert data.get("target") == "html"
    assert data.get("provider") in {"openai", "anthropic", "emergent"}, f"Unexpected provider: {data.get('provider')}"

    new_path = data["path"]
    # Verify the new file persists in the project + content uses runtime proxy
    r2 = auth_client.get(f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}", timeout=15)
    assert r2.status_code == 200
    files = r2.json().get("files", [])
    file_match = next((f for f in files if f["path"] == new_path), None)
    assert file_match is not None, f"Newly generated file '{new_path}' not present in project files"
    content = file_match.get("content", "")
    assert PROXY_SUBSTRING in content, (
        f"Expected runtime proxy substring '{PROXY_SUBSTRING}' inside generated HTML. "
        f"First 400 chars: {content[:400]}"
    )


# -------- Env upsert: in-place update (no duplicate row) --------
def test_env_inline_upsert(auth_client):
    # Snapshot current env list
    r0 = auth_client.get(f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/env", timeout=15)
    assert r0.status_code == 200
    initial = r0.json()
    initial_keys = [e["key"] for e in initial]

    test_key = "STRIPE_KEY"
    pre_existed = test_key in initial_keys

    # Seed it once if missing (so test is reproducible)
    seed_value = f"sk_test_seed_{int(time.time())}"
    r_seed = auth_client.post(
        f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/env",
        json={"key": test_key, "value": seed_value, "scope": "runtime"},
        timeout=15,
    )
    assert r_seed.status_code == 200, r_seed.text

    # Get count after seed
    r1 = auth_client.get(f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/env", timeout=15)
    assert r1.status_code == 200
    after_seed = r1.json()
    after_seed_keys = [e["key"] for e in after_seed]
    seed_count = after_seed_keys.count(test_key)
    assert seed_count == 1, f"Expected exactly 1 row for {test_key}, got {seed_count}"
    seed_updated_at = next(e for e in after_seed if e["key"] == test_key).get("updated_at")

    # Now do the inline edit (POST same key, new value)
    time.sleep(1.1)
    new_value = f"sk_test_edited_{int(time.time())}"
    r_edit = auth_client.post(
        f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/env",
        json={"key": test_key, "value": new_value, "scope": "runtime"},
        timeout=15,
    )
    assert r_edit.status_code == 200, r_edit.text
    body = r_edit.json()
    assert body.get("ok") is True
    assert body.get("key") == test_key

    # Verify still exactly 1 row, updated_at refreshed
    r2 = auth_client.get(f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/env", timeout=15)
    assert r2.status_code == 200
    after_edit = r2.json()
    after_edit_keys = [e["key"] for e in after_edit]
    assert after_edit_keys.count(test_key) == 1, "Inline edit duplicated the env row!"

    edited_row = next(e for e in after_edit if e["key"] == test_key)
    assert edited_row.get("updated_at") and edited_row["updated_at"] != seed_updated_at, \
        "updated_at not refreshed after inline edit"

    # Total key set unchanged
    assert sorted(after_edit_keys) == sorted(after_seed_keys), \
        "Inline edit changed the set of env keys"

    # Cleanup: if it didn't pre-exist, remove our seed
    if not pre_existed:
        auth_client.delete(f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/env/{test_key}", timeout=15)


# -------- Bad key validation still works --------
def test_env_bad_key_rejected(auth_client):
    r = auth_client.post(
        f"{BASE_URL}/api/projects/{EXISTING_PROJECT_ID}/env",
        json={"key": "bad-key", "value": "x"},
        timeout=15,
    )
    assert r.status_code == 400
