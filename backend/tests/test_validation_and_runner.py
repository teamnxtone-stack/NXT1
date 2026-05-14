"""Unit tests for validation_service + action_runner."""
import asyncio

import pytest

from services.action_runner import Action, ActionRunner
from services.validation_service import (
    diff_paths,
    format_for_repair_prompt,
    validate_files,
)


# ─── validation_service ────────────────────────────────────────────────────

def test_validate_clean_files():
    files = [
        {"path": "index.html", "content": "<!doctype html><html><body><h1>Hi</h1></body></html>"},
        {"path": "scripts/app.js", "content": "const x = 1; console.log(x);"},
        {"path": "styles/main.css", "content": "body { background: #000; }"},
        {"path": "package.json", "content": '{"name":"x","version":"1.0.0"}'},
        {"path": "backend/server.py", "content": "def f():\n    return 1\n"},
    ]
    r = validate_files(files)
    assert r.error_count == 0
    assert r.warn_count == 0
    assert r.checked == 5


def test_validate_broken_json():
    files = [{"path": "package.json", "content": '{"name":"x",'}]
    r = validate_files(files)
    assert r.has_errors
    assert r.issues[0].kind == "json"


def test_validate_broken_python():
    files = [{"path": "server.py", "content": "def f(\n    return 1"}]
    r = validate_files(files)
    assert r.has_errors
    assert r.issues[0].kind == "python"


def test_validate_unclosed_js_brace():
    files = [{"path": "app.js", "content": "function f() { const x = 1;"}]
    r = validate_files(files)
    assert r.has_errors
    assert r.issues[0].kind == "javascript"


def test_validate_unterminated_string():
    files = [{"path": "app.js", "content": "const s = 'hello"}]
    r = validate_files(files)
    assert r.has_errors


def test_validate_css_brace_mismatch():
    files = [{"path": "main.css", "content": "body { color: red; "}]
    r = validate_files(files)
    assert r.has_errors and r.issues[0].kind == "css"


def test_validate_unclosed_html_emits_warn():
    files = [{"path": "x.html", "content": "<div><section>"}]
    r = validate_files(files)
    assert r.warn_count >= 1


def test_validate_ignores_skipped_paths():
    files = [
        {"path": "node_modules/foo/index.js", "content": "broken {"},
        {"path": "yarn.lock", "content": "garbage"},
    ]
    r = validate_files(files)
    assert r.checked == 0


def test_validate_only_paths_filters():
    files = [
        {"path": "a.json", "content": "{"},   # broken
        {"path": "b.json", "content": "{}"},  # clean
    ]
    r = validate_files(files, only_paths=["b.json"])
    assert r.checked == 1
    assert not r.has_errors


def test_diff_paths_detects_changes():
    before = [{"path": "a.txt", "content": "x"}, {"path": "b.txt", "content": "y"}]
    after = [{"path": "a.txt", "content": "X"}, {"path": "c.txt", "content": "z"}]
    changed = set(diff_paths(before, after))
    assert changed == {"a.txt", "b.txt", "c.txt"}


def test_format_for_repair_prompt_handles_empty():
    from services.validation_service import ValidationReport
    assert format_for_repair_prompt(ValidationReport()) == ""


def test_format_for_repair_prompt_truncates():
    files = [{"path": f"f{i}.json", "content": "{"} for i in range(20)]
    r = validate_files(files)
    text = format_for_repair_prompt(r, max_issues=5)
    assert "and " in text and "more" in text


# ─── action_runner ─────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_action_runner_runs_sync_handler():
    r = ActionRunner()
    seen = []
    r.register("hello", lambda a, _r: seen.append(a.payload) or "ok")

    async def main():
        await r.submit(Action(type="hello", payload={"name": "world"}))
        await r.run()

    _run(main())
    actions = r.actions()
    assert actions[0].status == "complete"
    assert actions[0].output == "ok"
    assert seen == [{"name": "world"}]
    assert actions[0].duration_ms is not None and actions[0].duration_ms >= 0


def test_action_runner_runs_async_handler():
    r = ActionRunner()

    async def handler(a, _r):
        await asyncio.sleep(0.01)
        return f"hi {a.payload['name']}"

    r.register("greet", handler, async_=True)

    async def main():
        await r.submit(Action(type="greet", payload={"name": "NXT1"}))
        await r.run()

    _run(main())
    assert r.actions()[0].output == "hi NXT1"
    assert r.actions()[0].status == "complete"


def test_action_runner_failed_action():
    r = ActionRunner()

    def handler(_a, _r):
        raise RuntimeError("boom")

    r.register("bad", handler)

    async def main():
        await r.submit(Action(type="bad"))
        await r.run()

    _run(main())
    assert r.actions()[0].status == "failed"
    assert "boom" in r.actions()[0].error


def test_action_runner_unknown_kind_fails_cleanly():
    r = ActionRunner()

    async def main():
        await r.submit(Action(type="unknown"))
        await r.run()

    _run(main())
    a = r.actions()[0]
    assert a.status == "failed"
    assert "unknown" in a.error.lower()


def test_action_runner_abort_cancels_pending():
    r = ActionRunner()
    seen = []
    r.register("noop", lambda a, _r: seen.append(a.id) or "")

    async def main():
        await r.submit(Action(type="noop", id="a"))
        await r.submit(Action(type="noop", id="b"))
        r.abort()  # cancel BEFORE run
        await r.run()

    _run(main())
    statuses = [a.status for a in r.actions()]
    assert "aborted" in statuses
    assert seen == []   # nothing actually ran


def test_action_runner_timeline_shape():
    r = ActionRunner()
    r.register("x", lambda a, _r: "ok")

    async def main():
        await r.submit(Action(type="x", payload={"foo": "bar"}))
        await r.run()

    _run(main())
    tl = r.timeline()
    assert tl and tl[-1]["status"] == "complete"
    assert tl[-1]["kind"] == "x"
    assert tl[-1]["payload"] == {"foo": "bar"}
