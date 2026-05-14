"""NXT1 tag-protocol — streaming parser + apply layer.

Background
==========
Inspired by dyad's `<dyad-write>` and chef/bolt's `<boltAction>` tags. Instead
of forcing the model to emit a single `{"files":[...]}` JSON blob (which is
slow, token-expensive on incremental edits, and brittle to truncation), we let
it emit inline action tags that are parsed AND applied as bytes stream in.

This module:
  1. Defines a small, unambiguous tag vocabulary (see UPGRADE_PLAN.md §5).
  2. Implements a streaming state-machine parser (`TagStreamParser`).
  3. Implements an apply layer (`apply_tag_action`) that mutates a NXT1 file
     list in-place and reports the diff.

The parser is intentionally allocation-light: it walks the byte buffer once,
emitting events the caller's generator can yield. No regex over the whole
buffer, no full re-scan on each chunk. Memory stays bounded.

Vocabulary
==========
  <nxt1-write path="…">…content…</nxt1-write>           full-file write
  <nxt1-edit path="…">                                  surgical edit
    <search>…</search>
    <replace>…</replace>
  </nxt1-edit>
  <nxt1-rename from="…" to="…" />                       file rename
  <nxt1-delete path="…" />                              delete
  <nxt1-deps action="install"|"uninstall">a b c</nxt1-deps>
  <nxt1-explanation>…</nxt1-explanation>                short summary
  <nxt1-notes>…</nxt1-notes>                            optional follow-ups

Rules
=====
- Tag content is plain text (the model writes raw code). The only thing that
  CANNOT appear in content is the literal closing tag string. This is
  identical to dyad/chef behaviour and works well in practice.
- Tags are processed in stream order; order is mutation order.
- Self-closing tags (`<nxt1-rename ... />`, `<nxt1-delete ... />`) close on
  the trailing `/>`.

Apply semantics
===============
- write       → upsert {path, content}
- edit        → find `search` exactly once in current content, replace with
                `replace`; fail with `EditError` otherwise (so the AI knows
                to widen the search snippet or use `write`)
- rename      → move content from old path to new path
- delete      → remove path
- deps        → recorded into the build summary; install is performed by the
                runtime layer (not this module — it owns no shell)
- explanation → string captured for the chat turn
- notes       → string captured for the chat turn
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple


# ─── tag set ────────────────────────────────────────────────────────────────
# Order matters for prefix matching only when one tag is a prefix of another;
# our names are unique so we don't need to worry about that.
KNOWN_TAGS = {
    "nxt1-write",
    "nxt1-edit",
    "nxt1-rename",
    "nxt1-delete",
    "nxt1-deps",
    "nxt1-shell",          # arbitrary command — executed by shell_service IF
                           # NXT1_ENABLE_SHELL_EXEC=1, else recorded as intent.
    "nxt1-explanation",
    "nxt1-notes",
}
SELF_CLOSING_TAGS = {"nxt1-rename", "nxt1-delete"}
# Nested children that may appear inside <nxt1-edit>
EDIT_CHILD_TAGS = {"search", "replace"}

_ATTR_RE = re.compile(r'(\w+)\s*=\s*"((?:[^"\\]|\\.)*)"')


def _parse_attrs(attr_string: str) -> Dict[str, str]:
    """Parse `name="value"` pairs out of a tag's attribute string. Values may
    contain backslash-escaped quotes (`\\"`)."""
    out: Dict[str, str] = {}
    for m in _ATTR_RE.finditer(attr_string or ""):
        k = m.group(1)
        v = m.group(2).replace('\\"', '"').replace("\\\\", "\\")
        out[k] = v
    return out


# ─── events ────────────────────────────────────────────────────────────────
# Parser yields a sequence of these dicts; callers (e.g. SSE generator) can
# forward them to clients verbatim or convert to their own envelope.

def _ev(type_: str, **kw) -> Dict[str, Any]:
    return {"type": type_, **kw}


# ─── streaming parser ──────────────────────────────────────────────────────
@dataclass
class TagStreamParser:
    """Streaming state machine for NXT1 tag protocol.

    Usage:
        p = TagStreamParser()
        for delta in stream:
            for event in p.feed(delta):
                handle(event)
        for event in p.finish():
            handle(event)

    Events:
        {"type":"prose", "text": "…"}                  prose between tags
        {"type":"tag_open", "tag": "…", "attrs": {…}}  tag started
        {"type":"tag_chunk", "tag": "…", "delta": "…"} content delta (write only)
        {"type":"tag_close", "tag": "…",
                            "attrs": {…}, "content": "…"} tag ended, ready to apply
        {"type":"parse_error", "message": "…"}         malformed input (recoverable)
    """

    # Internal state
    _buf: str = ""
    _mode: str = "outside"   # "outside" | "inside_tag" | "inside_edit"
    _current_tag: Optional[str] = None
    _current_attrs: Dict[str, str] = field(default_factory=dict)
    _current_content_parts: List[str] = field(default_factory=list)
    _last_emitted_pos: int = 0  # position inside current content already emitted as tag_chunk
    # For <nxt1-edit>: child state
    _edit_children: Dict[str, str] = field(default_factory=dict)
    _edit_in_child: Optional[str] = None        # "search" | "replace" | None
    _edit_child_parts: List[str] = field(default_factory=list)

    # ─── public ───
    def feed(self, delta: str) -> Iterator[Dict[str, Any]]:
        if not delta:
            return
        self._buf += delta
        yield from self._drain()

    def finish(self) -> Iterator[Dict[str, Any]]:
        # Final drain. Anything still buffered as prose gets emitted.
        yield from self._drain(final=True)
        if self._mode != "outside":
            yield _ev("parse_error",
                      message=f"Unclosed tag <{self._current_tag}> at stream end")

    # ─── internals ───
    def _drain(self, final: bool = False) -> Iterator[Dict[str, Any]]:
        # Loop until buffer length stops shrinking AND no event is produced.
        # Mode transitions that consume bytes without emitting an event still
        # advance the buffer, so we keep looping in that case.
        while True:
            prev_len = len(self._buf)
            prev_mode = self._mode
            if self._mode == "outside":
                ev = self._drain_outside(final)
            elif self._mode == "inside_tag":
                ev = self._drain_inside_tag(final)
            elif self._mode == "inside_edit":
                ev = self._drain_inside_edit(final)
            else:
                return
            if ev is not None:
                if isinstance(ev, list):
                    yield from ev
                else:
                    yield ev
                # Continue draining — there may be more in the buffer.
                continue
            # No event. If the inner drain made progress (buf shrunk OR mode
            # changed), keep looping to see if more can be drained.
            if len(self._buf) < prev_len or self._mode != prev_mode:
                continue
            # Stalled — nothing more to do until next feed().
            return

    def _drain_outside(self, final: bool):
        # Look for the next "<nxt1-" tag opening.
        idx = self._buf.find("<nxt1-")
        if idx == -1:
            # Whole buffer is prose. Emit it (minus trailing fragment that
            # could become a tag — keep last <16 chars in case).
            if final:
                if self._buf:
                    out = _ev("prose", text=self._buf)
                    self._buf = ""
                    return out
                return None
            keep = 16 if len(self._buf) > 16 else 0
            if len(self._buf) > keep:
                prose = self._buf[: len(self._buf) - keep]
                self._buf = self._buf[len(self._buf) - keep:]
                if prose:
                    return _ev("prose", text=prose)
            return None
        # Emit any prose before the tag
        if idx > 0:
            prose = self._buf[:idx]
            self._buf = self._buf[idx:]
            return _ev("prose", text=prose)
        # Buffer starts with "<nxt1-" — try to parse the open header
        close_idx = self._buf.find(">")
        if close_idx == -1:
            # Header not complete yet; wait for more.
            return None
        header = self._buf[: close_idx + 1]
        # Parse: <nxt1-NAME ATTRS> or <nxt1-NAME ATTRS />
        m = re.match(r"<(nxt1-[a-z-]+)((?:\s+[^>]*?)?)(\s*/)?>$", header, re.DOTALL)
        if not m:
            # Malformed — treat first char as prose so we don't loop forever
            self._buf = self._buf[1:]
            return _ev("parse_error", message=f"Malformed tag header: {header[:80]!r}")
        tag = m.group(1)
        attrs_str = m.group(2) or ""
        self_close = m.group(3) is not None
        attrs = _parse_attrs(attrs_str)
        if tag not in KNOWN_TAGS:
            # Unknown tag — emit as prose char-by-char so we don't strip user content
            self._buf = self._buf[1:]
            return _ev("parse_error", message=f"Unknown tag <{tag}>")
        # Self-closing path
        if self_close or tag in SELF_CLOSING_TAGS:
            self._buf = self._buf[close_idx + 1:]
            # If it was written without "/" but tag IS self-closing, accept it
            return [
                _ev("tag_open", tag=tag, attrs=attrs),
                _ev("tag_close", tag=tag, attrs=attrs, content=""),
            ]
        # Container tag — switch state
        self._current_tag = tag
        self._current_attrs = attrs
        self._current_content_parts = []
        self._last_emitted_pos = 0
        self._buf = self._buf[close_idx + 1:]
        if tag == "nxt1-edit":
            self._mode = "inside_edit"
            self._edit_children = {}
            self._edit_in_child = None
            self._edit_child_parts = []
        else:
            self._mode = "inside_tag"
        return _ev("tag_open", tag=tag, attrs=attrs)

    def _drain_inside_tag(self, final: bool):
        close_str = f"</{self._current_tag}>"
        idx = self._buf.find(close_str)
        if idx == -1:
            # Stream content out incrementally (only for write — others are
            # short, we'll just buffer them).
            # We keep a tail of len(close_str)-1 in the buffer in case the
            # close marker is split across deltas.
            keep = len(close_str) - 1
            if len(self._buf) > keep:
                chunk = self._buf[: len(self._buf) - keep]
                self._buf = self._buf[len(self._buf) - keep:]
                self._current_content_parts.append(chunk)
                if self._current_tag == "nxt1-write":
                    return _ev("tag_chunk", tag=self._current_tag, delta=chunk)
                # Other container tags buffer silently
                return None
            if final:
                # No close found; surface error and reset so the outer drain
                # loop terminates instead of re-emitting the same error.
                tag = self._current_tag
                self._mode = "outside"
                self._current_tag = None
                self._current_attrs = {}
                self._current_content_parts = []
                self._buf = ""
                return _ev("parse_error",
                           message=f"Unclosed <{tag}> at end of stream")
            return None
        # Found close
        before = self._buf[:idx]
        self._current_content_parts.append(before)
        self._buf = self._buf[idx + len(close_str):]
        content = "".join(self._current_content_parts)
        ev = _ev("tag_close",
                 tag=self._current_tag,
                 attrs=self._current_attrs,
                 content=content)
        if self._current_tag == "nxt1-write" and before:
            # emit the residual chunk we didn't stream
            self._mode = "outside"
            tag = self._current_tag
            self._current_tag = None
            self._current_attrs = {}
            self._current_content_parts = []
            return [
                _ev("tag_chunk", tag=tag, delta=before),
                ev,
            ]
        self._mode = "outside"
        self._current_tag = None
        self._current_attrs = {}
        self._current_content_parts = []
        return ev

    def _drain_inside_edit(self, final: bool):
        """<nxt1-edit> body contains <search>…</search> then <replace>…</replace>.
        We scan for child openers/closers OR the parent close `</nxt1-edit>`.
        """
        if self._edit_in_child:
            close_str = f"</{self._edit_in_child}>"
            idx = self._buf.find(close_str)
            if idx == -1:
                keep = len(close_str) - 1
                if len(self._buf) > keep:
                    self._edit_child_parts.append(self._buf[: len(self._buf) - keep])
                    self._buf = self._buf[len(self._buf) - keep:]
                if final:
                    tag = self._edit_in_child
                    self._mode = "outside"
                    self._edit_in_child = None
                    self._edit_child_parts = []
                    self._current_tag = None
                    self._current_attrs = {}
                    self._edit_children = {}
                    self._buf = ""
                    return _ev("parse_error",
                               message=f"Unclosed <{tag}> inside <nxt1-edit>")
                return None
            self._edit_child_parts.append(self._buf[:idx])
            self._buf = self._buf[idx + len(close_str):]
            self._edit_children[self._edit_in_child] = "".join(self._edit_child_parts)
            self._edit_in_child = None
            self._edit_child_parts = []
            return None
        # Not in a child — look for next child open or parent close
        parent_close = "</nxt1-edit>"
        # Find earliest of [parent_close, "<search>", "<replace>"]
        candidates: List[Tuple[int, str]] = []
        for needle in (parent_close, "<search>", "<replace>"):
            i = self._buf.find(needle)
            if i != -1:
                candidates.append((i, needle))
        if not candidates:
            if final:
                self._mode = "outside"
                self._current_tag = None
                self._current_attrs = {}
                self._edit_children = {}
                self._buf = ""
                return _ev("parse_error",
                           message="Unclosed <nxt1-edit> at end of stream")
            return None
        candidates.sort()
        pos, needle = candidates[0]
        if needle == parent_close:
            # Done with edit
            self._buf = self._buf[pos + len(parent_close):]
            content = ""
            ev = _ev("tag_close",
                     tag="nxt1-edit",
                     attrs=self._current_attrs,
                     content=content,
                     children=dict(self._edit_children))
            self._mode = "outside"
            self._current_tag = None
            self._current_attrs = {}
            self._current_content_parts = []
            self._edit_children = {}
            return ev
        # Child opener (<search> or <replace>)
        child_name = needle[1:-1]
        if child_name not in EDIT_CHILD_TAGS:
            self._buf = self._buf[pos + 1:]
            return _ev("parse_error", message=f"Unknown edit child <{child_name}>")
        self._buf = self._buf[pos + len(needle):]
        self._edit_in_child = child_name
        self._edit_child_parts = []
        return None


# ─── apply layer ────────────────────────────────────────────────────────────

class TagApplyError(Exception):
    """Apply step rejected the action (missing path, search not unique, …).
    Caller surfaces these back to the LLM for repair."""


@dataclass
class ApplyResult:
    """Cumulative result of applying a sequence of tag events."""
    files: List[Dict[str, str]] = field(default_factory=list)
    receipts: List[Dict[str, Any]] = field(default_factory=list)
    deps_install: List[str] = field(default_factory=list)
    deps_uninstall: List[str] = field(default_factory=list)
    shell_commands: List[str] = field(default_factory=list)
    explanation: str = ""
    notes: str = ""
    errors: List[Dict[str, Any]] = field(default_factory=list)


def _file_map(files: List[Dict[str, str]]) -> Dict[str, int]:
    return {f["path"]: i for i, f in enumerate(files)}


def apply_tag_action(state: ApplyResult, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Mutate `state` based on a single tag_close event. Returns a receipt
    suitable for forwarding to the SSE client, or None if the event has no
    user-visible side effect.

    Does NOT touch the filesystem. The state lives in memory until the route
    handler persists it to Mongo at end-of-stream.
    """
    if event.get("type") != "tag_close":
        return None
    tag = event["tag"]
    attrs = event.get("attrs") or {}
    content = event.get("content") or ""
    fmap = _file_map(state.files)

    if tag == "nxt1-write":
        path = (attrs.get("path") or "").strip().lstrip("/")
        if not path:
            err = {"action": "write", "message": "<nxt1-write> missing path"}
            state.errors.append(err)
            raise TagApplyError(err["message"])
        action = "edited" if path in fmap else "created"
        if path in fmap:
            state.files[fmap[path]] = {"path": path, "content": content}
        else:
            state.files.append({"path": path, "content": content})
        receipt = {"action": action, "path": path}
        state.receipts.append(receipt)
        return receipt

    if tag == "nxt1-edit":
        path = (attrs.get("path") or "").strip().lstrip("/")
        children = event.get("children") or {}
        search = children.get("search")
        replace = children.get("replace")
        if not path or search is None or replace is None:
            err = {"action": "edit", "message": "<nxt1-edit> requires path + <search> + <replace>"}
            state.errors.append(err)
            raise TagApplyError(err["message"])
        if path not in fmap:
            err = {"action": "edit", "path": path,
                   "message": f"edit failed: file {path!r} does not exist"}
            state.errors.append(err)
            raise TagApplyError(err["message"])
        cur = state.files[fmap[path]]["content"] or ""
        occurrences = cur.count(search)
        if occurrences == 0:
            err = {"action": "edit", "path": path,
                   "message": f"edit failed: search snippet not found in {path!r}"}
            state.errors.append(err)
            raise TagApplyError(err["message"])
        if occurrences > 1:
            err = {"action": "edit", "path": path,
                   "message": f"edit failed: search snippet appeared {occurrences}× — widen it"}
            state.errors.append(err)
            raise TagApplyError(err["message"])
        new_content = cur.replace(search, replace, 1)
        state.files[fmap[path]] = {"path": path, "content": new_content}
        receipt = {"action": "edited", "path": path}
        state.receipts.append(receipt)
        return receipt

    if tag == "nxt1-rename":
        src = (attrs.get("from") or "").strip().lstrip("/")
        dst = (attrs.get("to") or "").strip().lstrip("/")
        if not src or not dst:
            err = {"action": "rename", "message": "<nxt1-rename> requires from + to"}
            state.errors.append(err)
            raise TagApplyError(err["message"])
        if src not in fmap:
            err = {"action": "rename", "message": f"rename failed: {src!r} does not exist"}
            state.errors.append(err)
            raise TagApplyError(err["message"])
        cur = state.files[fmap[src]]
        state.files[fmap[src]] = {"path": dst, "content": cur["content"]}
        receipt = {"action": "renamed", "path": dst, "from": src}
        state.receipts.append(receipt)
        return receipt

    if tag == "nxt1-delete":
        path = (attrs.get("path") or "").strip().lstrip("/")
        if not path:
            err = {"action": "delete", "message": "<nxt1-delete> missing path"}
            state.errors.append(err)
            raise TagApplyError(err["message"])
        if path not in fmap:
            err = {"action": "delete", "path": path,
                   "message": f"delete: {path!r} did not exist (no-op)"}
            state.errors.append(err)
            return {"action": "delete-noop", "path": path}
        # Rebuild list without this entry
        state.files = [f for f in state.files if f["path"] != path]
        receipt = {"action": "deleted", "path": path}
        state.receipts.append(receipt)
        return receipt

    if tag == "nxt1-deps":
        action = (attrs.get("action") or "install").lower()
        pkgs = [p for p in (content or "").split() if p]
        if action == "install":
            state.deps_install.extend(pkgs)
        elif action == "uninstall":
            state.deps_uninstall.extend(pkgs)
        receipt = {"action": f"deps-{action}", "packages": pkgs}
        state.receipts.append(receipt)
        return receipt

    if tag == "nxt1-shell":
        cmd = (content or "").strip()
        if not cmd:
            err = {"action": "shell", "message": "<nxt1-shell> body is empty"}
            state.errors.append(err)
            raise TagApplyError(err["message"])
        state.shell_commands.append(cmd)
        receipt = {"action": "shell-queued", "cmd": cmd}
        state.receipts.append(receipt)
        return receipt

    if tag == "nxt1-explanation":
        state.explanation = (content or "").strip()
        return None

    if tag == "nxt1-notes":
        state.notes = (content or "").strip()
        return None

    return None


__all__ = [
    "KNOWN_TAGS",
    "TagStreamParser",
    "ApplyResult",
    "TagApplyError",
    "apply_tag_action",
]
