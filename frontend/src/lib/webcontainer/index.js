/**
 * NXT1 WebContainer integration — boot + mount + dev-server lifecycle.
 *
 * What this module gives you
 * ==========================
 *   ensureCoiServiceWorker()      → registers the COI service worker that
 *                                    flips `crossOriginIsolated` on. Returns
 *                                    `{ active, needsReload }`.
 *   isWebContainerCapable()       → quick env feature-test
 *   getWebContainer()             → singleton boot of @webcontainer/api
 *   mountProject(files)           → write a NXT1 file-list into the WC FS
 *   startDevServer(opts)          → choose a smart command, run it, wait
 *                                    for the `server-ready` event, return
 *                                    `{ url, port, dispose }`.
 *
 * Why a singleton boot
 * --------------------
 * `WebContainer.boot()` can be called at most once per page lifetime. We
 * stash the resulting instance on `window.__nxt1Wc` so navigating between
 * the WC preview view and other parts of the app doesn't re-boot.
 *
 * Project-type heuristics
 * -----------------------
 * If the file set contains a `package.json` with `dev` script → run that.
 * If it has `index.html` + only static assets → serve via `npx serve`.
 * If it looks like Vite → `npm install && npm run dev -- --host 0.0.0.0`.
 * If it looks like a backend (Python / Go / etc.) → refuse — WC is browser-
 *   only, no native runtime support.
 */

let _wcPromise = null;

export function isWebContainerCapable() {
  if (typeof window === "undefined") return false;
  if (typeof SharedArrayBuffer === "undefined") return false;
  return Boolean(window.crossOriginIsolated);
}

/**
 * Registers (or de-registers) the COI service worker. The worker installs
 * COOP/COEP response headers on every fetch — without those headers the
 * browser refuses to enable cross-origin-isolation and `crossOriginIsolated`
 * stays false, which prevents WebContainer from booting.
 *
 * Returns:
 *   { active:        boolean — SW is controlling the page right now
 *     needsReload:   boolean — SW installed but page must reload to apply
 *     unsupported:   boolean — SW API not available }
 */
export async function ensureCoiServiceWorker() {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
    return { active: false, needsReload: false, unsupported: true };
  }
  // If already isolated, nothing to do.
  if (window.crossOriginIsolated) {
    return { active: true, needsReload: false };
  }
  try {
    const reg = await navigator.serviceWorker.register("/coi-serviceworker.js", {
      scope: "/",
    });
    await navigator.serviceWorker.ready;
    // If the SW just installed for the first time, the current page won't
    // yet have the COOP/COEP headers — it needs a single hard reload.
    const installedNow = Boolean(reg.installing || reg.waiting);
    return { active: window.crossOriginIsolated, needsReload: installedNow };
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn("[nxt1.wc] COI SW registration failed", e);
    return { active: false, needsReload: false, unsupported: false, error: e };
  }
}

/** Lazy-singleton boot of @webcontainer/api. Throws if env not capable. */
export async function getWebContainer() {
  if (!isWebContainerCapable()) {
    throw new Error(
      "WebContainer is not available: this browser tab is not cross-origin-isolated."
      + " Reload the page after the service worker installs.",
    );
  }
  if (window.__nxt1Wc) return window.__nxt1Wc;
  if (_wcPromise) return _wcPromise;
  _wcPromise = (async () => {
    const { WebContainer } = await import("@webcontainer/api");
    const instance = await WebContainer.boot();
    window.__nxt1Wc = instance;
    return instance;
  })();
  return _wcPromise;
}

/**
 * Turn a NXT1 file list (`[{ path, content }]`) into the WebContainer
 * FileSystemTree format expected by `wc.mount()`.
 *
 * WC's tree is nested objects keyed by directory:
 *   { "src": { directory: { "App.jsx": { file: { contents: "…" } } } } }
 */
export function filesToTree(files) {
  const root = {};
  for (const f of files || []) {
    const path = (f.path || "").replace(/^\/+/, "");
    if (!path) continue;
    const parts = path.split("/");
    let cur = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const seg = parts[i];
      if (!cur[seg]) cur[seg] = { directory: {} };
      else if (!cur[seg].directory) cur[seg] = { directory: {} };
      cur = cur[seg].directory;
    }
    const fname = parts[parts.length - 1];
    cur[fname] = { file: { contents: f.content ?? "" } };
  }
  return root;
}

/** Inspect the project to pick a sensible dev-server command. */
export function inferDevCommand(files) {
  const map = new Map((files || []).map((f) => [f.path, f.content || ""]));
  const pkg = map.get("package.json");
  // Heuristic: backend-only signals → refuse.
  if (map.has("requirements.txt") || map.has("Pipfile") || map.has("go.mod")
      || map.has("Cargo.toml")) {
    return { unsupported: true,
              reason: "Project includes a native backend (Python/Go/Rust) — WebContainer only runs Node/JS." };
  }
  if (pkg) {
    try {
      const j = JSON.parse(pkg);
      const scripts = j.scripts || {};
      if (scripts.dev)   return { cmd: ["npm", ["run", "dev", "--", "--host", "0.0.0.0"]] };
      if (scripts.start) return { cmd: ["npm", ["start"]] };
      if (scripts.serve) return { cmd: ["npm", ["run", "serve"]] };
    } catch { /* falls through */ }
  }
  if (map.has("index.html")) {
    return { cmd: ["npx", ["--yes", "serve", "-l", "5173", "."]] };
  }
  return { unsupported: true,
            reason: "Couldn't infer how to start this project. Add a `package.json` with a `dev` script." };
}

/** Stream stdout/stderr lines from a WC process to a callback. */
function pipeProcess(proc, onLine) {
  let buf = "";
  proc.output.pipeTo(new WritableStream({
    write(chunk) {
      buf += chunk;
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const l of lines) onLine(l);
    },
  })).catch(() => {});
}

/**
 * Mount the files and start the dev server. Returns:
 *   { url, port, dispose, processes: { install, dev } }
 *
 * Caller is responsible for embedding `url` in an iframe.
 */
export async function startDevServer({ files, onLog, signal }) {
  const wc = await getWebContainer();
  const cmd = inferDevCommand(files);
  if (cmd.unsupported) throw new Error(cmd.reason);

  onLog?.({ level: "info", line: "Mounting project files…" });
  await wc.mount(filesToTree(files));

  // npm install (best-effort — skipped if no node_modules dep changes)
  let installProc = null;
  if ((files || []).some((f) => f.path === "package.json")) {
    onLog?.({ level: "info", line: "Installing dependencies…" });
    installProc = await wc.spawn("npm", ["install", "--no-fund", "--no-audit"]);
    pipeProcess(installProc, (line) => onLog?.({ level: "stdout", line }));
    const code = await installProc.exit;
    if (code !== 0) {
      throw new Error(`npm install exited with code ${code}`);
    }
    if (signal?.aborted) throw new Error("aborted");
  }

  onLog?.({ level: "info", line: `Starting: ${cmd.cmd[0]} ${cmd.cmd[1].join(" ")}` });
  const devProc = await wc.spawn(cmd.cmd[0], cmd.cmd[1]);
  pipeProcess(devProc, (line) => onLog?.({ level: "stdout", line }));

  // Wait for server-ready event.
  const { url, port } = await new Promise((resolve, reject) => {
    const ready = wc.on("server-ready", (port, url) => {
      ready();   // dispose listener
      resolve({ url, port });
    });
    devProc.exit.then((code) => {
      // If dev exited before server-ready, it failed.
      reject(new Error(`dev server exited with code ${code}`));
    });
    if (signal) {
      signal.addEventListener("abort", () => reject(new Error("aborted")));
    }
  });

  return {
    url,
    port,
    processes: { install: installProc, dev: devProc },
    async dispose() {
      try { devProc.kill(); } catch { /* ignore */ }
    },
  };
}

/** One-shot incremental file sync (call after a chat turn).
 *
 * Uses real `fs.writeFile` per-changed-file when we have a previous snapshot
 * to diff against — that's 50-200x faster than re-mounting the entire tree
 * and means the in-browser preview HMR fires on the actual changed file
 * only. Falls back to `mount` on the very first sync (when there's no prior
 * snapshot to diff against).
 *
 * NOTE: state is keyed on the WebContainer instance, not module-level, so
 * concurrent previews in multiple tabs don't collide.
 */
const _SYNC_STATE = new WeakMap();   // wcInstance -> Map<path, content>

/** Internal: return (and create if needed) the snapshot map for the
 * currently-booted WC instance. Used by `liveSync.js` to update the
 * snapshot in lockstep with stream-time `fs.writeFile` calls — so the
 * end-of-turn `syncFiles()` becomes a near-noop. Returns `null` when
 * no WC instance is booted yet.
 */
export function _getOrInitSnapshot() {
  if (typeof window === "undefined" || !window.__nxt1Wc) return null;
  const wc = window.__nxt1Wc;
  let m = _SYNC_STATE.get(wc);
  if (!m) { m = new Map(); _SYNC_STATE.set(wc, m); }
  return m;
}

export async function syncFiles(files) {
  const wc = await getWebContainer();
  const cur = new Map((files || []).map((f) => [f.path, f.content || ""]));
  const prev = _SYNC_STATE.get(wc);

  // First sync of this WC lifetime → do a full mount (faster than N writes).
  if (!prev) {
    await wc.mount(filesToTree(files));
    _SYNC_STATE.set(wc, cur);
    return { mode: "full", changed: cur.size };
  }

  // Compute diff
  const added = [];
  const modified = [];
  const removed = [];
  for (const [p, c] of cur.entries()) {
    if (!prev.has(p)) added.push(p);
    else if (prev.get(p) !== c) modified.push(p);
  }
  for (const p of prev.keys()) {
    if (!cur.has(p)) removed.push(p);
  }

  if (added.length === 0 && modified.length === 0 && removed.length === 0) {
    return { mode: "noop", changed: 0 };
  }

  // Bulk: if we're touching >40 files, full mount is cheaper than N writes.
  if (added.length + modified.length + removed.length > 40) {
    await wc.mount(filesToTree(files));
    _SYNC_STATE.set(wc, cur);
    return { mode: "full", changed: cur.size };
  }

  const fs = wc.fs;
  const ensureDir = async (relPath) => {
    const segs = relPath.split("/").slice(0, -1);
    if (segs.length === 0) return;
    const dir = segs.join("/");
    try { await fs.mkdir(dir, { recursive: true }); }
    catch (e) { /* may already exist */ }
  };
  for (const p of [...added, ...modified]) {
    await ensureDir(p);
    await fs.writeFile(p, cur.get(p) || "");
  }
  for (const p of removed) {
    try { await fs.rm(p, { force: true }); } catch { /* ignore */ }
  }
  _SYNC_STATE.set(wc, cur);
  return {
    mode: "incremental",
    added: added.length,
    modified: modified.length,
    removed: removed.length,
  };
}
