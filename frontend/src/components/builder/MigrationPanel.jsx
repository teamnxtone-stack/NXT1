/**
 * MigrationPanel — analyses an imported project and produces a reconnect
 * plan: detected integrations + missing env vars + actionable steps.
 *
 * The goal: make moving an Emergent app into NXT1 a guided, 1-click flow.
 */
import { useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Cpu,
  Database,
  Github,
  Key,
  Loader2,
  PackageOpen,
  RefreshCw,
  Rocket,
  Sparkles,
} from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

const STATUS_STYLE = {
  ok:   "border-emerald-400/30 bg-emerald-500/[0.05] text-emerald-200",
  todo: "border-amber-400/30 bg-amber-500/[0.05] text-amber-200",
  info: "border-white/10 bg-white/[0.02] text-zinc-300",
};

const STATUS_DOT = {
  ok:   "bg-emerald-400",
  todo: "bg-amber-400",
  info: "bg-zinc-500",
};

const STEP_ICON = {
  github: Github,
  database: Database,
  deploy: Rocket,
  env: Key,
};

export default function MigrationPanel({ projectId, onOpenPanel, onSaveToGithub, onDeploy }) {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setRefreshing(true);
    try {
      const { data } = await api.get(`/projects/${projectId}/migration-plan`);
      setPlan(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't load plan");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (projectId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const runStepAction = async (step) => {
    const action = step.action;
    if (!action) return;
    if (action.type === "save_github") {
      onSaveToGithub?.();
    } else if (action.type === "deploy") {
      onDeploy?.(action.provider);
    } else if (action.type === "open_panel") {
      onOpenPanel?.(action.panel, action.payload);
    }
  };

  if (loading) {
    return (
      <div className="p-6 text-zinc-500 text-sm mono flex items-center gap-2">
        <Loader2 size={14} className="animate-spin" /> Analysing project…
      </div>
    );
  }

  if (!plan) return null;

  const todos = (plan.steps || []).filter((s) => s.status === "todo").length;
  const detected = plan.detected || [];

  return (
    <div className="flex flex-col h-full surface-recessed" data-testid="migration-panel">
      <div className="shrink-0 px-4 py-3 border-b border-white/5 flex items-center gap-3">
        <Sparkles size={14} className="text-emerald-300" />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium">Migration assistant</div>
          <div className="nxt-overline">
            // {detected.length} integration{detected.length === 1 ? "" : "s"} detected · {todos} step{todos === 1 ? "" : "s"} to go
          </div>
        </div>
        <button
          onClick={load}
          className="h-7 w-7 flex items-center justify-center rounded-full text-zinc-400 hover:text-white hover:bg-white/5 transition"
          data-testid="migration-refresh"
        >
          <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Detected integrations */}
        {detected.length > 0 && (
          <section>
            <h3 className="mono text-[10px] uppercase tracking-[0.28em] text-zinc-500 mb-2">
              // detected stack
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {detected.map((d) => (
                <span
                  key={d.kind}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-emerald-400/25 bg-emerald-500/[0.05] text-emerald-100 text-[11.5px]"
                  data-testid={`migration-detected-${d.kind}`}
                  title={d.action || ""}
                >
                  <Cpu size={10} className="opacity-70" />
                  {d.label}
                  <span className="text-emerald-300/50 mono">·{d.evidence_count}</span>
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Step-by-step plan */}
        {(plan.steps || []).length > 0 ? (
          <section>
            <h3 className="mono text-[10px] uppercase tracking-[0.28em] text-zinc-500 mb-2">
              // reconnect plan
            </h3>
            <div className="space-y-1.5">
              {plan.steps.map((s) => {
                const Icon = STEP_ICON[s.id] || PackageOpen;
                return (
                  <div
                    key={s.id}
                    className={`rounded-xl border p-3 ${STATUS_STYLE[s.status] || STATUS_STYLE.info}`}
                    data-testid={`migration-step-${s.id}`}
                  >
                    <div className="flex items-start gap-3">
                      <span className={`h-1.5 w-1.5 rounded-full mt-2 shrink-0 ${STATUS_DOT[s.status] || STATUS_DOT.info}`} />
                      <Icon size={14} className="mt-0.5 shrink-0 opacity-70" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-[13px] font-semibold text-white">{s.title}</span>
                          {s.status === "ok" && <CheckCircle2 size={12} className="text-emerald-300" />}
                        </div>
                        <p className="text-[12px] text-zinc-300 leading-relaxed mt-0.5">{s.hint}</p>
                        {Array.isArray(s.keys) && s.keys.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {s.keys.slice(0, 12).map((k) => (
                              <span key={k} className="px-1.5 py-0.5 rounded mono text-[10.5px] bg-graphite-scrim-soft text-zinc-300">
                                {k}
                              </span>
                            ))}
                            {s.keys.length > 12 && (
                              <span className="text-[10.5px] text-zinc-400">+{s.keys.length - 12} more</span>
                            )}
                          </div>
                        )}
                        {Array.isArray(s.missing) && s.missing.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {s.missing.map((k) => (
                              <span key={k} className="px-1.5 py-0.5 rounded mono text-[10.5px] bg-amber-500/15 text-amber-200 border border-amber-400/30">
                                {k}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      {s.status === "todo" && s.action && (
                        <button
                          onClick={() => runStepAction(s)}
                          className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-white text-black text-[11px] font-semibold hover:bg-zinc-200 transition"
                          data-testid={`migration-action-${s.id}`}
                        >
                          {s.action.type === "save_github" ? "Push" :
                           s.action.type === "deploy" ? "Deploy" : "Open"}
                          <ArrowRight size={10} />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ) : detected.length === 0 ? (
          <div className="rounded-2xl border border-white/8 surface-1 p-6 text-center">
            <AlertCircle size={20} className="mx-auto text-zinc-600 mb-2" />
            <div className="text-[13px] text-zinc-400">No migration steps detected.</div>
            <div className="text-[11.5px] text-zinc-600 mt-1">
              Either this project is brand new or its infrastructure is already reconnected.
            </div>
          </div>
        ) : null}

        {/* Missing env table */}
        {(plan.missing_env || []).length > 0 && (
          <section>
            <h3 className="mono text-[10px] uppercase tracking-[0.28em] text-zinc-500 mb-2">
              // missing env vars ({plan.missing_env.length})
            </h3>
            <div className="rounded-xl border border-white/8 surface-1 p-3">
              <div className="flex flex-wrap gap-1">
                {plan.missing_env.map((k) => (
                  <span key={k} className="px-2 py-0.5 rounded mono text-[11px] bg-amber-500/10 text-amber-200 border border-amber-400/20">
                    {k}
                  </span>
                ))}
              </div>
              <button
                onClick={() => onOpenPanel?.("env", { keys: plan.missing_env })}
                className="inline-flex items-center gap-1 mt-3 px-3 py-1.5 rounded-full bg-emerald-400 text-black text-[12px] font-semibold hover:bg-emerald-300 transition"
                data-testid="migration-open-env"
              >
                Set env vars <ArrowRight size={11} />
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
