"""Project memory / context system for NXT1 (Phase 5 scaffolding).

This module is the foundation for retrieval-augmented AI editing. Phase 5a
delivers:
  - file index (path, size, sha, lang)
  - architecture summary (AI-generated, lightweight)
  - storage on the project doc

Phase 5b will add:
  - chunked code retrieval per file
  - vector index (per-project, in-memory or via embeddings)
  - context-aware prompt assembly that pulls only relevant chunks
"""
import hashlib
import re
from typing import List, Dict


def _lang_of(path: str) -> str:
    if path.endswith(".html"): return "html"
    if path.endswith(".css"): return "css"
    if path.endswith((".js", ".jsx", ".mjs")): return "javascript"
    if path.endswith((".ts", ".tsx")): return "typescript"
    if path.endswith(".py"): return "python"
    if path.endswith(".json"): return "json"
    if path.endswith(".md"): return "markdown"
    return "text"


def build_index(files: List[dict]) -> List[dict]:
    out = []
    for f in files or []:
        content = f.get("content", "")
        out.append({
            "path": f["path"],
            "size": len(content),
            "lang": _lang_of(f["path"]),
            "sha": hashlib.sha1(content.encode("utf-8", errors="replace")).hexdigest()[:12],
            "loc": content.count("\n") + 1,
        })
    return out


def quick_summary(files: List[dict]) -> str:
    """A deterministic, rule-based summary used as a fast fallback when AI
    summary is not yet computed.
    """
    n_html = sum(1 for f in files if f["path"].endswith(".html"))
    n_css = sum(1 for f in files if f["path"].endswith(".css"))
    n_js = sum(1 for f in files if f["path"].endswith(".js"))
    n_py = sum(1 for f in files if f["path"].endswith(".py"))
    has_backend = any(f["path"].startswith("backend/") for f in files)
    n_pages = sum(1 for f in files if f["path"].endswith(".html"))
    parts = [f"{len(files)} files"]
    if n_pages: parts.append(f"{n_pages} HTML page(s)")
    if n_css: parts.append(f"{n_css} CSS")
    if n_js: parts.append(f"{n_js} JS")
    if n_py: parts.append(f"{n_py} Python")
    if has_backend: parts.append("backend present")
    return " · ".join(parts)
