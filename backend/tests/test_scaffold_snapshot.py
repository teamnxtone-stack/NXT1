"""Tests for the scaffold snapshot bootstrap path."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from services import scaffolds as scaffolds_pack
from services import scaffold_snapshot_service as snap


@pytest.fixture(autouse=True)
def _cache():
    snap.clear_cache()
    yield
    snap.clear_cache()


def test_lists_baked_snapshots():
    """Every kind we have a snapshot for should be listed without the
    `.tar` suffix bug."""
    listed = snap.list_snapshots()
    assert listed, "no snapshots baked — run scripts/build_scaffold_snapshots.py"
    for kind, path in listed.items():
        assert not kind.endswith(".tar"), kind
        assert path.exists()


def test_snapshot_load_substitutes_name_and_slug():
    files, info = snap.load_snapshot("nextjs-tailwind", project_name="My SaaS App")
    by_path = {f["path"]: f["content"] for f in files}
    pkg = by_path.get("package.json")
    assert pkg is not None
    assert '"name": "my-saas-app"' in pkg            # slug substituted
    assert "My SaaS App" in by_path.get("app/page.jsx", "")  # name in body
    # Sentinels must NOT survive into the output
    assert snap.NAME_SENTINEL not in pkg
    assert snap.SLUG_SENTINEL not in pkg
    assert info["source"] == "snapshot"
    assert info["file_count"] == len(files)


def test_snapshot_load_warm_cache_is_fast():
    """Second load should hit the in-process cache (no fs/gzip work)."""
    snap.load_snapshot("react-vite", project_name="One")
    _, info = snap.load_snapshot("react-vite", project_name="Two")
    # Warm read includes substitution but no decompress; budget < 5ms even
    # on a busy CI runner.
    assert info["loaded_at_ms"] < 5.0, info


def test_snapshot_matches_live_pack_byte_for_byte():
    """For every kind we have a snapshot for, loading it must match what
    the live pack would have generated for the same project name."""
    name = "Demo Project"
    for kind in snap.list_snapshots().keys():
        if kind not in scaffolds_pack.pack_kinds():
            continue
        snap_files = {f["path"]: f["content"]
                      for f in snap.load_snapshot(kind, name)[0]}
        live_files = {f["path"]: f["content"]
                      for f in scaffolds_pack.build_scaffold(kind, project_name=name)}
        assert set(snap_files.keys()) == set(live_files.keys()), (
            f"file-set mismatch for {kind}")
        for path in live_files:
            assert snap_files[path] == live_files[path], (
                f"content mismatch for {kind}:{path}")


def test_missing_snapshot_raises():
    with pytest.raises(FileNotFoundError):
        snap.load_snapshot("does-not-exist-kind")


def test_bake_round_trips(tmp_path):
    files = [
        {"path": "package.json",
         "content": f'{{"name": "{snap.SLUG_SENTINEL}"}}\n'},
        {"path": "src/App.jsx",
         "content": f'export default function App() {{ return "{snap.NAME_SENTINEL}"; }}\n'},
    ]
    out = snap.bake_snapshot("test-kind", tmp_path, files)
    assert out.exists()
    # Repoint the module's snapshot dir for this test only.
    saved = snap._SNAPSHOT_DIR
    snap._SNAPSHOT_DIR = tmp_path
    try:
        snap.clear_cache()
        loaded, info = snap.load_snapshot("test-kind", project_name="Hello World")
        by_path = {f["path"]: f["content"] for f in loaded}
        assert '"name": "hello-world"' in by_path["package.json"]
        assert "Hello World" in by_path["src/App.jsx"]
        assert info["file_count"] == 2
        assert info["source"] == "snapshot"
    finally:
        snap._SNAPSHOT_DIR = saved
        snap.clear_cache()
