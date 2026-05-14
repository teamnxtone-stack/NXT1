/**
 * Track D — Self-Heal Panel (sandboxed bounded retry loop).
 *
 * Drop this on the Builder page; given a project id it streams the
 * self-heal SSE feed showing attempt n/3 + agent-coded phases.
 */
import { useEffect, useRef, useState } from "react";
import { runnerQuickBuild, runnerSelfHealUrl } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { Wrench, Loader2, CheckCircle2, AlertTriangle, Hash, X } from "lucide-react";

const AGENT_COLORS = {
  planner: "#60a5fa",
  architect: "#a78bfa",
  coder: "#22d3ee",
  tester: "#10b981",
  debugger: "#f59e0b",
  devops: "#ec4899",
};

export default function SelfHealPanel({ projectId }) {
  const [events, setEvents] = useState([]);
  const [running, setRunning] = useState(false);
  const [quickBuild, setQuickBuild] = useState(null);
  const [maxAttempts, setMaxAttempts] = useState(3);
  const evtRef = useRef(null);

  useEffect(() => () => {
    if (evtRef.current) {
      try { evtRef.current.close(); } catch { /* ignore */ }
    }
  }, []);

  const startHeal = () => {
    if (!projectId || running) return;
    setEvents([]);
    setRunning(true);
    // We can't set arbitrary headers on EventSource, but the runner SSE doesn't
    // require auth (it's gated by the router-level Depends on the POST endpoint).
    // Instead, use fetch + ReadableStream so we can include the token.
    const url = runnerSelfHealUrl(projectId);
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json",
                 Authorization: `Bearer ${getToken()}` },
      body: JSON.stringify({ max_attempts: maxAttempts }),
    }).then(async (resp) => {
      if (!resp.body) { setRunning(false); return; }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const json = JSON.parse(line.slice(6));
              setEvents((prev) => [...prev, { ...json, _t: Date.now() }]);
            } catch { /* ignore */ }
          }
        }
      }
      setRunning(false);
    }).catch(() => setRunning(false));
  };

  const runQuickBuild = async () => {
    setQuickBuild({ loading: true });
    try {
      const r = await runnerQuickBuild(projectId);
      setQuickBuild(r.data);
    } catch (e) {
      setQuickBuild({ ok: false, error: e?.response?.data?.detail || e.message });
    }
  };

  return (
    <div data-testid="self-heal-panel" className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Wrench className="w-4 h-4" style={{ color: "#f59e0b" }} />
            <span className="mono text-[10px] tracking-[0.30em] uppercase"
                  style={{ color: "var(--nxt-fg-faint)" }}>
              Self-Heal · Sandboxed Build Loop
            </span>
          </div>
          <p className="text-[12px] leading-relaxed max-w-[520px]"
             style={{ color: "var(--nxt-fg-dim)" }}>
            Materialises your files into a fresh tmp sandbox, runs a smoke
            build, and if it fails routes the error to the Debug agent for
            a patch. Bounded retry (max {maxAttempts}) — no impact on running services.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-[11px]" style={{ color: "var(--nxt-fg-faint)" }}>Max attempts</label>
          <select
            value={maxAttempts}
            onChange={(e) => setMaxAttempts(Number(e.target.value))}
            disabled={running}
            data-testid="heal-max-attempts"
            className="text-[11px] px-2 py-1 rounded outline-none"
            style={{
              background: "var(--nxt-surface-hi)",
              border: "1px solid var(--nxt-border)",
              color: "var(--nxt-fg)",
            }}
          >
            {[1,2,3,4,5].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <button
            onClick={runQuickBuild}
            disabled={!projectId || running}
            data-testid="heal-quick-build"
            className="text-[11px] px-3 py-1.5 rounded-full"
            style={{
              color: "var(--nxt-fg-dim)",
              background: "var(--nxt-surface-hi)",
              border: "1px solid var(--nxt-border)",
            }}
          >
            Quick build
          </button>
          <button
            onClick={startHeal}
            disabled={!projectId || running}
            data-testid="heal-start"
            className="text-[11px] px-3 py-1.5 rounded-full flex items-center gap-1"
            style={{
              color: "#f59e0b",
              background: "rgba(245,158,11,0.12)",
              border: "1px solid rgba(245,158,11,0.3)",
            }}
          >
            {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wrench className="w-3 h-3" />}
            {running ? "Healing..." : "Self-heal"}
          </button>
        </div>
      </div>

      {quickBuild && !quickBuild.loading && (
        <div
          className="rounded-lg p-3 text-[11px] flex items-center gap-2"
          data-testid="heal-quick-result"
          style={{
            background: quickBuild.ok ? "rgba(16,185,129,0.08)" : "rgba(239,68,68,0.08)",
            color: quickBuild.ok ? "#86efac" : "#fca5a5",
          }}
        >
          {quickBuild.ok
            ? <CheckCircle2 className="w-3.5 h-3.5" />
            : <AlertTriangle className="w-3.5 h-3.5" />}
          <span className="mono">
            quick build · exit={quickBuild.exit_code} · {quickBuild.duration_ms}ms
            {quickBuild.skipped && " (no build detected)"}
          </span>
        </div>
      )}

      <div className="space-y-1.5" data-testid="heal-events">
        {events.length === 0 && !running && (
          <div className="rounded-lg p-4 text-center text-[12px] border"
               style={{ color: "var(--nxt-fg-dim)", borderColor: "var(--nxt-border)" }}>
            Click <strong>Self-heal</strong> to run the bounded retry loop. Each attempt
            uses an isolated sandbox — your live preview is never touched.
          </div>
        )}
        {events.map((e, i) => (
          <HealEvent key={i} event={e} />
        ))}
        {running && (
          <div className="flex items-center gap-2 text-[11px] py-2"
               style={{ color: "var(--nxt-fg-faint)" }}>
            <Loader2 className="w-3 h-3 animate-spin" /> waiting for next phase...
          </div>
        )}
      </div>
    </div>
  );
}

function HealEvent({ event }) {
  const color = AGENT_COLORS[event.agent] || "#94a3b8";
  const statusIcon = {
    running: <Loader2 className="w-3 h-3 animate-spin" />,
    done: <CheckCircle2 className="w-3 h-3" />,
    failed: <AlertTriangle className="w-3 h-3" />,
    waiting: <Hash className="w-3 h-3" />,
    completed: <CheckCircle2 className="w-3 h-3" />,
  }[event.status] || <Hash className="w-3 h-3" />;
  return (
    <div
      className="rounded-lg px-3 py-2 flex items-start gap-2 text-[11px] border"
      data-testid={`heal-event-${event.phase}`}
      style={{
        background: "var(--nxt-surface)",
        borderColor: event.status === "failed" ? "rgba(239,68,68,0.2)" : "var(--nxt-border)",
      }}
    >
      <span style={{ color }}>{statusIcon}</span>
      <span
        className="mono uppercase tracking-wider px-1.5 py-0.5 rounded text-[9px] flex-shrink-0"
        style={{ color, background: `${color}1a` }}
      >
        {event.agent || "system"}
      </span>
      {event.attempt && (
        <span className="mono text-[9px] flex-shrink-0"
              style={{ color: "var(--nxt-fg-faint)" }}>
          {event.attempt}/{event.max_attempts}
        </span>
      )}
      <span className="flex-1" style={{ color: "var(--nxt-fg-dim)" }}>
        {event.message}
      </span>
      {event.duration_ms && (
        <span className="mono text-[9px]" style={{ color: "var(--nxt-fg-faint)" }}>
          {event.duration_ms}ms
        </span>
      )}
    </div>
  );
}
