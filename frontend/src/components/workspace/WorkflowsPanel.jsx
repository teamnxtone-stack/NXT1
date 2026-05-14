/**
 * Track B — Workflows Panel (durable, LangGraph-backed).
 *
 * Shows queued / running / waiting / completed / failed workflows with
 * resume and cancel actions.
 */
import { useEffect, useState, useCallback } from "react";
import { listWorkflows, resumeWorkflow, cancelWorkflow, getWorkflow } from "@/lib/api";
import { Workflow, Clock, Loader2, CheckCircle2, AlertTriangle, XCircle, ChevronRight, PlayCircle, X } from "lucide-react";

const STATUS_META = {
  queued:    { label: "Queued",    icon: Clock,        color: "#94a3b8" },
  running:   { label: "Running",   icon: Loader2,      color: "#22d3ee" },
  waiting:   { label: "Waiting",   icon: PlayCircle,   color: "#f59e0b" },
  completed: { label: "Completed", icon: CheckCircle2, color: "#10b981" },
  failed:    { label: "Failed",    icon: AlertTriangle, color: "#ef4444" },
  cancelled: { label: "Cancelled", icon: XCircle,      color: "#64748b" },
};

const STATUSES = ["all", "queued", "running", "waiting", "completed", "failed", "cancelled"];

export default function WorkflowsPanel({ projectId = null }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params = filter !== "all" ? { status: filter } : {};
      if (projectId) params.project_id = projectId;
      const { data } = await listWorkflows(params);
      setItems(data.items || []);
    } catch (e) {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [filter, projectId]);

  useEffect(() => { refresh(); }, [refresh]);
  // Poll every 4s while there are non-terminal items
  useEffect(() => {
    const nonTerminal = items.some((i) =>
      ["queued", "running", "waiting"].includes(i.status));
    if (!nonTerminal) return;
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [items, refresh]);

  const counts = STATUSES.reduce((acc, s) => {
    acc[s] = s === "all"
      ? items.length
      : items.filter((i) => i.status === s).length;
    return acc;
  }, {});

  const handleResume = async (wfId, approval = true) => {
    setBusy(wfId);
    try {
      await resumeWorkflow(wfId, approval);
      await refresh();
      if (selected?.workflow_id === wfId) {
        const { data } = await getWorkflow(wfId);
        setSelected(data);
      }
    } finally { setBusy(null); }
  };

  const handleCancel = async (wfId) => {
    setBusy(wfId);
    try {
      await cancelWorkflow(wfId);
      await refresh();
    } catch {
      // ignore — already terminal
    } finally { setBusy(null); }
  };

  return (
    <div data-testid="workflows-panel" className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <Workflow className="w-4 h-4" style={{ color: "#22d3ee" }} />
            <span className="mono text-[10px] tracking-[0.30em] uppercase"
                  style={{ color: "var(--nxt-fg-faint)" }}>
              Durable Workflows · LangGraph
            </span>
          </div>
          <p className="text-[13px] max-w-[560px] leading-relaxed"
             style={{ color: "var(--nxt-fg-dim)" }}>
            Long-running agent pipelines (planner → architect → coder → tester → debugger → deployer)
            that persist across disconnects and pause for human approval before risky steps.
          </p>
        </div>
        <button
          onClick={refresh}
          data-testid="workflows-refresh"
          className="text-[11px] px-3 py-1.5 rounded-full transition"
          style={{
            color: "var(--nxt-fg-dim)",
            background: "var(--nxt-surface-hi)",
            border: "1px solid var(--nxt-border)",
          }}
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {/* Status filters */}
      <div className="flex flex-wrap gap-1.5" data-testid="workflows-filters">
        {STATUSES.map((s) => {
          const meta = s === "all" ? { label: "All", color: "var(--nxt-fg)" } : STATUS_META[s];
          return (
            <button
              key={s}
              onClick={() => setFilter(s)}
              data-testid={`wf-filter-${s}`}
              className="text-[11px] px-2.5 py-1 rounded-full transition"
              style={{
                background: filter === s
                  ? `${meta.color}22`
                  : "var(--nxt-surface-hi)",
                color: filter === s ? meta.color : "var(--nxt-fg-dim)",
                border: `1px solid ${filter === s ? meta.color : "var(--nxt-border)"}`,
              }}
            >
              {meta.label} · {counts[s] || 0}
            </button>
          );
        })}
      </div>

      {/* Items */}
      <div className="space-y-2">
        {items.length === 0 && !loading && (
          <div className="rounded-xl p-6 text-center border"
               style={{ borderColor: "var(--nxt-border)" }}
               data-testid="workflows-empty">
            <Workflow className="w-6 h-6 mx-auto mb-2 opacity-30"
                      style={{ color: "var(--nxt-fg-dim)" }} />
            <div className="text-[13px]" style={{ color: "var(--nxt-fg-dim)" }}>
              No workflows yet — start a build to see the pipeline here.
            </div>
          </div>
        )}
        {items.map((w) => {
          const meta = STATUS_META[w.status] || STATUS_META.queued;
          const Icon = meta.icon;
          const isOpen = selected?.workflow_id === w.workflow_id;
          const phaseCount = (w.history || []).length;
          return (
            <div
              key={w.workflow_id}
              data-testid={`wf-item-${w.workflow_id}`}
              className="rounded-xl border overflow-hidden transition-all"
              style={{
                borderColor: isOpen ? meta.color : "var(--nxt-border)",
                background: "var(--nxt-surface)",
              }}
            >
              <button
                onClick={() => setSelected(isOpen ? null : w)}
                className="w-full text-left px-4 py-3 flex items-center gap-3"
                data-testid={`wf-toggle-${w.workflow_id}`}
              >
                <Icon
                  className={`w-4 h-4 flex-shrink-0 ${w.status === "running" ? "animate-spin" : ""}`}
                  style={{ color: meta.color }}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[13px] font-medium truncate"
                          style={{ color: "var(--nxt-fg)" }}>
                      {w.prompt || "(no prompt)"}
                    </span>
                    <span
                      className="mono text-[9px] px-1.5 py-0.5 rounded uppercase"
                      style={{ color: meta.color, background: `${meta.color}1a` }}
                    >
                      {meta.label}
                    </span>
                  </div>
                  <div className="mono text-[10px] flex items-center gap-3"
                       style={{ color: "var(--nxt-fg-faint)" }}>
                    <span>phase: {w.current_phase}</span>
                    <span>steps: {phaseCount}</span>
                    <span>attempts: {w.attempts || 0}</span>
                    {w.requires_approval && (
                      <span style={{ color: "#f59e0b" }}>· awaits approval</span>
                    )}
                  </div>
                </div>
                <ChevronRight
                  className="w-3.5 h-3.5 transition-transform"
                  style={{
                    color: "var(--nxt-fg-faint)",
                    transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
                  }}
                />
              </button>

              {isOpen && (
                <div className="px-4 pb-4 pt-1 border-t"
                     style={{ borderColor: "var(--nxt-border)" }}>
                  <div className="space-y-1.5 mt-3" data-testid={`wf-history-${w.workflow_id}`}>
                    {(w.history || []).map((h, i) => (
                      <div key={i} className="flex items-start gap-2 text-[11px]">
                        <span
                          className="mono uppercase tracking-wider px-1.5 py-0.5 rounded flex-shrink-0"
                          style={{
                            background: "rgba(255,255,255,0.04)",
                            color: agentColor(h.agent),
                            fontSize: "9px",
                          }}
                        >
                          {h.agent}
                        </span>
                        <span style={{ color: "var(--nxt-fg-dim)" }}
                              className="flex-1">{h.message}</span>
                        <span className="mono opacity-50"
                              style={{ color: "var(--nxt-fg-faint)", fontSize: "9px" }}>
                          {h.status}
                        </span>
                      </div>
                    ))}
                  </div>
                  {w.error && (
                    <div
                      className="mt-3 text-[11px] p-2 rounded"
                      style={{ background: "rgba(239,68,68,0.08)", color: "#fca5a5" }}
                      data-testid={`wf-error-${w.workflow_id}`}
                    >
                      {w.error}
                    </div>
                  )}
                  {/* Actions */}
                  <div className="mt-3 flex gap-2">
                    {w.status === "waiting" && (
                      <>
                        <button
                          onClick={() => handleResume(w.workflow_id, true)}
                          disabled={busy === w.workflow_id}
                          data-testid={`wf-approve-${w.workflow_id}`}
                          className="text-[11px] px-3 py-1.5 rounded-full"
                          style={{
                            color: "#10b981",
                            background: "rgba(16,185,129,0.12)",
                            border: "1px solid rgba(16,185,129,0.3)",
                          }}
                        >
                          {busy === w.workflow_id ? "Approving..." : "Approve & deploy"}
                        </button>
                        <button
                          onClick={() => handleResume(w.workflow_id, false)}
                          disabled={busy === w.workflow_id}
                          data-testid={`wf-deny-${w.workflow_id}`}
                          className="text-[11px] px-3 py-1.5 rounded-full"
                          style={{
                            color: "var(--nxt-fg-dim)",
                            background: "var(--nxt-surface-hi)",
                            border: "1px solid var(--nxt-border)",
                          }}
                        >
                          Cancel deploy
                        </button>
                      </>
                    )}
                    {!["completed", "failed", "cancelled"].includes(w.status) && (
                      <button
                        onClick={() => handleCancel(w.workflow_id)}
                        disabled={busy === w.workflow_id}
                        data-testid={`wf-cancel-${w.workflow_id}`}
                        className="text-[11px] px-3 py-1.5 rounded-full ml-auto flex items-center gap-1"
                        style={{
                          color: "#ef4444",
                          background: "rgba(239,68,68,0.08)",
                          border: "1px solid rgba(239,68,68,0.2)",
                        }}
                      >
                        <X className="w-3 h-3" /> Cancel
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function agentColor(agent) {
  const c = {
    planner: "#60a5fa",
    architect: "#a78bfa",
    coder: "#22d3ee",
    tester: "#10b981",
    debugger: "#f59e0b",
    devops: "#ec4899",
  };
  return c[agent] || "#94a3b8";
}
