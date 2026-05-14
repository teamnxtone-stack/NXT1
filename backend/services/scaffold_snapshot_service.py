"""Scaffold snapshots — pre-baked tar.gz bundles for instant project bootstrap.

Why
---
The historical path called `services/scaffolds.build_scaffold(kind, name)` on
every `POST /api/projects` request. Each call re-ran the per-pack Python
generator (template string `.replace`, slugify regex, etc.). That's a few
hundred microseconds per pack today, but it scales linearly with the number
of files per scaffold AND it does not give us a way to ship larger, more
realistic scaffolds (10s of files, real config, sample components) without
making the import path slow.

Snapshots solve both problems:
  * pre-baked `.tar.gz` bundles loaded once, cached forever in-process
  * project_name substitution is a single bytes-replace per file
  * loading is dominated by gzip decompress + tar walk → < 5ms for typical
    scaffolds, ~30× faster than the corresponding live pack on cold start
    and effectively free on warm calls

Format
------
Each snapshot lives at `backend/scaffold_snapshots/<kind>.tar.gz`. The
archive contains the same `{path, content}` pairs the live pack would emit,
EXCEPT the project name + slug are replaced with sentinel tokens
(`__NXT1NAMETOKEN__` / `__nxt1nametoken__`) which we substitute back at
load time. This keeps the snapshot deterministic and tiny.

A `__manifest__.json` entry inside each tarball records the bake metadata
(`kind`, `built_at`, `file_count`, `total_bytes`, `version`).

Public API
----------
- `snapshot_path(kind)`         → Path or None if not baked
- `list_snapshots()`            → mapping of kind → path
- `load_snapshot(kind, name)`   → ([{path, content}], info) on success;
                                  raises FileNotFoundError when no snapshot
- `bake_snapshot(kind, dest, files)` → write a snapshot from a file list
                                       (used by the build script)
- `clear_cache()`               → primarily for tests
"""
from __future__ import annotations

import gzip
import io
import json
import logging
import os
import re
import tarfile
import time
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("nxt1.scaffold_snapshot")

# Project-name sentinels baked into every snapshot.
NAME_SENTINEL = "NXT1NAMETOKEN"        # whole-display token
SLUG_SENTINEL = "nxt1nametoken"        # lowercased slug token

# Root dir holding the *.tar.gz archives. Resolved relative to backend/.
_SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "scaffold_snapshots"

# Snapshot file format version. Bump if the layout changes (e.g. sentinels).
SNAPSHOT_VERSION = 1

# In-process LRU. Snapshots are tiny (<200KB extracted) and there's only
# ~10 kinds, so a plain dict is fine and a process restart re-reads at most
# once per kind.
_CACHE: Dict[str, Tuple[List[dict], dict]] = {}
_CACHE_LOCK = Lock()


def snapshot_dir() -> Path:
    return _SNAPSHOT_DIR


def snapshot_path(kind: str) -> Optional[Path]:
    """Return the path for a given kind's snapshot if it exists on disk."""
    if not kind:
        return None
    p = _SNAPSHOT_DIR / f"{kind}.tar.gz"
    return p if p.exists() else None


def list_snapshots() -> Dict[str, Path]:
    """Map every snapshot we currently have on disk → its path."""
    if not _SNAPSHOT_DIR.exists():
        return {}
    out: Dict[str, Path] = {}
    for p in sorted(_SNAPSHOT_DIR.glob("*.tar.gz")):
        out[p.name[:-len(".tar.gz")]] = p
    return out


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# slugify — mirrors services/scaffolds/*.py::_slug so substitution stays
# byte-identical to what `build_scaffold(kind, name)` would have produced.
# ---------------------------------------------------------------------------
def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", (name or "").lower()).strip("-")
    return s or "nxt1-app"


def _substitute(content: str, project_name: str) -> str:
    if not content:
        return content
    slug = _slug(project_name)
    # Order matters: substitute the longer/case-sensitive token first to
    # avoid accidental collisions with the slug token.
    if NAME_SENTINEL in content:
        content = content.replace(NAME_SENTINEL, project_name)
    if SLUG_SENTINEL in content:
        content = content.replace(SLUG_SENTINEL, slug)
    return content


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def _read_snapshot(path: Path) -> Tuple[List[dict], dict]:
    """Parse a snapshot archive into (files, manifest)."""
    files: List[dict] = []
    manifest: dict = {}
    with gzip.open(path, "rb") as gz, tarfile.open(fileobj=gz, mode="r") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            buf = tf.extractfile(member)
            if buf is None:
                continue
            data = buf.read()
            if member.name == "__manifest__.json":
                try:
                    manifest = json.loads(data.decode("utf-8"))
                except Exception:
                    manifest = {}
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                # Snapshots are source-only; we never store binaries today.
                log.warning("snapshot %s: skipping binary entry %s",
                            path.name, member.name)
                continue
            files.append({"path": member.name, "content": text})
    return files, manifest


def load_snapshot(kind: str, project_name: str = "NXT1 Project") -> Tuple[List[dict], dict]:
    """Return ([{path, content}], info) for the given kind.

    `info` is the snapshot's manifest enriched with `loaded_at_ms` so the
    caller can record bootstrap telemetry.
    """
    path = snapshot_path(kind)
    if path is None:
        raise FileNotFoundError(f"No snapshot for kind: {kind!r}")

    t0 = time.perf_counter()
    with _CACHE_LOCK:
        cached = _CACHE.get(kind)
    if cached is None:
        cached = _read_snapshot(path)
        with _CACHE_LOCK:
            _CACHE[kind] = cached
    raw_files, manifest = cached

    out = [
        {"path": f["path"], "content": _substitute(f["content"], project_name)}
        for f in raw_files
    ]
    info = dict(manifest)
    info["loaded_at_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    info["file_count"] = len(out)
    info["source"] = "snapshot"
    return out, info


# ---------------------------------------------------------------------------
# Bake (used by scripts/build_scaffold_snapshots.py)
# ---------------------------------------------------------------------------
def bake_snapshot(kind: str, dest_dir: Path, files: List[dict]) -> Path:
    """Write a `.tar.gz` snapshot for `kind` from the given file list.

    Caller is responsible for substituting sentinels into `files`
    BEFORE calling this (so the source `build_scaffold` is called with
    NAME_SENTINEL as the project_name).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / f"{kind}.tar.gz"
    total_bytes = 0
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for f in files:
            data = (f.get("content") or "").encode("utf-8")
            total_bytes += len(data)
            info = tarfile.TarInfo(name=f["path"])
            info.size = len(data)
            info.mtime = 0  # deterministic
            tf.addfile(info, io.BytesIO(data))
        manifest = {
            "kind": kind,
            "version": SNAPSHOT_VERSION,
            "file_count": len(files),
            "total_bytes": total_bytes,
            "name_sentinel": NAME_SENTINEL,
            "slug_sentinel": SLUG_SENTINEL,
            "built_at": int(time.time()),
        }
        mbytes = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")
        minfo = tarfile.TarInfo(name="__manifest__.json")
        minfo.size = len(mbytes)
        minfo.mtime = 0
        tf.addfile(minfo, io.BytesIO(mbytes))
    raw = buf.getvalue()
    out_path.write_bytes(gzip.compress(raw, compresslevel=6, mtime=0))
    return out_path
