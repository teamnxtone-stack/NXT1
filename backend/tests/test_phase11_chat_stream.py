"""Phase 11 — Verify chat streaming still works end-to-end."""
import os
import json
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PASSWORD = os.environ.get("APP_PASSWORD", "555")


def _token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=15)
    assert r.status_code == 200
    return r.json()["token"]


def test_chat_stream_emits_events_or_done():
    """Verify SSE chat stream is alive — emits user_message + start + chunk
    events (we accept early termination since full generation takes >60s in
    this env; the streaming infrastructure is what matters)."""
    hdr = {"Authorization": f"Bearer {_token()}"}
    r = requests.post(f"{BASE_URL}/api/projects", headers=hdr,
                      json={"name": "TEST_phase11_chat_stream", "description": ""}, timeout=15)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    try:
        with requests.post(
            f"{BASE_URL}/api/projects/{pid}/chat/stream",
            headers={**hdr, "Accept": "text/event-stream"},
            json={"message": "make a one-line hello"},
            stream=True, timeout=180,
        ) as resp:
            assert resp.status_code == 200, resp.text
            seen_types = set()
            saw_done = False
            chunk_count = 0
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if data == "[DONE]":
                    saw_done = True
                    break
                try:
                    obj = json.loads(data)
                except Exception:
                    continue
                t = obj.get("type")
                if t:
                    seen_types.add(t)
                if t == "chunk":
                    chunk_count += 1
                if t == "done":
                    saw_done = True
                # Stop early once we've proven SSE is flowing & generating
                if saw_done or chunk_count >= 4:
                    break
            assert "user_message" in seen_types, f"missing user_message; saw={seen_types}"
            assert "start" in seen_types, f"missing start; saw={seen_types}"
            assert chunk_count >= 1 or saw_done, f"no chunks streamed; saw={seen_types}"
    finally:
        requests.delete(f"{BASE_URL}/api/projects/{pid}", headers=hdr, timeout=10)
