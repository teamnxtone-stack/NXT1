"""NXT1 package.json mutator — pure-data helper for tag-mode <nxt1-deps> tags.

Why this exists
===============
The tag-mode generator emits `<nxt1-deps action="install">react-icons</nxt1-deps>`
when the AI wants new packages. We have two options for honouring it:

  1. Actually shell out to `yarn add` in a sandbox right now.
  2. Mutate `package.json` in-memory so the next runtime start picks it up.

We do (2) for now because:
  • zero shell, zero fs writes, zero network — perfectly safe
  • <1ms latency vs ~5-15s for `yarn add`
  • Result is immediately visible to the user as a file edit receipt
  • When the project actually boots (`runtime_service.start_runtime`), the
    existing `_install_node_deps` path runs `npm install` and picks up the
    new declarations
  • WebContainer mode (Phase B.3) installs deps in-browser, so this is also
    the right substrate for that path

`apply_deps_to_files()` returns the mutated file list and a structured diff
the caller surfaces as a `{type:"tool", action:"deps-applied", ...}` event.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("nxt1.deps")


DEFAULT_VERSION = "latest"   # let yarn/npm resolve at install time


@dataclass
class DepsResult:
    files: List[Dict[str, str]] = field(default_factory=list)
    installed: List[str] = field(default_factory=list)
    uninstalled: List[str] = field(default_factory=list)
    target_path: Optional[str] = None   # which package.json we modified
    warning: Optional[str] = None       # surfaced if package.json absent


def _find_package_json(files: List[Dict[str, str]]) -> Optional[Tuple[int, Dict[str, str]]]:
    """Find the FIRST root or near-root package.json. Prefers a root one to a
    nested workspace one so we mutate the canonical project manifest.
    """
    candidates: List[Tuple[int, int, Dict[str, str]]] = []
    for i, f in enumerate(files or []):
        p = (f.get("path") or "").strip().lstrip("/")
        if p == "package.json" or p.endswith("/package.json"):
            depth = p.count("/")
            candidates.append((depth, i, f))
    if not candidates:
        return None
    candidates.sort()
    _, idx, f = candidates[0]
    return idx, f


def _parse_or_default(content: str) -> Dict:
    try:
        d = json.loads(content) if (content or "").strip() else {}
        if not isinstance(d, dict):
            return {}
        return d
    except json.JSONDecodeError:
        return {}


def _format_package_json(data: Dict, original: str) -> str:
    """Re-emit package.json preserving 2-space indent (matches conventions).
    If the original ended with a trailing newline, preserve it."""
    s = json.dumps(data, indent=2, ensure_ascii=False)
    if original.endswith("\n"):
        s += "\n"
    return s


def _split_package(spec: str) -> Tuple[str, str]:
    """Split 'react@^18' into ('react','^18'); 'react' → ('react','latest').
    Scoped packages like '@scope/name@^1' split on the LAST '@' that comes
    after the slash.
    """
    s = spec.strip()
    if not s:
        return "", ""
    if s.startswith("@"):
        # @scope/name OR @scope/name@version
        slash = s.find("/")
        if slash == -1:
            return s, DEFAULT_VERSION
        rest_at = s.find("@", slash + 1)
        if rest_at == -1:
            return s, DEFAULT_VERSION
        return s[:rest_at], s[rest_at + 1:]
    at = s.find("@")
    if at == -1:
        return s, DEFAULT_VERSION
    return s[:at], s[at + 1:]


def apply_deps_to_files(
    files: List[Dict[str, str]],
    install: Optional[List[str]] = None,
    uninstall: Optional[List[str]] = None,
) -> DepsResult:
    """Mutate the package.json in `files` to add/remove deps. Pure function:
    returns a NEW file list; the original is not mutated.

    Behaviour
    ---------
    • Found a package.json → merge into `dependencies` (install) or pop from
      both `dependencies` and `devDependencies` (uninstall).
    • Already present → version stays unless a new version is declared.
    • No package.json present → returns the input files unchanged with a
      `warning` so the caller can either surface it or, for fully-blank web
      projects, create one. We deliberately don't auto-create here; the AI
      should write the package.json explicitly via <nxt1-write>.
    """
    install = install or []
    uninstall = uninstall or []
    if not install and not uninstall:
        return DepsResult(files=list(files), installed=[], uninstalled=[])

    located = _find_package_json(files)
    if not located:
        return DepsResult(
            files=list(files),
            installed=[],
            uninstalled=[],
            warning="No package.json in project — deps tag ignored. "
                    "Have the AI emit <nxt1-write path=\"package.json\"> first.",
        )

    idx, pkg_file = located
    original_content = pkg_file.get("content") or ""
    data = _parse_or_default(original_content)
    deps = data.setdefault("dependencies", {}) if isinstance(
        data.get("dependencies"), dict) else {}
    data["dependencies"] = deps
    dev_deps = data.get("devDependencies") if isinstance(
        data.get("devDependencies"), dict) else {}

    installed_clean: List[str] = []
    for spec in install:
        name, ver = _split_package(spec)
        if not name:
            continue
        deps[name] = ver
        installed_clean.append(name)

    uninstalled_clean: List[str] = []
    for spec in uninstall:
        name, _ = _split_package(spec)
        if not name:
            continue
        removed = False
        if name in deps:
            deps.pop(name, None)
            removed = True
        if name in dev_deps:
            dev_deps.pop(name, None)
            removed = True
        if removed:
            uninstalled_clean.append(name)
    if dev_deps:
        data["devDependencies"] = dev_deps

    new_content = _format_package_json(data, original_content)
    new_files = list(files)
    new_files[idx] = {"path": pkg_file["path"], "content": new_content}
    return DepsResult(
        files=new_files,
        installed=installed_clean,
        uninstalled=uninstalled_clean,
        target_path=pkg_file["path"],
    )


__all__ = ["apply_deps_to_files", "DepsResult"]
