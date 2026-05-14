/**
 * fileActivity — tiny pub-sub for live "currently being written / recently
 * changed" indicators in the file explorer.
 *
 * Why a module-level store instead of context?
 *   - ChatPanel is the producer (streams `tag_chunk` / `tool` events).
 *   - FileExplorer is the consumer.
 *   - They sit in sibling subtrees that don't share a meaningful context
 *     provider — putting one in would force the whole BuilderPage to
 *     re-render on every chunk, which would tank perf on long streams.
 *   - A standalone store + React hook subscribes only the explorer.
 *
 * State shape:
 *   { [path]: { state: "writing"|"recent", since: number } }
 *
 * Transitions:
 *   writing → recent on first idle (no chunk for 200ms) or on receipt
 *   recent  → cleared after 3.5s
 */
import { useEffect, useState } from "react";

const _state = new Map();   // path -> { state, since, idleTimer, fadeTimer }
const _subs = new Set();

const FADE_MS = 3500;
const IDLE_MS = 200;

function notify() {
  // Snapshot to plain object so React can detect change cheaply.
  const snap = {};
  for (const [k, v] of _state.entries()) snap[k] = { state: v.state, since: v.since };
  for (const fn of _subs) {
    try { fn(snap); } catch { /* ignore */ }
  }
}

function _setRecent(path) {
  const cur = _state.get(path);
  if (cur?.fadeTimer) clearTimeout(cur.fadeTimer);
  const fadeTimer = setTimeout(() => {
    _state.delete(path);
    notify();
  }, FADE_MS);
  _state.set(path, { state: "recent", since: Date.now(), fadeTimer });
  notify();
}

export const fileActivity = {
  /** Begin streaming chunks for a path. Marks it "writing". */
  writing(path) {
    if (!path) return;
    const cur = _state.get(path) || {};
    if (cur.idleTimer) clearTimeout(cur.idleTimer);
    if (cur.fadeTimer) clearTimeout(cur.fadeTimer);
    const idleTimer = setTimeout(() => _setRecent(path), IDLE_MS);
    _state.set(path, { state: "writing", since: Date.now(), idleTimer });
    notify();
  },
  /** A tool receipt closed for this path — mark "recent" and fade in 3.5s. */
  done(path) {
    if (!path) return;
    _setRecent(path);
  },
  /** Reset everything (call when a build starts / project changes). */
  reset() {
    for (const v of _state.values()) {
      if (v.idleTimer) clearTimeout(v.idleTimer);
      if (v.fadeTimer) clearTimeout(v.fadeTimer);
    }
    _state.clear();
    notify();
  },
  snapshot() {
    const snap = {};
    for (const [k, v] of _state.entries()) snap[k] = { state: v.state, since: v.since };
    return snap;
  },
  subscribe(fn) {
    _subs.add(fn);
    return () => _subs.delete(fn);
  },
};

/** React hook — re-renders the caller with a fresh snapshot on any change. */
export function useFileActivity() {
  const [snap, setSnap] = useState(() => fileActivity.snapshot());
  useEffect(() => {
    return fileActivity.subscribe(setSnap);
  }, []);
  return snap;
}
