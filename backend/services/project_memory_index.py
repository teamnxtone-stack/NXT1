"""NXT1 persistent workspace memory — per-project file index + smart context.

Why this exists
===============
Today the LLM gets the first 30 files of a project on every turn. That works
for small apps but degrades fast: a 200-file project blows the token budget,
the model can't answer "where is the auth code" because the relevant file
isn't in the window, and we re-stream the entire tree even when the user is
working on a single feature.

This module is the foundation of a smarter context strategy:

  • Index every file once (per project) on save: tokens, symbol names, path
    components, last-modified ts. Stored in a per-project in-process LRU plus
    Mongo for cold-start.
  • Score files at query time against the user's prompt using a cheap, fast
    BM25-like keyword score + recency bonus + path-name bonus + active-file
    boost.
  • Select the top-K (default 12) plus always-include critical files
    (`package.json`, `README.md`, the file the user is editing).
  • Return a compact "context pack" the AI prompt builders can drop in.

It is deliberately ML-free (no embeddings) for v1 — fast, deterministic,
cheap. We can layer embeddings on later if needed.
"""
from __future__ import annotations

import logging
import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("nxt1.memory")

# Files we always include even if their score is low — they anchor any
# response to the project's truth (deps, conventions, framework).
ALWAYS_INCLUDE = (
    "package.json", "tsconfig.json", "vite.config.js", "vite.config.ts",
    "next.config.js", "next.config.mjs", "tailwind.config.js", "tailwind.config.ts",
    "README.md", "AI_RULES.md",
    "frontend/.env", "backend/.env",
)

# Files we never include in context (lockfiles, binaries, generated output).
NEVER_INCLUDE_SUFFIX = (
    ".lock", ".min.js", ".min.css", ".map", ".png", ".jpg", ".jpeg", ".webp",
    ".gif", ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".mov", ".webm", ".zip", ".tar", ".gz",
)
NEVER_INCLUDE_PREFIX = (
    "node_modules/", ".git/", "dist/", "build/", ".next/", ".output/",
    "__pycache__/", ".cache/", "coverage/",
)


_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "by", "as", "is", "are", "was", "were", "be", "been", "being", "this",
    "that", "these", "those", "it", "its", "from", "but", "not", "no",
    "if", "then", "else", "do", "does", "did", "have", "has", "had",
    "i", "you", "he", "she", "we", "they", "me", "him", "her", "us", "them",
    "what", "which", "who", "when", "where", "why", "how",
    "page", "file", "code", "app", "component",
})


@dataclass
class FileEntry:
    path: str
    size: int
    tokens: Counter        # word freq for BM25-lite scoring
    updated_at: float
    symbols: Set[str] = field(default_factory=set)   # likely identifiers


@dataclass
class ProjectIndex:
    project_id: str
    files: Dict[str, FileEntry] = field(default_factory=dict)
    doc_count_by_token: Counter = field(default_factory=Counter)
    avg_len: float = 0.0
    last_built_at: float = 0.0

    def rebuild(self, files: List[Dict[str, str]]) -> None:
        self.files = {}
        self.doc_count_by_token = Counter()
        total_len = 0
        for f in files or []:
            path = (f.get("path") or "").strip().lstrip("/")
            if not path or _excluded(path):
                continue
            content = f.get("content") or ""
            tokens = _tokenise(content + " " + path.replace("/", " "))
            entry = FileEntry(
                path=path, size=len(content), tokens=tokens,
                updated_at=time.time(),
                symbols=_extract_symbols(content),
            )
            self.files[path] = entry
            total_len += sum(tokens.values())
            for tok in set(tokens):
                self.doc_count_by_token[tok] += 1
        self.avg_len = (total_len / max(1, len(self.files))) if self.files else 0.0
        self.last_built_at = time.time()


def _excluded(path: str) -> bool:
    if path.endswith(NEVER_INCLUDE_SUFFIX):
        return True
    if any(path.startswith(p) for p in NEVER_INCLUDE_PREFIX):
        return True
    return False


def _tokenise(text: str) -> Counter:
    out: Counter = Counter()
    if not text:
        return out
    for m in _WORD_RE.finditer(text[:200_000]):   # cap large files
        w = m.group(0).lower()
        if w in _STOPWORDS or len(w) < 2:
            continue
        out[w] += 1
    return out


_SYMBOL_RE = re.compile(
    r"\b(?:function|class|const|let|var|def|interface|type|export\s+default\s+function)"
    r"\s+([A-Za-z_][A-Za-z0-9_]*)"
)


def _extract_symbols(content: str) -> Set[str]:
    if not content:
        return set()
    out: Set[str] = set()
    for m in _SYMBOL_RE.finditer(content[:100_000]):
        out.add(m.group(1))
    return out


# ─── per-process cache ──────────────────────────────────────────────────────
_INDEX_CACHE: Dict[str, ProjectIndex] = {}


def get_index(project_id: str, files: List[Dict[str, str]],
              *, force_rebuild: bool = False,
              files_signature: Optional[str] = None) -> ProjectIndex:
    """Fetch (or build) a project's index. We rebuild eagerly when the file
    set changes — detecting via a cheap signature (sum of path lengths +
    file count) so we avoid hashing every byte."""
    sig = files_signature or _signature(files)
    cached = _INDEX_CACHE.get(project_id)
    if cached and not force_rebuild and getattr(cached, "_sig", None) == sig:
        return cached
    idx = ProjectIndex(project_id=project_id)
    idx.rebuild(files)
    idx._sig = sig   # type: ignore[attr-defined]
    _INDEX_CACHE[project_id] = idx
    return idx


def _signature(files: List[Dict[str, str]]) -> str:
    if not files:
        return "0:0"
    paths = sum(len(f.get("path") or "") for f in files)
    sizes = sum(len(f.get("content") or "") for f in files)
    return f"{len(files)}:{paths}:{sizes}"


def invalidate(project_id: str) -> None:
    _INDEX_CACHE.pop(project_id, None)


# ─── scoring ────────────────────────────────────────────────────────────────

K1 = 1.5
B = 0.75


def _bm25(entry: FileEntry, query_tokens: Counter, idx: ProjectIndex) -> float:
    if not query_tokens or not entry.tokens:
        return 0.0
    doc_len = sum(entry.tokens.values()) or 1
    score = 0.0
    N = len(idx.files) or 1
    for tok, qf in query_tokens.items():
        if qf <= 0:
            continue
        df = idx.doc_count_by_token.get(tok, 0)
        if df == 0:
            continue
        idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
        tf = entry.tokens.get(tok, 0)
        denom = tf + K1 * (1 - B + B * doc_len / max(1.0, idx.avg_len))
        score += idf * (tf * (K1 + 1)) / max(1.0, denom)
    return score


def _bonus(entry: FileEntry, query_tokens: Counter, active_file: Optional[str]) -> float:
    bonus = 0.0
    # path-name match
    path_lower = entry.path.lower()
    for tok in query_tokens:
        if tok in path_lower:
            bonus += 1.5
    # symbol match
    qset = {t.lower() for t in query_tokens}
    if entry.symbols and entry.symbols & qset:
        bonus += 1.2
    # active-file boost
    if active_file and entry.path == active_file:
        bonus += 3.0
    return bonus


@dataclass
class ContextPack:
    """Result of `select_context_for_prompt()` — ready to drop into the
    user-prompt blob. `files` is the slice of project files we want to send;
    `summary` is a one-line breadcrumb for telemetry."""
    files: List[Dict[str, str]] = field(default_factory=list)
    summary: str = ""
    chosen_paths: List[str] = field(default_factory=list)
    total_files: int = 0


def select_context_for_prompt(
    project_id: str,
    files: List[Dict[str, str]],
    user_message: str,
    *,
    active_file: Optional[str] = None,
    top_k: int = 12,
    max_bytes_per_file: int = 6000,
) -> ContextPack:
    """Return a focused subset of `files` for the AI prompt.

    Always includes a few canonical anchors (package.json etc.) when present.
    Then ranks the rest by BM25 + path/symbol bonus + active-file boost and
    takes the top `top_k`. Files larger than `max_bytes_per_file` are
    truncated with a `…truncated…` marker (the AI can still ask via
    <nxt1-edit>).
    """
    if not files:
        return ContextPack(files=[], summary="no files")

    idx = get_index(project_id, files)
    query_tokens = _tokenise(user_message or "")
    if not query_tokens:
        # No usable signal — fall back to recently-modified + anchors
        ranked = sorted(idx.files.values(), key=lambda e: -e.size)
    else:
        scored: List[Tuple[float, FileEntry]] = []
        for entry in idx.files.values():
            s = _bm25(entry, query_tokens, idx) + _bonus(entry, query_tokens, active_file)
            if s > 0:
                scored.append((s, entry))
        scored.sort(key=lambda t: -t[0])
        ranked = [e for _, e in scored]

    # Compose the chosen set
    chosen: List[str] = []
    seen: Set[str] = set()

    # 1. Anchors (always include)
    paths_map = {f["path"]: f for f in files}
    for anchor in ALWAYS_INCLUDE:
        if anchor in paths_map and anchor not in seen:
            chosen.append(anchor)
            seen.add(anchor)

    # 2. Active file (already might be anchored, but ensure it's here)
    if active_file and active_file in paths_map and active_file not in seen:
        chosen.append(active_file)
        seen.add(active_file)

    # 3. Top-K ranked
    for entry in ranked:
        if entry.path in seen:
            continue
        chosen.append(entry.path)
        seen.add(entry.path)
        if len(chosen) >= top_k + len(ALWAYS_INCLUDE):
            break

    # Build the pack
    out_files: List[Dict[str, str]] = []
    for p in chosen:
        f = paths_map.get(p)
        if not f:
            continue
        content = f.get("content") or ""
        if len(content) > max_bytes_per_file:
            content = content[:max_bytes_per_file] + "\n/* …truncated for context — use <nxt1-edit> for targeted changes… */"
        out_files.append({"path": p, "content": content})

    return ContextPack(
        files=out_files,
        chosen_paths=chosen,
        total_files=len(files),
        summary=(
            f"context: {len(chosen)} of {len(files)} files "
            f"({len(query_tokens)} query-tokens)"
        ),
    )


__all__ = [
    "ProjectIndex",
    "ContextPack",
    "get_index",
    "invalidate",
    "select_context_for_prompt",
    "ALWAYS_INCLUDE",
]
