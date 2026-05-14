/**
 * WebContainerPreview — opt-in, in-browser dev-server preview.
 *
 * Render this inside a modal/sheet over the existing PreviewPanel. On mount:
 *   1. Register the COI service worker (one-time per origin).
 *   2. Boot @webcontainer/api (singleton).
 *   3. Mount the project files; run `npm install`; run the dev script.
 *   4. Embed the resulting URL in an iframe.
 *
 * Failure modes are surfaced as calm, dark-themed inline notices — no toasts,
 * no modal stack. Carbon/tan aesthetic preserved.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";

import {
  ensureCoiServiceWorker,
  isWebContainerCapable,
  inferDevCommand,
  startDevServer,
  syncFiles,
} from "@/lib/webcontainer";

const PHASES = {
  idle:       { label: "Idle",                tone: "neutral" },
  isolating:  { label: "Preparing isolation", tone: "neutral" },
  reload:     { label: "Reload to enable",    tone: "warn"    },
  booting:    { label: "Booting WebContainer",tone: "active"  },
  mounting:   { label: "Mounting files",      tone: "active"  },
  installing: { label: "Installing deps",     tone: "active"  },
  starting:   { label: "Starting dev server", tone: "active"  },
  ready:      { label: "Live",                tone: "ok"      },
  error:      { label: "Failed",              tone: "err"     },
  unsupported:{ label: "Unsupported",         tone: "warn"    },
};

export default function WebContainerPreview({ files, onClose }) {
  const [phase, setPhase]   = useState("idle");
  const [error, setError]   = useState(null);
  const [logs, setLogs]     = useState([]);
  const [url, setUrl]       = useState(null);
  const handleRef           = useRef(null);
  const abortRef            = useRef(null);

  const inferred = useMemo(() => inferDevCommand(files || []), [files]);

  const appendLog = useCallback((entry) => {
    setLogs((prev) => {
      const next = prev.concat([entry]);
      return next.length > 200 ? next.slice(next.length - 200) : next;
    });
  }, []);

  // Boot pipeline
  useEffect(() => {
    let cancelled = false;
    abortRef.current = new AbortController();
    (async () => {
      try {
        if (inferred.unsupported) {
          setPhase("unsupported");
          setError(inferred.reason || "This project type isn't supported by WebContainer.");
          return;
        }
        setPhase("isolating");
        const coi = await ensureCoiServiceWorker();
        if (cancelled) return;
        if (coi.needsReload || !isWebContainerCapable()) {
          setPhase("reload");
          return;
        }
        setPhase("booting");
        appendLog({ level: "info", line: "Cross-origin isolation: ok" });

        setPhase("mounting");
        const handle = await startDevServer({
          files: files || [],
          signal: abortRef.current.signal,
          onLog: (e) => {
            // Phase transitions inferred from log content (cheap heuristic).
            const l = (e.line || "").toLowerCase();
            if (l.includes("install"))                  setPhase((p) => (p === "starting" ? p : "installing"));
            else if (l.includes("local:") || l.includes("ready in")) setPhase("starting");
            appendLog(e);
          },
        });
        if (cancelled) {
          handle.dispose?.();
          return;
        }
        handleRef.current = handle;
        setUrl(handle.url);
        setPhase("ready");
        appendLog({ level: "info", line: `Server ready at ${handle.url}` });
      } catch (e) {
        if (cancelled) return;
        setError(e?.message || String(e));
        setPhase("error");
        appendLog({ level: "error", line: e?.message || String(e) });
      }
    })();
    return () => {
      cancelled = true;
      try { abortRef.current?.abort(); } catch { /* ignore */ }
      try { handleRef.current?.dispose?.(); } catch { /* ignore */ }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Live file sync — re-mount when the project's files change while the
  // server is already running. WC's HMR will pick it up.
  useEffect(() => {
    if (phase !== "ready") return;
    let cancelled = false;
    (async () => {
      try {
        await syncFiles(files || []);
        if (!cancelled) appendLog({ level: "info", line: "Re-synced files (HMR)" });
      } catch (e) {
        if (!cancelled) appendLog({ level: "error", line: `Sync failed: ${e.message || e}` });
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files]);

  const tone = PHASES[phase]?.tone || "neutral";
  const toneCls = {
    active:  "bg-[#C8B98C] animate-pulse",
    ok:      "bg-emerald-400",
    err:     "bg-red-400",
    warn:    "bg-amber-300",
    neutral: "bg-white/30",
  }[tone];

  const phaseLabel = PHASES[phase]?.label || phase;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6"
      style={{ background: "rgba(0,0,0,0.62)", backdropFilter: "blur(6px)" }}
      data-testid="webcontainer-preview-modal"
    >
      <div
        className="relative w-full max-w-[1080px] h-[calc(100vh-48px)] sm:h-[80vh]
                   rounded-xl overflow-hidden border border-white/[0.06]
                   bg-[#0E0E10] flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-label="In-browser preview"
      >
        {/* Header */}
        <div className="shrink-0 h-12 px-3 sm:px-4 flex items-center gap-3
                        border-b border-white/[0.04] bg-[#13131680]"
             data-testid="webcontainer-preview-header">
          <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${toneCls}`} aria-hidden />
          <div className="flex-1 min-w-0">
            <div className="text-[11px] tracking-[0.10em] uppercase text-white/35 leading-none">
              In-browser preview · BETA
            </div>
            <div className="mt-0.5 text-[12.5px] text-white/85 leading-none truncate">
              {phaseLabel}
              {url ? <span className="text-white/35"> · {new URL(url).host}</span> : null}
            </div>
          </div>
          <button
            type="button"
            onClick={() => { try { handleRef.current?.dispose?.(); } catch { /* ignore */ } onClose?.(); }}
            className="h-8 w-8 rounded-md flex items-center justify-center
                       text-white/50 hover:text-white/90 hover:bg-white/[0.05]
                       transition-colors"
            data-testid="webcontainer-preview-close"
            aria-label="Close in-browser preview"
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 min-h-0 flex flex-col sm:flex-row">
          {/* Iframe */}
          <div className="flex-1 min-h-0 bg-white relative">
            {phase === "ready" && url ? (
              <iframe
                title="webcontainer-preview"
                src={url}
                className="w-full h-full block"
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                data-testid="webcontainer-preview-iframe"
              />
            ) : phase === "reload" ? (
              <ReloadNotice />
            ) : phase === "unsupported" ? (
              <ErrorNotice
                title="Not supported for this project"
                body={error || "WebContainer can only run JS/TS projects."}
              />
            ) : phase === "error" ? (
              <ErrorNotice title="Couldn't start in-browser preview" body={error} />
            ) : (
              <BootingNotice phase={phaseLabel} />
            )}
          </div>

          {/* Log strip */}
          <div className="shrink-0 h-32 sm:h-auto sm:w-72 border-t sm:border-t-0 sm:border-l
                          border-white/[0.04] bg-[#0B0B0D] overflow-auto"
               data-testid="webcontainer-preview-logs">
            <div className="px-3 py-2 text-[10px] tracking-[0.12em] uppercase text-white/30 sticky top-0
                            bg-[#0B0B0D] border-b border-white/[0.03]">
              Build log
            </div>
            <ul className="px-3 py-2 space-y-0.5 text-[11px] text-white/65 mono leading-relaxed">
              {logs.length === 0 ? (
                <li className="text-white/30 italic">waiting…</li>
              ) : logs.map((l, i) => (
                <li
                  key={i}
                  className={l.level === "error" ? "text-red-300"
                            : l.level === "info" ? "text-[#C8B98C]"
                            : "text-white/60"}
                >
                  {l.line}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function BootingNotice({ phase }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-[#0E0E10]">
      <div className="text-center max-w-sm px-6">
        <div className="mx-auto mb-4 h-2 w-2 rounded-full bg-[#C8B98C] animate-pulse" />
        <div className="text-[11px] tracking-[0.10em] uppercase text-white/35 mb-2">
          {phase}
        </div>
        <p className="text-[13px] text-white/60 leading-relaxed">
          Spinning up a virtual Node runtime inside your browser tab.
          First run can take 20–40 seconds while dependencies install — subsequent runs are near-instant.
        </p>
      </div>
    </div>
  );
}

function ReloadNotice() {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-[#0E0E10]">
      <div className="text-center max-w-md px-6">
        <div className="mx-auto mb-4 h-2 w-2 rounded-full bg-amber-300" />
        <div className="text-[11px] tracking-[0.10em] uppercase text-white/35 mb-2">
          One-time reload
        </div>
        <p className="text-[13px] text-white/60 leading-relaxed mb-4">
          NXT1 just installed a service worker that enables cross-origin
          isolation — a browser requirement for running Node inside the tab.
          Reload once and the in-browser preview will be ready.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="h-9 px-4 rounded-full text-[12.5px] text-[#0E0E10] bg-[#C8B98C]
                     hover:bg-[#D9CCA0] transition-colors"
          data-testid="webcontainer-preview-reload"
        >
          Reload now
        </button>
      </div>
    </div>
  );
}

function ErrorNotice({ title, body }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-[#0E0E10]">
      <div className="text-center max-w-md px-6">
        <div className="mx-auto mb-4 h-2 w-2 rounded-full bg-red-400" />
        <div className="text-[11px] tracking-[0.10em] uppercase text-white/35 mb-2">
          {title}
        </div>
        <p className="text-[13px] text-white/55 leading-relaxed whitespace-pre-wrap">
          {body || "Check the build log."}
        </p>
      </div>
    </div>
  );
}
