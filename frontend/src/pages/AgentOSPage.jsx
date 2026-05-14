/**
 * AgentOS — personal AI agent suite (Phase B.14).
 *
 * 8-tab dashboard inside the NXT1 workspace:
 *   Chat · Jobs · Resume · Social · Founders · Approvals · Builder · Settings
 *
 * Real, wired:
 *   - Profile / Settings (Mongo persistence)
 *   - Job discovery via jobspy → POST /api/v1/agentos/jobs/scan
 *   - Resume tailoring via litellm
 *   - Social: weekly content-strategy generation + Postiz iframe (sidecar)
 *   - Founders: warm-lead config + draft outreach + status tracking
 *   - Approvals queue
 *   - Builder: bolt.diy iframe (sidecar via docker compose --profile builder)
 *   - Chat → reuses our existing /api/agents catalog
 *
 * Coming next (requires infra):
 *   - Browser Agent → needs Playwright sandbox
 *   - Voice Agent → needs LiveKit Cloud + DEEPGRAM/CARTESIA keys
 *   - Real LinkedIn/X send → needs the Browser Agent + auth tokens
 */
import { useEffect, useMemo, useState } from "react";
import {
  Briefcase, FileText, Send, ShieldCheck, Settings as SettingsIcon,
  MessageSquare, Loader2, Check, X as XIcon, Mic, Globe,
  Building2, MapPin, DollarSign, ExternalLink, RefreshCw,
  Megaphone, Users, Sparkles, AlertTriangle,
} from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";
import { useTheme } from "@/components/theme/ThemeProvider";

const TABS = [
  { id: "chat",      label: "Chat",      icon: MessageSquare },
  { id: "jobs",      label: "Jobs",      icon: Briefcase },
  { id: "resume",    label: "Resume",    icon: FileText },
  { id: "social",    label: "Social",    icon: Megaphone },
  { id: "founders",  label: "Founders",  icon: Users },
  { id: "approvals", label: "Approvals", icon: ShieldCheck },
  { id: "settings",  label: "Settings",  icon: SettingsIcon },
];

export default function AgentOSPage() {
  const { theme } = useTheme();
  const isLight = theme === "light";
  const [tab, setTab] = useState("jobs");
  const [counts, setCounts] = useState({ jobs: 0, approvals: 0, founders: 0 });

  useEffect(() => {
    const load = async () => {
      try {
        const [j, a, f] = await Promise.all([
          api.get("/v1/agentos/jobs", { params: { status: "new", limit: 200 } }),
          api.get("/v1/agentos/approvals"),
          api.get("/v1/agentos/founders/stats").catch(() => ({ data: {} })),
        ]);
        setCounts({
          jobs: (j.data || []).length,
          approvals: (a.data || []).length,
          founders: f.data?.drafted || 0,
        });
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, []);

  return (
    <div
      className="w-full max-w-[1180px] mx-auto px-4 sm:px-8 py-6 sm:py-10"
      data-testid="agentos-page"
    >
      <Header />

      {/* Tab bar */}
      <nav
        className="mt-7 mb-6 flex items-center gap-1 overflow-x-auto"
        style={{ borderBottom: "1px solid var(--nxt-border-soft)" }}
        data-testid="agentos-tabs"
      >
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          const badge =
            t.id === "jobs" ? counts.jobs :
            t.id === "approvals" ? counts.approvals :
            t.id === "founders" ? counts.founders : 0;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="inline-flex items-center gap-2 px-3.5 py-3 transition relative whitespace-nowrap"
              style={{
                color: active ? "var(--nxt-fg)" : "var(--nxt-fg-dim)",
                borderBottom: `2px solid ${active ? "var(--nxt-fg)" : "transparent"}`,
                marginBottom: "-1px",
              }}
              data-testid={`agentos-tab-${t.id}`}
            >
              <Icon size={13} />
              <span className="text-[13px] font-medium tracking-tight">{t.label}</span>
              {badge > 0 && (
                <span
                  className="ml-0.5 mono text-[9.5px] px-1.5 py-0.5 rounded-full font-semibold"
                  style={{
                    background: "rgba(94,234,212,0.18)",
                    color: isLight ? "#0E7C66" : "#5EEAD4",
                  }}
                >
                  {badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Body */}
      {tab === "chat"      && <ChatPane     isLight={isLight} />}
      {tab === "jobs"      && <JobsPane     isLight={isLight} />}
      {tab === "resume"    && <ResumePane   isLight={isLight} />}
      {tab === "social"    && <SocialPane   isLight={isLight} />}
      {tab === "founders"  && <FoundersPane isLight={isLight} />}
      {tab === "approvals" && <ApprovalsPane isLight={isLight} />}
      {tab === "settings"  && <SettingsPane  isLight={isLight} />}
    </div>
  );
}

/* ─────────────────────────  Header  ───────────────────────── */
function Header() {
  return (
    <header>
      <div className="flex items-center gap-2 mb-3">
        <span
          className="mono text-[10.5px] tracking-[0.32em] uppercase font-medium"
          style={{ color: "var(--nxt-fg-faint)" }}
        >
          Workspace · AgentOS
        </span>
      </div>
      <h1
        className="text-[28px] sm:text-[44px] leading-[1.05] sm:leading-[1.02] tracking-[-0.025em] font-medium"
        style={{ fontFamily: "'Cabinet Grotesk', sans-serif", color: "var(--nxt-fg)" }}
      >
        Your personal agent suite.
      </h1>
      <p
        className="mt-3 max-w-[640px] text-[14px] sm:text-[15px] leading-relaxed"
        style={{ color: "var(--nxt-fg-dim)" }}
      >
        A constellation of specialised agents working for you on a schedule — job
        discovery, resume tailoring, content scheduling, warm-lead outreach,
        and a guarded approvals queue so nothing reaches the real world without
        you signing off.
      </p>
    </header>
  );
}

/* ─────────────────────────  Chat  ───────────────────────── */
function ChatPane({ isLight }) {
  const [active, setActive] = useState([]);
  const [recent, setRecent] = useState([]);
  const [notifPerm, setNotifPerm] = useState(
    typeof Notification !== "undefined" ? Notification.permission : "unsupported"
  );

  const load = async () => {
    try {
      const [a, r] = await Promise.all([
        api.get("/agents/conversations/active"),
        api.get("/agents/conversations"),
      ]);
      setActive(a.data || []);
      setRecent((r.data || []).slice(0, 12));
    } catch { /* ignore */ }
  };
  useEffect(() => {
    load();
    const t = setInterval(load, 6_000);
    return () => clearInterval(t);
  }, []);

  const askPerm = async () => {
    try {
      const { requestAgentNotificationPermission } = await import("@/lib/agentActivity");
      const r = await requestAgentNotificationPermission();
      setNotifPerm(r);
      if (r === "granted") toast.success("Notifications enabled — we'll ping you when an agent finishes");
      else if (r === "denied") toast.error("Notifications blocked — enable in your browser settings");
    } catch { /* ignore */ }
  };

  return (
    <Pane>
      {/* Running now — the most important section, sits at top */}
      <Card title={`Running now (${active.length})`}>
        {active.length === 0 ? (
          <p className="text-[12.5px]" style={{ color: "var(--nxt-fg-dim)" }}>
            No agents are working right now. Start a chat from the library and you'll see it light up here.
          </p>
        ) : (
          <ul className="space-y-2">
            {active.map((c) => (
              <li key={c.id}>
                <a
                  href={`/workspace/agents?cid=${c.id}`}
                  className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition hover:-translate-y-0.5"
                  style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)" }}
                  data-testid={`active-agent-${c.id}`}
                >
                  <span className="relative h-2 w-2 shrink-0">
                    <span className="absolute inset-0 rounded-full animate-ping" style={{ background: "#5EEAD4", opacity: 0.6 }} />
                    <span className="absolute inset-0 rounded-full" style={{ background: "#5EEAD4" }} />
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium truncate" style={{ color: "var(--nxt-fg)" }}>
                      {c.item_name}
                    </div>
                    <div className="text-[11px] truncate" style={{ color: "var(--nxt-fg-dim)" }}>
                      Working… · started {timeAgo(c.started_at || c.updated_at)}
                    </div>
                  </div>
                  <ExternalLink size={12} style={{ color: "var(--nxt-fg-faint)" }} />
                </a>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Notify me */}
      {notifPerm !== "granted" && notifPerm !== "unsupported" && (
        <button
          onClick={askPerm}
          className="w-full sm:w-auto inline-flex items-center justify-center gap-2 h-10 px-4 rounded-xl text-[13px] font-medium tracking-tight"
          style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)", color: "var(--nxt-fg)" }}
          data-testid="chat-notify-me"
        >
          {notifPerm === "denied" ? "Notifications blocked" : "Notify me when an agent finishes"}
        </button>
      )}

      <Card title={`Recent chats (${recent.length})`}>
        {recent.length === 0 ? (
          <p className="text-[12.5px]" style={{ color: "var(--nxt-fg-dim)" }}>
            Start chatting from the <a href="/workspace/agents" className="underline" style={{ color: "var(--nxt-fg)" }}>agents library</a> — your conversations show up here.
          </p>
        ) : (
          <ul className="divide-y" style={{ borderColor: "var(--nxt-border-soft)" }}>
            {recent.map((c) => (
              <li key={c.id}>
                <a
                  href={`/workspace/agents?cid=${c.id}`}
                  className="flex items-center gap-3 py-2.5"
                  data-testid={`recent-agent-${c.id}`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium truncate" style={{ color: "var(--nxt-fg)" }}>
                      {c.item_name}
                    </div>
                    <div className="text-[11px] truncate" style={{ color: "var(--nxt-fg-dim)" }}>
                      {c.title} · updated {timeAgo(c.updated_at)}
                    </div>
                  </div>
                  <ExternalLink size={12} style={{ color: "var(--nxt-fg-faint)" }} />
                </a>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-3">
          <a
            href="/workspace/agents"
            className="inline-flex items-center gap-2 h-9 px-3.5 rounded-lg text-[12.5px] font-medium tracking-tight"
            style={{
              background: isLight ? "#1F1F23" : "#FFFFFF",
              color: isLight ? "#FAFAFA" : "#1F1F23",
            }}
            data-testid="chat-open-library"
          >
            Open agents library
            <ExternalLink size={11} />
          </a>
        </div>
      </Card>
    </Pane>
  );
}

function timeAgo(iso) {
  if (!iso) return "just now";
  const t = new Date(iso).getTime();
  const s = Math.max(1, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/* ─────────────────────────  Jobs  ───────────────────────── */
function JobsPane({ isLight }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [status, setStatus] = useState("new");

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/v1/agentos/jobs", { params: { status, limit: 100 } });
      setJobs(r.data || []);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { load(); }, [status]);  // eslint-disable-line react-hooks/exhaustive-deps

  const scan = async () => {
    setScanning(true);
    try {
      const r = await api.post("/v1/agentos/jobs/scan", { results_wanted: 25, hours_old: 72 });
      toast.success(`${r.data.new_jobs} new jobs · ${r.data.total_returned} returned`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Scan failed");
    }
    setScanning(false);
  };

  const decide = async (id, action) => {
    try {
      await api.post(`/v1/agentos/jobs/${id}/${action}`);
      setJobs((prev) => prev.filter((j) => j.id !== id));
    } catch (e) {
      toast.error(e?.response?.data?.detail || `${action} failed`);
    }
  };

  return (
    <Pane>
      <div className="flex items-center gap-2 mb-4">
        <div className="flex items-center gap-1.5" data-testid="jobs-status-filter">
          {["new", "approved", "rejected"].map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className="h-9 px-3 rounded-lg text-[12.5px] font-medium tracking-tight transition"
              style={{
                background: status === s ? "var(--nxt-fg)" : "var(--nxt-surface-soft)",
                color:      status === s ? "var(--nxt-surface-soft)" : "var(--nxt-fg)",
                border: `1px solid ${status === s ? "var(--nxt-fg)" : "var(--nxt-border-soft)"}`,
              }}
            >
              {s[0].toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
        <span className="flex-1" />
        <button
          onClick={scan}
          disabled={scanning}
          className="inline-flex items-center gap-2 h-9 px-3 rounded-lg text-[12.5px] font-medium tracking-tight transition disabled:opacity-50"
          style={{
            background: isLight ? "#1F1F23" : "#FFFFFF",
            color: isLight ? "#FAFAFA" : "#1F1F23",
          }}
          data-testid="jobs-scan-button"
        >
          {scanning ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          {scanning ? "Scanning…" : "Scan now"}
        </button>
      </div>

      {loading && <SkeletonGrid />}

      {!loading && jobs.length === 0 && (
        <EmptyState
          icon={Briefcase}
          title={status === "new" ? "No new jobs yet" : `No ${status} jobs`}
          hint='Hit "Scan now" to fetch from LinkedIn, Indeed, and ZipRecruiter using your search preferences.'
        />
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        {jobs.map((j) => (
          <article
            key={j.id}
            className="rounded-2xl p-4"
            style={{
              background: "var(--nxt-surface-soft)",
              border: "1px solid var(--nxt-border-soft)",
            }}
            data-testid={`jobs-card-${j.id}`}
          >
            <div className="flex items-start justify-between gap-2 mb-1">
              <h3 className="text-[14px] font-medium tracking-tight" style={{ color: "var(--nxt-fg)" }}>
                {j.title}
              </h3>
              <span className="mono text-[9.5px] tracking-[0.22em] uppercase shrink-0"
                    style={{ color: "var(--nxt-fg-faint)" }}>
                {j.site}
              </span>
            </div>
            <div className="text-[12.5px] flex flex-wrap items-center gap-x-3 gap-y-1"
                 style={{ color: "var(--nxt-fg-dim)" }}>
              <span className="inline-flex items-center gap-1"><Building2 size={11} />{j.company}</span>
              {j.location && (
                <span className="inline-flex items-center gap-1"><MapPin size={11} />{j.location}</span>
              )}
              {j.min_amount != null && (
                <span className="inline-flex items-center gap-1">
                  <DollarSign size={11} />{Number(j.min_amount).toLocaleString()}
                  {j.max_amount != null && `–${Number(j.max_amount).toLocaleString()}`}
                </span>
              )}
            </div>
            {j.description && (
              <p className="mt-2 text-[12.5px] leading-relaxed line-clamp-3"
                 style={{ color: "var(--nxt-fg-dim)" }}>
                {j.description}
              </p>
            )}
            <div className="mt-3 flex items-center gap-2">
              {status === "new" && (
                <>
                  <button
                    onClick={() => decide(j.id, "approve")}
                    className="h-8 px-3 rounded-lg text-[12px] inline-flex items-center gap-1.5"
                    style={{
                      background: isLight ? "#1F1F23" : "#FFFFFF",
                      color: isLight ? "#FAFAFA" : "#1F1F23",
                    }}
                  >
                    <Check size={11} /> Apply
                  </button>
                  <button
                    onClick={() => decide(j.id, "reject")}
                    className="h-8 px-3 rounded-lg text-[12px] inline-flex items-center gap-1.5"
                    style={{
                      background: "var(--nxt-chip-bg)",
                      border: "1px solid var(--nxt-border-soft)",
                      color: "var(--nxt-fg-dim)",
                    }}
                  >
                    <XIcon size={11} /> Skip
                  </button>
                </>
              )}
              {j.job_url && (
                <a
                  href={j.job_url}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-auto h-8 px-2 rounded-lg text-[11px] inline-flex items-center gap-1"
                  style={{ color: "var(--nxt-fg-faint)" }}
                >
                  Open <ExternalLink size={10} />
                </a>
              )}
            </div>
          </article>
        ))}
      </div>
    </Pane>
  );
}

/* ─────────────────────────  Resume  ───────────────────────── */
function ResumePane({ isLight }) {
  const [master, setMaster] = useState("");
  const [tailored, setTailored] = useState([]);
  const [saving, setSaving] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [tailoringId, setTailoringId] = useState(null);

  useEffect(() => {
    api.get("/v1/agentos/resume/master")
      .then((r) => setMaster(r.data?.plain_text || ""))
      .catch(() => {});
    api.get("/v1/agentos/resume/tailored").then((r) => setTailored(r.data || [])).catch(() => {});
    api.get("/v1/agentos/jobs", { params: { status: "approved", limit: 50 } })
      .then((r) => setJobs(r.data || []))
      .catch(() => {});
  }, []);

  const save = async () => {
    if (master.length < 20) {
      toast.error("Resume must be at least 20 characters");
      return;
    }
    setSaving(true);
    try {
      await api.put("/v1/agentos/resume/master", { plain_text: master });
      toast.success("Master resume saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
    setSaving(false);
  };

  const tailor = async (jobId) => {
    setTailoringId(jobId);
    try {
      const r = await api.post("/v1/agentos/resume/tailor", { job_id: jobId });
      setTailored((prev) => [r.data, ...prev]);
      toast.success("Tailored resume drafted");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Tailor failed");
    }
    setTailoringId(null);
  };

  return (
    <Pane>
      <Card title="Master resume">
        <p className="text-[12px] mb-3" style={{ color: "var(--nxt-fg-dim)" }}>
          Paste your master resume as plain text. We rewrite it per-job — never inventing skills you don't have.
        </p>
        <textarea
          value={master}
          onChange={(e) => setMaster(e.target.value)}
          rows={12}
          placeholder="Paste your resume here…"
          className="w-full rounded-xl p-3 text-[12.5px] outline-none resize-y"
          style={{
            background: isLight ? "rgba(31,31,35,0.04)" : "rgba(255,255,255,0.03)",
            border: "1px solid var(--nxt-border-soft)",
            color: "var(--nxt-fg)",
            fontFamily: "ui-monospace, monospace",
          }}
          data-testid="resume-master-input"
        />
        <div className="mt-3 flex items-center gap-2">
          <button
            onClick={save}
            disabled={saving}
            className="h-9 px-4 rounded-lg text-[12.5px] font-medium tracking-tight disabled:opacity-50"
            style={{ background: isLight ? "#1F1F23" : "#FFFFFF", color: isLight ? "#FAFAFA" : "#1F1F23" }}
            data-testid="resume-save"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : "Save master"}
          </button>
          <span className="mono text-[11px]" style={{ color: "var(--nxt-fg-faint)" }}>
            {master.length} chars
          </span>
        </div>
      </Card>

      <Card title="Tailor for an approved job">
        {jobs.length === 0 ? (
          <p className="text-[12.5px]" style={{ color: "var(--nxt-fg-dim)" }}>
            Approve a job in the Jobs tab first — then tailor a resume to match.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {jobs.map((j) => (
              <li key={j.id} className="flex items-center gap-3 rounded-lg p-2"
                  style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)" }}>
                <div className="flex-1 min-w-0">
                  <div className="text-[12.5px] font-medium truncate" style={{ color: "var(--nxt-fg)" }}>
                    {j.title}
                  </div>
                  <div className="text-[11px] truncate" style={{ color: "var(--nxt-fg-dim)" }}>
                    {j.company} · {j.location}
                  </div>
                </div>
                <button
                  onClick={() => tailor(j.id)}
                  disabled={tailoringId === j.id}
                  className="h-8 px-3 rounded-lg text-[11.5px] font-medium disabled:opacity-50"
                  style={{ background: isLight ? "#1F1F23" : "#FFFFFF", color: isLight ? "#FAFAFA" : "#1F1F23" }}
                >
                  {tailoringId === j.id ? <Loader2 size={11} className="animate-spin" /> : "Tailor"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title={`Tailored versions (${tailored.length})`}>
        {tailored.length === 0 ? (
          <p className="text-[12.5px]" style={{ color: "var(--nxt-fg-dim)" }}>None yet.</p>
        ) : (
          <ul className="space-y-2">
            {tailored.map((t) => (
              <details
                key={t.id}
                className="rounded-lg p-3 group"
                style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)" }}
              >
                <summary className="cursor-pointer text-[12.5px] font-medium flex items-center justify-between"
                         style={{ color: "var(--nxt-fg)" }}>
                  <span className="truncate">{t.job_title} @ {t.company}</span>
                  <span className="mono text-[10px] opacity-60">
                    {new Date(t.created_at).toLocaleString(undefined, {
                      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                    })}
                  </span>
                </summary>
                <pre className="mt-3 whitespace-pre-wrap text-[11.5px] leading-relaxed"
                     style={{ color: "var(--nxt-fg-dim)", fontFamily: "ui-monospace, monospace" }}>
                  {t.markdown}
                </pre>
              </details>
            ))}
          </ul>
        )}
      </Card>
    </Pane>
  );
}

/* ─────────────────────────  Social (NEW)  ─────────────────────────
   Strategy generator + Postiz iframe (sidecar). When Postiz isn't
   reachable, we show a clear "boot it" notice with the docker command. */
function SocialPane({ isLight }) {
  const [status, setStatus] = useState(null);
  const [strategies, setStrategies] = useState([]);
  const [goals, setGoals] = useState("");
  const [cadence, setCadence] = useState(5);
  const [platforms, setPlatforms] = useState({ linkedin: true, x: true });
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    api.get("/v1/agentos/social/status").then((r) => setStatus(r.data)).catch(() => {});
    api.get("/v1/agentos/social/strategies").then((r) => setStrategies(r.data || [])).catch(() => {});
  }, []);

  const generate = async () => {
    setGenerating(true);
    try {
      const r = await api.post("/v1/agentos/social/strategy", {
        goals: goals || null,
        platforms: Object.entries(platforms).filter(([, v]) => v).map(([k]) => k),
        cadence_per_week: cadence,
      });
      setStrategies((prev) => [r.data, ...prev]);
      toast.success(`Strategy generated · ${r.data.posts?.length || 0} posts`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Strategy generation failed");
    }
    setGenerating(false);
  };

  return (
    <Pane>
      <Card title="Weekly content strategy">
        <p className="text-[12.5px] mb-3" style={{ color: "var(--nxt-fg-dim)" }}>
          Generate a week of posts tailored to your bio + goals. Then schedule them in Postiz below.
        </p>
        <textarea
          value={goals}
          onChange={(e) => setGoals(e.target.value)}
          placeholder="This week's goals (e.g. share build notes about NXT1, drive demo signups)…"
          rows={3}
          className="w-full rounded-xl p-3 text-[12.5px] outline-none resize-y mb-3"
          style={{
            background: isLight ? "rgba(31,31,35,0.04)" : "rgba(255,255,255,0.03)",
            border: "1px solid var(--nxt-border-soft)",
            color: "var(--nxt-fg)",
          }}
          data-testid="social-goals-input"
        />
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <div className="flex gap-1.5">
            {["linkedin", "x"].map((p) => (
              <button
                key={p}
                onClick={() => setPlatforms((prev) => ({ ...prev, [p]: !prev[p] }))}
                className="h-9 px-3 rounded-lg text-[12px] font-medium tracking-tight transition"
                style={{
                  background: platforms[p] ? "var(--nxt-fg)" : "var(--nxt-surface-soft)",
                  color:      platforms[p] ? "var(--nxt-surface-soft)" : "var(--nxt-fg)",
                  border: `1px solid ${platforms[p] ? "var(--nxt-fg)" : "var(--nxt-border-soft)"}`,
                }}
                data-testid={`social-platform-${p}`}
              >
                {p === "linkedin" ? "LinkedIn" : "X / Twitter"}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-[12px]" style={{ color: "var(--nxt-fg-dim)" }}>
            Cadence
            <input
              type="number"
              min={1}
              max={21}
              value={cadence}
              onChange={(e) => setCadence(Number(e.target.value) || 5)}
              className="w-16 h-8 px-2 rounded-lg text-[12px] outline-none"
              style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)", color: "var(--nxt-fg)" }}
            />
            <span style={{ color: "var(--nxt-fg-faint)" }}>posts / week</span>
          </label>
          <span className="flex-1" />
          <button
            onClick={generate}
            disabled={generating}
            className="inline-flex items-center gap-2 h-9 px-4 rounded-lg text-[12.5px] font-medium disabled:opacity-50"
            style={{ background: isLight ? "#1F1F23" : "#FFFFFF", color: isLight ? "#FAFAFA" : "#1F1F23" }}
            data-testid="social-generate-button"
          >
            {generating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            {generating ? "Drafting…" : "Generate"}
          </button>
        </div>
      </Card>

      {strategies.length > 0 && (
        <Card title={`Recent strategies (${strategies.length})`}>
          <ul className="space-y-2">
            {strategies.slice(0, 6).map((s) => (
              <details
                key={s.id}
                className="rounded-lg p-3"
                style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)" }}
              >
                <summary className="cursor-pointer text-[12.5px] font-medium flex items-center justify-between"
                         style={{ color: "var(--nxt-fg)" }}>
                  <span className="truncate">
                    {s.posts?.length || 0} posts · {(s.platforms || []).join(" + ")}
                  </span>
                  <span className="mono text-[10px] opacity-60">
                    {new Date(s.created_at).toLocaleString(undefined, {
                      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                    })}
                  </span>
                </summary>
                <ul className="mt-3 space-y-2.5">
                  {(s.posts || []).map((p, idx) => (
                    <li key={idx} className="rounded-lg p-3"
                        style={{ background: "var(--nxt-surface-soft)", border: "1px solid var(--nxt-border-soft)" }}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="mono text-[10px] tracking-[0.22em] uppercase"
                              style={{ color: "var(--nxt-fg-faint)" }}>
                          {p.day} · {p.platform}
                        </span>
                      </div>
                      {p.hook && (
                        <p className="text-[12.5px] font-medium mb-1" style={{ color: "var(--nxt-fg)" }}>
                          {p.hook}
                        </p>
                      )}
                      <p className="text-[12px] leading-relaxed whitespace-pre-wrap"
                         style={{ color: "var(--nxt-fg-dim)" }}>
                        {p.body}
                      </p>
                      {p.why && (
                        <p className="mt-1.5 text-[10.5px] italic" style={{ color: "var(--nxt-fg-faint)" }}>
                          why: {p.why}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </ul>
        </Card>
      )}

      <SidecarFrame
        title="Postiz scheduler"
        status={status}
        height={680}
        bootHint="docker compose --profile social up -d"
        envHint="POSTIZ_URL"
      />
    </Pane>
  );
}

/* ─────────────────────────  Founders (was Outreach)  ───────────────────────── */
function FoundersPane({ isLight }) {
  const [config, setConfig] = useState(null);
  const [stats, setStats] = useState({ drafted: 0, queued: 0, sent: 0, rejected: 0 });
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ platform: "linkedin", name: "", snippet: "", profile_url: "" });
  const [drafting, setDrafting] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [c, s, l] = await Promise.all([
        api.get("/v1/agentos/founders/config"),
        api.get("/v1/agentos/founders/stats"),
        api.get("/v1/agentos/leads"),
      ]);
      setConfig(c.data);
      setStats(s.data);
      setLeads(l.data || []);
    } catch { /* ignore */ }
    setLoading(false);
  };
  useEffect(() => { loadAll(); }, []);

  const saveConfig = async () => {
    setSavingConfig(true);
    try {
      const r = await api.put("/v1/agentos/founders/config", config);
      setConfig(r.data);
      toast.success("Search config saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
    setSavingConfig(false);
  };

  const draft = async (e) => {
    e.preventDefault();
    if (!form.name || form.snippet.length < 20) {
      toast.error("Name + at least 20 chars of their post are required");
      return;
    }
    setDrafting(true);
    try {
      const r = await api.post("/v1/agentos/leads/draft", form);
      setLeads((prev) => [r.data, ...prev]);
      setForm({ platform: form.platform, name: "", snippet: "", profile_url: "" });
      toast.success("Draft created");
      api.get("/v1/agentos/founders/stats").then((r2) => setStats(r2.data)).catch(() => {});
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Draft failed");
    }
    setDrafting(false);
  };

  const decide = async (id, action) => {
    try {
      await api.post(`/v1/agentos/leads/${id}/${action}`);
      loadAll();
    } catch (e) {
      toast.error(e?.response?.data?.detail || `${action} failed`);
    }
  };

  if (loading || !config) return <Pane><SkeletonGrid /></Pane>;

  const setCfg = (k, v) => setConfig((p) => ({ ...p, [k]: v }));

  return (
    <Pane>
      {/* Stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        {[
          ["Drafted",  stats.drafted,  "#5EEAD4"],
          ["Queued",   stats.queued,   "#FFD37A"],
          ["Sent",     stats.sent,     "#A78BFA"],
          ["Rejected", stats.rejected, "var(--nxt-fg-faint)"],
        ].map(([label, n, color]) => (
          <div key={label} className="rounded-2xl p-3.5"
               style={{ background: "var(--nxt-surface-soft)", border: "1px solid var(--nxt-border-soft)" }}>
            <div className="mono text-[10px] tracking-[0.22em] uppercase mb-1"
                 style={{ color: "var(--nxt-fg-faint)" }}>{label}</div>
            <div className="text-[22px] font-medium tracking-tight" style={{ color }}>{n}</div>
          </div>
        ))}
      </div>

      <Card title="Search config">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SettingsList label="Stages"           value={config.stages}      onChange={(v) => setCfg("stages", v)} />
          <SettingsList label="Industries"       value={config.industries}  onChange={(v) => setCfg("industries", v)} />
          <SettingsList label="Geographies"      value={config.geographies} onChange={(v) => setCfg("geographies", v)} />
          <SettingsList label="Keywords"         value={config.keywords}    onChange={(v) => setCfg("keywords", v)} />
          <SettingsList label="Exclude keywords" value={config.exclude_keywords} onChange={(v) => setCfg("exclude_keywords", v)} />
        </div>
        <div className="mt-3">
          <button
            onClick={saveConfig}
            disabled={savingConfig}
            className="h-9 px-4 rounded-lg text-[12.5px] font-medium disabled:opacity-50"
            style={{ background: isLight ? "#1F1F23" : "#FFFFFF", color: isLight ? "#FAFAFA" : "#1F1F23" }}
            data-testid="founders-config-save"
          >
            {savingConfig ? <Loader2 size={12} className="animate-spin" /> : "Save search config"}
          </button>
        </div>
      </Card>

      <ComingSoonCard
        title="Auto-discover founder leads on LinkedIn / X"
        env={["LINKEDIN_SESSION_COOKIE", "X_SESSION_COOKIE"]}
        icon={Globe}
      />

      <Card title="Draft a new outreach manually">
        <form onSubmit={draft} className="space-y-2.5">
          <div className="flex gap-2">
            {["linkedin", "x"].map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setForm({ ...form, platform: p })}
                className="h-9 px-3 rounded-lg text-[12px] font-medium tracking-tight transition"
                style={{
                  background: form.platform === p ? "var(--nxt-fg)" : "var(--nxt-surface-soft)",
                  color:      form.platform === p ? "var(--nxt-surface-soft)" : "var(--nxt-fg)",
                  border: `1px solid ${form.platform === p ? "var(--nxt-fg)" : "var(--nxt-border-soft)"}`,
                }}
              >
                {p === "linkedin" ? "LinkedIn" : "X"}
              </button>
            ))}
          </div>
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Lead name (e.g. Jane Doe, founder of Acme)"
            className="w-full rounded-lg h-10 px-3 text-[12.5px] outline-none"
            style={{
              background: isLight ? "rgba(31,31,35,0.04)" : "rgba(255,255,255,0.03)",
              border: "1px solid var(--nxt-border-soft)",
              color: "var(--nxt-fg)",
            }}
          />
          <textarea
            value={form.snippet}
            onChange={(e) => setForm({ ...form, snippet: e.target.value })}
            rows={4}
            placeholder="Paste their post or bio so the AI can reference it…"
            className="w-full rounded-lg p-3 text-[12.5px] outline-none resize-y"
            style={{
              background: isLight ? "rgba(31,31,35,0.04)" : "rgba(255,255,255,0.03)",
              border: "1px solid var(--nxt-border-soft)",
              color: "var(--nxt-fg)",
            }}
          />
          <button
            type="submit"
            disabled={drafting}
            className="h-9 px-4 rounded-lg text-[12.5px] font-medium tracking-tight disabled:opacity-50"
            style={{ background: isLight ? "#1F1F23" : "#FFFFFF", color: isLight ? "#FAFAFA" : "#1F1F23" }}
            data-testid="founders-draft-submit"
          >
            {drafting ? <Loader2 size={12} className="animate-spin" /> : "Draft message"}
          </button>
        </form>
      </Card>

      <Card title={`Drafted leads (${leads.filter((l) => l.status === "drafted").length})`}>
        {leads.length === 0 ? (
          <p className="text-[12.5px]" style={{ color: "var(--nxt-fg-dim)" }}>None yet.</p>
        ) : (
          <ul className="space-y-2.5">
            {leads.map((l) => (
              <li key={l.id}
                  className="rounded-lg p-3"
                  style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)" }}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="mono text-[10px] tracking-[0.22em] uppercase"
                        style={{ color: "var(--nxt-fg-faint)" }}>{l.platform}</span>
                  <span className="text-[12.5px] font-medium" style={{ color: "var(--nxt-fg)" }}>{l.name}</span>
                  <span className="mono text-[10px] ml-auto opacity-60"
                        style={{ color: "var(--nxt-fg-faint)" }}>{l.status}</span>
                </div>
                <p className="text-[11.5px] italic mb-2 line-clamp-2"
                   style={{ color: "var(--nxt-fg-dim)" }}>“{l.snippet}”</p>
                <p className="text-[12.5px] leading-relaxed whitespace-pre-wrap mb-2"
                   style={{ color: "var(--nxt-fg)" }}>
                  {l.draft}
                </p>
                {l.status === "drafted" && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => decide(l.id, "approve")}
                      className="h-8 px-3 rounded-lg text-[11.5px] font-medium"
                      style={{ background: isLight ? "#1F1F23" : "#FFFFFF", color: isLight ? "#FAFAFA" : "#1F1F23" }}
                    >
                      Queue for send
                    </button>
                    <button
                      onClick={() => decide(l.id, "reject")}
                      className="h-8 px-3 rounded-lg text-[11.5px]"
                      style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)", color: "var(--nxt-fg-dim)" }}
                    >
                      Skip
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Pane>
  );
}

/* ─────────────────────────  Approvals  ───────────────────────── */
function ApprovalsPane({ isLight }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { setItems((await api.get("/v1/agentos/approvals")).data || []); } catch { /* ignore */ }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const decide = async (id, action) => {
    try {
      await api.post(`/v1/agentos/approvals/${id}/${action}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || `${action} failed`);
    }
  };

  if (loading) return <Pane><SkeletonGrid /></Pane>;
  if (items.length === 0) return (
    <Pane>
      <EmptyState
        icon={ShieldCheck}
        title="Approvals queue empty"
        hint="Approve a job in the Jobs tab to see real-world actions queued here."
      />
    </Pane>
  );
  return (
    <Pane>
      <ul className="space-y-3">
        {items.map((a) => (
          <li
            key={a.id}
            className="rounded-2xl p-4"
            style={{ background: "var(--nxt-surface-soft)", border: "1px solid var(--nxt-border-soft)" }}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="mono text-[10px] tracking-[0.22em] uppercase"
                    style={{ color: "var(--nxt-fg-faint)" }}>{a.kind}</span>
              <span className="text-[13px] font-medium" style={{ color: "var(--nxt-fg)" }}>{a.title}</span>
            </div>
            {a.preview?.job && (
              <p className="text-[12px] mb-2" style={{ color: "var(--nxt-fg-dim)" }}>
                {a.preview.job.company} · {a.preview.job.location} · {a.preview.job.site}
              </p>
            )}
            <div className="flex gap-2">
              <button
                onClick={() => decide(a.id, "approve")}
                className="h-8 px-3 rounded-lg text-[12px] font-medium"
                style={{ background: isLight ? "#1F1F23" : "#FFFFFF", color: isLight ? "#FAFAFA" : "#1F1F23" }}
              >
                Approve
              </button>
              <button
                onClick={() => decide(a.id, "reject")}
                className="h-8 px-3 rounded-lg text-[12px]"
                style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)", color: "var(--nxt-fg-dim)" }}
              >
                Reject
              </button>
            </div>
          </li>
        ))}
      </ul>
    </Pane>
  );
}

/* ─────────────────────────  Settings  ───────────────────────── */
function SettingsPane({ isLight }) {
  const [profile, setProfile] = useState(null);
  const [keys, setKeys] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/v1/agentos/profile").then((r) => setProfile(r.data)).catch(() => {});
    api.get("/v1/agentos/system/keys").then((r) => setKeys(r.data)).catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const r = await api.put("/v1/agentos/profile", profile);
      setProfile(r.data);
      toast.success("Settings saved");
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    setSaving(false);
  };

  if (!profile) return <Pane><SkeletonGrid /></Pane>;

  const set = (k, v) => setProfile((p) => ({ ...p, [k]: v }));

  return (
    <Pane>
      <Card title="My profile">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SettingsField label="Full name"        value={profile.name}            onChange={(v) => set("name", v)} />
          <SettingsField label="Current role"     value={profile.current_role}     onChange={(v) => set("current_role", v)} />
          <SettingsField label="Years experience" value={profile.years_experience} onChange={(v) => set("years_experience", Number(v))} type="number" />
          <SettingsField label="Location"         value={profile.location}         onChange={(v) => set("location", v)} />
          <SettingsField label="Min salary (USD)" value={profile.min_salary || ""} onChange={(v) => set("min_salary", Number(v) || null)} type="number" />
          <div className="flex items-center gap-2 px-1">
            <input
              type="checkbox"
              checked={!!profile.remote_only}
              onChange={(e) => set("remote_only", e.target.checked)}
              id="remote_only"
            />
            <label htmlFor="remote_only" className="text-[12.5px]" style={{ color: "var(--nxt-fg)" }}>
              Remote only
            </label>
          </div>
        </div>
        <div className="mt-3">
          <SettingsTextArea
            label="Elevator pitch (used by Outreach Agent)"
            value={profile.bio}
            onChange={(v) => set("bio", v)}
          />
        </div>
      </Card>

      <Card title="Job-search preferences">
        <SettingsList label="Target titles"     value={profile.target_titles}     onChange={(v) => set("target_titles", v)} />
        <SettingsList label="Target locations"  value={profile.target_locations}  onChange={(v) => set("target_locations", v)} />
        <SettingsList label="Exclude companies" value={profile.exclude_companies} onChange={(v) => set("exclude_companies", v)} />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-2">
          <SettingsField label="Scan / hours"    value={profile.job_scan_freq_hours}     type="number" onChange={(v) => set("job_scan_freq_hours", Number(v))} />
          <SettingsField label="Outreach / hours" value={profile.outreach_scan_freq_hours} type="number" onChange={(v) => set("outreach_scan_freq_hours", Number(v))} />
          <SettingsField label="Apply / day"     value={profile.daily_application_limit} type="number" onChange={(v) => set("daily_application_limit", Number(v))} />
          <SettingsField label="Outreach / day"  value={profile.daily_outreach_limit}    type="number" onChange={(v) => set("daily_outreach_limit", Number(v))} />
        </div>
      </Card>

      <Card title="Integrations">
        {keys && <IntegrationsList keys={keys} isLight={isLight} />}
      </Card>

      <div>
        <button
          onClick={save}
          disabled={saving}
          className="h-10 px-5 rounded-xl text-[13px] font-medium tracking-tight disabled:opacity-50"
          style={{ background: isLight ? "#1F1F23" : "#FFFFFF", color: isLight ? "#FAFAFA" : "#1F1F23" }}
          data-testid="settings-save"
        >
          {saving ? <Loader2 size={13} className="animate-spin" /> : "Save settings"}
        </button>
      </div>
    </Pane>
  );
}

function IntegrationsList({ keys }) {
  const rows = useMemo(() => {
    const out = [];
    for (const [grp, items] of Object.entries(keys)) {
      if (typeof items !== "object" || items === null) {
        out.push({ group: grp, label: grp, ok: !!items, key: grp.toUpperCase() });
        continue;
      }
      for (const [k, ok] of Object.entries(items)) {
        out.push({ group: grp, label: k, ok, key: k.toUpperCase() });
      }
    }
    return out;
  }, [keys]);
  return (
    <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {rows.map((r) => (
        <li key={`${r.group}.${r.label}`}
            className="flex items-center justify-between px-3 py-2 rounded-lg"
            style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)" }}>
          <span>
            <span className="mono text-[10px] tracking-[0.22em] uppercase mr-2"
                  style={{ color: "var(--nxt-fg-faint)" }}>{r.group}</span>
            <span className="text-[12.5px]" style={{ color: "var(--nxt-fg)" }}>{r.label}</span>
          </span>
          <span className={`mono text-[10.5px] tracking-wider ${r.ok ? "" : "opacity-60"}`}
                style={{ color: r.ok ? "#5EEAD4" : "var(--nxt-fg-faint)" }}>
            {r.ok ? "Configured ✓" : "Not set"}
          </span>
        </li>
      ))}
    </ul>
  );
}

/* ─────────────────────────  Atoms  ───────────────────────── */
function Pane({ children }) { return <div className="space-y-4 sm:space-y-5">{children}</div>; }

function Card({ title, children }) {
  return (
    <section
      className="rounded-2xl p-4 sm:p-5"
      style={{ background: "var(--nxt-surface-soft)", border: "1px solid var(--nxt-border-soft)" }}
    >
      {title && (
        <h3 className="text-[13px] font-medium tracking-tight mb-3"
            style={{ color: "var(--nxt-fg)" }}>{title}</h3>
      )}
      {children}
    </section>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-28 rounded-2xl animate-pulse"
             style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)" }} />
      ))}
    </div>
  );
}

function EmptyState({ icon: Icon, title, hint }) {
  return (
    <div className="rounded-2xl p-10 text-center"
         style={{ background: "var(--nxt-surface-soft)", border: "1px solid var(--nxt-border-soft)" }}>
      <Icon size={18} className="mx-auto opacity-50 mb-3" style={{ color: "var(--nxt-fg-dim)" }} />
      <p className="text-[14px] font-medium" style={{ color: "var(--nxt-fg)" }}>{title}</p>
      <p className="text-[12.5px] mt-1" style={{ color: "var(--nxt-fg-dim)" }}>{hint}</p>
    </div>
  );
}

function ComingSoonCard({ title, env, icon: Icon }) {
  return (
    <section
      className="rounded-2xl p-4 sm:p-5 flex items-start gap-3"
      style={{ background: "var(--nxt-surface-soft)", border: "1px dashed var(--nxt-border-soft)" }}
    >
      <span
        className="h-9 w-9 shrink-0 rounded-xl flex items-center justify-center"
        style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)" }}
      >
        <Icon size={13} style={{ color: "var(--nxt-fg-dim)" }} />
      </span>
      <div className="flex-1">
        <h4 className="text-[13.5px] font-medium" style={{ color: "var(--nxt-fg)" }}>{title}</h4>
        <p className="text-[12px] mt-0.5 mb-1.5" style={{ color: "var(--nxt-fg-dim)" }}>
          Set these env vars on Render to enable:
        </p>
        <div className="flex flex-wrap gap-1.5">
          {env.map((k) => (
            <span key={k}
                  className="mono text-[10.5px] tracking-wider px-1.5 py-0.5 rounded"
                  style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)", color: "var(--nxt-fg-dim)" }}>
              {k}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

/* SidecarFrame — renders an iframe when the sidecar is reachable, otherwise
   a clean "boot it" notice with the docker command. Used by Social + Builder. */
function SidecarFrame({ title, status, height = 680, bootHint, envHint }) {
  if (!status) {
    return (
      <div className="h-40 rounded-2xl animate-pulse"
           style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)" }} />
    );
  }
  const ok = status.reachable;
  return (
    <section
      className="rounded-2xl overflow-hidden"
      style={{ background: "var(--nxt-surface-soft)", border: "1px solid var(--nxt-border-soft)" }}
      data-testid={`sidecar-${status.service}`}
    >
      <header
        className="flex items-center gap-3 px-4 py-2.5"
        style={{ borderBottom: "1px solid var(--nxt-border-soft)" }}
      >
        <span className="mono text-[10px] tracking-[0.22em] uppercase"
              style={{ color: "var(--nxt-fg-faint)" }}>sidecar</span>
        <span className="text-[12.5px] font-medium" style={{ color: "var(--nxt-fg)" }}>{title}</span>
        <span
          className="ml-1 mono text-[9.5px] px-1.5 py-0.5 rounded"
          style={{
            background: ok ? "rgba(94,234,212,0.18)" : "var(--nxt-chip-bg)",
            color: ok ? "#5EEAD4" : "var(--nxt-fg-faint)",
            border: "1px solid var(--nxt-border-soft)",
          }}
        >
          {ok ? "READY" : "OFFLINE"}
        </span>
        <span className="flex-1" />
        <a
          href={status.url}
          target="_blank"
          rel="noreferrer"
          className="text-[11.5px] inline-flex items-center gap-1"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          {status.url} <ExternalLink size={10} />
        </a>
      </header>
      {ok ? (
        <iframe
          title={title}
          src={status.url}
          style={{ width: "100%", height, border: 0, background: "#0A0A0B" }}
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-downloads"
        />
      ) : (
        <div className="p-7 sm:p-9">
          <div className="flex items-start gap-3">
            <span className="h-9 w-9 rounded-xl flex items-center justify-center"
                  style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)" }}>
              <AlertTriangle size={13} style={{ color: "var(--nxt-fg-dim)" }} />
            </span>
            <div className="flex-1">
              <h4 className="text-[14px] font-medium mb-1" style={{ color: "var(--nxt-fg)" }}>
                {title} sidecar isn't running
              </h4>
              <p className="text-[12.5px] mb-3" style={{ color: "var(--nxt-fg-dim)" }}>
                This pane embeds {title} as an iframe. Boot the sidecar in your self-hosted environment:
              </p>
              <pre className="rounded-lg p-3 text-[11.5px] overflow-x-auto"
                   style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)",
                            color: "var(--nxt-fg)", fontFamily: "ui-monospace, monospace" }}>
{bootHint || status.boot_hint}
              </pre>
              {envHint && (
                <p className="mt-2 text-[11px]" style={{ color: "var(--nxt-fg-faint)" }}>
                  Or override the host by setting <span className="mono">{envHint}</span> in your <span className="mono">.env</span>.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function SettingsField({ label, value, onChange, type = "text" }) {
  return (
    <label className="block">
      <span className="mono text-[10px] tracking-[0.22em] uppercase mb-1 block"
            style={{ color: "var(--nxt-fg-faint)" }}>{label}</span>
      <input
        type={type}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg h-9 px-3 text-[12.5px] outline-none"
        style={{
          background: "var(--nxt-chip-bg)",
          border: "1px solid var(--nxt-border-soft)",
          color: "var(--nxt-fg)",
        }}
      />
    </label>
  );
}

function SettingsTextArea({ label, value, onChange }) {
  return (
    <label className="block">
      <span className="mono text-[10px] tracking-[0.22em] uppercase mb-1 block"
            style={{ color: "var(--nxt-fg-faint)" }}>{label}</span>
      <textarea
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        className="w-full rounded-lg p-3 text-[12.5px] outline-none resize-y"
        style={{
          background: "var(--nxt-chip-bg)",
          border: "1px solid var(--nxt-border-soft)",
          color: "var(--nxt-fg)",
        }}
      />
    </label>
  );
}

function SettingsList({ label, value, onChange }) {
  return (
    <label className="block mt-2">
      <span className="mono text-[10px] tracking-[0.22em] uppercase mb-1 block"
            style={{ color: "var(--nxt-fg-faint)" }}>{label} (comma separated)</span>
      <input
        type="text"
        value={(value || []).join(", ")}
        onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
        className="w-full rounded-lg h-9 px-3 text-[12.5px] outline-none"
        style={{
          background: "var(--nxt-chip-bg)",
          border: "1px solid var(--nxt-border-soft)",
          color: "var(--nxt-fg)",
        }}
      />
    </label>
  );
}
