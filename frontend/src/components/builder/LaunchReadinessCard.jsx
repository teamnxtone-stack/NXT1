/**
 * LaunchReadinessCard — surfaces the ProductAgent + readiness data inline in
 * the OverviewPanel. Shows score, blockers, missing env vars, suggested next
 * actions, and an "Ask ProductAgent what to do next" prompt that produces a
 * structured plan with personas / MVP features / api routes / milestones.
 */
import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Target,
  Wand2,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { generateProductPlan } from "@/lib/api";

const STATUS_META = {
  pass: { Icon: CheckCircle2, color: "text-emerald-300", bg: "bg-emerald-500/5", border: "border-emerald-400/20" },
  warn: { Icon: AlertTriangle, color: "text-amber-300", bg: "bg-amber-500/5", border: "border-amber-400/20" },
  fail: { Icon: XCircle, color: "text-red-300", bg: "bg-red-500/5", border: "border-red-400/20" },
  skip: { Icon: CheckCircle2, color: "text-zinc-500", bg: "bg-white/[0.02]", border: "border-white/10" },
};

export default function LaunchReadinessCard({
  projectId,
  readiness,
  project,
  onGoTab,
  onSendChat,
}) {
  const [expanded, setExpanded] = useState(false);
  const [planBusy, setPlanBusy] = useState(false);
  const [plan, setPlan] = useState(null);
  const [briefDraft, setBriefDraft] = useState("");
  const [showBrief, setShowBrief] = useState(false);

  if (!readiness) {
    return (
      <section className="px-4 sm:px-6 py-5 border-b border-white/5">
        <div className="flex items-center gap-2 text-zinc-500 text-sm">
          <Loader2 size={13} className="animate-spin" />
          Loading launch readiness…
        </div>
      </section>
    );
  }

  const fails = (readiness.checks || []).filter((c) => c.status === "fail");
  const warns = (readiness.checks || []).filter((c) => c.status === "warn");
  const passes = (readiness.checks || []).filter((c) => c.status === "pass");
  const missingEnvCheck = (readiness.checks || []).find((c) => c.id === "env_filled");

  const askProductAgent = async () => {
    const brief = (briefDraft || project?.description || project?.name || "").trim();
    if (!brief) {
      toast.error("Add a short description first.");
      setShowBrief(true);
      return;
    }
    setPlanBusy(true);
    try {
      const { data } = await generateProductPlan(projectId, brief);
      setPlan(data.plan || {});
      toast.success("ProductAgent has a plan ready.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "ProductAgent failed");
    } finally {
      setPlanBusy(false);
    }
  };

  return (
    <section
      className="px-4 sm:px-6 py-5 border-b border-white/5"
      data-testid="launch-readiness-card"
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="nxt-overline">// productagent · launch readiness</div>
          <div className="text-sm text-zinc-400 mt-0.5">
            {fails.length === 0 && warns.length === 0
              ? "All checks pass. You're cleared for launch."
              : fails.length > 0
                ? `${fails.length} blocker${fails.length === 1 ? "" : "s"} to clear before shipping.`
                : `${warns.length} warning${warns.length === 1 ? "" : "s"} — non-blocking.`}
          </div>
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="nxt-btn !py-1.5 !px-3 text-[11px]"
          data-testid="readiness-expand-toggle"
        >
          {expanded ? "Hide" : "View"} {readiness.checks?.length || 0} checks
          {expanded ? (
            <ChevronUp size={11} className="ml-1" />
          ) : (
            <ChevronDown size={11} className="ml-1" />
          )}
        </button>
      </div>

      {/* Always-visible blockers (fails + warns) for at-a-glance focus */}
      {(fails.length > 0 || warns.length > 0) && (
        <div className="space-y-1.5 mb-3" data-testid="readiness-blockers">
          {[...fails, ...warns].slice(0, 4).map((c) => {
            const m = STATUS_META[c.status] || STATUS_META.skip;
            return (
              <div
                key={c.id}
                className={`flex items-start gap-2.5 px-3 py-2 border ${m.border} ${m.bg} rounded-sm`}
              >
                <m.Icon size={13} className={`${m.color} mt-0.5 shrink-0`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white">{c.label}</div>
                  <div className="text-[12px] text-zinc-500 mt-0.5 truncate">
                    {c.detail}
                  </div>
                </div>
                {c.id === "env_filled" && (
                  <button
                    onClick={() => onGoTab?.("env")}
                    className="text-[11px] mono text-zinc-400 hover:text-white shrink-0"
                  >
                    fix →
                  </button>
                )}
                {c.id === "deployed" && (
                  <button
                    onClick={() => onGoTab?.("deploy")}
                    className="text-[11px] mono text-zinc-400 hover:text-white shrink-0"
                  >
                    deploy →
                  </button>
                )}
                {c.id === "domain" && (
                  <button
                    onClick={() => onGoTab?.("domains")}
                    className="text-[11px] mono text-zinc-400 hover:text-white shrink-0"
                  >
                    add →
                  </button>
                )}
                {c.id === "runtime_alive" && (
                  <button
                    onClick={() => onGoTab?.("runtime")}
                    className="text-[11px] mono text-zinc-400 hover:text-white shrink-0"
                  >
                    start →
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Expanded full check list */}
      {expanded && (
        <div className="space-y-1 mb-3" data-testid="readiness-all-checks">
          {(readiness.checks || []).map((c) => {
            const m = STATUS_META[c.status] || STATUS_META.skip;
            return (
              <div
                key={c.id}
                className="flex items-center gap-2.5 px-2.5 py-1.5 text-[13px]"
              >
                <m.Icon size={12} className={`${m.color} shrink-0`} />
                <span className="text-zinc-300 flex-1 truncate">{c.label}</span>
                <span className="mono text-[10px] text-zinc-500 truncate max-w-[40%]">
                  {c.detail}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Missing env vars pill */}
      {missingEnvCheck?.missing?.length > 0 && (
        <div
          className="flex items-center gap-2 flex-wrap px-3 py-2 border border-red-400/20 bg-red-500/5 rounded-sm mb-3"
          data-testid="readiness-missing-env"
        >
          <span className="mono text-[10px] tracking-wider text-red-300">
            MISSING ENV
          </span>
          {missingEnvCheck.missing.slice(0, 6).map((k) => (
            <span
              key={k}
              className="mono text-[11px] px-1.5 py-0.5 border border-red-400/30 text-red-200 rounded-sm"
            >
              {k}
            </span>
          ))}
          {missingEnvCheck.missing.length > 6 && (
            <span className="mono text-[11px] text-red-300/70">
              +{missingEnvCheck.missing.length - 6}
            </span>
          )}
        </div>
      )}

      {/* Ask ProductAgent — primary CTA */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={askProductAgent}
          disabled={planBusy}
          className="nxt-btn-primary !py-2 !px-3.5 text-[12px]"
          data-testid="ask-productagent-button"
        >
          {planBusy ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Wand2 size={13} />
          )}
          Ask ProductAgent what to do next
        </button>
        {!showBrief && (
          <button
            onClick={() => setShowBrief(true)}
            className="nxt-btn !py-2 !px-3 text-[11px]"
            data-testid="set-brief-button"
          >
            <Target size={11} /> Set brief
          </button>
        )}
        <button
          onClick={() => onSendChat?.("Review my project and tell me what to fix or build next.")}
          className="nxt-btn !py-2 !px-3 text-[11px]"
          data-testid="ask-chat-review-button"
        >
          Ask in chat
        </button>
      </div>

      {showBrief && (
        <div className="mt-3 nxt-fade-up">
          <textarea
            value={briefDraft}
            onChange={(e) => setBriefDraft(e.target.value)}
            placeholder="Describe what this product is — e.g. 'A booking SaaS for roofers with calendar sync and Stripe payments.'"
            rows={3}
            className="nxt-input resize-y w-full text-[13px]"
            data-testid="brief-input"
          />
          <div className="text-[11px] mono text-zinc-500 mt-1">
            ProductAgent will plan personas, MVP features, screens, API routes, data models and milestones from this brief.
          </div>
        </div>
      )}

      {/* AI plan output */}
      {plan && (
        <div
          className="mt-4 border border-white/10 bg-[#1F1F23] rounded-sm p-4 space-y-4 text-[13px]"
          data-testid="productagent-plan"
        >
          {plan.summary && (
            <div>
              <div className="nxt-overline mb-1">// summary</div>
              <p className="text-zinc-300 leading-relaxed">{plan.summary}</p>
            </div>
          )}
          {plan.user_personas?.length > 0 && (
            <PlanList title="Personas" items={plan.user_personas} />
          )}
          {plan.mvp_features?.length > 0 && (
            <div>
              <div className="nxt-overline mb-1.5">// mvp features</div>
              <div className="space-y-1.5">
                {plan.mvp_features.map((f, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 text-zinc-300"
                  >
                    <span
                      className={`mono text-[10px] tracking-wider px-1.5 py-0.5 border rounded-sm shrink-0 mt-0.5 ${
                        f.priority === "P0"
                          ? "text-red-300 border-red-400/30"
                          : f.priority === "P1"
                            ? "text-amber-300 border-amber-400/30"
                            : "text-emerald-300 border-emerald-400/30"
                      }`}
                    >
                      {f.priority || "P?"}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-white">{f.name}</div>
                      {f.why && (
                        <div className="text-[12px] text-zinc-500 mt-0.5">
                          {f.why}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => onSendChat?.(`Build the "${f.name}" feature: ${f.why || ""}`)}
                      className="text-[11px] mono text-emerald-300/80 hover:text-emerald-200 shrink-0"
                    >
                      build →
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
          {plan.screens?.length > 0 && (
            <PlanList
              title="Screens"
              items={plan.screens.map((s) => `${s.name}${s.purpose ? ` — ${s.purpose}` : ""}`)}
            />
          )}
          {plan.api_routes?.length > 0 && (
            <div>
              <div className="nxt-overline mb-1.5">// api routes</div>
              <div className="space-y-1">
                {plan.api_routes.map((r, i) => (
                  <div key={i} className="flex items-center gap-2 mono text-[12px]">
                    <span className="text-emerald-300 w-12 shrink-0">{r.method}</span>
                    <span className="text-zinc-200 truncate flex-1">{r.path}</span>
                    <span className="text-zinc-500 truncate max-w-[40%]">{r.purpose}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {plan.milestones?.length > 0 && (
            <div>
              <div className="nxt-overline mb-1.5">// milestones</div>
              <div className="space-y-2">
                {plan.milestones.map((m, i) => (
                  <div key={i} className="border-l border-emerald-400/30 pl-3">
                    <div className="text-white font-medium">{m.title}</div>
                    <ul className="text-[12px] text-zinc-400 mt-1 space-y-0.5 list-disc list-inside">
                      {(m.tasks || []).slice(0, 4).map((t, j) => (
                        <li key={j}>{t}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Quick stat ribbon */}
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <Stat label="passing" count={passes.length} tone="emerald" />
        <Stat label="warning" count={warns.length} tone="amber" />
        <Stat label="blocking" count={fails.length} tone="red" />
      </div>
    </section>
  );
}

function PlanList({ title, items }) {
  return (
    <div>
      <div className="nxt-overline mb-1.5">// {title.toLowerCase()}</div>
      <ul className="space-y-1 list-disc list-inside text-zinc-300">
        {items.slice(0, 6).map((it, i) => (
          <li key={i} className="text-[13px]">{it}</li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, count, tone }) {
  const colorMap = {
    emerald: "text-emerald-300 border-emerald-400/20 bg-emerald-500/5",
    amber: "text-amber-300 border-amber-400/20 bg-amber-500/5",
    red: "text-red-300 border-red-400/20 bg-red-500/5",
  };
  return (
    <div className={`px-2 py-2 border rounded-sm ${colorMap[tone]}`}>
      <div className="text-xl font-bold mono">{count}</div>
      <div className="text-[10px] mono tracking-[0.2em] uppercase opacity-80">
        {label}
      </div>
    </div>
  );
}
