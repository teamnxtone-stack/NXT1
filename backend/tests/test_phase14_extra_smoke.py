"""Phase 14 — extra smoke for review:
- New user defaults to access_status='pending'
- Site editor: list returns 11 whitelisted paths + non-empty preview
- Propose with real LLM scoped to a small whitelisted file
- Apply: friendly 502 hint expected (read-only PAT) but disk apply works → status='applied' in history
- Rollback: status='rolled_back'
- 404 on unknown user access update
"""
import os
import time
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PW = os.environ.get("APP_PASSWORD", "555")


def _admin_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"password": PW}, timeout=15)
    return r.json()["token"]


def _hdr():
    return {"Authorization": f"Bearer {_admin_token()}"}


def test_new_user_defaults_pending():
    email = f"phase14_pending_{int(time.time()*1000)}@nxt1.test"
    r = requests.post(f"{BASE}/api/users/signup",
                      json={"email": email, "password": "test1234"}, timeout=15)
    assert r.status_code in (200, 201)
    body = r.json()
    assert body["user"]["access_status"] == "pending"
    token = body["token"]
    me = requests.get(f"{BASE}/api/users/me",
                      headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert me.status_code == 200
    assert me.json()["access_status"] == "pending"


def test_user_access_unknown_id_404():
    r = requests.post(f"{BASE}/api/users/does-not-exist-xyz/access",
                      headers=_hdr(),
                      json={"access_status": "approved"}, timeout=10)
    assert r.status_code == 404


def test_site_editor_files_count_and_preview():
    r = requests.get(f"{BASE}/api/site-editor/files",
                     headers=_hdr(), timeout=15)
    assert r.status_code == 200
    items = r.json()["items"]
    # Per request: 11 whitelisted paths
    assert len(items) == 11, f"expected 11 paths, got {len(items)}: {[i['path'] for i in items]}"
    # Preview should be non-empty for at least one file
    assert any((it.get("preview") or "").strip() for it in items)


def test_propose_apply_rollback_flow():
    # Pick a small whitelisted file — PrivacyPage.jsx
    files_resp = requests.get(f"{BASE}/api/site-editor/files",
                              headers=_hdr(), timeout=15).json()
    paths = [it["path"] for it in files_resp["items"]]
    target = next((p for p in paths if p.endswith("PrivacyPage.jsx")), None)
    assert target, f"PrivacyPage.jsx must be whitelisted; got {paths}"

    # Propose with a tiny prompt
    prop = requests.post(
        f"{BASE}/api/site-editor/propose",
        headers=_hdr(),
        json={"prompt": "Add an HTML comment '<!-- phase14-smoke -->' at the top of this file. Keep all other content intact.",
              "paths": [target]},
        timeout=120,  # LLM may take 10-30s
    )
    assert prop.status_code == 200, prop.text
    pj = prop.json()
    assert "edit_id" in pj
    assert "summary" in pj
    assert "files" in pj and len(pj["files"]) >= 1
    edit_id = pj["edit_id"]

    # Apply → should write to disk; GitHub push may 502 on read-only PAT
    apl = requests.post(f"{BASE}/api/site-editor/apply",
                        headers=_hdr(), json={"edit_id": edit_id}, timeout=60)
    # Either success (200) or 502 with friendly hint — but spec says local apply succeeds.
    # Per request: history should record status='applied' regardless.
    print("apply status:", apl.status_code, "body:", apl.text[:300])

    # Inspect history
    hist = requests.get(f"{BASE}/api/site-editor/history",
                        headers=_hdr(), timeout=15).json()
    matched = next((it for it in hist["items"] if it.get("edit_id") == edit_id), None)
    assert matched, f"edit {edit_id} not found in history"
    assert matched["status"] == "applied", f"expected applied, got {matched['status']}"

    # Rollback
    rb = requests.post(f"{BASE}/api/site-editor/rollback/{edit_id}",
                       headers=_hdr(), timeout=30)
    assert rb.status_code == 200, rb.text

    hist2 = requests.get(f"{BASE}/api/site-editor/history",
                         headers=_hdr(), timeout=15).json()
    matched2 = next((it for it in hist2["items"] if it.get("edit_id") == edit_id), None)
    assert matched2 and matched2["status"] == "rolled_back", \
        f"expected rolled_back, got {matched2}"
