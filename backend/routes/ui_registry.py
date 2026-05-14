"""Premium UI registry route (Track A).

Exposes the curated UI component registry to:
- The frontend (so users can browse / pin / hot-swap blocks)
- The build agents (so generation defaults to premium blocks)
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse

from ._deps import verify_token

logger = logging.getLogger("nxt1.ui_registry")
router = APIRouter(prefix="/api/ui-registry", tags=["ui-registry"])

_REGISTRY_PATH = Path(__file__).parent.parent / "data" / "ui_registry.json"
_BLOCKS_DIR = Path("/app/frontend/src/components/ui/blocks")
_BLOCK_SOURCES_MANIFEST = Path(__file__).parent.parent / "data" / "block_sources.json"


def _load_block_sources() -> Dict[str, dict]:
    """Read the auto-generated manifest produced by
    `scripts/sync_block_sources.js`. Falls back to an empty dict (with a
    warning) if the manifest is missing — the gallery degrades to
    "documentation-only" mode rather than blowing up.
    """
    try:
        with open(_BLOCK_SOURCES_MANIFEST, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("blocks") or {}
    except FileNotFoundError:
        logger.warning(
            "block_sources.json missing — run `node scripts/sync_block_sources.js`"
        )
        return {}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"block_sources.json unreadable: {e}")
        return {}


# Loaded eagerly so the FastAPI router has a consistent view; the gallery /
# AI agent never see stale state because the file is written once at build
# time. To pick up changes during dev, restart the backend (or call the
# sync script + re-import).
_BLOCK_SOURCES: Dict[str, dict] = _load_block_sources()

_CACHE: dict = {}


def load_registry() -> dict:
    global _CACHE
    if _CACHE.get("_loaded"):
        return _CACHE
    try:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["_loaded"] = True
        _CACHE = data
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"UI registry unreadable: {e}") from None


@router.get("")
async def get_registry(
    kind: str = Query(None, description="Filter blocks by kind (hero, card, feature, ...)"),
    pack: str = Query(None, description="Filter blocks by pack (magicui, aceternity, ...)"),
    tag: str = Query(None, description="Filter blocks by tag"),
):
    """Public read of the registry. No auth so AI agents can fetch."""
    data = load_registry()
    blocks = data.get("blocks", [])
    if kind:
        blocks = [b for b in blocks if b.get("kind") == kind]
    if pack:
        blocks = [b for b in blocks if b.get("pack") == pack]
    if tag:
        blocks = [b for b in blocks if tag in (b.get("tags") or [])]
    return {
        "version": data.get("version"),
        "updated_at": data.get("updated_at"),
        "packs": data.get("packs", []),
        "blocks": blocks,
        "total": len(blocks),
    }


@router.get("/directive")
async def get_directive():
    """The generation directive AI agents prepend to their system prompt."""
    data = load_registry()
    return {
        "directive": data.get("generation_directive", ""),
        "block_count": len(data.get("blocks", [])),
    }


@router.get("/blocks/{block_id}")
async def get_block(block_id: str):
    data = load_registry()
    for b in data.get("blocks", []):
        if b.get("id") == block_id:
            entry = _BLOCK_SOURCES.get(block_id) or {}
            b = dict(b)
            b["implemented"] = bool(entry)
            b["source_url"] = (
                f"/api/ui-registry/blocks/{block_id}/source" if entry else None
            )
            b["named_export"] = entry.get("named_export")
            b["file"] = entry.get("file")
            return b
    raise HTTPException(status_code=404, detail="Block not found")


@router.get("/blocks/{block_id}/source", response_class=PlainTextResponse)
async def get_block_source(block_id: str):
    """Return the raw JSX source of a vendored premium block so AI agents
    (and developers) can drop it into generated apps verbatim.

    Vendored files are immutable per release, so we serve them with a
    one-hour public cache to cut backend load.
    """
    entry = _BLOCK_SOURCES.get(block_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Block source not vendored")
    path = _BLOCKS_DIR / entry["file"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Source file missing")
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Read failed: {e}") from None
    return PlainTextResponse(
        content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=3600, immutable",
            "X-NXT1-Block-Id": block_id,
            "X-NXT1-Block-File": entry["file"],
            "X-NXT1-Named-Export": entry.get("named_export") or "",
        },
    )


@router.get("/implemented")
async def list_implemented():
    """List which block ids have actual React source vendored."""
    return {
        "implemented": list(_BLOCK_SOURCES.keys()),
        "count": len(_BLOCK_SOURCES),
        "blocks_dir": str(_BLOCKS_DIR),
        "manifest": str(_BLOCK_SOURCES_MANIFEST),
        "source_of_truth": "frontend/src/components/ui/blocks/index.js BLOCK_MAP",
    }
