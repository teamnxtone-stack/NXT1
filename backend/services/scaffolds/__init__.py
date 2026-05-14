"""Scaffold packs — prompt→foundation seed code.

Each pack exposes a `files()` generator returning a list of
{path, content} dicts. The build pipeline picks the right pack based on
`inference_service.infer_project_kind` and merges those files into the
project BEFORE the AI starts editing.

Packs intentionally ship a working skeleton (zero placeholder code), so
even if the AI fails the user still sees something runnable.
"""
from typing import Callable, Dict, List

from .web_static import files as web_static_files
from .react_vite import files as react_vite_files
from .nextjs_tailwind import files as nextjs_tailwind_files
from .expo_rn import files as expo_rn_files
from .browser_extension import files as browser_extension_files
from .ai_chat_streaming import files as ai_chat_streaming_files

_PACKS: Dict[str, Callable[[str], List[dict]]] = {
    "web-static":          web_static_files,
    "react-vite":          react_vite_files,
    "nextjs-tailwind":     nextjs_tailwind_files,
    "expo-rn":             expo_rn_files,
    "browser-extension":   browser_extension_files,
    "ai-chat-streaming":   ai_chat_streaming_files,
}


def pack_kinds() -> List[str]:
    return list(_PACKS.keys())


def build_scaffold(kind: str, project_name: str = "NXT1 Project") -> List[dict]:
    """Return the file set for a scaffold pack. Falls back to web-static if
    the kind is unknown.
    """
    fn = _PACKS.get(kind) or _PACKS["web-static"]
    return fn(project_name)


# ----------------------------------------------------------------------
# Phase 11 W4 — Track 1 catalogue layer (additive).
#
# The original `_PACKS` above are *execution-only* — they return raw file
# generators. The catalogue layer below (services/scaffolds/catalog.py)
# adds rich UX metadata (label, framework, capabilities, package_manager,
# build/start/preview commands, env_vars) on top of the same kinds, so
# the workspace UI can render a premium scaffold picker without duplicating
# the file content. Both layers coexist:
#
#     build_scaffold(kind)      -> file bodies (real scaffold)
#     list_scaffolds()          -> UX metadata for the picker
#     get_scaffold(scaffold_id) -> full manifest (incl. files) for a chosen pack
#     pick_scaffold(kind)       -> full manifest by inference kind
# ----------------------------------------------------------------------
from .catalog import (
    list_scaffolds,
    get_scaffold,
    pick_scaffold,
    enrich_kind_with_scaffold,
    SCAFFOLD_BY_KIND,
)

__all__ = [
    "pack_kinds",
    "build_scaffold",
    "list_scaffolds",
    "get_scaffold",
    "pick_scaffold",
    "enrich_kind_with_scaffold",
    "SCAFFOLD_BY_KIND",
]

