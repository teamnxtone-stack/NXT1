/**
 * NXT1 AgentOS — Command Center (Phase 22 full redesign)
 *
 * Single-file dashboard shell. Tabs: Home / Chat / Jobs / Resume / Social /
 * Founders / Agents / Approvals / Settings. Sidebar on desktop, bottom-nav
 * on mobile. Dark navy theme. Status cards, live activity feed, approvals
 * inline. All agents really run (backend `agentos_v2`).
 *
 * Sub-pages live inline (small) or imported (large — Custom + Jobs).
 */
import { useEffect, useState, useCallback, useMemo } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Home, MessageSquare, Briefcase, FileText, Megaphone, Users,
  Sparkles, Bell, Mic, Settings as Cog, Menu, X, ArrowLeft,
  Play, Square, CheckCircle2, AlertTriangle, Loader2, Clock, Plus,
  Activity, ChevronRight, Rocket, Upload, Copy, Download,
} from "lucide-react";
import {
  listAgents, listAgentTasks, agentosStats, submitAgentTask,
  cancelAgentTask, getAgentTask, openAgentTaskWS, extractResumeFile,
} from "@/lib/agentosApi";
import { toast } from "sonner";

const NAV = [
  { id: "home",      label: "Home",      icon: Home,           mobile: true  },
  { id: "chat",      label: "Chat",      icon: MessageSquare,  mobile: false },
  { id: "jobs",      label: "Jobs",      icon: Briefcase,      mobile: true  },
  { id: "resume",    label: "Resume",    icon: FileText,       mobile: false },
  { id: "social",    label: "Social",    icon: Megaphone,      mobile: true  },
  { id: "founders",  label: "Founders",  icon: Users,          mobile: false },
  { id: "agents",    label: "Agents",    icon: Sparkles,       mobile: true  },
  { id: "approvals", label: "Approvals", icon: Bell,           mobile: true  },
  { id: "settings",  label: "Settings",  icon: Cog,            mobile: false },
];

const STATUS_COLOR = {
  running:   "#22c55e",
  idle:      "#94a3b8",
  needs_you: "#fbbf24",
  done:      "#22c55e",
  failed:    "#ef4444",
  cancelled: "#94a3b8",
  queued:    "#94a3b8",
  waiting:   "#fbbf24",
};

export default function AgentOSDashboard() {
  const [params, setParams] = useSearchParams();
  const tab = NAV.find((n) => n.id === params.get("tab"))?.id || "home";
  const setTab = (id) => setParams((p) => { p.set("tab", id); return p; });
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div
      data-testid="agentos-dashboard"
      className="min-h-screen flex flex-col"
      style={{ background: "var(--nxt-bg)", color: "var(--nxt-fg)",
                fontFamily: "'IBM Plex Sans', Inter, -apple-system, sans-serif" }}
    >
      <DashboardHeader
        onMenu={() => setSidebarOpen((v) => !v)}
        onExit={() => navigate("/workspace")}
      />
      <div className="flex-1 flex">
        {/* Desktop sidebar */}
        <aside className="hidden md:flex flex-col w-[220px] flex-shrink-0 border-r"
               style={{ borderColor: "var(--hairline)" }}>
          <Sidebar tab={tab} setTab={setTab} />
        </aside>
        {/* Mobile drawer */}
        <AnimatePresence>
          {sidebarOpen && (
            <motion.aside
              initial={{ x: -260 }}
              animate={{ x: 0 }}
              exit={{ x: -260 }}
              transition={{ type: "spring", stiffness: 380, damping: 32 }}
              className="md:hidden fixed inset-y-0 left-0 w-[260px] z-50 border-r"
              style={{ borderColor: "var(--hairline)", background: "var(--nxt-bg)" }}
            >
              <Sidebar tab={tab} setTab={(id) => { setTab(id); setSidebarOpen(false); }} />
            </motion.aside>
          )}
        </AnimatePresence>

        {/* Main content */}
        <main className="flex-1 min-w-0 pb-20 md:pb-6">
          <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-5 sm:py-8">
            {tab === "home"      && <HomePage     setTab={setTab} />}
            {tab === "agents"    && <AgentsPage   />}
            {tab === "jobs"      && <JobsPage     />}
            {tab === "social"    && <SocialPage   />}
            {tab === "founders"  && <FoundersPage />}
            {tab === "approvals" && <ApprovalsPage />}
            {tab === "chat"      && <ChatPage     />}
            {tab === "resume"    && <ResumePage   />}
            {tab === "settings"  && <SettingsPage />}
          </div>
        </main>
      </div>
      {/* Mobile bottom nav */}
      <MobileBottomNav tab={tab} setTab={setTab} />
    </div>
  );
}

// ─── Header ──────────────────────────────────────────────────────────────
function DashboardHeader({ onMenu, onExit }) {
  const [pending, setPending] = useState(0);
  useEffect(() => {
    let cancel = false;
    const tick = async () => {
      try {
        const { data } = await listAgentTasks({ status: "queued", limit: 50 });
        if (!cancel) setPending(data.count || 0);
      } catch { /* ignore */ }
    };
    tick();
    const t = setInterval(tick, 8000);
    return () => { cancel = true; clearInterval(t); };
  }, []);
  return (
    <header
      className="flex-shrink-0 h-14 flex items-center gap-2 px-3 sm:px-6 border-b"
      style={{
        borderColor: "var(--hairline)",
        background:  "var(--nxt-bg)",
        backdropFilter: "blur(10px)",
      }}
    >
      {/* Prominent back arrow — visible on EVERY screen size */}
      <button onClick={onExit}
              data-testid="agentos-back"
              aria-label="Back to workspace"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition group"
              style={{
                background: "transparent",
                color: "var(--nxt-fg-dim)",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "var(--hairline)"; e.currentTarget.style.color = "var(--nxt-fg)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--nxt-fg-dim)"; }}>
        <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-0.5" />
        <span className="hidden sm:inline text-[12px] font-medium">Workspace</span>
      </button>

      <span className="hidden sm:block w-px h-5"
            style={{ background: "var(--hairline-strong)" }} />

      <button onClick={onMenu} className="md:hidden p-1.5 rounded-lg transition"
              style={{ color: "var(--nxt-fg-dim)" }}
              data-testid="agentos-menu" aria-label="Menu">
        <Menu className="w-5 h-5" />
      </button>

      <div className="flex items-center gap-2 min-w-0">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center font-semibold text-[12px] flex-shrink-0"
             style={{
               background: "linear-gradient(135deg, var(--nxt-accent) 0%, var(--nxt-accent-2, #6366F1) 100%)",
               color: "var(--nxt-bg)",
             }}>N1</div>
        <span className="font-semibold tracking-tight truncate">AgentOS</span>
      </div>

      <span className="hidden md:inline mono text-[10px] tracking-[0.3em] uppercase opacity-50">
        Command center
      </span>
      <div className="flex-1" />

      <button className="relative p-2 rounded-lg transition"
              style={{ color: "var(--nxt-fg-dim)" }}
              onMouseEnter={(e) => e.currentTarget.style.background = "var(--hairline)"}
              onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
              aria-label="Voice" data-testid="agentos-voice">
        <Mic className="w-4 h-4" />
      </button>
      <button className="relative p-2 rounded-lg transition"
              style={{ color: "var(--nxt-fg-dim)" }}
              onMouseEnter={(e) => e.currentTarget.style.background = "var(--hairline)"}
              onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
              aria-label="Approvals" data-testid="agentos-bell">
        <Bell className="w-4 h-4" />
        {pending > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full text-[9px] font-semibold flex items-center justify-center"
                style={{ background: "var(--nxt-error, #ef4444)", color: "white" }}>
            {pending > 9 ? "9+" : pending}
          </span>
        )}
      </button>
    </header>
  );
}

function Sidebar({ tab, setTab }) {
  return (
    <nav className="flex-1 py-4 px-2">
      {NAV.map(({ id, label, icon: Icon }) => {
        const isActive = id === tab;
        return (
          <button
            key={id}
            onClick={() => setTab(id)}
            data-testid={`agentos-nav-${id}`}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition mb-0.5 text-left"
            style={{
              background: isActive ? "var(--nxt-accent-bg)" : "transparent",
              color:      isActive ? "var(--nxt-accent)" : "var(--nxt-fg-dim)",
            }}
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </button>
        );
      })}
    </nav>
  );
}

function MobileBottomNav({ tab, setTab }) {
  return (
    <nav
      className="md:hidden fixed bottom-0 inset-x-0 z-40 grid grid-cols-5 border-t"
      style={{
        background: "var(--nxt-bg)",
        backdropFilter: "blur(14px)",
        borderColor: "var(--hairline)",
      }}
      data-testid="agentos-bottom-nav"
    >
      {NAV.filter((n) => n.mobile).map(({ id, label, icon: Icon }) => {
        const isActive = id === tab;
        return (
          <button
            key={id}
            onClick={() => setTab(id)}
            data-testid={`agentos-bottom-${id}`}
            className="flex flex-col items-center justify-center py-2.5 text-[10px]"
            style={{ color: isActive ? "var(--nxt-accent)" : "var(--nxt-fg-faint)",
                     minHeight: 56 }}
          >
            <Icon className="w-5 h-5 mb-0.5" />
            {label}
          </button>
        );
      })}
    </nav>
  );
}

// ─── Home page ───────────────────────────────────────────────────────────
function HomePage({ setTab }) {
  const [stats, setStats] = useState(null);
  const [agents, setAgents] = useState([]);
  const [feed, setFeed] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const [s, a, t] = await Promise.all([
        agentosStats(),
        listAgents(),
        listAgentTasks({ limit: 30 }),
      ]);
      setStats(s.data?.agents || {});
      setAgents(a.data?.agents || []);
      setFeed(t.data?.items || []);
    } catch { /* ignore */ }
  }, []);
  useEffect(() => { refresh(); const t = setInterval(refresh, 6000); return () => clearInterval(t); }, [refresh]);

  // Roll-up counters
  const totals = useMemo(() => {
    const total   = feed.length;
    const running = feed.filter((t) => t.status === "running").length;
    const today   = (() => {
      const start = new Date(); start.setHours(0,0,0,0);
      return feed.filter((t) => t.status === "done" &&
        new Date(t.updated_at) >= start).length;
    })();
    const failed  = feed.filter((t) => t.status === "failed").length;
    return { total, running, today, failed };
  }, [feed]);

  return (
    <div className="space-y-7" data-testid="agentos-home">
      {/* Hero */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="mono text-[10px] tracking-[0.3em] uppercase mb-2"
               style={{ color: "var(--nxt-accent)" }}>Mission control</div>
          <h1 className="text-[clamp(26px,4vw,34px)] font-semibold tracking-tight mb-1">
            Your agents are at work.
          </h1>
          <p className="text-[14px]" style={{ color: "var(--nxt-fg-dim)" }}>
            Real background jobs. Real status. Click anywhere to drill in.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap" data-testid="hero-counters">
          <Counter label="Running"   value={totals.running} color="#22c55e" pulse={totals.running > 0} />
          <Counter label="Done today" value={totals.today}   color="var(--nxt-accent)" />
          <Counter label="All time"  value={totals.total}   color="#94a3b8" />
          {totals.failed > 0 && (
            <Counter label="Failed" value={totals.failed} color="#ef4444" />
          )}
        </div>
      </div>

      {/* Agent status cards */}
      <div className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4 md:mx-0 md:px-0 md:grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
           data-testid="agentos-status-row">
        {agents.map((a) => {
          const s = stats?.[a.id] || {};
          const Icon = ICONS[a.icon] || Sparkles;
          const color = STATUS_COLOR[s.status] || "#94a3b8";
          const isRunning = s.status === "running";
          return (
            <button
              key={a.id}
              onClick={() => setTab(AGENT_TO_TAB[a.id] || "agents")}
              data-testid={`status-card-${a.id}`}
              className="text-left flex-shrink-0 w-[260px] md:w-auto rounded-2xl p-4 transition-all hover:translate-y-[-2px] group relative overflow-hidden"
              style={{
                background: "var(--nxt-surface)",
                border: `1px solid ${isRunning ? `${a.color}40` : "var(--hairline-strong)"}`,
                boxShadow: isRunning ? `0 0 0 1px ${a.color}30, 0 12px 32px -16px ${a.color}80` : "none",
              }}
            >
              {/* glow accent */}
              <div className="absolute -top-12 -right-12 w-32 h-32 rounded-full opacity-0 group-hover:opacity-40 transition-opacity blur-3xl"
                   style={{ background: a.color }} />
              <div className="relative">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-9 h-9 rounded-xl flex items-center justify-center"
                       style={{ background: `${a.color}1F`, color: a.color }}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-semibold truncate">{a.label}</div>
                    <div className="text-[10px] capitalize" style={{ color }}>
                      {isRunning && <span className="inline-block w-1.5 h-1.5 rounded-full mr-1 animate-pulse" style={{ background: color }} />}
                      {s.status || "idle"}
                    </div>
                  </div>
                </div>
                <div className="text-[11px] mb-3 line-clamp-2 min-h-[28px]"
                     style={{ color: "var(--nxt-fg-faint)" }}>
                  {s.running_now || s.last_done || a.description}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] mono uppercase tracking-wider"
                        style={{ color: "var(--nxt-fg-faint)" }}>
                    {s.last_at ? timeAgo(s.last_at) : "—"}
                  </span>
                  <span className="flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full transition group-hover:translate-x-0.5"
                        style={{ background: `${a.color}1A`, color: a.color }}>
                    Open <ChevronRight className="w-3 h-3" />
                  </span>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Activity Feed */}
      <div>
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-3.5 h-3.5" style={{ color: "var(--nxt-fg-faint)" }} />
            <span className="mono text-[10px] tracking-[0.3em] uppercase"
                  style={{ color: "var(--nxt-fg-faint)" }}>
              Live activity · {feed.length}
            </span>
          </div>
          <button onClick={() => setTab("agents")}
                  data-testid="home-view-all"
                  className="text-[10px] mono uppercase tracking-[0.2em] transition hover:text-white"
                  style={{ color: "var(--nxt-fg-faint)" }}>
            View all →
          </button>
        </div>
        <div className="space-y-1.5">
          {feed.length === 0 && (
            <EmptyState icon={Activity} text="No tasks yet — start one from any agent tab." />
          )}
          {feed.slice(0, 6).map((t) => (
            <FeedItem key={t.task_id} t={t}
                      onClick={() => setTab(AGENT_TO_TAB[t.agent] || "agents")} />
          ))}
        </div>
      </div>

      <div className="rounded-xl p-4 flex items-center justify-between gap-3"
           style={{ background: "var(--nxt-surface)",
                    border: "1px solid var(--hairline-strong)" }}>
        <div>
          <div className="text-[13px] font-medium mb-0.5">All clear ✨</div>
          <div className="text-[11px]" style={{ color: "var(--nxt-fg-faint)" }}>
            No approvals waiting right now.
          </div>
        </div>
        <button onClick={() => setTab("approvals")}
                data-testid="home-open-approvals"
                className="text-[11px] px-3 py-1.5 rounded-full transition hover:bg-white/10"
                style={{ background: "var(--hairline-strong)",
                         border: "1px solid var(--hairline-strong)" }}>
          Open queue
        </button>
      </div>
    </div>
  );
}

function Counter({ label, value, color, pulse }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-xl"
         style={{ background: "var(--nxt-surface)",
                  border: "1px solid var(--hairline-strong)" }}>
      <span className={`w-1.5 h-1.5 rounded-full ${pulse ? "animate-pulse" : ""}`}
            style={{ background: color }} />
      <span className="text-[18px] font-semibold tabular-nums" style={{ color }}>
        {value}
      </span>
      <span className="mono text-[9px] uppercase tracking-[0.2em]"
            style={{ color: "var(--nxt-fg-faint)" }}>{label}</span>
    </div>
  );
}

function FeedItem({ t, onClick }) {
  const color = STATUS_COLOR[t.status] || "#94a3b8";
  const Icon = t.status === "running" ? Loader2 :
                t.status === "done"    ? CheckCircle2 :
                t.status === "failed"  ? AlertTriangle :
                                          Clock;
  return (
    <button onClick={onClick}
            className="w-full text-left flex items-start gap-2.5 rounded-lg px-3 py-2.5 transition hover:bg-white/[0.02]"
            style={{ background: "var(--nxt-surface)", border: "1px solid var(--hairline)" }}
            data-testid={`feed-${t.task_id}`}>
      <Icon className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${t.status === "running" ? "animate-spin" : ""}`}
            style={{ color }} />
      <div className="flex-1 min-w-0">
        <div className="text-[12px] font-medium truncate">{t.label}</div>
        <div className="text-[10px] mt-0.5" style={{ color: "var(--nxt-fg-faint)" }}>
          {t.agent} · {timeAgo(t.updated_at)}
        </div>
      </div>
      <span className="text-[10px] mono uppercase tracking-wider"
            style={{ color }}>{t.status}</span>
    </button>
  );
}

function EmptyState({ icon: Icon, text }) {
  return (
    <div className="rounded-xl p-6 text-center"
         style={{ background: "var(--nxt-surface)", border: "1px solid var(--hairline)" }}>
      <Icon className="w-5 h-5 mx-auto mb-2 opacity-30" />
      <div className="text-[12px]" style={{ color: "var(--nxt-fg-faint)" }}>{text}</div>
    </div>
  );
}

// ─── Agents page (the Custom agent — heart of AgentOS) ──────────────────
function AgentsPage() {
  const [tasks, setTasks] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const { data } = await listAgentTasks({ agent: "custom", limit: 30 });
      setTasks(data.items || []);
      if (!selectedId && (data.items || []).length) {
        setSelectedId(data.items[0].task_id);
      }
    } catch { /* ignore */ }
  }, [selectedId]);
  useEffect(() => { refresh(); const t = setInterval(refresh, 5000); return () => clearInterval(t); }, [refresh]);

  return (
    <div className="space-y-5" data-testid="agentos-agents-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="mono text-[10px] tracking-[0.3em] uppercase mb-1"
               style={{ color: "#a78bfa" }}>Custom Agent</div>
          <h1 className="text-[24px] font-semibold tracking-tight">
            Give it a task. It works on it.
          </h1>
          <p className="text-[13px] mt-1" style={{ color: "var(--nxt-fg-faint)" }}>
            Multiple tasks run simultaneously. Live log, real results.
          </p>
        </div>
        <button onClick={() => setShowNew(true)}
                data-testid="agentos-new-task"
                className="flex items-center gap-1.5 text-[13px] font-medium px-4 py-2 rounded-full"
                style={{ background: "var(--nxt-accent)", color: "white" }}>
          <Plus className="w-3.5 h-3.5" /> New task
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
        {/* Left rail — tasks */}
        <div className="space-y-1.5">
          {tasks.length === 0 && (
            <EmptyState icon={Sparkles} text="No tasks yet — kick one off." />
          )}
          {tasks.map((t) => {
            const isActive = t.task_id === selectedId;
            const color = STATUS_COLOR[t.status] || "#94a3b8";
            return (
              <button
                key={t.task_id}
                onClick={() => setSelectedId(t.task_id)}
                data-testid={`task-pill-${t.task_id}`}
                className="w-full text-left rounded-xl p-3 transition"
                style={{
                  background: isActive ? "var(--nxt-accent-bg)" : "var(--nxt-surface)",
                  border: `1px solid ${isActive ? "var(--nxt-accent-border)" : "var(--hairline)"}`,
                }}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
                  <span className="text-[10px] mono uppercase tracking-wider"
                        style={{ color }}>{t.status}</span>
                  <span className="text-[10px] ml-auto" style={{ color: "var(--nxt-fg-faint)" }}>
                    {timeAgo(t.updated_at)}
                  </span>
                </div>
                <div className="text-[12px] truncate">{t.label}</div>
                <div className="text-[10px] mt-0.5"
                     style={{ color: "var(--nxt-fg-faint)" }}>
                  {t.steps?.length || 0} step(s)
                </div>
              </button>
            );
          })}
        </div>
        {/* Right rail — selected task detail */}
        <div>
          {selectedId
            ? <TaskDetail taskId={selectedId} onUpdated={refresh} />
            : <EmptyState icon={Sparkles} text="Pick a task or start a new one." />}
        </div>
      </div>

      {showNew && <NewTaskModal onClose={() => setShowNew(false)} onCreated={(id) => { setShowNew(false); setSelectedId(id); refresh(); }} />}
    </div>
  );
}

function TaskDetail({ taskId, onUpdated }) {
  const [task, setTask] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    let ws = null;
    setTask(null);
    getAgentTask(taskId).then((r) => { if (active) setTask(r.data); }).catch(() => {});
    if (taskId) {
      ws = openAgentTaskWS(taskId, (event) => {
        if (event.type === "snapshot") setTask(event.task);
        else if (event.type === "step" || event.type === "log") {
          setTask((cur) => {
            if (!cur) return cur;
            if (event.type === "step")
              return { ...cur, steps: [...(cur.steps || []), event.step] };
            return { ...cur, logs: [...(cur.logs || []), event.entry] };
          });
        } else if (event.type === "complete") {
          setTask((cur) => cur ? { ...cur, status: event.status, result: event.result, error: event.error } : cur);
          onUpdated?.();
        } else if (event.type === "status") {
          setTask((cur) => cur ? { ...cur, status: event.status } : cur);
        }
      });
    }
    return () => { active = false; try { ws?.close(); } catch { /* ignore */ } };
  }, [taskId, onUpdated]);

  const stop = async () => {
    setBusy(true);
    try { await cancelAgentTask(taskId); toast("Task cancelled"); onUpdated?.(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Cancel failed"); }
    finally { setBusy(false); }
  };

  if (!task) return <EmptyState icon={Loader2} text="Loading task..." />;

  return (
    <div className="rounded-xl p-5"
         style={{ background: "var(--nxt-surface)", border: "1px solid var(--hairline-strong)" }}
         data-testid={`task-detail-${task.task_id}`}>
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="min-w-0">
          <div className="text-[15px] font-semibold truncate">{task.label}</div>
          <div className="text-[10px] mono uppercase tracking-wider mt-1"
               style={{ color: STATUS_COLOR[task.status] || "#94a3b8" }}>
            {task.status} · {timeAgo(task.created_at)}
          </div>
        </div>
        {["queued", "running"].includes(task.status) && (
          <button onClick={stop} disabled={busy}
                  className="text-[11px] px-3 py-1.5 rounded-full flex items-center gap-1"
                  style={{ background: "rgba(239,68,68,0.10)",
                           border: "1px solid rgba(239,68,68,0.3)",
                           color: "#fca5a5" }}>
            <Square className="w-3 h-3" /> Stop
          </button>
        )}
      </div>

      <div className="mb-4">
        <div className="mono text-[9px] uppercase tracking-[0.3em] mb-2"
             style={{ color: "var(--nxt-fg-faint)" }}>
          Live log · {task.steps?.length || 0} step(s)
        </div>
        <div className="space-y-1.5 max-h-[300px] overflow-y-auto pr-1">
          {(task.steps || []).map((s) => (
            <div key={s.id} className="flex items-start gap-2 text-[11px]">
              <span style={{ color: STATUS_COLOR[s.status] || "#94a3b8" }}>
                {s.status === "done"    ? "✓" :
                 s.status === "running" ? "⏳" :
                 s.status === "failed"  ? "✗" : "•"}
              </span>
              <span style={{ color: "var(--nxt-fg)" }}>{s.label}</span>
              {s.detail && (
                <span className="ml-1 truncate" style={{ color: "var(--nxt-fg-faint)" }}>
                  · {s.detail.slice(0, 80)}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {task.result && (
        <div>
          <div className="mono text-[9px] uppercase tracking-[0.3em] mb-2"
               style={{ color: "var(--nxt-fg-faint)" }}>Result</div>
          <div className="rounded-lg p-3 text-[12px] leading-relaxed whitespace-pre-wrap max-h-[400px] overflow-y-auto"
               style={{ background: "var(--surface-recessed)",
                        border: "1px solid var(--hairline)",
                        color: "var(--nxt-fg)" }}
               data-testid="task-result">
            {typeof task.result === "string" ? task.result : (task.result.report || JSON.stringify(task.result, null, 2))}
          </div>
        </div>
      )}

      {task.error && (
        <div className="rounded-lg p-3 mt-3 text-[11px]"
             style={{ background: "rgba(239,68,68,0.08)", color: "#fca5a5" }}>
          {task.error}
        </div>
      )}
    </div>
  );
}

function NewTaskModal({ onClose, onCreated }) {
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const EXAMPLES = [
    "Research the top 10 VC firms investing in AI startups",
    "Write a 5-email cold outreach sequence for enterprise clients",
    "Find 20 potential customers for a B2B SaaS tool",
    "Summarize everything happening in AI this week",
  ];
  const submit = async () => {
    if (!prompt.trim()) return;
    setBusy(true);
    try {
      const { data } = await submitAgentTask("custom",
        { prompt: prompt.trim() }, prompt.trim().slice(0, 80));
      toast.success("Task started");
      onCreated?.(data.task_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't start task");
    } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4"
         style={{ background: "var(--scrim)", backdropFilter: "blur(6px)" }}
         onClick={onClose} data-testid="new-task-modal">
      <div className="w-full max-w-[560px] rounded-2xl p-5"
           onClick={(e) => e.stopPropagation()}
           style={{ background: "var(--nxt-surface)", border: "1px solid var(--hairline-strong)" }}>
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="mono text-[10px] uppercase tracking-[0.3em]"
                 style={{ color: "#a78bfa" }}>New task</div>
            <div className="text-[15px] font-semibold mt-1">What should the agent do?</div>
          </div>
          <button onClick={onClose}><X className="w-4 h-4 opacity-60" /></button>
        </div>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe the task in plain English..."
          data-testid="new-task-prompt"
          className="w-full text-[13px] px-3 py-2.5 rounded-lg outline-none resize-none"
          rows={4}
          style={{ background: "var(--surface-recessed)",
                   border: "1px solid var(--hairline-strong)",
                   color: "white" }}
        />
        <div className="text-[10px] mono uppercase tracking-[0.3em] mt-3 mb-1.5"
             style={{ color: "var(--nxt-fg-faint)" }}>Examples</div>
        <div className="flex flex-wrap gap-1.5 mb-4">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => setPrompt(ex)}
                    className="text-[11px] px-2.5 py-1 rounded-full transition"
                    style={{ background: "var(--hairline)",
                             border: "1px solid var(--hairline-strong)",
                             color: "var(--nxt-fg-dim)" }}>
              {ex}
            </button>
          ))}
        </div>
        <button onClick={submit} disabled={!prompt.trim() || busy}
                data-testid="new-task-submit"
                className="w-full text-[13px] font-medium px-4 py-2.5 rounded-full"
                style={{ background: "var(--nxt-accent)", color: "white",
                         opacity: !prompt.trim() || busy ? 0.5 : 1 }}>
          {busy ? "Starting..." : "Run task"}
        </button>
      </div>
    </div>
  );
}

// ─── Jobs page ─────────────────────────────────────────────────────────
function JobsPage() {
  const [tasks, setTasks] = useState([]);
  const [title, setTitle] = useState("Product Manager");
  const [location, setLocation] = useState("Remote");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    const { data } = await listAgentTasks({ agent: "job_scout", limit: 10 });
    setTasks(data.items || []);
  }, []);
  useEffect(() => { refresh(); const t = setInterval(refresh, 6000); return () => clearInterval(t); }, [refresh]);
  const scan = async () => {
    setBusy(true);
    try {
      await submitAgentTask("job_scout",
        { titles: [title], location, results_wanted: 15 },
        `Scan: ${title} · ${location}`);
      toast.success("Scanning job boards...");
      refresh();
    } catch (e) { toast.error(e?.response?.data?.detail || "Couldn't start scan"); }
    finally { setBusy(false); }
  };
  const latestDone = tasks.find((t) => t.status === "done");
  const jobs = latestDone?.result?.jobs || [];
  return (
    <div className="space-y-5" data-testid="agentos-jobs-page">
      <div>
        <div className="mono text-[10px] tracking-[0.3em] uppercase mb-1"
             style={{ color: "#22d3ee" }}>Job Scout</div>
        <h1 className="text-[24px] font-semibold tracking-tight">Find roles, fast.</h1>
        <p className="text-[13px] mt-1" style={{ color: "var(--nxt-fg-faint)" }}>
          JobSpy scans LinkedIn, Indeed, Glassdoor, ZipRecruiter — runs in background.
        </p>
      </div>

      <div className="rounded-xl p-4 grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2"
           style={{ background: "var(--nxt-surface)", border: "1px solid var(--hairline-strong)" }}>
        <input
          value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="Title (e.g. Product Manager)"
          data-testid="jobs-title-input"
          className="text-[13px] px-3 py-2 rounded-lg outline-none"
          style={{ background: "var(--surface-recessed)",
                   border: "1px solid var(--hairline-strong)" }}
        />
        <input
          value={location} onChange={(e) => setLocation(e.target.value)}
          placeholder="Location"
          data-testid="jobs-location-input"
          className="text-[13px] px-3 py-2 rounded-lg outline-none"
          style={{ background: "var(--surface-recessed)",
                   border: "1px solid var(--hairline-strong)" }}
        />
        <button onClick={scan} disabled={busy}
                data-testid="jobs-scan-btn"
                className="text-[13px] font-medium px-4 py-2 rounded-full flex items-center gap-1.5 justify-center"
                style={{ background: "#22d3ee", color: "var(--nxt-bg)" }}>
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
          Scan now
        </button>
      </div>

      <div>
        <div className="text-[11px] mono uppercase tracking-[0.3em] mb-2"
             style={{ color: "var(--nxt-fg-faint)" }}>
          {tasks.filter((t) => t.status === "running").length} scan(s) running · {jobs.length} jobs in latest result
        </div>
        {jobs.length === 0
          ? <EmptyState icon={Briefcase} text={tasks.length ? "Scan in progress... results appear here." : "Hit Scan now to start your first job hunt."} />
          : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {jobs.slice(0, 20).map((j, i) => (
                <a key={i} href={j.url} target="_blank" rel="noopener noreferrer"
                   data-testid={`job-card-${i}`}
                   className="rounded-xl p-4 transition hover:translate-y-[-2px]"
                   style={{ background: "var(--nxt-surface)",
                            border: "1px solid var(--hairline-strong)" }}>
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="mono text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded"
                          style={{ background: "rgba(34,211,238,0.1)", color: "#22d3ee" }}>
                      {j.platform}
                    </span>
                    {j.salary_min && (
                      <span className="text-[10px]" style={{ color: "var(--nxt-fg-faint)" }}>
                        ${Math.round(j.salary_min/1000)}k+
                      </span>
                    )}
                  </div>
                  <div className="text-[13px] font-medium leading-snug mb-0.5">{j.title}</div>
                  <div className="text-[11px] mb-1" style={{ color: "var(--nxt-fg-dim)" }}>
                    {j.company} · {j.location}
                  </div>
                  <div className="text-[10px]" style={{ color: "var(--nxt-fg-faint)" }}>
                    Posted {j.posted?.slice(0, 10) || "recently"}
                  </div>
                </a>
              ))}
            </div>
          )}
      </div>
    </div>
  );
}

// ─── Social page (Postiz iframe + content generator) ──────────────────────
function SocialPage() {
  const [tasks, setTasks] = useState([]);
  const [industry, setIndustry] = useState("AI / startups");
  const [tone, setTone] = useState("founder");
  const [busy, setBusy] = useState(false);
  const refresh = async () => {
    const { data } = await listAgentTasks({ agent: "social_strategist", limit: 5 });
    setTasks(data.items || []);
  };
  useEffect(() => { refresh(); const t = setInterval(refresh, 6000); return () => clearInterval(t); }, []);
  const generate = async () => {
    setBusy(true);
    try {
      await submitAgentTask("social_strategist",
        { industry, tone, days: 7 },
        `7-day plan · ${industry}`);
      toast.success("Generating content strategy...");
      refresh();
    } catch (e) { toast.error(e?.response?.data?.detail || "Couldn't start"); }
    finally { setBusy(false); }
  };
  const postizUrl = process.env.REACT_APP_POSTIZ_URL;
  return (
    <div className="space-y-5" data-testid="agentos-social-page">
      <div>
        <div className="mono text-[10px] tracking-[0.3em] uppercase mb-1"
             style={{ color: "#f472b6" }}>Social</div>
        <h1 className="text-[24px] font-semibold tracking-tight">Postiz + AI strategist.</h1>
        <p className="text-[13px] mt-1" style={{ color: "var(--nxt-fg-faint)" }}>
          Generate weeks of branded content. Postiz schedules and publishes.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl p-4 space-y-3"
             style={{ background: "var(--nxt-surface)", border: "1px solid var(--hairline-strong)" }}>
          <div className="mono text-[9px] uppercase tracking-[0.3em]"
               style={{ color: "var(--nxt-fg-faint)" }}>Content generator</div>
          <input value={industry} onChange={(e) => setIndustry(e.target.value)}
                 placeholder="Industry"
                 data-testid="social-industry"
                 className="w-full text-[13px] px-3 py-2 rounded-lg outline-none"
                 style={{ background: "var(--surface-recessed)", border: "1px solid var(--hairline-strong)" }} />
          <select value={tone} onChange={(e) => setTone(e.target.value)}
                  data-testid="social-tone"
                  className="w-full text-[13px] px-3 py-2 rounded-lg outline-none"
                  style={{ background: "var(--surface-recessed)", border: "1px solid var(--hairline-strong)" }}>
            <option value="founder">Founder</option>
            <option value="professional">Professional</option>
            <option value="casual">Casual</option>
          </select>
          <button onClick={generate} disabled={busy}
                  data-testid="social-generate"
                  className="w-full text-[13px] font-medium px-4 py-2.5 rounded-full flex items-center justify-center gap-1.5"
                  style={{ background: "#f472b6", color: "var(--nxt-bg)" }}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Rocket className="w-3.5 h-3.5" />}
            Generate week of content
          </button>
          <div className="space-y-1.5 pt-2">
            {tasks.slice(0, 3).map((t) => (
              <div key={t.task_id} className="text-[11px] flex items-center gap-2"
                   data-testid={`social-task-${t.task_id}`}>
                <span style={{ color: STATUS_COLOR[t.status] }}>●</span>
                <span className="truncate flex-1">{t.label}</span>
                <span className="mono uppercase opacity-50">{t.status}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-xl overflow-hidden"
             style={{ background: "var(--nxt-surface)", border: "1px solid var(--hairline-strong)",
                      minHeight: 360 }}>
          {postizUrl ? (
            <iframe src={postizUrl} title="Postiz"
                    data-testid="postiz-iframe"
                    className="w-full h-full min-h-[480px]"
                    style={{ border: "none" }} />
          ) : (
            <div className="p-6 h-full flex flex-col items-center justify-center text-center">
              <Megaphone className="w-6 h-6 mb-3 opacity-30" />
              <div className="text-[13px] mb-1">Postiz not configured</div>
              <div className="text-[11px] mb-3" style={{ color: "var(--nxt-fg-faint)" }}>
                Set <code className="mono">REACT_APP_POSTIZ_URL</code> in frontend/.env<br/>
                and bring up the Postiz docker-compose service.
              </div>
              <a href="https://github.com/gitroomhq/postiz-app" target="_blank" rel="noopener noreferrer"
                 className="text-[11px] underline" style={{ color: "#f472b6" }}>
                Postiz setup guide →
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Other pages ────────────────────────────────────────────────────────
function FoundersPage() {
  const [tasks, setTasks] = useState([]);
  const [busy, setBusy] = useState(false);
  const refresh = async () => {
    const { data } = await listAgentTasks({ agent: "founders_scout", limit: 10 });
    setTasks(data.items || []);
  };
  useEffect(() => { refresh(); const t = setInterval(refresh, 6000); return () => clearInterval(t); }, []);
  const scan = async () => {
    setBusy(true);
    try {
      await submitAgentTask("founders_scout", {}, "Scan cofounder signals");
      toast.success("Scanning Reddit + GitHub...");
      refresh();
    } catch (e) { toast.error(e?.response?.data?.detail || "Couldn't start"); }
    finally { setBusy(false); }
  };
  const latestDone = tasks.find((t) => t.status === "done");
  const leads = latestDone?.result?.leads || [];
  return (
    <div className="space-y-5" data-testid="agentos-founders-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="mono text-[10px] tracking-[0.3em] uppercase mb-1"
               style={{ color: "#10b981" }}>Founders</div>
          <h1 className="text-[24px] font-semibold tracking-tight">Find cofounders.</h1>
          <p className="text-[13px] mt-1" style={{ color: "var(--nxt-fg-faint)" }}>
            Scans Reddit + GitHub for technical-cofounder signals. X requires API key.
          </p>
        </div>
        <button onClick={scan} disabled={busy}
                data-testid="founders-scan"
                className="text-[13px] font-medium px-4 py-2 rounded-full flex items-center gap-1.5"
                style={{ background: "#10b981", color: "var(--nxt-bg)" }}>
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
          Scan now
        </button>
      </div>
      {leads.length === 0
        ? <EmptyState icon={Users} text={tasks.length ? "Scanning..." : "Hit Scan now to find leads."} />
        : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {leads.slice(0, 20).map((l, i) => (
              <a key={i} href={l.url} target="_blank" rel="noopener noreferrer"
                 data-testid={`lead-${i}`}
                 className="rounded-xl p-4 transition hover:translate-y-[-2px]"
                 style={{ background: "var(--nxt-surface)",
                          border: "1px solid var(--hairline-strong)" }}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="mono text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded"
                        style={{ background: "rgba(16,185,129,0.1)", color: "#10b981" }}>
                    {l.platform}
                  </span>
                  {l.subreddit && (
                    <span className="text-[10px]" style={{ color: "var(--nxt-fg-faint)" }}>
                      r/{l.subreddit}
                    </span>
                  )}
                </div>
                <div className="text-[13px] font-medium mb-0.5">{l.author}</div>
                {l.title && <div className="text-[11px] leading-snug" style={{ color: "var(--nxt-fg-dim)" }}>{l.title}</div>}
                {l.snippet && (
                  <div className="text-[10px] mt-1 line-clamp-2" style={{ color: "var(--nxt-fg-faint)" }}>
                    {l.snippet}
                  </div>
                )}
              </a>
            ))}
          </div>
        )}
    </div>
  );
}

function ApprovalsPage() {
  return (
    <div className="space-y-5" data-testid="agentos-approvals-page">
      <h1 className="text-[24px] font-semibold tracking-tight">Approvals</h1>
      <EmptyState icon={Bell} text="All clear ✨ — approvals queue from existing /api/agentos/approvals routes will surface here." />
    </div>
  );
}

function ChatPage() {
  return (
    <div className="space-y-4" data-testid="agentos-chat-page">
      <h1 className="text-[24px] font-semibold tracking-tight">Chat</h1>
      <EmptyState icon={MessageSquare} text="@assistant-ui/react chat with Claude streaming will live here. Backend ready via /api/agentos/tasks (agent='custom')." />
    </div>
  );
}

function ResumePage() {
  const [tasks, setTasks] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [resumeText, setResumeText] = useState("");
  const [resumeName, setResumeName] = useState("");
  const [jdText, setJdText] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [extracting, setExtracting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const { data } = await listAgentTasks({ agent: "resume_tailor", limit: 20 });
      setTasks(data.items || []);
    } catch { /* ignore */ }
  }, []);
  useEffect(() => { refresh(); const t = setInterval(refresh, 5000); return () => clearInterval(t); }, [refresh]);

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setExtracting(true);
    try {
      const { data } = await extractResumeFile(f);
      setResumeText(data.text || "");
      setResumeName(data.filename || f.name);
      toast.success(`Extracted ${data.char_count} characters from ${data.filename}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't read file");
    } finally {
      setExtracting(false);
      e.target.value = "";  // reset so user can re-upload same file
    }
  };

  const tailor = async () => {
    if (!resumeText.trim() || !jdText.trim()) {
      toast.error("Need both resume text and job description");
      return;
    }
    setBusy(true);
    try {
      const { data } = await submitAgentTask("resume_tailor", {
        resume_text: resumeText,
        job_description: jdText,
        job_title: jobTitle || "the role",
      }, `Tailor → ${jobTitle || "role"}`);
      toast.success("Tailoring in progress…");
      setSelectedId(data.task_id);
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't start");
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5" data-testid="agentos-resume-page">
      <div>
        <div className="mono text-[10px] tracking-[0.3em] uppercase mb-1"
             style={{ color: "#fb923c" }}>Resume Tailor</div>
        <h1 className="text-[24px] font-semibold tracking-tight">
          ATS-grade tailoring, truthfully.
        </h1>
        <p className="text-[13px] mt-1" style={{ color: "var(--nxt-fg-faint)" }}>
          Upload your resume, paste any JD, and get keyword coverage, ATS score, a tailored rewrite + coach tips.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4">
        {/* Resume input */}
        <div className="rounded-xl p-4 space-y-3"
             style={{ background: "var(--nxt-surface)", border: "1px solid var(--hairline-strong)" }}>
          <div className="flex items-center justify-between">
            <div className="mono text-[9px] uppercase tracking-[0.3em]"
                 style={{ color: "var(--nxt-fg-faint)" }}>Your resume</div>
            <label className="text-[11px] px-2.5 py-1 rounded-full cursor-pointer flex items-center gap-1 transition hover:bg-white/5"
                   style={{ background: "var(--hairline)",
                            border: "1px solid var(--hairline-strong)" }}
                   data-testid="resume-upload-btn">
              {extracting
                ? <Loader2 className="w-3 h-3 animate-spin" />
                : <Upload className="w-3 h-3" />}
              {extracting ? "Reading…" : "Upload PDF / DOCX"}
              <input type="file" accept=".pdf,.docx,.txt,.md"
                     className="hidden" onChange={onFile}
                     data-testid="resume-file-input" />
            </label>
          </div>
          {resumeName && (
            <div className="text-[11px]" style={{ color: "var(--nxt-fg-dim)" }}>
              📄 {resumeName} · {resumeText.length} chars
            </div>
          )}
          <textarea
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            placeholder="…or paste your resume here"
            data-testid="resume-text-input"
            rows={10}
            className="w-full text-[12px] px-3 py-2.5 rounded-lg outline-none resize-y font-mono"
            style={{ background: "var(--surface-recessed)",
                     border: "1px solid var(--hairline-strong)",
                     color: "white",
                     minHeight: 220 }}
          />
        </div>

        {/* JD input */}
        <div className="rounded-xl p-4 space-y-3"
             style={{ background: "var(--nxt-surface)", border: "1px solid var(--hairline-strong)" }}>
          <div className="mono text-[9px] uppercase tracking-[0.3em]"
               style={{ color: "var(--nxt-fg-faint)" }}>Target role</div>
          <input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)}
                 placeholder="Job title (e.g. Senior PM @ Stripe)"
                 data-testid="resume-job-title"
                 className="w-full text-[13px] px-3 py-2 rounded-lg outline-none"
                 style={{ background: "var(--surface-recessed)",
                          border: "1px solid var(--hairline-strong)",
                          color: "white" }} />
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            placeholder="Paste the full job description here"
            data-testid="resume-jd-input"
            rows={10}
            className="w-full text-[12px] px-3 py-2.5 rounded-lg outline-none resize-y"
            style={{ background: "var(--surface-recessed)",
                     border: "1px solid var(--hairline-strong)",
                     color: "white",
                     minHeight: 220 }}
          />
          <button onClick={tailor}
                  disabled={busy || !resumeText.trim() || !jdText.trim()}
                  data-testid="resume-tailor-btn"
                  className="w-full text-[13px] font-medium px-4 py-2.5 rounded-full flex items-center justify-center gap-1.5"
                  style={{ background: "#fb923c", color: "var(--nxt-bg)",
                           opacity: busy || !resumeText.trim() || !jdText.trim() ? 0.5 : 1 }}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Rocket className="w-3.5 h-3.5" />}
            Tailor my resume
          </button>
        </div>
      </div>

      {/* Past tailorings + selected detail */}
      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4">
        <div className="space-y-1.5">
          <div className="mono text-[9px] uppercase tracking-[0.3em] mb-1"
               style={{ color: "var(--nxt-fg-faint)" }}>
            History · {tasks.length}
          </div>
          {tasks.length === 0 && (
            <EmptyState icon={FileText} text="No tailorings yet." />
          )}
          {tasks.map((t) => {
            const isActive = t.task_id === selectedId;
            const color = STATUS_COLOR[t.status] || "#94a3b8";
            return (
              <button key={t.task_id}
                      onClick={() => setSelectedId(t.task_id)}
                      data-testid={`resume-task-${t.task_id}`}
                      className="w-full text-left rounded-xl p-3 transition"
                      style={{
                        background: isActive ? "rgba(251,146,60,0.10)" : "var(--nxt-surface)",
                        border: `1px solid ${isActive ? "rgba(251,146,60,0.4)" : "var(--hairline)"}`,
                      }}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
                  <span className="text-[10px] mono uppercase tracking-wider"
                        style={{ color }}>{t.status}</span>
                  <span className="text-[10px] ml-auto"
                        style={{ color: "var(--nxt-fg-faint)" }}>
                    {timeAgo(t.updated_at)}
                  </span>
                </div>
                <div className="text-[12px] truncate">{t.label}</div>
                {t.result?.ats_score != null && (
                  <div className="text-[10px] mt-0.5"
                       style={{ color: "var(--nxt-fg-faint)" }}>
                    ATS {t.result.ats_score}/100
                  </div>
                )}
              </button>
            );
          })}
        </div>
        <div>
          {selectedId
            ? <ResumeTaskDetail taskId={selectedId} onUpdated={refresh} />
            : <EmptyState icon={FileText}
                          text="Tailor a resume above, or pick one from history to see the score breakdown." />}
        </div>
      </div>
    </div>
  );
}

function ResumeTaskDetail({ taskId, onUpdated }) {
  const [task, setTask] = useState(null);

  useEffect(() => {
    let active = true;
    let ws = null;
    setTask(null);
    getAgentTask(taskId).then((r) => { if (active) setTask(r.data); }).catch(() => {});
    ws = openAgentTaskWS(taskId, (event) => {
      if (event.type === "snapshot") setTask(event.task);
      else if (event.type === "step")
        setTask((cur) => cur ? { ...cur, steps: [...(cur.steps || []), event.step] } : cur);
      else if (event.type === "complete") {
        setTask((cur) => cur ? { ...cur, status: event.status, result: event.result, error: event.error } : cur);
        onUpdated?.();
      } else if (event.type === "status") {
        setTask((cur) => cur ? { ...cur, status: event.status } : cur);
      }
    });
    return () => { active = false; try { ws?.close(); } catch { /* ignore */ } };
  }, [taskId, onUpdated]);

  const copy = () => {
    if (task?.result?.tailored_resume) {
      navigator.clipboard.writeText(task.result.tailored_resume);
      toast.success("Copied to clipboard");
    }
  };
  const download = () => {
    if (!task?.result?.tailored_resume) return;
    const blob = new Blob([task.result.tailored_resume], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${task.label || "tailored-resume"}.md`;
    a.click(); URL.revokeObjectURL(url);
  };

  if (!task) return <EmptyState icon={Loader2} text="Loading…" />;
  const r = task.result;
  const isDone = task.status === "done" && r;

  return (
    <div className="rounded-xl p-5 space-y-4"
         style={{ background: "var(--nxt-surface)", border: "1px solid var(--hairline-strong)" }}
         data-testid={`resume-detail-${task.task_id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[15px] font-semibold truncate">{task.label}</div>
          <div className="text-[10px] mono uppercase tracking-wider mt-1"
               style={{ color: STATUS_COLOR[task.status] || "#94a3b8" }}>
            {task.status} · {timeAgo(task.created_at)}
          </div>
        </div>
        {isDone && (
          <div className="flex gap-1.5">
            <button onClick={copy}
                    data-testid="resume-copy"
                    className="text-[11px] px-2.5 py-1.5 rounded-full flex items-center gap-1"
                    style={{ background: "var(--hairline)",
                             border: "1px solid var(--hairline-strong)" }}>
              <Copy className="w-3 h-3" /> Copy
            </button>
            <button onClick={download}
                    data-testid="resume-download"
                    className="text-[11px] px-2.5 py-1.5 rounded-full flex items-center gap-1"
                    style={{ background: "var(--hairline)",
                             border: "1px solid var(--hairline-strong)" }}>
              <Download className="w-3 h-3" /> .md
            </button>
          </div>
        )}
      </div>

      {/* Live steps */}
      {!isDone && (
        <div>
          <div className="mono text-[9px] uppercase tracking-[0.3em] mb-2"
               style={{ color: "var(--nxt-fg-faint)" }}>
            Live · {task.steps?.length || 0} step(s)
          </div>
          <div className="space-y-1.5 max-h-[240px] overflow-y-auto pr-1">
            {(task.steps || []).map((s) => (
              <div key={s.id} className="flex items-start gap-2 text-[11px]">
                <span style={{ color: STATUS_COLOR[s.status] || "#94a3b8" }}>
                  {s.status === "done" ? "✓" : s.status === "running" ? "⏳" : "•"}
                </span>
                <span style={{ color: "var(--nxt-fg)" }}>{s.label}</span>
                {s.detail && (
                  <span className="ml-1 truncate"
                        style={{ color: "var(--nxt-fg-faint)" }}>· {s.detail.slice(0, 80)}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Score gauge + keyword pills */}
      {isDone && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <ScoreCard label="ATS score" value={r.ats_score} suffix="/100"
                       testid="resume-ats-score" highlight />
            <ScoreCard label="Keyword coverage" value={r.keyword_coverage} suffix="%"
                       testid="resume-kw-coverage" />
            <ScoreCard label="Cosine similarity" value={r.cosine_similarity} suffix="%"
                       testid="resume-cosine" />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <KeywordList title={`Matched (${r.matched?.length || 0})`}
                         items={r.matched || []} color="#22c55e"
                         testid="resume-matched" />
            <KeywordList title={`Missing (${r.missing?.length || 0})`}
                         items={r.missing || []} color="#fbbf24"
                         testid="resume-missing" />
          </div>

          <div>
            <div className="mono text-[9px] uppercase tracking-[0.3em] mb-2"
                 style={{ color: "var(--nxt-fg-faint)" }}>Tailored resume</div>
            <div className="rounded-lg p-4 text-[12px] leading-relaxed whitespace-pre-wrap max-h-[420px] overflow-y-auto"
                 style={{ background: "var(--surface-recessed)",
                          border: "1px solid var(--hairline)",
                          color: "var(--nxt-fg)" }}
                 data-testid="resume-tailored-output">
              {r.tailored_resume}
            </div>
          </div>

          {r.suggestions && (
            <div>
              <div className="mono text-[9px] uppercase tracking-[0.3em] mb-2"
                   style={{ color: "var(--nxt-fg-faint)" }}>Coach&apos;s suggestions</div>
              <div className="rounded-lg p-4 text-[12px] leading-relaxed whitespace-pre-wrap"
                   style={{ background: "rgba(251,146,60,0.06)",
                            border: "1px solid rgba(251,146,60,0.2)",
                            color: "var(--nxt-fg)" }}
                   data-testid="resume-suggestions">
                {r.suggestions}
              </div>
            </div>
          )}
        </>
      )}

      {task.error && (
        <div className="rounded-lg p-3 text-[11px]"
             style={{ background: "rgba(239,68,68,0.08)", color: "#fca5a5" }}>
          {task.error}
        </div>
      )}
    </div>
  );
}

function ScoreCard({ label, value, suffix, testid, highlight }) {
  const v = value ?? 0;
  const color = v >= 75 ? "#22c55e" : v >= 50 ? "#fbbf24" : "#ef4444";
  return (
    <div className="rounded-xl p-3"
         data-testid={testid}
         style={{ background: highlight ? "rgba(251,146,60,0.06)" : "var(--surface-recessed)",
                  border: `1px solid ${highlight ? "rgba(251,146,60,0.25)" : "var(--hairline)"}` }}>
      <div className="mono text-[9px] uppercase tracking-[0.3em] mb-1"
           style={{ color: "var(--nxt-fg-faint)" }}>{label}</div>
      <div className="text-[22px] font-semibold" style={{ color }}>
        {v}{suffix}
      </div>
    </div>
  );
}

function KeywordList({ title, items, color, testid }) {
  return (
    <div className="rounded-xl p-3"
         data-testid={testid}
         style={{ background: "var(--surface-recessed)",
                  border: "1px solid var(--hairline)" }}>
      <div className="mono text-[9px] uppercase tracking-[0.3em] mb-2"
           style={{ color: "var(--nxt-fg-faint)" }}>{title}</div>
      <div className="flex flex-wrap gap-1">
        {items.length === 0 && (
          <span className="text-[11px]" style={{ color: "var(--nxt-fg-faint)" }}>—</span>
        )}
        {items.slice(0, 20).map((k) => (
          <span key={k}
                className="text-[10px] px-2 py-0.5 rounded-full"
                style={{ background: `${color}1A`, color,
                         border: `1px solid ${color}33` }}>
            {k}
          </span>
        ))}
      </div>
    </div>
  );
}

function SettingsPage() {
  return (
    <div className="space-y-4" data-testid="agentos-settings-page">
      <h1 className="text-[24px] font-semibold tracking-tight">Settings</h1>
      <div className="rounded-xl p-4"
           style={{ background: "var(--nxt-surface)", border: "1px solid var(--hairline-strong)" }}>
        <div className="text-[13px] mb-1">Environment</div>
        <div className="text-[11px]" style={{ color: "var(--nxt-fg-faint)" }}>
          Configured server-side. See /app/SELF_HOSTING.md for the full list of env vars.
        </div>
      </div>
    </div>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────
const ICONS = {
  Sparkles, Briefcase, Users, Megaphone, FileText, MessageSquare,
};

const AGENT_TO_TAB = {
  custom:            "agents",
  job_scout:         "jobs",
  founders_scout:    "founders",
  social_strategist: "social",
  resume_tailor:     "resume",
};

function timeAgo(iso) {
  if (!iso) return "";
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60)    return `${Math.floor(d)}s ago`;
  if (d < 3600)  return `${Math.floor(d/60)}m ago`;
  if (d < 86400) return `${Math.floor(d/3600)}h ago`;
  return `${Math.floor(d/86400)}d ago`;
}
