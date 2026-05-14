"""NXT1 post-generation validation service.

After the AI completes a build (JSON path) or applies all tag actions (tag
path), we run a fast STATIC validation across the changed files. The goal is
NOT to compile or boot the project — that's what `runtime_service` does. The
goal is to catch obvious failures the model emits routinely:

  • broken JSON (`package.json`, `tsconfig.json`)
  • unterminated strings / mismatched braces in JS/JSX/TS/TSX
  • Python `SyntaxError` (`py_compile`)
  • orphan HTML closing tags / unclosed elements (lightweight)
  • CSS unclosed braces

Validation is intentionally LIGHT — we want it to finish in <100ms for a
typical project. Anything more elaborate (TypeScript type-check, ESLint
rules) is deferred to `runtime_service` once the project boots.

If we find errors, the caller can:
  1. Surface them to the user via SSE `{type:"validate", errors:[…]}`
  2. Auto-trigger ONE repair pass by re-calling the generator with the error
     report appended to the user prompt — the "self-healing" loop.

Self-healing rules
==================
  • Only one auto-repair attempt per build. Avoids runaway token spend.
  • Auto-repair only fires on `error` severity (not `warn`).
  • Repair is suppressed if the user explicitly cancelled (`state["cancelled"]`).
  • Repair re-uses the same protocol (tag stays tag, JSON stays JSON).
"""
from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("nxt1.validate")


@dataclass
class ValidationIssue:
    path: str
    severity: str            # "error" | "warn"
    kind: str                # "json" | "python" | "javascript" | "html" | "css" | "missing-import"
    message: str
    line: Optional[int] = None
    col: Optional[int] = None


@dataclass
class ValidationReport:
    issues: List[ValidationIssue] = field(default_factory=list)
    checked: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warn_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warn")

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    def to_dict(self) -> dict:
        return {
            "checked": self.checked,
            "error_count": self.error_count,
            "warn_count": self.warn_count,
            "issues": [asdict(i) for i in self.issues],
        }


# Languages we attempt to validate. Anything else is skipped.
_EXT_LANG = {
    ".json": "json",
    ".py":   "python",
    ".js":   "javascript",
    ".jsx":  "javascript",
    ".ts":   "javascript",
    ".tsx":  "javascript",
    ".mjs":  "javascript",
    ".cjs":  "javascript",
    ".html": "html",
    ".htm":  "html",
    ".css":  "css",
    ".scss": "css",
}

# Paths we deliberately skip (lockfiles, configs we don't fully understand,
# generated/vendored output).
_SKIP_PREFIXES = (
    "node_modules/", ".git/", "dist/", "build/", ".next/", ".output/",
    "public/", "static/", "coverage/", "__pycache__/", ".cache/",
)
_SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock",
}


def _detect_lang(path: str) -> Optional[str]:
    p = (path or "").lower()
    for pre in _SKIP_PREFIXES:
        if p.startswith(pre) or f"/{pre}" in f"/{p}":
            return None
    base = p.rsplit("/", 1)[-1]
    if base in _SKIP_FILES:
        return None
    for ext, lang in _EXT_LANG.items():
        if p.endswith(ext):
            return lang
    return None


# ─── per-language validators ────────────────────────────────────────────────

def _check_json(path: str, content: str) -> List[ValidationIssue]:
    if not content.strip():
        return []
    try:
        json.loads(content)
        return []
    except json.JSONDecodeError as e:
        return [ValidationIssue(
            path=path, severity="error", kind="json",
            message=f"Invalid JSON: {e.msg}",
            line=getattr(e, "lineno", None),
            col=getattr(e, "colno", None),
        )]


def _check_python(path: str, content: str) -> List[ValidationIssue]:
    if not content.strip():
        return []
    try:
        ast.parse(content, filename=path)
        return []
    except SyntaxError as e:
        return [ValidationIssue(
            path=path, severity="error", kind="python",
            message=f"SyntaxError: {e.msg}",
            line=e.lineno, col=e.offset,
        )]


# Cheap JS/JSX validator: bracket/quote balance check. Does NOT parse JSX
# semantically (that requires a full Babel parser). Catches the most common
# AI failures (unclosed strings, missing braces, dangling JSX tags).
_JS_OPEN = "({["
_JS_CLOSE = ")}]"
_JS_PAIR = {")": "(", "}": "{", "]": "["}


def _check_javascript(path: str, content: str) -> List[ValidationIssue]:
    if not content.strip():
        return []
    issues: List[ValidationIssue] = []
    stack: List[Tuple[str, int, int]] = []   # (char, line, col)
    in_str: Optional[str] = None             # "'" | "\"" | "`"
    in_line_cmt = False
    in_block_cmt = False
    in_regex = False
    line = 1
    col = 0
    i = 0
    last_significant = ""                    # for regex/divide disambiguation
    while i < len(content):
        ch = content[i]
        nxt = content[i + 1] if i + 1 < len(content) else ""
        col += 1
        if ch == "\n":
            line += 1
            col = 0
            if in_line_cmt:
                in_line_cmt = False
        if in_line_cmt:
            i += 1
            continue
        if in_block_cmt:
            if ch == "*" and nxt == "/":
                in_block_cmt = False
                i += 2
                continue
            i += 1
            continue
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if in_regex:
            if ch == "\\":
                i += 2
                continue
            if ch == "/":
                in_regex = False
            i += 1
            continue
        # Not in string/comment/regex
        if ch == "/" and nxt == "/":
            in_line_cmt = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_cmt = True
            i += 2
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            i += 1
            last_significant = ch
            continue
        # Heuristic regex detection: '/' after these tokens => regex literal
        if ch == "/" and last_significant in {"", "(", ",", "=", ":", ";", "!",
                                                "&", "|", "?", "{", "}", "["}:
            in_regex = True
            i += 1
            continue
        if ch in _JS_OPEN:
            stack.append((ch, line, col))
        elif ch in _JS_CLOSE:
            if not stack or stack[-1][0] != _JS_PAIR[ch]:
                issues.append(ValidationIssue(
                    path=path, severity="error", kind="javascript",
                    message=f"Unmatched '{ch}' (no opener)",
                    line=line, col=col,
                ))
                break
            stack.pop()
        if not ch.isspace():
            last_significant = ch
        i += 1
    if in_str:
        issues.append(ValidationIssue(
            path=path, severity="error", kind="javascript",
            message=f"Unterminated {in_str}-string literal",
            line=line, col=col,
        ))
    if in_block_cmt:
        issues.append(ValidationIssue(
            path=path, severity="error", kind="javascript",
            message="Unterminated /* … */ block comment",
            line=line, col=col,
        ))
    if stack and not issues:
        last = stack[-1]
        issues.append(ValidationIssue(
            path=path, severity="error", kind="javascript",
            message=f"Unclosed '{last[0]}' from line {last[1]} col {last[2]}",
            line=last[1], col=last[2],
        ))
    return issues


def _check_css(path: str, content: str) -> List[ValidationIssue]:
    if not content.strip():
        return []
    opens = content.count("{")
    closes = content.count("}")
    if opens != closes:
        return [ValidationIssue(
            path=path, severity="error", kind="css",
            message=f"Brace mismatch: {opens} '{{' vs {closes} '}}'",
        )]
    return []


# Cheap HTML check: look for unmatched <tag> / </tag> for a few canonical
# block tags. Void elements (img, br, etc.) are ignored. This is NOT a
# full HTML5 parser; just catches the AI's most common slip — emitting a
# `<div>` without `</div>`.
_HTML_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
              "link", "meta", "param", "source", "track", "wbr"}
_HTML_TAG_RE = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9:-]*)[^>]*?(/?)\s*>")


def _check_html(path: str, content: str) -> List[ValidationIssue]:
    if not content.strip():
        return []
    stack: List[str] = []
    for m in _HTML_TAG_RE.finditer(content):
        is_close = m.group(1) == "/"
        name = m.group(2).lower()
        self_close = m.group(3) == "/"
        if name in _HTML_VOID or self_close:
            continue
        if is_close:
            if stack and stack[-1] == name:
                stack.pop()
            else:
                # mismatch — surface once and stop scanning
                return [ValidationIssue(
                    path=path, severity="warn", kind="html",
                    message=f"Unexpected closing tag </{name}> "
                            f"(stack top: {stack[-1] if stack else 'empty'})",
                )]
        else:
            stack.append(name)
    if stack:
        return [ValidationIssue(
            path=path, severity="warn", kind="html",
            message=f"Unclosed tags: {', '.join(stack[-3:])}",
        )]
    return []


_CHECKERS = {
    "json": _check_json,
    "python": _check_python,
    "javascript": _check_javascript,
    "html": _check_html,
    "css": _check_css,
}


# ─── public API ────────────────────────────────────────────────────────────

def validate_files(files: List[Dict[str, str]],
                    only_paths: Optional[List[str]] = None,
                    max_files: int = 60) -> ValidationReport:
    """Run static validation across a project's files.

    Args:
        files: list of {path, content}.
        only_paths: if given, only validate these paths (post-generation,
            we only need to check files the AI actually touched).
        max_files: hard cap on how many files we'll scan, to keep latency low.
    """
    report = ValidationReport()
    if not files:
        return report
    only = set(only_paths or [])
    n = 0
    for f in files:
        path = f.get("path") or ""
        if only and path not in only:
            continue
        lang = _detect_lang(path)
        if not lang:
            continue
        n += 1
        if n > max_files:
            break
        content = f.get("content") or ""
        try:
            issues = _CHECKERS[lang](path, content)
        except Exception as e:
            logger.warning(f"validator crashed on {path}: {e}")
            continue
        report.issues.extend(issues)
        report.checked += 1
    return report


def diff_paths(before: List[Dict[str, str]],
                after: List[Dict[str, str]]) -> List[str]:
    """Return paths whose content changed (or that were created/deleted)."""
    before_map = {f["path"]: f.get("content") or "" for f in (before or [])}
    after_map = {f["path"]: f.get("content") or "" for f in (after or [])}
    out: List[str] = []
    for p, c in after_map.items():
        if before_map.get(p) != c:
            out.append(p)
    for p in before_map:
        if p not in after_map:
            out.append(p)
    return out


def format_for_repair_prompt(report: ValidationReport, max_issues: int = 10) -> str:
    """Pretty-print the report in a way the LLM can act on directly during
    the self-healing repair pass.
    """
    if not report.issues:
        return ""
    lines = [
        "Static validation found problems in the files you just wrote. "
        "Fix them with surgical edits — do NOT rewrite unrelated files."
    ]
    for i in report.issues[:max_issues]:
        loc = ""
        if i.line:
            loc = f" line {i.line}"
            if i.col:
                loc += f", col {i.col}"
        lines.append(f"- [{i.severity.upper()}] {i.path}{loc} ({i.kind}): {i.message}")
    if len(report.issues) > max_issues:
        lines.append(f"... and {len(report.issues) - max_issues} more.")
    return "\n".join(lines)


__all__ = [
    "ValidationIssue",
    "ValidationReport",
    "validate_files",
    "diff_paths",
    "format_for_repair_prompt",
]
