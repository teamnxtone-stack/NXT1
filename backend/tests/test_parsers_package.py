"""Tests for the extracted services/parsers/ package.

Phase B.7 (2026-05-13) — `parse_ai_response` was moved out of
`services/ai_service.py` into `services/parsers/json_pipeline.py`. These
tests are intentionally identical in spirit to the existing
`test_parse_ai_response.py` but import via the NEW module path, so we
catch any drift if the public surface ever changes again.
"""
from __future__ import annotations

import pytest

from services.parsers import (
    AIProviderError,
    parse_ai_response,
    extract_json_block,
    strip_markdown_fences,
    strip_outer_fence,
    escape_control_chars_in_strings,
    salvage_files_array,
    salvage_files_from_fences,
)


def test_l1_strict_parse_returns_dict_with_level():
    text = '{"files": [{"path": "index.html", "content": "<h1>ok</h1>"}], '\
            '"explanation": "ok", "notes": ""}'
    out = parse_ai_response(text)
    assert out["_parse_level"] == "L1"
    assert out["files"][0]["path"] == "index.html"


def test_l2_normalizes_raw_newlines_inside_strings():
    raw = '{"files": [{"path": "a.txt", "content": "line1\nline2"}]}'
    out = parse_ai_response(raw)
    assert out["_parse_level"] in {"L1", "L2", "L3"}
    assert out["files"][0]["content"] == "line1\nline2"


def test_l5_codefence_salvage_when_no_json_at_all():
    text = (
        "Here are the files you requested:\n\n"
        "```src/App.jsx\nexport default function App() { return <div/>; }\n```\n\n"
        "```index.html\n<!doctype html><html><body><div id='root'/></body></html>\n```\n"
    )
    out = parse_ai_response(text)
    assert out["_parse_level"] == "L5"
    assert out["_partial"] is True
    paths = {f["path"] for f in out["files"]}
    assert "src/App.jsx" in paths
    assert "index.html" in paths


def test_empty_response_raises():
    with pytest.raises(AIProviderError):
        parse_ai_response("")
    with pytest.raises(AIProviderError):
        parse_ai_response("   \n  \t  ")


def test_total_failure_raises_aiprovidererror():
    # Completely unparseable garbage AND no fenced files.
    text = "lorem ipsum nothing parseable here"
    with pytest.raises(AIProviderError):
        parse_ai_response(text)


def test_helpers_are_publicly_re_exported():
    """Spot-check that the underscore-prefix-free names are usable
    by anyone who imports `services.parsers`."""
    assert strip_markdown_fences("```json\n{}\n```").strip() == "{}"
    assert strip_outer_fence("```\n{}\n```") == "{}"
    assert extract_json_block('prose {"a":1} trail') == '{"a":1}'
    assert "\\n" in escape_control_chars_in_strings('{"k":"a\nb"}')
    assert salvage_files_array('{"path":"x","content":"y"}')[0]["path"] == "x"
    assert salvage_files_from_fences("```x.txt\nhi\n```")[0]["content"] == "hi"


def test_backwards_compat_import_from_ai_service():
    """The old import path must continue to work after the refactor."""
    from services.ai_service import AIProviderError as A
    from services.ai_service import parse_ai_response as p
    assert A is AIProviderError
    assert p is parse_ai_response
