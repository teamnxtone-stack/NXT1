"""
Iteration 6 — Full E2E verification:
- 5 agents registered (custom, job_scout, founders_scout, social_strategist, resume_tailor)
- NaN-JSON fix: GET /api/agentos/tasks?limit=30 must not 500
- App builder regression: POST /api/projects + workflow autostart
- UI registry, system/ready, resume extract
- Each agent end-to-end (with appropriate poll timeouts)
"""
import os
import io
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://preserve-load.preview.emergentagent.com").rstrip("/")
ADMIN_PASSWORD = "555"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in {r.json()}"
    return tok


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Catalog & stats ----------
def test_agents_catalog(auth_headers):
    r = requests.get(f"{BASE_URL}/api/agentos/agents", headers=auth_headers, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    data = r.json()
    agents = data.get("agents", data) if isinstance(data, dict) else data
    ids = {a["id"] for a in agents}
    expected = {"custom", "job_scout", "founders_scout", "social_strategist", "resume_tailor"}
    assert expected.issubset(ids), f"missing agents, got {ids}"
    for a in agents:
        for f in ("id", "label", "icon", "color", "description", "engine"):
            assert f in a, f"agent {a.get('id')} missing field {f}"


def test_agentos_stats(auth_headers):
    r = requests.get(f"{BASE_URL}/api/agentos/stats", headers=auth_headers, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    data = r.json()
    # response shape: { "agents": { "<agent_id>": {running, last_done, last_at, ...}, ... } }
    agents = data.get("agents") or data.get("stats") or data
    assert isinstance(agents, dict), f"unexpected stats shape: {type(agents)}"
    expected = {"custom", "job_scout", "founders_scout", "social_strategist", "resume_tailor"}
    assert expected.issubset(set(agents.keys())), f"stats missing agents: {agents.keys()}"
    for aid, slot in agents.items():
        for f in ("running", "last_done", "last_at"):
            assert f in slot, f"{aid} slot missing {f}: {slot}"


# ---------- NaN-JSON regression ----------
def test_tasks_list_no_500(auth_headers):
    """The previous bug: pandas NaN broke JSON encoding on this endpoint."""
    r = requests.get(f"{BASE_URL}/api/agentos/tasks?limit=30", headers=auth_headers, timeout=20)
    assert r.status_code == 200, f"NaN regression: {r.status_code} {r.text[:500]}"
    body = r.json()
    items = body.get("tasks") or body.get("items") or body
    assert isinstance(items, list)


# ---------- UI registry & system ready ----------
def test_ui_registry(auth_headers):
    r = requests.get(f"{BASE_URL}/api/ui-registry", headers=auth_headers, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    data = r.json()
    packs = data.get("packs") or []
    blocks = data.get("blocks") or []
    assert len(packs) >= 6, f"packs={len(packs)}"
    assert len(blocks) >= 17, f"blocks={len(blocks)}"


def test_ui_registry_implemented(auth_headers):
    r = requests.get(f"{BASE_URL}/api/ui-registry/implemented", headers=auth_headers, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"


def test_system_ready():
    # try a couple of likely paths
    paths = ["/api/system/ready", "/api/health", "/api/system/health"]
    last = None
    for p in paths:
        r = requests.get(f"{BASE_URL}{p}", timeout=10)
        last = (p, r.status_code, r.text[:200])
        if r.status_code == 200:
            return
    pytest.fail(f"no readiness endpoint returned 200: {last}")


# ---------- Resume extract ----------
def test_resume_extract_ok(token):
    text = "Jane Doe — Sr Product Manager. " + ("Built B2B SaaS roadmaps. " * 6)
    assert len(text) >= 80
    files = {"file": ("resume.txt", io.BytesIO(text.encode()), "text/plain")}
    r = requests.post(
        f"{BASE_URL}/api/agentos/resume/extract",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        timeout=20,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    body = r.json()
    assert "text" in body and "char_count" in body
    assert body["char_count"] >= 80


def test_resume_extract_too_short(token):
    files = {"file": ("tiny.txt", io.BytesIO(b"too short"), "text/plain")}
    r = requests.post(
        f"{BASE_URL}/api/agentos/resume/extract",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        timeout=20,
    )
    assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text[:200]}"


# ---------- Helpers for agent submission ----------
def _submit_and_poll(auth_headers, agent, payload, label, max_wait=90, accept_failed=False):
    body = {"agent": agent, "payload": payload, "label": label}
    r = requests.post(f"{BASE_URL}/api/agentos/tasks", headers=auth_headers, json=body, timeout=30)
    assert r.status_code in (200, 201), f"submit {agent}: {r.status_code} {r.text[:300]}"
    task = r.json()
    tid = task.get("id") or task.get("task_id") or task.get("_id")
    assert tid, f"no id in {task}"
    deadline = time.time() + max_wait
    last = None
    while time.time() < deadline:
        rr = requests.get(f"{BASE_URL}/api/agentos/tasks/{tid}", headers=auth_headers, timeout=15)
        assert rr.status_code == 200, f"poll {agent}: {rr.status_code} {rr.text[:300]}"
        last = rr.json()
        status = last.get("status")
        if status in ("done", "completed", "success"):
            return last
        if status in ("failed", "error"):
            if accept_failed:
                return last
            pytest.fail(f"{agent} failed: {last.get('error') or last}")
        time.sleep(3)
    pytest.fail(f"{agent} timed out after {max_wait}s — last={last}")


# ---------- Agent runs ----------
def test_custom_agent_run(auth_headers):
    res = _submit_and_poll(
        auth_headers,
        "custom",
        {"prompt": "Top 3 open-source agent frameworks 2025"},
        "Custom test",
        max_wait=120,
    )
    result = res.get("result") or {}
    report = result.get("report") or ""
    assert isinstance(report, str) and len(report.strip()) > 30, f"empty report: {result}"


def test_founders_scout_run(auth_headers):
    res = _submit_and_poll(auth_headers, "founders_scout", {}, "Founders test", max_wait=90)
    result = res.get("result") or {}
    assert "leads" in result, f"no leads field: {result}"
    assert isinstance(result["leads"], list)


def test_social_strategist_run(auth_headers):
    res = _submit_and_poll(
        auth_headers,
        "social_strategist",
        {"industry": "AI", "tone": "founder", "days": 3},
        "Social test",
        max_wait=120,
    )
    result = res.get("result") or {}
    plan = result.get("plan")
    assert plan, f"empty plan: {result}"


def test_resume_tailor_run(auth_headers):
    res = _submit_and_poll(
        auth_headers,
        "resume_tailor",
        {
            "job_title": "Sr PM",
            "job_description": "B2B SaaS PM, Python, SQL, Kubernetes, AI/ML, agile, stakeholder, OKRs",
            "resume_text": "Jane Doe — PM. Acme 2020-2024. B2B SaaS roadmap. Python+SQL. Agile.",
        },
        "Resume test",
        max_wait=180,
    )
    result = res.get("result") or {}
    for k in ("ats_score", "keyword_coverage", "cosine_similarity", "jd_keywords",
              "matched", "missing", "tailored_resume", "suggestions", "report"):
        assert k in result, f"resume_tailor missing {k}: keys={list(result.keys())}"
    assert isinstance(result["tailored_resume"], str) and result["tailored_resume"].strip()


def test_job_scout_soft(auth_headers):
    """JobSpy can rate-limit. Accept failed but ensure tasks-list stays 200."""
    res = _submit_and_poll(
        auth_headers,
        "job_scout",
        {"titles": ["Product Manager"], "location": "Remote", "results_wanted": 3, "sites": ["indeed"]},
        "Job test",
        max_wait=120,
        accept_failed=True,
    )
    status = res.get("status")
    if status in ("done", "completed", "success"):
        result = res.get("result") or {}
        jobs = result.get("jobs") or []
        # Spot-check: no NaN — every salary field is number or null
        for j in jobs[:5]:
            for k in ("salary_min", "salary_max"):
                if k in j and j[k] is not None:
                    assert isinstance(j[k], (int, float)), f"{k} not number: {j[k]}"
    # Regardless of pass/fail, list must stay 200
    r = requests.get(f"{BASE_URL}/api/agentos/tasks?limit=30", headers=auth_headers, timeout=20)
    assert r.status_code == 200, f"tasks list 500'd after job_scout: {r.status_code} {r.text[:300]}"


# ---------- App builder regression ----------
def test_app_builder_create_and_workflow(auth_headers):
    body = {"name": "TEST_iter6_smoke", "prompt": "A simple landing page with a hero and signup form", "template": None}
    r = requests.post(f"{BASE_URL}/api/projects", headers=auth_headers, json=body, timeout=30)
    assert r.status_code in (200, 201), f"create: {r.status_code} {r.text[:500]}"
    proj = r.json()
    pid = proj.get("id") or proj.get("_id") or proj.get("project_id")
    assert pid, f"no project id: {proj}"

    try:
        # GET project
        rg = requests.get(f"{BASE_URL}/api/projects/{pid}", headers=auth_headers, timeout=15)
        assert rg.status_code == 200, f"get project: {rg.status_code} {rg.text[:300]}"

        # Workflow must be present (auto-started)
        rw = requests.get(f"{BASE_URL}/api/workflows/list?project_id={pid}", headers=auth_headers, timeout=15)
        assert rw.status_code == 200, f"workflows: {rw.status_code} {rw.text[:300]}"
        wf = rw.json()
        items = wf.get("items", wf if isinstance(wf, list) else [])
        assert len(items) >= 1, f"workflow NOT auto-started (was the iter4 critical): {wf}"
    finally:
        requests.delete(f"{BASE_URL}/api/projects/{pid}", headers=auth_headers, timeout=15)
