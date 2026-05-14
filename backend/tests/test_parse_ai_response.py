"""Tests for parse_ai_response — the multi-level recovery that keeps the
JSON-path resilient against malformed AI output.

These tests deliberately bypass any LLM call; they pass synthetic strings
through the parser and assert recovery + telemetry behaviour.
"""
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database_eval")

import pytest   # noqa: E402

from services.ai_service import AIProviderError, parse_ai_response   # noqa: E402


# ─── L1 — strict parse ─────────────────────────────────────────────────────

def test_L1_strict_parse():
    text = '{"files":[{"path":"a.txt","content":"hi"}],"explanation":"done"}'
    out = parse_ai_response(text)
    assert out["_parse_level"] == "L1"
    assert out["files"][0]["path"] == "a.txt"
    assert "_partial" not in out


def test_L1_strict_parse_with_markdown_fence():
    """The model sometimes wraps the entire JSON in a `json fence."""
    text = '```json\n{"files":[{"path":"a.txt","content":"hi"}]}\n```'
    out = parse_ai_response(text)
    assert out["_parse_level"] == "L1"
    assert out["files"][0]["path"] == "a.txt"


def test_L1_strict_parse_with_uppercase_fence():
    text = '```JSON\n{"files":[]}\n```'
    out = parse_ai_response(text)
    assert out["_parse_level"] == "L1"
    assert out["files"] == []


# ─── L2 — control-char normalisation ───────────────────────────────────────

def test_L2_normalises_raw_newlines_inside_string():
    # Real newline inside the JSON string value (very common for code content)
    text = '{"files":[{"path":"a.js","content":"line1\nline2"}]}'
    out = parse_ai_response(text)
    assert out["_parse_level"] in ("L2", "L3")   # L3 may also handle it
    assert "line1" in out["files"][0]["content"]
    assert "line2" in out["files"][0]["content"]


# ─── L3 — json_repair library ──────────────────────────────────────────────

def test_L3_json_repair_handles_trailing_comma():
    text = '{"files":[{"path":"a.txt","content":"hi"},],"notes":"ok",}'
    out = parse_ai_response(text)
    assert out["_parse_level"] in ("L1", "L2", "L3")
    assert out["files"][0]["path"] == "a.txt"


# ─── L4 — regex salvage of {path, content} pairs ────────────────────────────

def test_L4_salvages_files_from_broken_json():
    """Mid-file truncation: closing brace missing, salvage still works."""
    text = (
        '{"files":[\n'
        '  {"path":"a.txt","content":"complete file"},\n'
        '  {"path":"b.txt","content":"another complete file"},\n'
        '  {"path":"c.txt","content":"truncated mid-file ABRUPT END...'
    )
    out = parse_ai_response(text)
    assert out["_parse_level"] in ("L3", "L4")
    paths = [f["path"] for f in out["files"]]
    assert "a.txt" in paths
    assert "b.txt" in paths
    if out["_parse_level"] == "L4":
        assert out["_partial"] is True


def test_L4_handles_content_before_path():
    text = (
        'GARBAGE GARBAGE '
        '{"content":"hello", "path":"a.txt"} '
        'MORE GARBAGE '
        '{"content":"world", "path":"b.txt"} '
        'NO END'
    )
    out = parse_ai_response(text)
    if out["_parse_level"] == "L4":
        paths = [f["path"] for f in out["files"]]
        assert "a.txt" in paths and "b.txt" in paths
        assert out["_partial"] is True


def test_L4_dedupes_paths():
    """If the same path appears twice in a salvage scan, keep only one."""
    text = (
        '{"files":[ '
        '{"path":"x.txt","content":"first"},'
        '{"path":"x.txt","content":"second"}'
        '] BROKEN'
    )
    out = parse_ai_response(text)
    # If L3 (json_repair) fixed the trailing garbage, both entries remain
    # — that's correct behaviour at L3. Only L4 has the dedupe contract.
    if out["_parse_level"] == "L4":
        paths = [f["path"] for f in out["files"]]
        assert paths.count("x.txt") == 1


# ─── L5 — code-fence per-file salvage ──────────────────────────────────────

def test_L5_salvages_files_from_pure_codefences():
    """The model gave up on JSON entirely and emitted per-file fences."""
    text = """Sure, here are the files:

```src/App.jsx
export default function App() {
  return <h1>Hello</h1>;
}
```

```styles/main.css
body { background: #000; color: #fff; }
```

Done.
"""
    out = parse_ai_response(text)
    assert out["_parse_level"] == "L5"
    paths = [f["path"] for f in out["files"]]
    assert "src/App.jsx" in paths
    assert "styles/main.css" in paths
    assert out["_partial"] is True
    # Content should NOT include the surrounding fence markers
    app = next(f for f in out["files"] if f["path"] == "src/App.jsx")
    assert "```" not in app["content"]
    assert "Hello" in app["content"]


def test_L5_dedupes_paths():
    text = "```a.txt\nfirst\n```\n```a.txt\nsecond\n```"
    out = parse_ai_response(text)
    assert out["_parse_level"] == "L5"
    paths = [f["path"] for f in out["files"]]
    assert paths.count("a.txt") == 1


# ─── total failure ──────────────────────────────────────────────────────────

def test_empty_raises():
    with pytest.raises(AIProviderError):
        parse_ai_response("")


def test_pure_garbage_with_no_recoverable_content_raises():
    with pytest.raises(AIProviderError):
        parse_ai_response("just a sentence with no json or code fences here.")


# ─── telemetry is always present on success ────────────────────────────────

@pytest.mark.parametrize("text", [
    '{"files":[]}',
    '```json\n{"files":[]}\n```',
])
def test_parse_level_is_always_set(text):
    out = parse_ai_response(text)
    assert "_parse_level" in out
    assert out["_parse_level"].startswith("L")
