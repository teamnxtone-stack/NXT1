import { useEffect, useRef, useState } from "react";
import {
  Server,
  Play,
  Square,
  RefreshCw,
  Loader2,
  Terminal,
  ExternalLink,
  AlertTriangle,
  Activity,
  Copy,
  Heart,
  Zap,
  ChevronRight,
  Code2,
  Wand2,
  Bot,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import {
  runtimeStart,
  runtimeStop,
  runtimeRestart,
  runtimeStatus,
  runtimeLogs,
  runtimeProxyUrl,
  runtimeHealth,
  runtimeTry,
  scaffoldBackend,
  generatePageFromRoute,
  runtimeAutoFix,
  runtimeAutoFixApply,
} from "@/lib/api";
import { toast } from "sonner";

const LEVEL_COLOR = {
  info: "text-zinc-300",
  debug: "text-zinc-500",
  warn: "text-amber-300",
  error: "text-red-300",
  stdout: "text-zinc-300",
  stderr: "text-amber-200",
};

const METHOD_COLOR = {
  GET: "text-emerald-300 border-emerald-400/30",
  POST: "text-sky-300 border-sky-400/30",
  PUT: "text-amber-300 border-amber-400/30",
  PATCH: "text-amber-300 border-amber-400/30",
  DELETE: "text-red-300 border-red-400/30",
};

export default function RuntimePanel({ projectId, hasBackend }) {
  const [status, setStatus] = useState(null);
  const [logs, setLogs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [scaffoldBusy, setScaffoldBusy] = useState(null); // 'fastapi' | 'express'
  const [tick, setTick] = useState(0);
  const [health, setHealth] = useState(null);
  const [tryOpen, setTryOpen] = useState(null); // {method, path}
  const [tryBody, setTryBody] = useState("{}");
  const [tryResult, setTryResult] = useState(null);
  const [tryBusy, setTryBusy] = useState(false);
  const logRef = useRef(null);
  const previousAliveRef = useRef(null);
  const failedHealthCountRef = useRef(0);
  const autoFixTriggeredForRef = useRef(null); // started_at marker

  const refresh = async () => {
    try {
      const { data } = await runtimeStatus(projectId);
      setStatus(data);
      setLogs(data.logs || []);
      if (data.health) setHealth(data.health);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    refresh();
    /* eslint-disable-next-line */
  }, [projectId, tick]);

  // Poll while alive
  useEffect(() => {
    if (!status?.alive) return;
    const t = setInterval(async () => {
      try {
        const { data } = await runtimeLogs(projectId, logs.length);
        if (data.logs?.length) setLogs((prev) => [...prev, ...data.logs]);
      } catch {
        /* ignore */
      }
    }, 2000);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [status?.alive, logs.length]);

  // Periodic health probe (every 8s when alive)
  useEffect(() => {
    if (!status?.alive) return;
    const probe = async () => {
      try {
        const { data } = await runtimeHealth(projectId, "/api/health");
        setHealth(data);
      } catch {
        /* ignore */
      }
    };
    probe();
    const t = setInterval(probe, 8000);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [status?.alive]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs.length]);

  // ---- Proactive runtime monitoring (Phase 7+) ----
  // 1) On alive → dead transition (with an error), automatically ask the
  //    debug agent for a fix and open the modal.
  useEffect(() => {
    const wasAlive = previousAliveRef.current;
    const nowAlive = status?.alive;
    if (wasAlive === true && nowAlive === false) {
      const startedKey = status?.started_at || "no-start";
      if (
        autoFixTriggeredForRef.current !== startedKey &&
        !fixProposal &&
        !autoFixBusy &&
        !applyBusy
      ) {
        autoFixTriggeredForRef.current = startedKey;
        toast.warning("Runtime crashed — analysing with debug agent…", {
          duration: 4000,
        });
        askAIToFix().catch(() => {});
      }
    }
    previousAliveRef.current = nowAlive;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.alive, status?.started_at]);

  // 2) Three consecutive health-check failures while still "alive" → trigger fix
  useEffect(() => {
    if (!status?.alive || !health) {
      failedHealthCountRef.current = 0;
      return;
    }
    if (health.ok) {
      failedHealthCountRef.current = 0;
    } else {
      failedHealthCountRef.current += 1;
      if (failedHealthCountRef.current >= 3) {
        const startedKey = `health-${status?.started_at}`;
        if (
          autoFixTriggeredForRef.current !== startedKey &&
          !fixProposal &&
          !autoFixBusy &&
          !applyBusy
        ) {
          autoFixTriggeredForRef.current = startedKey;
          failedHealthCountRef.current = 0;
          toast.warning("Health check failing — analysing with debug agent…", {
            duration: 4000,
          });
          askAIToFix().catch(() => {});
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [health?.ok, health?.ts]);

  const start = async () => {
    setBusy(true);
    try {
      const { data } = await runtimeStart(projectId);
      setStatus(data);
      toast.success(`Runtime started on port ${data.port}`);
      setTick((x) => x + 1);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Start failed");
    } finally {
      setBusy(false);
    }
  };
  const stop = async () => {
    setBusy(true);
    try {
      await runtimeStop(projectId);
      toast.success("Runtime stopped");
      setHealth(null);
      setTick((x) => x + 1);
    } catch {
      toast.error("Stop failed");
    } finally {
      setBusy(false);
    }
  };
  const restart = async () => {
    setBusy(true);
    try {
      const { data } = await runtimeRestart(projectId);
      setStatus(data);
      toast.success("Runtime restarted");
      setTick((x) => x + 1);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Restart failed");
    } finally {
      setBusy(false);
    }
  };

  const scaffold = async (kind) => {
    setScaffoldBusy(kind);
    try {
      const { data } = await scaffoldBackend(projectId, kind, true);
      toast.success(`Generated ${kind} starter`);
      if (data.runtime) setStatus(data.runtime);
      setTick((x) => x + 1);
      // Tell parent to refresh files
      window.dispatchEvent(new CustomEvent("nxt1:filesChanged"));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Scaffold failed");
    } finally {
      setScaffoldBusy(null);
    }
  };

  const openTry = (ep) => {
    setTryOpen(ep);
    setTryBody(ep.method === "GET" ? "" : "{}");
    setTryResult(null);
  };

  const runTry = async () => {
    setTryBusy(true);
    setTryResult(null);
    try {
      let body = null;
      if (tryOpen.method !== "GET" && tryBody.trim()) {
        try {
          body = JSON.parse(tryBody);
        } catch {
          toast.error("Body must be valid JSON");
          setTryBusy(false);
          return;
        }
      }
      const { data } = await runtimeTry(projectId, {
        method: tryOpen.method,
        path: tryOpen.path,
        body,
      });
      setTryResult(data);
    } catch (e) {
      setTryResult({ error: e?.response?.data?.detail || "Request failed" });
    } finally {
      setTryBusy(false);
    }
  };

  const [genBusyKey, setGenBusyKey] = useState(null);
  const [autoFixBusy, setAutoFixBusy] = useState(false);
  const [fixProposal, setFixProposal] = useState(null); // {fix_id,diagnosis,fix_summary,files,...}
  const [applyBusy, setApplyBusy] = useState(false);
  const handleGenerateForRoute = async (ep) => {
    const key = `${ep.method}-${ep.path}`;
    setGenBusyKey(key);
    try {
      const { data } = await generatePageFromRoute(projectId, {
        method: ep.method,
        path: ep.path,
        target: "auto",
      });
      toast.success(`Generated ${data.path}`);
      window.dispatchEvent(new CustomEvent("nxt1:filesChanged"));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Generation failed");
    } finally {
      setGenBusyKey(null);
    }
  };

  const ERROR_HINTS = [
    "Traceback",
    "Error",
    "Exception",
    "TypeError",
    "ValueError",
    "ImportError",
    "ModuleNotFoundError",
    "SyntaxError",
    "RuntimeError",
    "AttributeError",
    "NameError",
    "FileNotFoundError",
    "Cannot find module",
    "EADDRINUSE",
    "ECONNREFUSED",
  ];
  const hasErrorsInLogs =
    logs.some(
      (l) =>
        l.level === "error" ||
        l.level === "stderr" ||
        ERROR_HINTS.some((h) => (l.msg || "").includes(h))
    ) || (status?.error && !status?.alive);

  const askAIToFix = async () => {
    setAutoFixBusy(true);
    setFixProposal(null);
    try {
      const { data } = await runtimeAutoFix(projectId, "", "");
      if (!data.has_errors) {
        toast.info("No errors detected in the runtime buffer.");
        setAutoFixBusy(false);
        return;
      }
      setFixProposal(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Auto-fix failed");
    } finally {
      setAutoFixBusy(false);
    }
  };

  const applyFix = async () => {
    if (!fixProposal) return;
    setApplyBusy(true);
    try {
      const { data } = await runtimeAutoFixApply(projectId, {
        fix_id: fixProposal.fix_id,
        files: fixProposal.files.map((f) => ({ path: f.path, after: f.after })),
        fix_summary: fixProposal.fix_summary,
        diagnosis: fixProposal.diagnosis,
        restart_runtime: fixProposal.post_fix_action === "restart_runtime",
      });
      if (data.runtime) setStatus(data.runtime);
      toast.success(
        `Fix applied to ${data.applied_files.length} file${
          data.applied_files.length === 1 ? "" : "s"
        }${data.restarted ? " · runtime restarted" : ""}`
      );
      setFixProposal(null);
      window.dispatchEvent(new CustomEvent("nxt1:filesChanged"));
      setTick((x) => x + 1);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Apply failed");
    } finally {
      setApplyBusy(false);
    }
  };

  const proxyBase = runtimeProxyUrl(projectId);
  const endpointsFull = status?.endpoints_full || [];
  const noBackend =
    !status?.kind && (!endpointsFull || endpointsFull.length === 0) && !hasBackend;

  // Empty state — no backend yet → show scaffold buttons
  if (noBackend && !status?.alive) {
    return (
      <div
        className="flex flex-col h-full surface-recessed items-center justify-center p-6"
        data-testid="runtime-panel"
      >
        <div className="max-w-md text-center">
          <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-white/5 border border-white/10 mb-4">
            <Server size={20} className="text-zinc-300" />
          </div>
          <div className="text-base font-medium text-white">No backend yet</div>
          <div className="text-sm text-zinc-500 mt-1 leading-relaxed">
            Generate a one-click starter with /api/health, /api/echo and CORS pre-wired. The
            sandbox will boot it instantly.
          </div>
          <div className="mt-5 flex flex-col sm:flex-row gap-2 justify-center">
            <button
              onClick={() => scaffold("fastapi")}
              disabled={scaffoldBusy !== null}
              className="nxt-btn-primary !py-2 !px-4"
              data-testid="scaffold-fastapi-button"
            >
              {scaffoldBusy === "fastapi" ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Zap size={13} />
              )}{" "}
              Generate FastAPI starter
            </button>
            <button
              onClick={() => scaffold("express")}
              disabled={scaffoldBusy !== null}
              className="nxt-btn !py-2 !px-4"
              data-testid="scaffold-express-button"
            >
              {scaffoldBusy === "express" ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Zap size={13} />
              )}{" "}
              Generate Node/Express starter
            </button>
          </div>
          <div className="mt-4 nxt-overline text-zinc-600">
            // or ask the AI in chat: "create a FastAPI backend with /api/posts CRUD"
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full surface-recessed" data-testid="runtime-panel">
      <div className="shrink-0 px-3 sm:px-4 py-3 border-b border-white/5 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3 min-w-0">
          <Server size={14} className="text-white" />
          <div className="min-w-0">
            <div className="text-sm font-medium">Backend runtime</div>
            <div className="nxt-overline">// {status?.kind || "—"} · idle stop after 15 min</div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {status?.alive ? (
            <>
              <span className="inline-flex items-center gap-1.5 nxt-overline text-emerald-300">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                RUNNING · port {status.port}
              </span>
              {health && (
                <span
                  className={`inline-flex items-center gap-1 nxt-overline ${
                    health.ok ? "text-emerald-300" : "text-amber-300"
                  }`}
                  title={health.body_preview || health.error || ""}
                  data-testid="runtime-health-badge"
                >
                  <Heart size={9} className={health.ok ? "fill-emerald-400" : ""} />
                  HEALTH {health.ok ? "OK" : `${health.status_code || "ERR"}`}
                </span>
              )}
              <button
                onClick={restart}
                disabled={busy}
                className="nxt-btn !py-1.5 !px-3"
                data-testid="runtime-restart"
              >
                {busy ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <RefreshCw size={12} />
                )}{" "}
                Restart
              </button>
              {hasErrorsInLogs && (
                <button
                  onClick={askAIToFix}
                  disabled={autoFixBusy}
                  className="nxt-btn-primary !py-1.5 !px-3 !bg-amber-500/15 !border-amber-400/40 text-amber-200 hover:!bg-amber-500/25"
                  data-testid="ask-ai-to-fix-running"
                  title="Bundle recent errors + relevant files to the debug agent"
                >
                  {autoFixBusy ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Bot size={12} />
                  )}{" "}
                  Ask AI to fix
                </button>
              )}
              <button
                onClick={stop}
                disabled={busy}
                className="nxt-btn !py-1.5 !px-3 text-red-300 border-red-500/30"
                data-testid="runtime-stop"
              >
                <Square size={12} /> Stop
              </button>
            </>
          ) : (
            <>
              <span className="inline-flex items-center gap-1.5 nxt-overline text-zinc-500">
                <span className="h-1.5 w-1.5 rounded-full bg-zinc-600" /> STOPPED
              </span>
              {(hasErrorsInLogs || status?.error) && (
                <button
                  onClick={askAIToFix}
                  disabled={autoFixBusy}
                  className="nxt-btn !py-1.5 !px-3 text-amber-200 border-amber-400/40 hover:bg-amber-500/10"
                  data-testid="ask-ai-to-fix-stopped"
                  title="Bundle recent errors + relevant files to the debug agent"
                >
                  {autoFixBusy ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Bot size={12} />
                  )}{" "}
                  Ask AI to fix
                </button>
              )}
              <button
                onClick={start}
                disabled={busy}
                className="nxt-btn-primary !py-1.5 !px-3"
                data-testid="runtime-start"
              >
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />} Start
                runtime
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 min-h-0">
        <aside className="lg:col-span-5 lg:border-r border-b lg:border-b-0 border-white/5 overflow-y-auto p-3 space-y-3">
          <div>
            <div className="nxt-overline mb-1">// status</div>
            {status ? (
              <div className="text-xs mono text-zinc-300 space-y-1">
                <div>
                  kind: <span className="text-white">{status.kind || "—"}</span>
                </div>
                <div>
                  entry: <span className="text-white break-all">{status.entry || "—"}</span>
                </div>
                <div>
                  port: <span className="text-white">{status.port || "—"}</span>
                </div>
                <div>
                  started:{" "}
                  <span className="text-zinc-500">
                    {status.started_at
                      ? new Date(status.started_at).toLocaleTimeString()
                      : "—"}
                  </span>
                </div>
                {status.error && (
                  <div className="text-red-300 flex items-start gap-1 mt-2">
                    <AlertTriangle size={12} className="mt-0.5 shrink-0" />{" "}
                    <span>{status.error}</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-zinc-600 mono">loading…</div>
            )}
          </div>

          <div>
            <div className="nxt-overline mb-2">// detected api routes</div>
            {endpointsFull.length === 0 ? (
              <div className="text-xs text-zinc-600 mono">
                (none — add @app.get / app.get in backend/)
              </div>
            ) : (
              <div className="space-y-1" data-testid="runtime-endpoints">
                {endpointsFull.map((ep, i) => {
                  const url = `${proxyBase}${ep.path.startsWith("/") ? ep.path : `/${ep.path}`}`;
                  return (
                  <div
                    key={`${ep.method}-${ep.path}-${i}`}
                    className="group flex items-center gap-2 px-2 py-1.5 rounded-sm hover:bg-white/5 transition"
                    data-testid={`endpoint-${ep.method}-${ep.path}`}
                  >
                    <span
                      className={`mono text-[10px] tracking-wider px-1.5 py-0.5 border rounded-sm shrink-0 ${
                        METHOD_COLOR[ep.method] || "text-zinc-300 border-white/10"
                      }`}
                    >
                      {ep.method}
                    </span>
                    <span className="text-xs mono text-zinc-200 truncate flex-1">
                      {ep.path}
                    </span>
                    <button
                      onClick={() => handleGenerateForRoute(ep)}
                      disabled={genBusyKey === `${ep.method}-${ep.path}`}
                      className="opacity-0 group-hover:opacity-100 sm:opacity-100 inline-flex items-center gap-1 text-[10px] mono text-emerald-300 hover:text-white px-1 disabled:opacity-50"
                      title="Generate frontend page that calls this route"
                      data-testid={`generate-page-${ep.method}-${ep.path}`}
                    >
                      {genBusyKey === `${ep.method}-${ep.path}` ? (
                        <Loader2 size={9} className="animate-spin" />
                      ) : (
                        <Wand2 size={9} />
                      )}
                      page
                    </button>
                    {status?.alive && (
                      <button
                        onClick={() => openTry(ep)}
                        className="opacity-0 group-hover:opacity-100 sm:opacity-100 text-[10px] mono text-emerald-300 hover:text-white px-1"
                        title="Try it"
                        data-testid={`try-${ep.method}-${ep.path}`}
                      >
                        try ▸
                      </button>
                    )}
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(url);
                        toast.success("Copied");
                      }}
                      className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-white"
                      title="Copy URL"
                    >
                      <Copy size={10} />
                    </button>
                    {status?.alive && (
                      <a
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-white"
                      >
                        <ExternalLink size={10} />
                      </a>
                    )}
                  </div>
                  );
                })}
              </div>
            )}
          </div>

          <div>
            <div className="nxt-overline mb-1">// proxy base</div>
            <div className="text-[11px] mono text-zinc-400 break-all bg-[#1F1F23] border border-white/5 px-2 py-1.5 rounded-sm">
              {proxyBase}
            </div>
            <button
              onClick={() => {
                navigator.clipboard.writeText(proxyBase);
                toast.success("Copied");
              }}
              className="mt-1 text-[11px] mono text-zinc-500 hover:text-white"
            >
              copy →
            </button>
          </div>
        </aside>

        <section
          className="lg:col-span-7 flex flex-col min-h-0"
          data-testid="runtime-logs-panel"
        >
          <div className="px-3 py-2 border-b border-white/5 flex items-center justify-between">
            <span className="nxt-overline flex items-center gap-2">
              <Terminal size={11} /> // runtime console
            </span>
            <span className="nxt-overline text-zinc-600">{logs.length} lines</span>
          </div>
          <div
            ref={logRef}
            className="flex-1 overflow-y-auto p-3 mono text-[12px] leading-relaxed bg-[#1F1F23]"
          >
            {logs.length === 0 ? (
              <div className="text-zinc-600">no output yet — start the runtime above</div>
            ) : (
              logs.map((l, i) => (
                <div key={i} className="flex gap-3">
                  <span className="text-zinc-700 shrink-0 hidden sm:inline">
                    {new Date(l.ts).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </span>
                  <span className={`break-words ${LEVEL_COLOR[l.level] || "text-zinc-300"}`}>
                    {l.msg}
                  </span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      {/* Try-it modal */}
      {tryOpen && (
        <div
          className="fixed inset-0 z-50 bg-graphite-scrim-strong backdrop-blur-sm flex items-center justify-center p-3 sm:p-6"
          onClick={() => setTryOpen(null)}
          data-testid="try-it-modal"
        >
          <div
            className="nxt-panel rounded-sm bg-[#1F1F23] w-[820px] max-w-full max-h-[92vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="h-11 shrink-0 flex items-center justify-between px-4 border-b border-white/5">
              <div className="flex items-center gap-2 min-w-0">
                <Code2 size={13} className="text-emerald-300 shrink-0" />
                <span
                  className={`mono text-[10px] tracking-wider px-1.5 py-0.5 border rounded-sm ${
                    METHOD_COLOR[tryOpen.method] || "text-zinc-300 border-white/10"
                  }`}
                >
                  {tryOpen.method}
                </span>
                <span className="text-sm font-medium truncate mono">{tryOpen.path}</span>
              </div>
              <button
                onClick={() => setTryOpen(null)}
                className="text-zinc-500 hover:text-white text-sm px-2"
              >
                close
              </button>
            </div>
            <div className="flex-1 overflow-auto grid grid-rows-[auto_1fr_auto_1fr] gap-2 p-3 sm:p-4">
              {tryOpen.method !== "GET" && (
                <>
                  <div className="nxt-overline">// request body (json)</div>
                  <textarea
                    value={tryBody}
                    onChange={(e) => setTryBody(e.target.value)}
                    rows={6}
                    className="nxt-input mono !text-[12px] resize-none"
                    spellCheck={false}
                    data-testid="try-it-body"
                  />
                </>
              )}
              <div className="flex items-center gap-2">
                <button
                  onClick={runTry}
                  disabled={tryBusy}
                  className="nxt-btn-primary !py-1.5 !px-3"
                  data-testid="try-it-send"
                >
                  {tryBusy ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <ChevronRight size={12} />
                  )}{" "}
                  Send
                </button>
                <button
                  onClick={() => {
                    const url = `${proxyBase}${
                      tryOpen.path.startsWith("/") ? tryOpen.path : "/" + tryOpen.path
                    }`;
                    const cmd =
                      tryOpen.method === "GET"
                        ? `curl ${url}`
                        : `curl -X ${tryOpen.method} -H 'content-type: application/json' -d '${tryBody}' ${url}`;
                    navigator.clipboard.writeText(cmd);
                    toast.success("cURL copied");
                  }}
                  className="nxt-btn !py-1.5 !px-3"
                >
                  <Copy size={11} /> as cURL
                </button>
              </div>
              <div className="min-h-0 flex flex-col">
                <div className="nxt-overline mb-1">// response</div>
                <pre
                  className="flex-1 overflow-auto surface-recessed border border-white/5 rounded-sm p-3 mono text-[12px] text-zinc-200"
                  data-testid="try-it-result"
                >
                  {tryResult
                    ? `${tryResult.error ? "" : "status: " + tryResult.status_code + "\n\n"}${
                        tryResult.error || tryResult.body_text || ""
                      }`
                    : "(send a request to see the response)"}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Auto-fix proposal modal */}
      {fixProposal && (
        <div
          className="fixed inset-0 z-50 bg-graphite-scrim-strong backdrop-blur-sm flex items-center justify-center p-3 sm:p-6"
          onClick={() => !applyBusy && setFixProposal(null)}
          data-testid="auto-fix-modal"
        >
          <div
            className="nxt-panel rounded-sm bg-[#1F1F23] w-[920px] max-w-full max-h-[92vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-white/5">
              <div className="flex items-center gap-2 min-w-0">
                <Bot size={14} className="text-amber-300 shrink-0" />
                <div className="text-sm font-medium truncate">
                  AI-proposed fix
                </div>
                <span
                  className={`mono text-[10px] tracking-wider px-1.5 py-0.5 border rounded-sm shrink-0 ${
                    fixProposal.confidence === "high"
                      ? "text-emerald-300 border-emerald-400/30"
                      : fixProposal.confidence === "low"
                      ? "text-amber-300 border-amber-400/30"
                      : "text-zinc-300 border-white/10"
                  }`}
                >
                  CONFIDENCE · {fixProposal.confidence?.toUpperCase()}
                </span>
                {fixProposal.requires_approval && (
                  <span
                    className="mono text-[10px] tracking-wider px-1.5 py-0.5 border rounded-sm shrink-0 text-red-300 border-red-400/30"
                    title="The AI flagged this fix as risky — review carefully"
                    data-testid="fix-requires-approval-badge"
                  >
                    APPROVAL REQUIRED
                  </span>
                )}
              </div>
              <button
                onClick={() => !applyBusy && setFixProposal(null)}
                className="text-zinc-500 hover:text-white text-sm px-2"
              >
                close
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4 sm:p-5 space-y-4">
              <div>
                <div className="nxt-overline mb-1">// diagnosis</div>
                <p className="text-sm text-zinc-200 leading-relaxed" data-testid="fix-diagnosis">
                  {fixProposal.diagnosis}
                </p>
              </div>
              <div>
                <div className="nxt-overline mb-1">// proposed fix</div>
                <p className="text-sm text-zinc-300 leading-relaxed" data-testid="fix-summary">
                  {fixProposal.fix_summary || "(no summary)"}
                </p>
                {fixProposal.next_check && (
                  <p className="text-xs text-zinc-500 mt-2 leading-relaxed">
                    <span className="text-emerald-400 mono">›</span> After applying:{" "}
                    {fixProposal.next_check}
                  </p>
                )}
              </div>
              <div>
                <div className="nxt-overline mb-2">
                  // file changes ({fixProposal.files.length})
                </div>
                <div className="space-y-2" data-testid="fix-files">
                  {fixProposal.files.map((f, i) => (
                    <details
                      key={`${f.path}-${i}`}
                      className="border border-white/5 rounded-sm surface-recessed"
                    >
                      <summary className="cursor-pointer px-3 py-2 flex items-center gap-2 text-xs mono hover:bg-white/[0.03]">
                        <span className="text-zinc-300 truncate flex-1">{f.path}</span>
                        <span className="text-emerald-300">+{f.diff?.added || 0}</span>
                        <span className="text-red-300">−{f.diff?.removed || 0}</span>
                        <ChevronRight size={11} className="text-zinc-500" />
                      </summary>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-white/5 border-t border-white/5">
                        <pre className="surface-recessed p-2 mono text-[11px] text-zinc-500 overflow-auto max-h-[260px] whitespace-pre-wrap">
                          <span className="block nxt-overline text-red-300 mb-1">
                            // before
                          </span>
                          {f.before || "(new file)"}
                        </pre>
                        <pre className="surface-recessed p-2 mono text-[11px] text-zinc-200 overflow-auto max-h-[260px] whitespace-pre-wrap">
                          <span className="block nxt-overline text-emerald-300 mb-1">
                            // after
                          </span>
                          {f.after}
                        </pre>
                      </div>
                    </details>
                  ))}
                </div>
              </div>
            </div>
            <div className="shrink-0 px-4 py-3 border-t border-white/5 flex items-center justify-between gap-3 flex-wrap">
              <span className="text-xs text-zinc-500 mono">
                rollback any time from the History tab
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setFixProposal(null)}
                  disabled={applyBusy}
                  className="nxt-btn !py-2 !px-3"
                  data-testid="fix-discard"
                >
                  Discard
                </button>
                <button
                  onClick={applyFix}
                  disabled={applyBusy || fixProposal.files.length === 0}
                  className="nxt-btn-primary !py-2 !px-4"
                  data-testid="fix-apply"
                >
                  {applyBusy ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <ShieldCheck size={13} />
                  )}{" "}
                  Apply &amp;{" "}
                  {fixProposal.post_fix_action === "restart_runtime"
                    ? "restart runtime"
                    : "save"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
