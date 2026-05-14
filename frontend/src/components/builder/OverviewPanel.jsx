import { useEffect, useState } from "react";
import {
  Sparkles,
  Server,
  Rocket,
  Globe,
  Zap,
  ChevronRight,
  Loader2,
  CheckCircle2,
  Circle,
  Code2,
  Database,
  Cpu,
  Wand2,
} from "lucide-react";
import {
  getAnalysis,
  refreshAnalysis,
  runtimeStatus,
  listDomains,
  generatePageFromRoute,
  getReadiness,
} from "@/lib/api";
import { toast } from "sonner";
import LaunchReadinessCard from "./LaunchReadinessCard";

const METHOD_COLOR = {
  GET: "text-emerald-300 border-emerald-400/30",
  POST: "text-sky-300 border-sky-400/30",
  PUT: "text-amber-300 border-amber-400/30",
  PATCH: "text-amber-300 border-amber-400/30",
  DELETE: "text-red-300 border-red-400/30",
  ANY: "text-zinc-300 border-white/10",
};

function StatRow({ icon: Icon, label, value, status, accent, action, onAction, actionLabel }) {
  const statusColor =
    status === "ok"
      ? "text-emerald-300 bg-emerald-500/10 border-emerald-400/30"
      : status === "warn"
      ? "text-amber-300 bg-amber-500/10 border-amber-400/30"
      : status === "err"
      ? "text-red-300 bg-red-500/10 border-red-400/30"
      : "text-zinc-500 bg-white/5 border-white/10";
  return (
    <div className="flex items-center gap-3 sm:gap-4 px-4 py-4 hover:bg-white/[0.02] transition border-b border-white/5">
      <div className="h-9 w-9 rounded-sm bg-white/5 border border-white/10 flex items-center justify-center shrink-0">
        <Icon size={15} className="text-zinc-300" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-white truncate">{label}</div>
        <div className="text-xs text-zinc-500 mt-0.5 truncate">{value || "—"}</div>
      </div>
      {accent !== undefined && (
        <span
          className={`hidden sm:inline-flex items-center gap-1.5 px-2 py-1 border rounded-sm mono text-[10px] tracking-wider ${statusColor}`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              status === "ok"
                ? "bg-emerald-400 animate-pulse"
                : status === "warn"
                ? "bg-amber-400"
                : status === "err"
                ? "bg-red-400"
                : "bg-zinc-600"
            }`}
          />
          {accent}
        </span>
      )}
      {action && (
        <button
          onClick={onAction}
          className="nxt-btn !py-1.5 !px-2.5 sm:!px-3 text-[11px] shrink-0"
        >
          {actionLabel || "Open"} <ChevronRight size={11} />
        </button>
      )}
    </div>
  );
}

export default function OverviewPanel({
  projectId,
  project,
  onGoTab,
  onSendChat,
  onScaffoldBackend,
}) {
  const [analysis, setAnalysis] = useState(null);
  const [runtime, setRuntime] = useState(null);
  const [domains, setDomains] = useState([]);
  const [readiness, setReadiness] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadAll = async () => {
    try {
      const [a, r, d, rd] = await Promise.allSettled([
        getAnalysis(projectId),
        runtimeStatus(projectId),
        listDomains(projectId),
        getReadiness(projectId),
      ]);
      if (a.status === "fulfilled") setAnalysis(a.value.data);
      if (r.status === "fulfilled") setRuntime(r.value.data);
      if (d.status === "fulfilled") setDomains(d.value.data);
      if (rd.status === "fulfilled") setReadiness(rd.value.data);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    loadAll();
    const onFC = () => loadAll();
    window.addEventListener("nxt1:filesChanged", onFC);
    return () => window.removeEventListener("nxt1:filesChanged", onFC);
    /* eslint-disable-next-line */
  }, [projectId]);

  const refresh = async () => {
    setRefreshing(true);
    try {
      await refreshAnalysis(projectId);
      await loadAll();
      toast.success("Analysis refreshed");
    } catch {
      toast.error("Refresh failed");
    } finally {
      setRefreshing(false);
    }
  };

  const [genBusyKey, setGenBusyKey] = useState(null);

  const handleGenerateForRoute = async (route) => {
    const key = `${route.method}-${route.path}`;
    setGenBusyKey(key);
    try {
      const { data } = await generatePageFromRoute(projectId, {
        method: route.method,
        path: route.path,
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

  const filesCount = project?.files?.length ?? 0;
  const hasBackend = (project?.files || []).some((f) => f.path.startsWith("backend/"));
  const primaryDomain = domains.find((d) => d.is_primary) || domains[0];

  const runtimeAccent = runtime?.alive ? "RUNNING" : "STOPPED";
  const runtimeStatusKey = runtime?.alive ? "ok" : (hasBackend ? "warn" : "idle");

  const deployAccent = project?.deployed ? "LIVE" : "DRAFT";
  const deployStatusKey = project?.deployed ? "ok" : "idle";

  const domainAccent = primaryDomain
    ? primaryDomain.status === "verified"
      ? "VERIFIED"
      : "PENDING"
    : "NONE";
  const domainStatusKey = primaryDomain
    ? primaryDomain.status === "verified"
      ? "ok"
      : "warn"
    : "idle";

  return (
    <div className="flex flex-col h-full overflow-y-auto surface-recessed" data-testid="overview-panel">
      {/* Hero / quick prompt */}
      <div className="px-4 sm:px-6 py-6 border-b border-white/5">
        <div className="nxt-overline mb-2">// command center</div>
        <h2
          className="text-2xl sm:text-3xl font-bold tracking-tight"
          style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
        >
          {project?.name || "Project"}
        </h2>
        {analysis?.summary && (
          <p className="text-sm text-zinc-400 mt-1.5 leading-relaxed">{analysis.summary}</p>
        )}

        {readiness && (
          <div
            className="mt-4 flex items-center gap-3 flex-wrap"
            data-testid="overview-readiness"
          >
            <div className="flex items-center gap-2">
              <span className="nxt-overline">// launch readiness</span>
              <span
                className={`mono text-[12px] font-bold ${
                  readiness.score >= 80
                    ? "text-emerald-300"
                    : readiness.score >= 50
                    ? "text-amber-300"
                    : "text-red-300"
                }`}
                data-testid="readiness-score"
              >
                {readiness.score}/100
              </span>
            </div>
            <div className="h-1 flex-1 max-w-[260px] rounded-full bg-white/5 overflow-hidden">
              <div
                className={`h-full transition-all ${
                  readiness.score >= 80
                    ? "bg-emerald-400"
                    : readiness.score >= 50
                    ? "bg-amber-400"
                    : "bg-red-400"
                }`}
                style={{ width: `${readiness.score}%` }}
              />
            </div>
            {readiness.fail_count > 0 && (
              <span className="text-[11px] mono text-red-300">
                {readiness.fail_count} fail
              </span>
            )}
            {readiness.warn_count > 0 && (
              <span className="text-[11px] mono text-amber-300">
                {readiness.warn_count} warn
              </span>
            )}
          </div>
        )}

        <div className="mt-5 flex flex-wrap gap-2">
          <button
            onClick={() => onGoTab?.("chat")}
            className="nxt-btn-primary !py-2 !px-3.5"
            data-testid="overview-open-chat"
          >
            <Sparkles size={13} /> Ask AI
          </button>
          <button
            onClick={() => onGoTab?.("deploy")}
            className="nxt-btn !py-2 !px-3.5"
            data-testid="overview-deploy"
          >
            <Rocket size={13} /> Deploy
          </button>
          {!hasBackend && onScaffoldBackend && (
            <button
              onClick={() => onScaffoldBackend("fastapi")}
              className="nxt-btn !py-2 !px-3.5 text-emerald-300 border-emerald-400/30"
              data-testid="overview-scaffold-fastapi"
            >
              <Zap size={13} /> Add backend
            </button>
          )}
          <button
            onClick={refresh}
            disabled={refreshing}
            className="nxt-btn !py-2 !px-3.5"
            title="Re-analyse project"
            data-testid="overview-refresh-analysis"
          >
            {refreshing ? <Loader2 size={13} className="animate-spin" /> : <Cpu size={13} />}{" "}
            Re-analyse
          </button>
        </div>
      </div>

      {/* Quick stats: runtime / deploy / domain */}
      <div data-testid="overview-stats">
        <StatRow
          icon={Server}
          label="Backend runtime"
          value={
            runtime?.alive
              ? `${runtime.kind || "—"} · port ${runtime.port}`
              : hasBackend
              ? "stopped — start it from the Runtime tab"
              : "no backend yet"
          }
          accent={runtimeAccent}
          status={runtimeStatusKey}
          action
          onAction={() => onGoTab?.("runtime")}
          actionLabel="Runtime"
        />
        <StatRow
          icon={Rocket}
          label="Deployment"
          value={
            project?.deployed && project?.deploy_slug
              ? `Live · /api/deploy/${project.deploy_slug}`
              : "Not deployed"
          }
          accent={deployAccent}
          status={deployStatusKey}
          action
          onAction={() => onGoTab?.("deploy")}
          actionLabel="Deploy"
        />
        <StatRow
          icon={Globe}
          label="Custom domain"
          value={primaryDomain?.hostname || "No domain connected"}
          accent={domainAccent}
          status={domainStatusKey}
          action
          onAction={() => onGoTab?.("domains")}
          actionLabel="Domains"
        />
      </div>

      {/* Launch readiness — ProductAgent surface */}
      <LaunchReadinessCard
        projectId={projectId}
        readiness={readiness}
        project={project}
        onGoTab={onGoTab}
        onSendChat={onSendChat}
      />

      {/* Detected routes (if any) */}
      {(analysis?.routes || []).length > 0 && (
        <section className="px-4 sm:px-6 py-5 border-b border-white/5" data-testid="overview-routes">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="nxt-overline">// detected api routes</div>
              <div className="text-sm font-medium mt-0.5">
                {analysis.routes.length} backend route{analysis.routes.length === 1 ? "" : "s"}
              </div>
            </div>
            <button
              onClick={() => onGoTab?.("runtime")}
              className="nxt-btn !py-1.5 !px-3 text-[11px]"
            >
              Test in Runtime <ChevronRight size={11} />
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
            {analysis.routes.slice(0, 8).map((r, i) => {
              const key = `${r.method}-${r.path}`;
              const busy = genBusyKey === key;
              return (
                <div
                  key={`${r.method}-${r.path}-${i}`}
                  className="flex items-center gap-2 text-xs mono px-2.5 py-1.5 border border-white/5 rounded-sm bg-[#1F1F23] hover:bg-[#1F1F23] transition group"
                  data-testid={`overview-route-${r.method}-${r.path}`}
                >
                  <span
                    className={`text-[10px] tracking-wider px-1.5 py-0.5 border rounded-sm shrink-0 ${
                      METHOD_COLOR[r.method] || METHOD_COLOR.ANY
                    }`}
                  >
                    {r.method}
                  </span>
                  <span className="text-zinc-200 truncate flex-1">{r.path}</span>
                  <button
                    onClick={() => handleGenerateForRoute(r)}
                    disabled={busy}
                    className="opacity-0 group-hover:opacity-100 sm:opacity-100 inline-flex items-center gap-1 text-[10px] mono px-1.5 py-0.5 border border-emerald-400/30 text-emerald-300 hover:bg-emerald-500/10 rounded-sm transition disabled:opacity-50"
                    title="Generate frontend page that calls this route"
                    data-testid={`generate-page-${r.method}-${r.path}`}
                  >
                    {busy ? (
                      <Loader2 size={10} className="animate-spin" />
                    ) : (
                      <Wand2 size={10} />
                    )}
                    page
                  </button>
                  <span className="text-zinc-600 truncate hidden md:inline">{r.file}</span>
                </div>
              );
            })}
            {analysis.routes.length > 8 && (
              <div className="text-xs text-zinc-500 mono col-span-full">
                +{analysis.routes.length - 8} more — see Runtime tab
              </div>
            )}
          </div>
        </section>
      )}

      {/* Frameworks & dependencies */}
      {analysis && (analysis.frameworks?.length || analysis.env_keys?.length) ? (
        <section className="px-4 sm:px-6 py-5 border-b border-white/5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {analysis.frameworks?.length > 0 && (
              <div>
                <div className="nxt-overline mb-2">// frameworks</div>
                <div className="flex flex-wrap gap-1.5">
                  {analysis.frameworks.map((f) => (
                    <span
                      key={f}
                      className="text-[11px] mono px-2 py-1 border border-white/10 rounded-sm text-zinc-300 bg-white/[0.03]"
                    >
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {analysis.env_keys?.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="nxt-overline">// env vars referenced</div>
                  <button
                    onClick={() => onGoTab?.("env")}
                    className="text-[11px] mono text-zinc-500 hover:text-white"
                  >
                    set values →
                  </button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {analysis.env_keys.slice(0, 12).map((k) => (
                    <span
                      key={k}
                      className="text-[11px] mono px-2 py-1 border border-white/10 rounded-sm text-zinc-300 bg-white/[0.03]"
                    >
                      {k}
                    </span>
                  ))}
                  {analysis.env_keys.length > 12 && (
                    <span className="text-[11px] mono text-zinc-500">
                      +{analysis.env_keys.length - 12}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>
      ) : null}

      {/* Files at-a-glance */}
      <section className="px-4 sm:px-6 py-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="nxt-overline">// codebase</div>
            <div className="text-sm font-medium mt-0.5">
              {filesCount} file{filesCount === 1 ? "" : "s"}
              {analysis?.split?.frontend && " · frontend ✓"}
              {analysis?.split?.backend && " · backend ✓"}
            </div>
          </div>
          <button
            onClick={() => onGoTab?.("history")}
            className="nxt-btn !py-1.5 !px-3 text-[11px]"
          >
            History
          </button>
        </div>
        <p className="text-xs text-zinc-500 mt-3 leading-relaxed">
          NXT1 keeps a versioned snapshot of every AI change. Open the <span className="text-zinc-300">Chat</span> tab to describe what to build or modify — the AI reads your project structure, env vars, and live runtime URL.
        </p>
      </section>
    </div>
  );
}
