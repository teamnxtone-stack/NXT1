import { useMemo, useState, useEffect, useRef } from "react";
import {
  RefreshCw,
  ExternalLink,
  Monitor,
  Tablet,
  Smartphone,
  AlertTriangle,
  Sparkles,
  X,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { API, runtimeAutoFix, runtimeAutoFixApply } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { friendlyError } from "@/lib/errors";
import DeviceFrame from "@/components/premium/DeviceFrame";
import WebContainerPreview from "@/components/builder/WebContainerPreview";
import { inferDevCommand } from "@/lib/webcontainer";

/**
 * Build the iframe `srcDoc` for the generated app preview.
 *
 * In addition to inlining linked CSS/JS and rewriting asset URLs, we inject
 * a small **runtime-error capture shim** that catches any `window.onerror`,
 * `unhandledrejection`, or `console.error` event inside the iframe and posts
 * it to the parent via `postMessage({type:'nxt1-runtime-error', ...})`.
 *
 * The parent `<PreviewPanel>` listens for that message and replaces the
 * raw browser dev-overlay with a calm, on-brand "App crashed" card.
 */
function buildSrcDoc(files, projectId, pagePath) {
  const map = {};
  for (const f of files || []) map[f.path] = f.content;
  let html =
    map[pagePath] ||
    map["index.html"] ||
    "<!DOCTYPE html><html><body><h1 style='color:#fff;background:#1F1F23;height:100vh;display:flex;align-items:center;justify-content:center;font-family:sans-serif'>No index.html</h1></body></html>";

  // Inline ALL referenced CSS files (links)
  const linkRe = /<link\s+[^>]*?(?:rel=["']stylesheet["'][^>]*?href=["']([^"']+\.css)["']|href=["']([^"']+\.css)["'][^>]*?rel=["']stylesheet["'])[^>]*?\/?>/gi;
  html = html.replace(linkRe, (m, h1, h2) => {
    const href = h1 || h2;
    const css = map[href];
    return css != null ? `<style data-from="${href}">${css}</style>` : m;
  });
  // Inline ALL referenced JS files (script src)
  const scriptRe = /<script\s+[^>]*?src=["']([^"']+\.js)["'][^>]*?>\s*<\/script>/gi;
  html = html.replace(scriptRe, (m, src) => {
    const js = map[src];
    return js != null ? `<script data-from="${src}">${js}<\/script>` : m;
  });

  // Replace asset references with authenticated URLs
  const token = getToken();
  const assetBase = `${API}/projects/${projectId}/assets`;
  html = html.replace(
    /(src|href)=["']assets\/([^"']+)["']/g,
    (_m, attr, name) => `${attr}="${assetBase}/${name}?auth=${token}"`
  );

  // ── Runtime error capture shim ──────────────────────────────────────
  // Sent BEFORE any user JS so we catch even synchronous errors thrown
  // during initial render. Filters common dev-only noise (DevTools probes,
  // hot-reload heartbeat, ResizeObserver loop, etc).
  const errorShim = `<script>(function(){
    var POST = function(payload){
      try { parent.postMessage(Object.assign({type:'nxt1-runtime-error'}, payload), '*'); } catch(_) {}
    };
    var IGNORED = /ResizeObserver loop|Script error\\.?$|Non-Error promise rejection captured|__REACT_DEVTOOLS_GLOBAL_HOOK__|sourceMappingURL/i;
    var serialize = function(err){
      if (!err) return {message: 'Unknown error'};
      if (typeof err === 'string') return {message: err};
      var msg = err.message || String(err);
      var stack = err.stack ? String(err.stack).split('\\n').slice(0,4).join('\\n') : '';
      var name = err.name || (err.constructor && err.constructor.name) || 'Error';
      return {message: msg, stack: stack, name: name};
    };
    window.addEventListener('error', function(ev){
      var msg = (ev.message || (ev.error && ev.error.message) || '');
      if (IGNORED.test(msg)) return;
      POST({source:'window.onerror', error: serialize(ev.error || ev.message), filename: ev.filename || '', line: ev.lineno || 0});
    }, true);
    window.addEventListener('unhandledrejection', function(ev){
      var reason = ev.reason;
      var msg = reason && (reason.message || reason.toString && reason.toString()) || '';
      if (IGNORED.test(msg)) return;
      POST({source:'unhandledrejection', error: serialize(reason)});
    });
    // Capture console.error as a soft signal too — many React apps log
    // hydration / render errors there without throwing synchronously.
    var origErr = console.error;
    console.error = function(){
      try {
        var first = arguments[0];
        var msg = (first && first.message) || (typeof first === 'string' ? first : '');
        if (msg && !IGNORED.test(msg) && /error|fail|crash|invalid/i.test(msg)) {
          POST({source:'console.error', error: serialize(first), severity: 'soft'});
        }
      } catch(_){}
      return origErr.apply(console, arguments);
    };
    // Heartbeat — tell parent we successfully booted so it can clear any
    // stale error overlay after a successful reload.
    setTimeout(function(){ POST({source:'boot', ok: true}); }, 150);
  })();<\/script>`;

  // Intercept relative .html navigations to swap iframe srcDoc — uses
  // postMessage to parent
  const navShim = `<script>(function(){
    document.addEventListener('click', function(e){
      var a = e.target.closest('a');
      if(!a) return;
      var href = a.getAttribute('href') || '';
      if(/^https?:\\/\\//.test(href) || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:')) return;
      if(/\\.html(\\?|#|$)/.test(href)){
        e.preventDefault();
        try { parent.postMessage({type:'nxt1-nav', path: href.split('#')[0].split('?')[0]}, '*'); } catch(_){}
      }
    }, true);
  })();<\/script>`;

  // Inject error shim as early as possible (right after <head> or at top)
  if (/<head[^>]*>/i.test(html)) {
    html = html.replace(/<head[^>]*>/i, (m) => `${m}${errorShim}`);
  } else {
    html = errorShim + html;
  }
  // Nav shim at end of body
  if (/<\/body>/i.test(html)) {
    html = html.replace(/<\/body>/i, `${navShim}</body>`);
  } else {
    html += navShim;
  }
  return html;
}

const VIEWPORTS = {
  desktop: { w: "100%", h: "100%", label: "Desktop" },
  tablet: { w: 820, h: 1180, label: "Tablet" },
  mobile: { w: 390, h: 844, label: "Mobile" },
};

/**
 * Map raw iframe runtime errors to a calm, on-brand summary.
 * Never expose the raw stack trace to the user UI — keep it internal.
 */
function summarizeRuntimeError(err) {
  const msg = (err?.error?.message || err?.message || "").toString();
  const lower = msg.toLowerCase();
  if (lower.includes("is not defined") || lower.includes("is not a function")) {
    return {
      title: "Missing reference",
      hint: "The app called something that doesn't exist yet. Ask NXT1 to wire it up.",
    };
  }
  if (lower.includes("cannot read") || lower.includes("undefined")) {
    return {
      title: "Undefined value",
      hint: "Something the app expected wasn't there. A retry or a small fix from NXT1 usually resolves it.",
    };
  }
  if (lower.includes("syntax") || lower.includes("unexpected token")) {
    return {
      title: "Syntax error in generated code",
      hint: "The generator slipped on a comma. Ask NXT1 to repair the file.",
    };
  }
  if (lower.includes("network") || lower.includes("failed to fetch")) {
    return {
      title: "Network call failed",
      hint: "An API call in the preview didn't reach the server. Retry the preview.",
    };
  }
  return {
    title: "App crashed in preview",
    hint: "The generated app threw an error. Try reloading — or ask NXT1 to fix it.",
  };
}

export default function PreviewPanel({ files, activeFile: _activeFile, projectId, onFileSaved: _onFileSaved }) {
  const [viewport, setViewport] = useState("desktop");
  const [iframeKey, setIframeKey] = useState(0);
  const [previewPage, setPreviewPage] = useState("index.html");
  const [previewInfo, setPreviewInfo] = useState(null);
  const [liveUrl, setLiveUrl] = useState(null);
  const [useLive, setUseLive] = useState(false);
  // Runtime-error capture (from iframe shim)
  const [runtimeError, setRuntimeError] = useState(null);
  const errorDismissedRef = useRef(false); // user explicitly dismissed — don't re-show
  // WebContainer preview (Phase B.3) — opt-in, in-browser dev server.
  // Only offered when the project looks like a JS/TS app (no native backend).
  const [wcOpen, setWcOpen] = useState(false);
  const wcSupportedForProject = useMemo(
    () => !inferDevCommand(files || []).unsupported,
    [files]
  );

  // Pull import-detection metadata so we know whether to render in-iframe
  // or fall back to the live deploy URL automatically.
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      try {
        const api = (await import("@/lib/api")).default;
        const { data } = await api.get(`/projects/${projectId}/preview-info`);
        if (cancelled) return;
        setPreviewInfo(data.preview_info || null);
        setLiveUrl(data.live_url || null);
        if (data.preview_info && data.preview_info.preview_ok === false && data.live_url) {
          setUseLive(true);
        }
      } catch {
        /* preview-info is optional — silently degrade */
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  const htmlPages = useMemo(
    () => (files || []).filter((f) => f.path.endsWith(".html")).map((f) => f.path),
    [files]
  );

  // Listen for nav clicks + runtime errors from iframe
  useEffect(() => {
    const handler = (e) => {
      const d = e?.data;
      if (!d || typeof d !== "object") return;
      if (d.type === "nxt1-nav" && typeof d.path === "string") {
        if (htmlPages.includes(d.path)) {
          setPreviewPage(d.path);
          // Reset error state on intentional navigation
          errorDismissedRef.current = false;
          setRuntimeError(null);
        }
      } else if (d.type === "nxt1-runtime-error") {
        // Boot heartbeat — clear stale error overlay on successful re-render
        if (d.source === "boot" && d.ok) {
          // Only clear if no hard error has fired since boot. The boot
          // event arrives ~150ms after iframe load; if a real error fired
          // synchronously, it has already populated `runtimeError` via
          // the same channel earlier in the queue.
          return;
        }
        // Soft signals (console.error) don't override a hard error and
        // don't show if user has dismissed.
        if (errorDismissedRef.current) return;
        if (d.severity === "soft" && runtimeError) return;
        setRuntimeError({
          source: d.source,
          message: d.error?.message || "Unknown error",
          filename: d.filename || "",
          line: d.line || 0,
          soft: d.severity === "soft",
        });
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [htmlPages, runtimeError]);

  // When the project gets a NEW build (file count, paths, or any content
  // length change), clear the dismissed flag so a fresh crash will surface
  // again. We deliberately do NOT depend on the `files` array reference —
  // BuilderPage can re-pass the same files on every re-render, which would
  // wipe a fresh error overlay before the user ever sees it. The content
  // fingerprint is stable across re-renders of the same build.
  const filesFingerprint = useMemo(
    () => (files || []).map((f) => `${f.path}:${(f.content || "").length}`).join("|"),
    [files]
  );
  useEffect(() => {
    errorDismissedRef.current = false;
    setRuntimeError(null);
  }, [filesFingerprint]);

  const srcDoc = useMemo(
    () => buildSrcDoc(files, projectId, previewPage),
    [files, projectId, previewPage, iframeKey]
  );

  const reload = () => {
    errorDismissedRef.current = false;
    setRuntimeError(null);
    setIframeKey((k) => k + 1);
  };

  const askNxt1ToFix = () => {
    if (!runtimeError) return;
    const friendly = summarizeRuntimeError({ error: runtimeError });
    // Build a clean, redacted prompt — never include raw stack traces from
    // the iframe (could be enormous or contain bundler noise).
    const prompt =
      `The preview is crashing with a runtime error: "${friendly.title}" — ` +
      `${friendly.hint}\n\nMessage observed: ${runtimeError.message}` +
      (runtimeError.filename ? `\nFile: ${runtimeError.filename}` : "") +
      (runtimeError.line ? ` (line ${runtimeError.line})` : "") +
      `\n\nPlease diagnose and fix the affected file(s).`;
    // ChatPanel listens for this exact event.
    window.dispatchEvent(new CustomEvent("nxt1:sendChat", { detail: { text: prompt } }));
    setRuntimeError(null);
    errorDismissedRef.current = true;
  };

  const dismiss = () => {
    errorDismissedRef.current = true;
    setRuntimeError(null);
  };

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: "var(--surface-recessed)" }}
      data-testid="preview-panel"
    >
      <div
        className="h-11 shrink-0 flex items-center justify-between border-b px-3 gap-2"
        style={{ borderColor: "var(--hairline)" }}
      >
        <div className="flex items-center gap-2 min-w-0">
          {htmlPages.length > 1 ? (
            <select
              value={previewPage}
              onChange={(e) => setPreviewPage(e.target.value)}
              className="bg-transparent text-[12px] mono outline-none cursor-pointer min-w-0 truncate"
              style={{ color: "var(--nxt-fg-dim)" }}
              data-testid="preview-page-select"
            >
              {htmlPages.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          ) : (
            <span
              className="text-[12px] mono truncate"
              style={{ color: "var(--nxt-fg-dim)" }}
            >
              {previewPage}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <div
            className="flex items-center rounded-full overflow-hidden"
            style={{
              background: "rgba(255, 255, 255, 0.04)",
              border: "1px solid var(--hairline-strong)",
            }}
            data-testid="preview-viewport"
          >
            {Object.entries(VIEWPORTS).map(([k, v]) => {
              const Icon = k === "desktop" ? Monitor : k === "tablet" ? Tablet : Smartphone;
              const active = viewport === k;
              return (
                <button
                  key={k}
                  onClick={() => setViewport(k)}
                  title={v.label}
                  className="px-2.5 py-1 transition"
                  style={{
                    background: active ? "var(--nxt-fg)" : "transparent",
                    color: active ? "var(--nxt-bg)" : "var(--nxt-fg-faint)",
                  }}
                  data-testid={`viewport-${k}`}
                >
                  <Icon size={12} />
                </button>
              );
            })}
          </div>
          <button
            onClick={reload}
            className="h-7 w-7 flex items-center justify-center rounded-full transition"
            style={{
              background: "rgba(255, 255, 255, 0.04)",
              border: "1px solid var(--hairline-strong)",
              color: "var(--nxt-fg-faint)",
            }}
            title="Reload"
            data-testid="reload-preview-button"
          >
            <RefreshCw size={12} />
          </button>
          <button
            onClick={() => {
              const w = window.open();
              if (w) { w.document.write(srcDoc); w.document.close(); }
            }}
            className="h-7 w-7 flex items-center justify-center rounded-full transition"
            style={{
              background: "rgba(255, 255, 255, 0.04)",
              border: "1px solid var(--hairline-strong)",
              color: "var(--nxt-fg-faint)",
            }}
            title="Open in new tab"
            data-testid="open-preview-newtab"
          >
            <ExternalLink size={12} />
          </button>
          {wcSupportedForProject ? (
            <button
              onClick={() => setWcOpen(true)}
              className="h-7 px-2.5 rounded-full transition flex items-center gap-1.5
                         text-[10.5px] tracking-[0.08em] uppercase"
              style={{
                background: "rgba(200, 185, 140, 0.08)",
                border: "1px solid rgba(200, 185, 140, 0.35)",
                color: "#C8B98C",
              }}
              title="Run this project in a virtual Node runtime inside your browser tab (beta)"
              data-testid="open-webcontainer-preview"
            >
              <span className="h-1 w-1 rounded-full bg-[#C8B98C]" aria-hidden />
              In-browser
            </button>
          ) : null}
        </div>
      </div>
      <div
        className="flex-1 overflow-auto flex items-start justify-center p-4 relative"
        style={{ background: "var(--surface-recessed)" }}
      >
        <DeviceFrame variant={viewport} url={previewPage}>
          <iframe
            key={`${iframeKey}-${previewPage}-${useLive ? "live" : "local"}`}
            title="preview"
            {...(useLive && liveUrl
              ? { src: liveUrl }
              : { srcDoc })}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
            className="w-full h-full bg-white block"
            data-testid="live-preview-iframe"
          />
          {previewInfo && previewInfo.preview_ok === false && liveUrl && (
            <div
              className="absolute top-2 right-2 z-30 flex items-center gap-1.5 px-2.5 py-1 rounded-full backdrop-blur text-[10.5px] mono uppercase tracking-wider"
              style={{
                background: "var(--scrim)",
                border: "1px solid var(--nxt-border)",
                color: "var(--nxt-fg)",
              }}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${useLive ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`} />
              {useLive ? "live deploy" : "fallback ready"}
              <button
                onClick={() => setUseLive((v) => !v)}
                className="ml-1 transition"
                style={{ color: "var(--nxt-accent)" }}
                data-testid="preview-fallback-toggle"
              >
                {useLive ? "use local" : "use live"}
              </button>
            </div>
          )}
          {/* Runtime crash overlay — replaces raw browser dev-overlay with a
              calm, on-brand "App crashed" card that drives the real backend
              auto-fix loop. */}
          {runtimeError && !runtimeError.soft && (
            <RuntimeCrashOverlay
              error={runtimeError}
              projectId={projectId}
              onRetry={reload}
              onAskNxt1={askNxt1ToFix}
              onDismiss={dismiss}
              onFixApplied={() => {
                // Files just changed on disk — clear and force iframe reload.
                errorDismissedRef.current = false;
                setRuntimeError(null);
                _onFileSaved?.();
                setIframeKey((k) => k + 1);
              }}
            />
          )}
        </DeviceFrame>
      </div>
    </div>
  );
}

/**
 * RuntimeCrashOverlay — overlays the iframe when generated code crashes.
 * Never renders raw stack traces; drives the real backend auto-fix loop:
 *
 *   crashed → (Ask NXT1 to fix) → diagnosing → proposal → (Apply) → applying → done
 *
 * The Retry path (Reload preview) is always available as a fast escape.
 */
function RuntimeCrashOverlay({ error, projectId, onRetry, onAskNxt1, onDismiss, onFixApplied }) {
  const summary = summarizeRuntimeError({ error });
  const [phase, setPhase] = useState("crashed"); // crashed | diagnosing | proposal | applying | done | failed
  const [proposal, setProposal] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");

  const requestFix = async () => {
    if (!projectId) {
      // No project context — fall back to chat prompt
      onAskNxt1?.();
      return;
    }
    setPhase("diagnosing");
    setErrorMsg("");
    try {
      const errText = [
        `Runtime error: ${error.message}`,
        error.filename ? `File: ${error.filename}` : "",
        error.line ? `Line: ${error.line}` : "",
      ].filter(Boolean).join("\n");
      const { data } = await runtimeAutoFix(projectId, errText, "Preview iframe runtime crash");
      if (!data?.fix_id || !data?.files?.length) {
        // No usable proposal — fall back to chat
        onAskNxt1?.();
        return;
      }
      setProposal(data);
      setPhase("proposal");
    } catch (e) {
      const fe = friendlyError(e?.response?.data?.detail || e?.message);
      setErrorMsg(fe.hint);
      setPhase("failed");
    }
  };

  const applyFix = async () => {
    if (!proposal) return;
    setPhase("applying");
    setErrorMsg("");
    try {
      await runtimeAutoFixApply(projectId, {
        fix_id: proposal.fix_id,
        files: proposal.files,
        fix_summary: proposal.fix_summary || "",
        diagnosis: proposal.diagnosis || "",
        restart_runtime: true,
      });
      setPhase("done");
      // Brief celebration then reload
      setTimeout(() => {
        onFixApplied?.();
      }, 700);
    } catch (e) {
      const fe = friendlyError(e?.response?.data?.detail || e?.message);
      setErrorMsg(fe.hint);
      setPhase("failed");
    }
  };

  return (
    <div
      className="absolute inset-0 z-40 flex items-end sm:items-center justify-center p-4 sm:p-8"
      style={{
        background: "var(--scrim)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
      }}
      data-testid="runtime-crash-overlay"
    >
      <div
        className="relative w-full max-w-md rounded-2xl p-5 sm:p-6"
        style={{
          background: "var(--nxt-surface, var(--surface-1))",
          border: "1px solid var(--nxt-border)",
          boxShadow: "var(--elev-2)",
        }}
      >
        {phase !== "applying" && phase !== "diagnosing" && (
          <button
            onClick={onDismiss}
            className="absolute top-3 right-3 h-7 w-7 rounded-full flex items-center justify-center transition"
            style={{ background: "transparent", color: "var(--nxt-fg-faint)" }}
            title="Dismiss"
            data-testid="runtime-crash-dismiss"
          >
            <X size={14} />
          </button>
        )}

        {/* Header */}
        <div className="flex items-start gap-3">
          <span
            className="h-9 w-9 rounded-full flex items-center justify-center shrink-0"
            style={{
              background: phase === "done"
                ? "rgba(20, 130, 110, 0.16)"
                : "rgba(245, 158, 11, 0.14)",
              border: `1px solid ${phase === "done"
                ? "rgba(20, 130, 110, 0.4)"
                : "rgba(245, 158, 11, 0.36)"}`,
            }}
          >
            {phase === "done"
              ? <CheckCircle2 size={16} style={{ color: "var(--nxt-accent)" }} />
              : phase === "diagnosing" || phase === "applying"
                ? <Loader2 size={14} className="animate-spin" style={{ color: "#F59E0B" }} />
                : <AlertTriangle size={16} style={{ color: "#F59E0B" }} />
            }
          </span>
          <div className="flex-1 min-w-0">
            <div
              className="text-[15px] font-semibold tracking-tight"
              style={{ color: "var(--nxt-fg)" }}
            >
              {phase === "diagnosing" && "Diagnosing the crash…"}
              {phase === "proposal"   && "Fix proposed"}
              {phase === "applying"   && "Applying fix…"}
              {phase === "done"       && "Fix applied"}
              {phase === "failed"     && "Auto-fix didn't land"}
              {phase === "crashed"    && summary.title}
            </div>
            <div
              className="text-[13px] leading-relaxed mt-1"
              style={{ color: "var(--nxt-fg-dim)" }}
            >
              {phase === "diagnosing" && "Reading the error and the surrounding files. This takes a few seconds."}
              {phase === "proposal"   && (proposal?.fix_summary || proposal?.diagnosis || "NXT1 has a proposed change ready to apply.")}
              {phase === "applying"   && "Writing the patched files and warming the preview."}
              {phase === "done"       && "Reloading the preview now."}
              {phase === "failed"     && (errorMsg || "Try again, switch model, or ask NXT1 directly in chat.")}
              {phase === "crashed"    && summary.hint}
            </div>
            {phase === "crashed" && (error.filename || error.line) && (
              <div
                className="mt-2.5 text-[11px] mono px-2 py-1 rounded-md inline-block"
                style={{
                  background: "rgba(255, 255, 255, 0.04)",
                  color: "var(--nxt-fg-faint)",
                  border: "1px solid var(--hairline)",
                }}
              >
                {error.filename || "preview"}{error.line ? `:${error.line}` : ""}
              </div>
            )}
            {phase === "proposal" && proposal?.files?.length > 0 && (
              <div className="mt-3 space-y-1">
                <div
                  className="mono text-[10px] tracking-[0.22em] uppercase"
                  style={{ color: "var(--nxt-fg-faint)" }}
                >
                  changes
                </div>
                <ul className="space-y-0.5">
                  {proposal.files.slice(0, 5).map((f, idx) => (
                    <li
                      key={`${f.path}-${idx}`}
                      className="text-[11.5px] mono truncate"
                      style={{ color: "var(--nxt-fg-dim)" }}
                    >
                      <span style={{ color: "var(--nxt-accent)" }}>~</span> {f.path}
                    </li>
                  ))}
                  {proposal.files.length > 5 && (
                    <li
                      className="text-[11px] italic"
                      style={{ color: "var(--nxt-fg-faint)" }}
                    >
                      +{proposal.files.length - 5} more
                    </li>
                  )}
                </ul>
              </div>
            )}
          </div>
        </div>

        {/* Action row — varies by phase */}
        <div className="flex flex-wrap gap-2 mt-5">
          {phase === "crashed" && (
            <>
              <button
                type="button"
                onClick={requestFix}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[12.5px] font-medium transition"
                style={{ background: "var(--nxt-accent)", color: "var(--nxt-bg)" }}
                data-testid="runtime-crash-ask-nxt1"
              >
                <Sparkles size={12} strokeWidth={2.4} />
                Ask NXT1 to fix
              </button>
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[12.5px] transition"
                style={{
                  background: "transparent",
                  border: "1px solid var(--nxt-border)",
                  color: "var(--nxt-fg-dim)",
                }}
                data-testid="runtime-crash-retry"
              >
                <RefreshCw size={11} strokeWidth={2.4} />
                Reload preview
              </button>
            </>
          )}
          {phase === "proposal" && (
            <>
              <button
                type="button"
                onClick={applyFix}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[12.5px] font-medium transition"
                style={{ background: "var(--nxt-accent)", color: "var(--nxt-bg)" }}
                data-testid="runtime-crash-apply-fix"
              >
                <CheckCircle2 size={12} strokeWidth={2.4} />
                Apply fix
              </button>
              <button
                type="button"
                onClick={() => setPhase("crashed")}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[12.5px] transition"
                style={{
                  background: "transparent",
                  border: "1px solid var(--nxt-border)",
                  color: "var(--nxt-fg-dim)",
                }}
              >
                Back
              </button>
            </>
          )}
          {phase === "failed" && (
            <>
              <button
                type="button"
                onClick={onAskNxt1}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[12.5px] font-medium transition"
                style={{ background: "var(--nxt-accent)", color: "var(--nxt-bg)" }}
              >
                <Sparkles size={12} strokeWidth={2.4} />
                Ask in chat instead
              </button>
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[12.5px] transition"
                style={{
                  background: "transparent",
                  border: "1px solid var(--nxt-border)",
                  color: "var(--nxt-fg-dim)",
                }}
              >
                <RefreshCw size={11} strokeWidth={2.4} />
                Reload preview
              </button>
            </>
          )}
          {(phase === "diagnosing" || phase === "applying") && (
            <div
              className="text-[11.5px] mono inline-flex items-center gap-2"
              style={{ color: "var(--nxt-fg-faint)" }}
            >
              <span className="nxt-cursor inline-block w-2 h-3" /> working
            </div>
          )}
        </div>
      </div>
      {wcOpen ? (
        <WebContainerPreview
          files={files}
          onClose={() => setWcOpen(false)}
        />
      ) : null}
    </div>
  );
}
