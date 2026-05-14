"""Five-level JSON parsing pipeline for AI builder responses.

Recovery ladder (strictest → most lenient)
==========================================
  L0  strip an outer markdown fence around the whole blob
  L1  extract JSON block + strict json.loads
  L2  normalize raw control chars inside string literals + json.loads
  L3  json_repair library fallback
  L4  regex-salvage `{path, content}` pairs from anywhere in the blob
  L5  code-fence salvage — extract per-file `\\\\`\\\\`\\\\`path\\\\n…\\\\`\\\\`\\\\``
      blocks the model emitted instead of (or alongside) JSON

`parse_ai_response()` only raises `AIProviderError` when ALL levels fail.
The caller is expected to persist the raw payload on failure so operators
can inspect what the model actually emitted.

All helpers below are pure functions and free of side effects.
"""
from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

logger = logging.getLogger("nxt1.parsers")


class AIProviderError(Exception):
    """Raised when an AI response cannot be parsed even after all
    fallback levels have been exhausted, or when a provider call errors
    out at the network/auth layer.
    """


# ---------------------------------------------------------------------------
# L0 — markdown-fence handling
# ---------------------------------------------------------------------------
def strip_markdown_fences(s: str) -> str:
    """Aggressively strip markdown code fences.

    Handles:
    - ```json …``` (standard)
    - ``` …``` (no language tag)
    - ~~~json …~~~ (tilde variant)
    - Multiple/nested fences (takes the largest valid block)
    - Unterminated fences (just strips the opening ```)
    """
    if not s:
        return s
    s = s.strip()
    # Standard triple-backtick fence (with optional language)
    fences = re.findall(r"```(?:json|JSON|javascript|js|)?\s*(.*?)```", s, re.DOTALL)
    if fences:
        # Prefer the longest fenced block (most likely the JSON payload)
        candidate = max(fences, key=len).strip()
        if candidate:
            return candidate
    # Tilde-fenced variant
    tilde = re.findall(r"~~~(?:json|JSON)?\s*(.*?)~~~", s, re.DOTALL)
    if tilde:
        candidate = max(tilde, key=len).strip()
        if candidate:
            return candidate
    # Unterminated opening fence (model started but didn't close)
    m = re.match(r"^```(?:json|JSON|javascript|js|)?\s*\n?", s)
    if m:
        s = s[m.end():]
    return s.strip()


_MD_FENCE_TRIM_RE = re.compile(
    r"^\s*```(?:json|JSON|jsonc|JSONC)?\s*\n?(.*?)\n?```\s*$", re.DOTALL
)


def strip_outer_fence(s: str) -> str:
    """If the model wrapped the entire JSON blob in a markdown fence, peel it."""
    if not s:
        return s
    m = _MD_FENCE_TRIM_RE.match(s)
    if m:
        return m.group(1)
    return s


# ---------------------------------------------------------------------------
# L1 — balanced-brace JSON block extraction
# ---------------------------------------------------------------------------
def extract_json_block(text: str) -> str:
    """Pull the largest JSON object out of an LLM response.

    Strips markdown fences, leading prose, and trailing prose. Uses balanced
    brace counting so partial fences ("```json …") and stray braces inside
    string literals don't confuse the slice.
    """
    s = strip_markdown_fences(text or "")
    start = s.find("{")
    if start == -1:
        return ""
    depth = 0
    in_str = False
    esc = False
    last_complete = -1
    for i in range(start, len(s)):
        ch = s[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_complete = i
                # Don't return immediately — there might be a longer second
                # JSON object after this one (rare, but happens with "I'll
                # give you two responses" style outputs).
                tail = s[i + 1:].lstrip()
                if not tail.startswith("{"):
                    return s[start: i + 1]
                start = i + 1 + (len(s[i + 1:]) - len(tail))
    if last_complete > 0:
        return s[start: last_complete + 1] if depth == 0 else s[start:]
    # Unbalanced — return what we have so the repair step can try.
    return s[start:]


# ---------------------------------------------------------------------------
# L2 — control-char escaping inside JSON string literals
# ---------------------------------------------------------------------------
_CTRL_CHAR_MAP = {
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


def escape_control_chars_in_strings(s: str) -> str:
    """Escape raw control chars that appear INSIDE JSON string literals.

    Strict json.loads rejects raw \\n/\\t inside strings, but LLMs frequently
    embed real newlines in `content` fields. This walks the JSON and replaces
    them only inside strings (preserving the JSON structure outside).
    """
    if not s:
        return s
    out: list[str] = []
    in_str = False
    esc = False
    for ch in s:
        if esc:
            out.append(ch)
            esc = False
            continue
        if ch == "\\":
            out.append(ch)
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            out.append(ch)
            continue
        if in_str and ch in _CTRL_CHAR_MAP:
            out.append(_CTRL_CHAR_MAP[ch])
        elif in_str and ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


# ---------------------------------------------------------------------------
# L4 — regex salvage of `{path, content}` pairs
# ---------------------------------------------------------------------------
def salvage_files_array(block: str) -> Optional[List[dict]]:
    """Last-ditch regex extraction of `{path, content}` pairs from a broken
    JSON blob. Returns the files that look complete & valid, or None if
    nothing salvageable was found.

    Accepts a few key/quote variations the model slips into under stress:
      • `"path"` or `'path'`
      • field order `path,content` or `content,path`
      • surrounding whitespace / line breaks
    """
    if not block:
        return None
    patterns = [
        # path then content, double-quoted
        re.compile(
            r'\{\s*"path"\s*:\s*"([^"]+)"\s*,\s*"content"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}',
            re.DOTALL,
        ),
        # content then path, double-quoted
        re.compile(
            r'\{\s*"content"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"path"\s*:\s*"([^"]+)"\s*\}',
            re.DOTALL,
        ),
    ]
    found: list[tuple[str, str]] = []
    for i, pat in enumerate(patterns):
        for m in pat.finditer(block):
            if i == 0:
                path, raw_content = m.group(1), m.group(2)
            else:
                raw_content, path = m.group(1), m.group(2)
            found.append((path, raw_content))
    if not found:
        return None
    salvaged: list[dict] = []
    seen: set[str] = set()
    for path, raw_content in found:
        clean = path.strip().lstrip("/")
        if not clean or clean in seen:
            continue
        seen.add(clean)
        try:
            content = json.loads('"' + raw_content + '"')
        except Exception:
            content = (raw_content.replace('\\n', '\n').replace('\\r', '\r')
                                  .replace('\\t', '\t').replace('\\"', '"')
                                  .replace('\\\\', '\\'))
        salvaged.append({"path": clean, "content": content})
    return salvaged or None


# ---------------------------------------------------------------------------
# L5 — code-fence file-block salvage
# ---------------------------------------------------------------------------
# Some models, especially under truncation pressure, emit per-file markdown
# fences instead of (or alongside) JSON, e.g.
#
#     ```src/App.jsx
#     export default function App() { … }
#     ```
#
# This is a strict last resort below `salvage_files_array`; if it pulls back
# any plausible files we prefer them over a hard failure.
_FENCE_FILE_RE = re.compile(
    r"```(?:file:)?\s*(?P<path>[\w./\-_+]+\.[\w]{1,8})\s*\n(?P<content>.*?)\n```",
    re.DOTALL,
)


def salvage_files_from_fences(text: str) -> Optional[List[dict]]:
    if not text:
        return None
    out: list[dict] = []
    seen: set[str] = set()
    for m in _FENCE_FILE_RE.finditer(text):
        path = m.group("path").strip().lstrip("/")
        if not path or path in seen:
            continue
        seen.add(path)
        out.append({"path": path, "content": m.group("content") or ""})
    return out or None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def parse_ai_response(text: str) -> dict:
    """Multi-level JSON parser with progressive recovery.

    Returns the parsed dict, with telemetry fields the caller can surface:
      _parse_level: "L1" | "L2" | "L3" | "L4" | "L5"
      _partial:     True if L4/L5 fired (only some content was recoverable)

    Only raises AIProviderError when ALL levels fail. The caller is expected
    to persist the raw payload on failure so operators can inspect what the
    model actually emitted.
    """
    if not text or not text.strip():
        raise AIProviderError("AI response was empty")

    cleaned = strip_outer_fence(text)
    block = extract_json_block(cleaned) or extract_json_block(text)
    # We still keep `text` around for fence salvage; `block` is what we try
    # to actually parse as JSON.

    if block:
        # L1: strict parse
        try:
            out = json.loads(block)
            if isinstance(out, dict):
                out["_parse_level"] = "L1"
                return out
        except json.JSONDecodeError as e:
            logger.info(f"L1 strict parse failed at line {e.lineno} col {e.colno}: {e.msg}")

        # L2: normalize raw control chars inside strings
        try:
            normalized = escape_control_chars_in_strings(block)
            out = json.loads(normalized)
            if isinstance(out, dict):
                logger.info("L2 control-char normalization succeeded")
                out["_parse_level"] = "L2"
                return out
        except json.JSONDecodeError as e:
            logger.info(f"L2 normalized parse failed: {e.msg}")
        except Exception as e:
            logger.info(f"L2 normalization errored: {e}")

        # L3: json_repair library
        try:
            from json_repair import repair_json as _repair
            repaired = _repair(block, return_objects=True)
            if isinstance(repaired, dict):
                logger.info("L3 json_repair succeeded")
                repaired["_parse_level"] = "L3"
                return repaired
            if isinstance(repaired, list) and repaired and isinstance(repaired[0], dict):
                logger.info("L3 json_repair returned list, taking first dict")
                d = repaired[0]
                d["_parse_level"] = "L3"
                return d
        except Exception as e:
            logger.info(f"L3 json_repair errored: {e}")

        # L4: regex salvage on the JSON block itself
        salvaged_files = salvage_files_array(block)
        if salvaged_files:
            logger.warning(
                f"L4 regex salvage recovered {len(salvaged_files)} file(s) from malformed AI output"
            )
            return {
                "files": salvaged_files,
                "explanation": "Recovered from malformed AI output — output was truncated or malformed; some files may be incomplete.",
                "notes": "Build was partially recovered. Run again if needed for a complete result.",
                "_parse_level": "L4",
                "_partial": True,
                "_recovered": True,
            }

    # L5: code-fence salvage on the FULL raw text (block-or-not). Some models
    # skip JSON entirely under pressure and emit per-file fenced blocks.
    fence_files = salvage_files_from_fences(text)
    if fence_files:
        logger.warning(
            f"L5 code-fence salvage recovered {len(fence_files)} file(s) from fenced-only AI output"
        )
        return {
            "files": fence_files,
            "explanation": "Recovered files from fenced output (AI skipped JSON).",
            "notes": "Run again for a clean, complete generation.",
            "_parse_level": "L5",
            "_partial": True,
            "_recovered": True,
        }

    raise AIProviderError(
        "AI response could not be parsed (L1 strict + L2 normalize + L3 repair + L4 regex + L5 fence-salvage all failed)"
    )


__all__ = [
    "AIProviderError",
    "parse_ai_response",
    "strip_markdown_fences",
    "strip_outer_fence",
    "extract_json_block",
    "escape_control_chars_in_strings",
    "salvage_files_array",
    "salvage_files_from_fences",
]
