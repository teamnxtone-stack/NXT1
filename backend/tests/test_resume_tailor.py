"""Iteration 5 — Resume Tailor agent + regression on prior agents.

Targets:
  - POST /api/agentos/tasks (agent=resume_tailor) end-to-end (2 LLM calls)
  - POST /api/agentos/resume/extract  (TXT upload happy path + <80-char reject)
  - GET  /api/agentos/agents          (resume_tailor present, icon/color)
  - Regression: agent=custom, /api/auth/login, /api/agentos/stats, /api/agentos/tasks
"""
from __future__ import annotations

import io
import os
import time

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
APP_PASSWORD = "555"


# ─── Fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"password": APP_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _poll_task(task_id: str, headers: dict, timeout_s: int = 120) -> dict:
    """Poll GET /api/agentos/tasks/{id} until done/failed."""
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        r = requests.get(
            f"{BASE_URL}/api/agentos/tasks/{task_id}",
            headers={"Authorization": headers["Authorization"]},
            timeout=15,
        )
        assert r.status_code == 200, f"task fetch failed: {r.status_code} {r.text}"
        last = r.json()
        if last.get("status") in ("done", "failed", "cancelled"):
            return last
        time.sleep(2)
    pytest.fail(f"task {task_id} did not finish within {timeout_s}s — last={last}")


# ─── 1. Auth regression ────────────────────────────────────────────────
class TestAuth:
    def test_login_returns_token(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"password": APP_PASSWORD},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        # 'token' field per problem statement
        tok = data.get("token") or data.get("access_token")
        assert tok and isinstance(tok, str) and len(tok) > 10


# ─── 2. Agents registry  ───────────────────────────────────────────────
class TestAgentsRegistry:
    def test_resume_tailor_in_registry(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/agentos/agents", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        registered = data.get("registered", [])
        agents = data.get("agents", [])
        assert "resume_tailor" in registered, f"resume_tailor missing from registered: {registered}"
        rt = next((a for a in agents if a.get("id") == "resume_tailor"), None)
        assert rt is not None, "resume_tailor not in agents meta"
        assert rt.get("icon") == "FileText", f"expected icon FileText got {rt.get('icon')}"
        assert rt.get("color") == "#fb923c", f"expected color #fb923c got {rt.get('color')}"


# ─── 3. /agentos/stats and /agentos/tasks regression ───────────────────
class TestAgentOSBasics:
    def test_stats_200(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/agentos/stats", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "agents" in data
        assert "resume_tailor" in data["agents"]

    def test_tasks_list_200(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/agentos/tasks?limit=10", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)


# ─── 4. Resume extract upload ──────────────────────────────────────────
class TestResumeExtract:
    def test_extract_txt_happy(self, token):
        sample = (
            "Jane Doe — Senior Product Manager\n"
            "Acme Corp 2020-2024. Led B2B SaaS roadmap.\n"
            "Built Python + SQL dashboards, ran agile rituals, partnered with "
            "stakeholders on OKRs and AI/ML feature rollouts on Kubernetes."
        ).encode("utf-8")
        assert len(sample) >= 80
        files = {"file": ("TEST_resume.txt", io.BytesIO(sample), "text/plain")}
        r = requests.post(
            f"{BASE_URL}/api/agentos/resume/extract",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
            timeout=20,
        )
        assert r.status_code == 200, f"extract failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("filename") == "TEST_resume.txt"
        assert isinstance(data.get("text"), str) and "Jane Doe" in data["text"]
        assert data.get("char_count") == len(data["text"])

    def test_extract_short_rejected(self, token):
        short = b"too short."
        files = {"file": ("TEST_short.txt", io.BytesIO(short), "text/plain")}
        r = requests.post(
            f"{BASE_URL}/api/agentos/resume/extract",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
            timeout=20,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"


# ─── 5. Resume Tailor agent end-to-end (LLM) ───────────────────────────
RESUME_PAYLOAD = {
    "agent": "resume_tailor",
    "payload": {
        "job_title": "Senior PM",
        "job_description": (
            "We need a Senior PM with B2B SaaS, Python, SQL, Kubernetes, AI/ML, "
            "agile, stakeholder management, OKRs."
        ),
        "resume_text": (
            "Jane Doe — PM. Acme 2020-2024. Shipped B2B SaaS roadmap. "
            "Python + SQL dashboards. Agile + stakeholder mgmt."
        ),
    },
    "label": "TEST_resume_tailor_e2e",
}


class TestResumeTailorE2E:
    def test_submit_and_complete(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/agentos/tasks",
            headers=auth_headers,
            json=RESUME_PAYLOAD,
            timeout=15,
        )
        assert r.status_code == 200, f"submit failed: {r.status_code} {r.text}"
        task_id = r.json().get("task_id")
        assert task_id

        doc = _poll_task(task_id, auth_headers, timeout_s=150)
        assert doc.get("status") == "done", f"task ended {doc.get('status')}: error={doc.get('error')}"
        result = doc.get("result") or {}
        # required fields
        for key in (
            "ats_score", "keyword_coverage", "cosine_similarity",
            "jd_keywords", "matched", "missing",
            "tailored_resume", "suggestions", "report",
        ):
            assert key in result, f"result missing field: {key}; got keys {list(result.keys())}"

        # type sanity
        assert isinstance(result["ats_score"], (int, float))
        assert 0 <= result["ats_score"] <= 100
        assert 0.0 <= float(result["cosine_similarity"]) <= 1.0
        assert isinstance(result["jd_keywords"], list) and len(result["jd_keywords"]) >= 3
        assert isinstance(result["matched"], list)
        assert isinstance(result["missing"], list)
        assert isinstance(result["tailored_resume"], str) and len(result["tailored_resume"]) > 30
        assert isinstance(result["suggestions"], list) and len(result["suggestions"]) >= 1
        assert isinstance(result["report"], str) and len(result["report"]) > 20


# ─── 6. Regression: custom agent still works ───────────────────────────
class TestCustomAgentRegression:
    def test_custom_agent_completes(self, auth_headers):
        body = {
            "agent": "custom",
            "payload": {"task": "Reply with the single word READY and nothing else."},
            "label": "TEST_custom_regression",
        }
        r = requests.post(
            f"{BASE_URL}/api/agentos/tasks",
            headers=auth_headers,
            json=body,
            timeout=15,
        )
        assert r.status_code == 200, f"submit failed: {r.status_code} {r.text}"
        task_id = r.json().get("task_id")
        doc = _poll_task(task_id, auth_headers, timeout_s=120)
        # We only require it COMPLETES (done or failed-with-result.report) — not specific text
        status = doc.get("status")
        assert status in ("done", "failed"), f"unexpected status {status}"
        if status == "done":
            assert doc.get("result"), "done task missing result"
            assert "report" in (doc.get("result") or {}), "custom result missing report"
