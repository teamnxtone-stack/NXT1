import { useEffect, useMemo, useRef, useState } from "react";
import {
  Rocket,
  Loader2,
  Check,
  X,
  ExternalLink,
  RefreshCw,
  AlertTriangle,
  Clock,
  Server,
  Copy,
  Zap,
  Bot,
  ShieldCheck,
  ChevronRight,
} from "lucide-react";
import {
  createDeployment,
  listDeployments,
  getDeployment,
  cancelDeployment,
  deployUrl,
  getProviders,
  setPublishOnSave,
  getProjectState,
  deployAutoFix,
  deployAutoFixApply,
} from "@/lib/api";
import { toast } from "sonner";

const STATUS_STYLE = {
  pending:   { color: "text-zinc-400",    dot: "bg-zinc-500",                       label: "Queued",    accent: "rgba(255,255,255,0.20)" },
  building:  { color: "text-amber-300",   dot: "bg-amber-400 nxt-pulse-warm",       label: "Building",  accent: "rgba(245,158,11,0.55)" },
  deployed:  { color: "text-emerald-300", dot: "bg-emerald-400 nxt-pulse",          label: "Live",      accent: "rgba(94,234,212,0.55)" },
  failed:    { color: "text-rose-300",    dot: "bg-rose-500 nxt-pulse-pink",        label: "Failed",    accent: "rgba(244,114,182,0.55)" },
  cancelled: { color: "text-zinc-400",    dot: "bg-zinc-500",                       label: "Cancelled", accent: "rgba(255,255,255,0.20)" },
};

function StatusBadge({ status }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.pending;
  return (
    <span className={`inline-flex items-center gap-2 mono text-[10.5px] tracking-[0.2em] uppercase ${s.color}`}>
      <span className={`h-2 w-2 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

// Group log lines by step keyword so the stream reads like a CI timeline
const STEP_KEYWORDS = [
  { key: "queue",   match: /(queu|enqueu)/i,                     label: "queue"   },
  { key: "clone",   match: /(clone|fetch|checkout|download)/i,   label: "clone"   },
  { key: "install", match: /(install|yarn|npm|pip|deps)/i,       label: "install" },
  { key: "build",   match: /(build|compile|bundle|webpack|vite)/i, label: "build" },
  { key: "deploy",  match: /(deploy|publish|upload|push|host)/i, label: "deploy"  },
];

function detectStep(msg = "") {
  for (const s of STEP_KEYWORDS) if (s.match.test(msg)) return s.key;
  return null;
}

function LogLine({ entry, index, isLast }) {
  const lvlColor = {
    info:  "text-zinc-200",
    debug: "text-zinc-500",
    warn:  "text-amber-300",
    error: "text-rose-300",
  };
  const lvlDot = {
    info:  "bg-white/30",
    debug: "bg-white/15",
    warn:  "bg-amber-400",
    error: "bg-rose-400",
  };
  return (
    <div
      className="group grid grid-cols-[40px_72px_8px_1fr] gap-x-2 items-baseline px-3 py-0.5 mono text-[11.5px] leading-[1.6] hover:bg-white/[0.02] transition-colors nxt-fade-up"
      style={{ animationDelay: `${Math.min(index * 8, 240)}ms` }}
    >
      <span className="text-white/15 text-right tabular-nums select-none">{String(index + 1).padStart(3, "0")}</span>
      <span className="text-white/35 tabular-nums">
        {new Date(entry.ts).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })}
      </span>
      <span className={`h-1.5 w-1.5 rounded-full mt-1.5 ${lvlDot[entry.level] || lvlDot.info}`} />
      <span className={`${lvlColor[entry.level] || lvlColor.info} whitespace-pre-wrap break-words`}>
        {entry.msg}
        {isLast && entry.level !== "error" && (
          <span className="nxt-cursor" />
        )}
      </span>
    </div>
  );
}

// Cinematic step timeline — derived from log entries; mirrors Vercel-style
function StepTimeline({ logs = [], status }) {
  // Find first occurrence of each step keyword
  const reached = new Set();
  for (const l of logs) {
    const s = detectStep(l.msg);
    if (s) reached.add(s);
  }
  const steps = STEP_KEYWORDS.filter((s) => s.key !== "queue"); // queue is implicit
  if (steps.every((s) => !reached.has(s.key)) && status !== "building") return null;

  return (
    <div className="flex items-center gap-2 sm:gap-3 px-3 py-3 overflow-x-auto no-scrollbar nxt-fade-up">
      {steps.map((s, i) => {
        const done = reached.has(s.key);
        const isActive = !done && (i === 0 || reached.has(steps[i - 1].key)) && status === "building";
        return (
          <div key={s.key} className="flex items-center gap-2 shrink-0">
            <span
              className={`relative h-2 w-2 rounded-full ${done ? "bg-emerald-400" : isActive ? "bg-amber-400 nxt-pulse-warm" : "bg-white/12"}`}
            />
            <span
              className={`mono text-[10.5px] tracking-[0.22em] uppercase ${
                done ? "text-emerald-300/90" : isActive ? "text-amber-200" : "text-white/30"
              }`}
            >
              {s.label}
            </span>
            {i < steps.length - 1 && (
              <span className={`h-px w-6 sm:w-10 ${done ? "bg-emerald-400/35" : "bg-white/8"} transition-colors`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function DeploymentPanel({ projectId, project, onProjectUpdated, externalDeployment }) {
  const [history, setHistory] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [active, setActive] = useState(null);
  const [deploying, setDeploying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState("internal");
  const [publishOnSave, setPublishOnSaveState] = useState(false);
  const [savingToggle, setSavingToggle] = useState(false);
  const [fixBusy, setFixBusy] = useState(false);
  const [fixProposal, setFixProposal] = useState(null);
  const [applyBusy, setApplyBusy] = useState(false);

  const askAIToFix = async (deploymentId) => {
    setFixBusy(true);
    setFixProposal(null);
    try {
      const { data } = await deployAutoFix(projectId, deploymentId, "");
      if (!data.has_errors) {
        toast.info("This deployment did not fail — nothing to fix.");
        setFixBusy(false);
        return;
      }
      setFixProposal(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Auto-fix failed");
    } finally {
      setFixBusy(false);
    }
  };

  const applyFix = async () => {
    if (!fixProposal) return;
    setApplyBusy(true);
    try {
      const { data } = await deployAutoFixApply(projectId, {
        fix_id: fixProposal.fix_id,
        deployment_id: fixProposal.deployment_id,
        files: fixProposal.files.map((f) => ({ path: f.path, after: f.after })),
        fix_summary: fixProposal.fix_summary,
        diagnosis: fixProposal.diagnosis,
        auto_redeploy: true,
      });
      toast.success(
        `Fix applied · ${data.applied_files.length} file${
          data.applied_files.length === 1 ? "" : "s"
        }${data.redeployed_deployment_id ? " · re-deploying" : ""}`,
      );
      setFixProposal(null);
      window.dispatchEvent(new CustomEvent("nxt1:filesChanged"));
      await refreshHistory();
      if (data.redeployed_deployment_id) setActiveId(data.redeployed_deployment_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Apply failed");
    } finally {
      setApplyBusy(false);
    }
  };

  const refreshHistory = async () => {
    try {
      const { data } = await listDeployments(projectId);
      setHistory(data);
      if (!activeId && data.length > 0) setActiveId(data[0].id);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const refreshActive = async (id) => {
    if (!id) return;
    try {
      const { data } = await getDeployment(projectId, id);
      setActive(data);
    } catch {
      // ignore
    }
  };

  const refreshProviders = async () => {
    try {
      const { data } = await getProviders();
      setProviders(data.deploy || []);
    } catch {
      // ignore
    }
  };

  const refreshState = async () => {
    try {
      const { data } = await getProjectState(projectId);
      setPublishOnSaveState(!!data.publish_on_save);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    refreshHistory();
    refreshProviders();
    refreshState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // React to external auto-deployments (from ChatPanel)
  useEffect(() => {
    if (externalDeployment?.id) {
      refreshHistory();
      setActiveId(externalDeployment.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalDeployment?.id]);

  useEffect(() => {
    refreshActive(activeId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  // ---- Proactive deploy monitoring (Phase 7+) ----
  // Watch every deployment status transition. When ANY deployment moves to
  // 'failed', automatically call /deploy/auto-fix and show the proposal modal.
  const failedSeenRef = useRef(new Set());
  useEffect(() => {
    if (!history || history.length === 0) return;
    for (const d of history) {
      if (d.status === "failed" && !failedSeenRef.current.has(d.id)) {
        failedSeenRef.current.add(d.id);
        // Only auto-trigger for THE most recent failure (avoid bombing
        // multiple modals for old historical failures on first load).
        const newest = [...history].sort(
          (a, b) => new Date(b.created_at) - new Date(a.created_at),
        )[0];
        if (newest?.id !== d.id) continue;
        // Skip if user already has a modal open or busy
        if (fixProposal || fixBusy || applyBusy) continue;
        toast.warning(
          "Deployment failed — analysing with DevOps agent…",
          { duration: 4000 },
        );
        askAIToFix(d.id).catch(() => {});
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history.map((d) => `${d.id}:${d.status}`).join(",")]);

  // Poll the deployment list while any deployment is pending/building so we
  // catch the failure transition the moment it happens.
  useEffect(() => {
    const pending = history.some(
      (d) => d.status === "pending" || d.status === "building",
    );
    if (!pending) return;
    const t = setInterval(() => refreshHistory(), 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history.map((d) => `${d.id}:${d.status}`).join(",")]);

  const onDeploy = async () => {
    setDeploying(true);
    try {
      const { data } = await createDeployment(projectId, provider);
      if (data.status === "deployed") {
        toast.success(`Deployed via ${data.provider}`);
      } else if (data.status === "failed") {
        toast.error(data.error || `Deploy failed (${data.provider})`);
      } else {
        toast.info(`Status: ${data.status}`);
      }
      setActiveId(data.id);
      setActive(data);
      await refreshHistory();
      onProjectUpdated?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Deployment failed");
    } finally {
      setDeploying(false);
    }
  };

  const togglePublishOnSave = async () => {
    setSavingToggle(true);
    const next = !publishOnSave;
    try {
      await setPublishOnSave(projectId, next);
      setPublishOnSaveState(next);
      toast.success(next ? "Auto-publish on save: ON" : "Auto-publish on save: OFF");
    } catch {
      toast.error("Could not update setting");
    } finally {
      setSavingToggle(false);
    }
  };

  const onCancel = async (id) => {
    try {
      await cancelDeployment(projectId, id);
      toast.success("Cancelled");
      await refreshHistory();
      await refreshActive(id);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Cancel failed");
    }
  };

  const liveUrl = useMemo(
    () => (project?.deployed && project?.deploy_slug ? deployUrl(project.deploy_slug) : null),
    [project]
  );

  return (
    <div className="flex flex-col h-full surface-0" data-testid="deployment-panel">
      {/* ─────────── Header: cinematic glass with status pulse ─────────── */}
      <div className="shrink-0 relative">
        {/* Subtle accent line at the top — pulses with active deploy status */}
        <div
          className="absolute inset-x-0 top-0 h-px transition-colors duration-500"
          style={{
            background: active
              ? (STATUS_STYLE[active.status]?.accent || "rgba(255,255,255,0.06)")
              : "rgba(255,255,255,0.06)",
            boxShadow: active && active.status === "building"
              ? "0 0 18px 0 rgba(245,158,11,0.45)"
              : active && active.status === "deployed"
              ? "0 0 18px 0 rgba(94,234,212,0.45)"
              : "none",
          }}
        />
        <div className="glass-1 border-0 border-b border-white/5 px-4 sm:px-5 py-3 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3 min-w-0">
            <span className="h-9 w-9 rounded-xl surface-2 flex items-center justify-center shrink-0"
              style={{ boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.06)" }}
            >
              <Rocket size={14} className="text-white/85" />
            </span>
            <div className="min-w-0">
              <div className="text-[14px] font-semibold tracking-tight">Deployment</div>
              <div className="nxt-overline mt-0.5">// publish your project to a public URL</div>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              disabled={deploying}
              className="surface-1 border border-white/8 rounded-lg text-[11.5px] mono px-2.5 py-1.5 text-zinc-300 outline-none focus:border-white/25 transition-colors"
              data-testid="deploy-provider-select"
            >
              {providers.map((p) => (
                <option key={p.name} value={p.name} className="surface-1" disabled={!p.configured && p.requires_token_env}>
                  {p.name}{p.configured ? "" : (p.requires_token_env ? ` — needs ${p.requires_token_env}` : " — not implemented")}
                </option>
              ))}
            </select>
            <label
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer transition-all ${
                publishOnSave
                  ? "bg-emerald-500/10 border border-emerald-400/30 text-emerald-200"
                  : "surface-1 border border-white/8 text-zinc-400 hover:text-white"
              }`}
              title="When ON, every accepted AI change auto-deploys via internal provider."
              data-testid="publish-on-save-toggle"
            >
              <Zap size={11} className={publishOnSave ? "text-emerald-300" : ""} />
              <span className="mono text-[10px] tracking-[0.20em] uppercase">auto-publish</span>
              <input type="checkbox" checked={publishOnSave} onChange={togglePublishOnSave} disabled={savingToggle} className="sr-only" />
              <span className={`inline-block w-7 h-4 relative rounded-full transition ${publishOnSave ? "bg-emerald-500/40" : "bg-white/10"}`}>
                <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition ${publishOnSave ? "left-3.5" : "left-0.5"}`} />
              </span>
            </label>
            {liveUrl && (
              <a
                href={liveUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11.5px] font-medium border border-emerald-400/30 text-emerald-300 hover:bg-emerald-500/10 hover:border-emerald-400/50 transition-all"
                data-testid="deploy-panel-live-link"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 nxt-pulse" />
                Live <ExternalLink size={11} />
              </a>
            )}
            <button
              onClick={onDeploy}
              disabled={deploying}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-[12px] font-semibold bg-white text-[#1F1F23] hover:bg-white/95 transition-all shadow-[0_6px_20px_-8px_rgba(255,255,255,0.45)] hover:-translate-y-0.5 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0"
              data-testid="deploy-now-button"
            >
              {deploying ? (
                <><Loader2 size={11} className="animate-spin" /> Deploying</>
              ) : project?.deployed ? (
                <><RefreshCw size={11} /> Redeploy</>
              ) : (
                <><Rocket size={11} /> Deploy now</>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 grid grid-cols-12 min-h-0">
        {/* ─────────── History sidebar (quiet, no hard borders) ─────────── */}
        <aside className="col-span-4 surface-1 border-r border-white/5 overflow-y-auto">
          <div className="px-3 py-2.5 nxt-overline border-b border-white/5 sticky top-0 surface-1/95 backdrop-blur z-10">// history</div>
          {loading ? (
            <div className="p-3 text-zinc-500 text-xs mono">loading…</div>
          ) : history.length === 0 ? (
            <div className="p-4 text-zinc-500 text-[12px] leading-relaxed">
              No deployments yet. Click <span className="text-white/85 font-medium">Deploy now</span> to publish.
            </div>
          ) : (
            history.map((d) => {
              const isActive = activeId === d.id;
              const s = STATUS_STYLE[d.status] || STATUS_STYLE.pending;
              return (
                <button
                  key={d.id}
                  onClick={() => setActiveId(d.id)}
                  className={`relative w-full text-left px-3 py-2.5 transition-colors ${
                    isActive ? "bg-white/[0.06]" : "hover:bg-white/[0.03]"
                  }`}
                  data-testid={`deployment-history-${d.id}`}
                >
                  {isActive && (
                    <span
                      className="absolute left-0 top-2 bottom-2 w-[2px] rounded-r"
                      style={{ background: s.accent }}
                    />
                  )}
                  <div className="flex items-center justify-between">
                    <StatusBadge status={d.status} />
                    <span className="mono text-[10px] tracking-wider text-white/30">
                      {new Date(d.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                  <div className="mt-1 text-[12px] text-zinc-300 truncate mono">
                    {d.slug || d.id.slice(0, 8)}
                  </div>
                  <div className="mt-0.5 mono text-[10px] tracking-[0.18em] uppercase text-white/30">
                    via {d.provider}
                  </div>
                </button>
              );
            })
          )}
        </aside>

        {/* ─────────── Detail / cinematic terminal stream ─────────── */}
        <section className="col-span-8 overflow-y-auto" data-testid="deployment-detail">
          {!active ? (
            <div className="p-8 h-full flex items-center justify-center">
              <div className="text-center max-w-sm">
                <span className="inline-flex h-12 w-12 rounded-2xl items-center justify-center mb-4 surface-2"
                  style={{ boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.06)" }}
                >
                  <Rocket size={18} className="text-white/55" />
                </span>
                <div className="text-[14px] text-white/85 mb-1.5 font-medium">Select a deployment</div>
                <div className="text-[12px] text-white/40 leading-relaxed">Pick a build from the timeline on the left to view its log stream.</div>
              </div>
            </div>
          ) : (
            <div className="p-4 sm:p-5 space-y-4">
              {/* Active deployment header */}
              <div className="flex items-start justify-between flex-wrap gap-3">
                <div>
                  <StatusBadge status={active.status} />
                  <div className="mt-2 text-[11px] mono text-white/40 flex items-center gap-3 flex-wrap">
                    <span className="flex items-center gap-1.5"><Clock size={10} /> started {new Date(active.started_at).toLocaleString()}</span>
                    {active.completed_at && (
                      <span className="flex items-center gap-1.5"><Check size={10} /> completed {new Date(active.completed_at).toLocaleString()}</span>
                    )}
                    <span className="flex items-center gap-1.5"><Server size={10} /> {active.provider}</span>
                  </div>
                </div>
                {(active.status === "pending" || active.status === "building") && (
                  <button
                    onClick={() => onCancel(active.id)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11.5px] border border-rose-400/30 text-rose-300 hover:bg-rose-500/10 transition-all"
                  >
                    <X size={11} /> Cancel
                  </button>
                )}
                {active.status === "failed" && (
                  <button
                    onClick={() => askAIToFix(active.id)}
                    disabled={fixBusy}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11.5px] font-medium bg-amber-500/12 border border-amber-400/40 text-amber-200 hover:bg-amber-500/22 transition-all"
                    data-testid="deploy-ask-ai-to-fix"
                    title="Bundle deploy logs + relevant config files to the DevOps agent"
                  >
                    {fixBusy ? <Loader2 size={11} className="animate-spin" /> : <Bot size={11} />}
                    Ask AI to fix
                  </button>
                )}
              </div>

              {/* Step timeline — cinematic, derived from log stream */}
              <div className="rounded-xl surface-1 border border-white/5">
                <StepTimeline logs={active.logs || []} status={active.status} />
              </div>

              {/* Public URL banner */}
              {active.public_url && (
                <div
                  className="rounded-xl p-3 flex items-center justify-between gap-3 flex-wrap"
                  style={{
                    background: "linear-gradient(180deg, rgba(94,234,212,0.06) 0%, rgba(36,36,40,0.6) 100%)",
                    border: "1px solid rgba(94,234,212,0.18)",
                  }}
                >
                  <div className="min-w-0">
                    <div className="nxt-overline mb-1">// public url</div>
                    <div className="mono text-[13px] truncate text-white/90">{active.public_url}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => { navigator.clipboard.writeText(active.public_url); toast.success("Copied"); }}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11.5px] surface-2 border border-white/8 hover:border-white/20 transition-all text-white/85"
                      data-testid="copy-public-url"
                    >
                      <Copy size={11} /> Copy
                    </button>
                    <a
                      href={active.public_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11.5px] font-semibold bg-white text-[#1F1F23] hover:bg-white/95 transition-all"
                    >
                      Open <ExternalLink size={11} />
                    </a>
                  </div>
                </div>
              )}

              {/* Error banner */}
              {active.error && (
                <div
                  className="rounded-xl p-3"
                  style={{
                    background: "linear-gradient(180deg, rgba(244,114,182,0.05) 0%, rgba(36,36,40,0.55) 100%)",
                    border: "1px solid rgba(244,114,182,0.30)",
                  }}
                >
                  <div className="flex items-center gap-2 text-rose-300 text-[13px]">
                    <AlertTriangle size={13} /> {active.error}
                  </div>
                </div>
              )}

              {/* Terminal log stream — the cinematic centerpiece */}
              <LogStream
                active={active}
                onRefresh={() => refreshActive(active.id)}
              />
            </div>
          )}
        </section>
      </div>

      {fixProposal && (
        <div
          className="fixed inset-0 z-50 bg-graphite-scrim-strong flex items-center justify-center p-3 sm:p-6"
          onClick={() => !applyBusy && setFixProposal(null)}
          data-testid="deploy-auto-fix-modal"
        >
          <div
            className="rounded-2xl surface-2 w-[920px] max-w-full max-h-[92vh] flex flex-col"
            style={{ boxShadow: "var(--elev-3)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-white/5">
              <div className="flex items-center gap-2 min-w-0 flex-wrap">
                <Bot size={14} className="text-amber-300 shrink-0" />
                <div className="text-sm font-medium truncate">DevOps fix proposal</div>
                <span
                  className={`mono text-[10px] tracking-wider px-1.5 py-0.5 border rounded-sm shrink-0 ${
                    fixProposal.confidence === "high"
                      ? "text-emerald-300 border-emerald-400/30"
                      : fixProposal.confidence === "low"
                      ? "text-amber-300 border-amber-400/30"
                      : "text-zinc-300 border-white/10"
                  }`}
                >
                  {fixProposal.confidence?.toUpperCase()} CONFIDENCE
                </span>
                <span
                  className="mono text-[10px] tracking-wider px-1.5 py-0.5 border rounded-sm shrink-0 text-zinc-300 border-white/10"
                  data-testid="deploy-fix-failing-step"
                >
                  STEP · {(fixProposal.failing_step || "unknown").toUpperCase()}
                </span>
                {fixProposal.requires_approval && (
                  <span
                    className="mono text-[10px] tracking-wider px-1.5 py-0.5 border rounded-sm shrink-0 text-red-300 border-red-400/30"
                    data-testid="deploy-fix-requires-approval"
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
                <p className="text-sm text-zinc-200 leading-relaxed" data-testid="deploy-fix-diagnosis">
                  {fixProposal.diagnosis}
                </p>
              </div>
              <div>
                <div className="nxt-overline mb-1">// proposed fix</div>
                <p className="text-sm text-zinc-300 leading-relaxed" data-testid="deploy-fix-summary">
                  {fixProposal.fix_summary || "(no summary)"}
                </p>
                {fixProposal.next_check && (
                  <p className="text-xs text-zinc-500 mt-2 leading-relaxed">
                    <span className="text-emerald-400 mono">›</span> {fixProposal.next_check}
                  </p>
                )}
              </div>
              <div>
                <div className="nxt-overline mb-2">
                  // file/config changes ({fixProposal.files.length})
                </div>
                <div className="space-y-2" data-testid="deploy-fix-files">
                  {fixProposal.files.length === 0 ? (
                    <p className="text-xs text-zinc-500 mono">
                      The DevOps agent did not propose file edits. The diagnosis above may
                      require an env-var or provider-side action — see "next" line.
                    </p>
                  ) : fixProposal.files.map((f, i) => (
                    <details
                      key={`${f.path}-${i}`}
                      className="border border-white/5 rounded-lg surface-1 overflow-hidden"
                    >
                      <summary className="cursor-pointer px-3 py-2 flex items-center gap-2 text-xs mono hover:bg-white/[0.03] transition-colors">
                        <span className="text-zinc-300 truncate flex-1">{f.path}</span>
                        <span className="text-emerald-300">+{f.diff?.added || 0}</span>
                        <span className="text-red-300">−{f.diff?.removed || 0}</span>
                        <ChevronRight size={11} className="text-zinc-500" />
                      </summary>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-white/5 border-t border-white/5">
                        <pre className="surface-recessed p-2 mono text-[11px] text-zinc-500 overflow-auto max-h-[260px] whitespace-pre-wrap">
                          <span className="block nxt-overline text-red-300 mb-1">// before</span>
                          {f.before || "(new file)"}
                        </pre>
                        <pre className="surface-recessed p-2 mono text-[11px] text-zinc-200 overflow-auto max-h-[260px] whitespace-pre-wrap">
                          <span className="block nxt-overline text-emerald-300 mb-1">// after</span>
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
                  data-testid="deploy-fix-discard"
                >
                  Discard
                </button>
                <button
                  onClick={applyFix}
                  disabled={applyBusy || fixProposal.files.length === 0}
                  className="nxt-btn-primary !py-2 !px-4"
                  data-testid="deploy-fix-apply"
                >
                  {applyBusy ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <ShieldCheck size={13} />
                  )}{" "}
                  Apply &amp; redeploy
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


/* ============================================================================
   LogStream — cinematic terminal centerpiece
   • Auto-scrolls to bottom while active
   • Soft fade at the top so old lines feel like they recede
   • Top bar shows step + run-time + live "Tailing" indicator
   • Status pulse on the run dot for building state
   ============================================================================ */
function LogStream({ active, onRefresh }) {
  const scrollRef = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const logs = active?.logs || [];
  const isLive = active?.status === "pending" || active?.status === "building";

  // Auto-scroll to bottom on new logs
  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return;
    const el = scrollRef.current;
    el.scrollTop = el.scrollHeight;
  }, [logs.length, autoScroll]);

  // Detect user scroll-up → pause autoscroll
  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    setAutoScroll(atBottom);
  };

  // Compute elapsed time
  const elapsed = useMemo(() => {
    if (!active?.started_at) return "—";
    const start = new Date(active.started_at).getTime();
    const end = active?.completed_at ? new Date(active.completed_at).getTime() : Date.now();
    const ms = Math.max(0, end - start);
    const s = Math.floor(ms / 1000);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60); const r = s % 60;
    return `${m}m ${String(r).padStart(2, "0")}s`;
  }, [active?.started_at, active?.completed_at, active?.status, logs.length]);

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        background: "linear-gradient(180deg, var(--surface-1) 0%, var(--surface-recessed) 100%)",
        border: "1px solid rgba(255,255,255,0.05)",
        boxShadow: "var(--elev-1)",
      }}
    >
      {/* Stream header */}
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-white/5">
        <div className="flex items-center gap-2.5">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-rose-400/70" />
            <span className="h-2 w-2 rounded-full bg-amber-400/70" />
            <span className="h-2 w-2 rounded-full bg-emerald-400/70" />
          </span>
          <span className="mono text-[10.5px] tracking-[0.22em] uppercase text-white/55">
            build · log stream
          </span>
        </div>
        <div className="flex items-center gap-2.5">
          {isLive && (
            <span className="inline-flex items-center gap-1.5 mono text-[10px] tracking-[0.22em] uppercase text-amber-200">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400 nxt-pulse-warm" />
              Tailing · {elapsed}
            </span>
          )}
          {!isLive && (
            <span className="mono text-[10px] tracking-[0.22em] uppercase text-white/35">
              {logs.length} lines · {elapsed}
            </span>
          )}
          <button
            onClick={onRefresh}
            className="rail-btn"
            style={{ width: 28, height: 28 }}
            title="Refresh logs"
            data-testid="deploy-refresh-logs"
          >
            <RefreshCw size={11} />
          </button>
        </div>
      </div>

      {/* Stream body */}
      <div className="relative">
        {/* Soft top fade — old lines recede */}
        <div
          className="absolute inset-x-0 top-0 h-8 pointer-events-none z-10"
          style={{
            background: "linear-gradient(180deg, var(--surface-1) 0%, rgba(36,36,40,0) 100%)",
          }}
        />
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="max-h-[360px] min-h-[160px] overflow-y-auto py-2"
          data-testid="deployment-logs"
        >
          {logs.length === 0 ? (
            <div className="px-4 py-6 text-center">
              <div className="mono text-[11px] tracking-[0.22em] uppercase text-white/30">
                {isLive ? "Waiting for first log line…" : "No logs available"}
              </div>
            </div>
          ) : (
            logs.map((l, idx) => (
              <LogLine key={idx} entry={l} index={idx} isLast={idx === logs.length - 1} />
            ))
          )}
        </div>
        {/* Resume-tail floater when user scrolled up */}
        {!autoScroll && isLive && (
          <button
            onClick={() => { setAutoScroll(true); if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }}
            className="absolute bottom-2 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10.5px] mono uppercase tracking-[0.22em] surface-3 border border-white/10 text-white/85 hover:text-white shadow-[0_8px_24px_-10px_rgba(0,0,0,0.6)] transition-all"
            data-testid="deploy-resume-tail"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
            Resume tail
          </button>
        )}
      </div>
    </div>
  );
}
