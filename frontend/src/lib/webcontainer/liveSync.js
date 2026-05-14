/**
 * webcontainer/liveSync — true stream-time file sync.
 *
 * What this does
 * ==============
 * As `<nxt1-write path="…">` tags stream in from the AI, the backend
 * forwards `tag_chunk` events (one per content delta) and a `tool` event
 * on close. The historical sync model waited for the END of the whole
 * turn, snapshotted the final project state, and called `syncFiles()`
 * (one re-mount / many writes).
 *
 * With live-sync enabled we:
 *   1. Accumulate per-path deltas as `tag_chunk` events arrive.
 *   2. On `tool` close for action `created`/`edited`, immediately call
 *      `fs.writeFile(path, accumulated)` against the booted WebContainer.
 *   3. On `tool` close for action `deleted`/`renamed`, mirror that to
 *      the WC filesystem.
 *
 * This lets HMR fire on each file as soon as the AI finishes that file,
 * which makes the preview feel "drawn in real time" instead of waiting
 * for the whole chat turn to complete.
 *
 * Guarantees
 * ----------
 * - No-op when the WC singleton hasn't booted (`window.__nxt1Wc` unset).
 *   The cost on a non-WC project is a `Map.get + return`.
 * - Updates the same WeakMap snapshot `syncFiles()` uses, so the
 *   end-of-turn `syncFiles()` becomes a near-noop (no redundant writes).
 * - Failures swallow into a console.warn — never throw into the chat
 *   stream loop.
 */

import { _getOrInitSnapshot } from "./index.js";

const _buffers = new Map();   // path -> accumulated content this turn

function _wc() {
  if (typeof window === "undefined") return null;
  return window.__nxt1Wc || null;
}

function _isEnabled() {
  return Boolean(_wc());
}

/** Reset internal accumulators. Call when a new chat turn starts. */
export function liveSyncReset() {
  _buffers.clear();
}

/** Accumulate a delta for a path. Cheap; no FS work. */
export function liveSyncAppend(path, delta) {
  if (!path || !delta || !_isEnabled()) return;
  _buffers.set(path, (_buffers.get(path) || "") + delta);
}

/** Commit a fully-written file (called on the `tool` close event). */
export async function liveSyncCommit(path) {
  if (!path || !_isEnabled()) return;
  const wc = _wc();
  if (!wc) return;
  const content = _buffers.get(path);
  _buffers.delete(path);
  if (content === undefined) return;
  try {
    const segs = path.split("/").slice(0, -1);
    if (segs.length) {
      try { await wc.fs.mkdir(segs.join("/"), { recursive: true }); }
      catch { /* may already exist */ }
    }
    await wc.fs.writeFile(path, content);
    const snap = _getOrInitSnapshot();
    if (snap) snap.set(path, content);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn("[nxt1.wc] liveSync write failed", path, e);
  }
}

/** Mirror a delete/rename source onto the WC FS. */
export async function liveSyncRemove(path) {
  if (!path || !_isEnabled()) return;
  _buffers.delete(path);
  const wc = _wc();
  if (!wc) return;
  try { await wc.fs.rm(path, { force: true }); }
  catch (e) {
    // eslint-disable-next-line no-console
    console.warn("[nxt1.wc] liveSync rm failed", path, e);
  }
  const snap = _getOrInitSnapshot();
  if (snap) snap.delete(path);
}

/** Test-only escape hatch. */
export function _liveSyncSnapshotForTests() {
  return new Map(_buffers);
}
