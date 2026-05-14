/**
 * Connections + Autopilot — drop-in panel for SocialPage's left aside.
 *
 * Connections: list IG / X / LinkedIn with Connect / Disconnect.
 *   - "Connect" opens the OAuth URL in a new tab; on success the platform
 *     redirects back to /workspace/social?connected=… and we refresh the list.
 *   - Disabled if the server doesn't have client_id / secret yet — shows a
 *     "Server creds not configured" hint that mirrors what the backend says.
 *
 * Autopilot: toggle + weekly cadence (day + hour) + brief.
 *   - Saved server-side; the background scheduler reads it every minute.
 */
import { useEffect, useState, useCallback } from "react";
import {
  Instagram, Linkedin, Twitter, Check, X, Clock,
  Loader2, Plug, Sparkles, RefreshCw,
} from "lucide-react";
import {
  socialListConnections, socialDisconnect, socialOAuthStart,
  socialGetAutopilot, socialSetAutopilot,
} from "@/lib/api";

const ICONS = { instagram: Instagram, linkedin: Linkedin, twitter: Twitter };
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function ConnectionsAndAutopilot() {
  const [conns, setConns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");

  const [ap, setAp] = useState(null);
  const [apSaving, setApSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [c, a] = await Promise.all([socialListConnections(), socialGetAutopilot()]);
      setConns(c.data.items || []);
      setAp(a.data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Re-fetch when the user comes back from an OAuth redirect (?connected=...)
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    if (p.get("connected")) {
      // strip the query string then refresh
      const url = window.location.pathname;
      window.history.replaceState({}, "", url);
      refresh();
    }
  }, [refresh]);

  const onConnect = async (platform) => {
    setBusyId(platform);
    try {
      const { data } = await socialOAuthStart(platform);
      window.open(data.auth_url, "_blank", "noopener,noreferrer");
    } catch (e) {
      alert(e?.response?.data?.detail || "Could not start OAuth");
    } finally {
      setBusyId("");
    }
  };

  const onDisconnect = async (platform) => {
    if (!confirm(`Disconnect ${platform}?`)) return;
    setBusyId(platform);
    try {
      await socialDisconnect(platform);
      await refresh();
    } finally {
      setBusyId("");
    }
  };

  const updateAp = async (patch) => {
    const next = { ...(ap || {}), ...patch };
    setAp(next);
    setApSaving(true);
    try {
      await socialSetAutopilot({
        enabled: !!next.enabled,
        brief: next.brief || "",
        tone: next.tone || "professional",
        platforms: next.platforms || ["linkedin", "twitter"],
        duration: next.duration || "this week",
        cadence_day: Number(next.cadence_day ?? 1),
        cadence_hour: Number(next.cadence_hour ?? 9),
      });
    } finally {
      setApSaving(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="social-connections-panel">
      {/* CONNECTIONS */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <span className="mono text-[10.5px] tracking-[0.2em] uppercase"
                style={{ color: "var(--nxt-text-3)" }}>
            Connected accounts
          </span>
          <button
            type="button"
            onClick={refresh}
            className="text-[10.5px] inline-flex items-center gap-1 opacity-70 hover:opacity-100"
            style={{ color: "var(--nxt-fg-dim)" }}
            data-testid="social-conn-refresh"
          >
            <RefreshCw size={10} /> Refresh
          </button>
        </div>
        <div className="space-y-1.5">
          {loading && (
            <div className="py-4 text-center text-[12px]"
                 style={{ color: "var(--nxt-text-3)" }}>
              <Loader2 size={14} className="inline animate-spin mr-1" /> Loading…
            </div>
          )}
          {!loading && conns.map((c) => {
            const Icon = ICONS[c.platform] || Plug;
            const isConnected = !!c.connected;
            const isConfigured = !!c.configured;
            const busy = busyId === c.platform;
            return (
              <div
                key={c.platform}
                className="flex items-center gap-2 px-2.5 py-2 rounded-lg"
                style={{
                  background: "var(--nxt-surface)",
                  border: "1px solid var(--nxt-border)",
                }}
                data-testid={`social-conn-row-${c.platform}`}
              >
                <span
                  className="h-7 w-7 rounded-full grid place-items-center shrink-0"
                  style={{
                    background: isConnected ? "var(--nxt-accent)" : "var(--nxt-surface-3)",
                    color: isConnected ? "#0F1117" : "var(--nxt-fg-dim)",
                  }}
                >
                  <Icon size={13} />
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-[12.5px] truncate" style={{ color: "var(--nxt-fg)" }}>
                    {c.label}
                  </div>
                  <div className="text-[10.5px] truncate"
                       style={{ color: isConnected ? "var(--nxt-success)" : "var(--nxt-text-3)" }}>
                    {isConnected
                      ? (c.account_name || "Connected")
                      : isConfigured ? "Not connected" : "Server creds not configured"}
                  </div>
                </div>
                {isConnected ? (
                  <button
                    type="button"
                    onClick={() => onDisconnect(c.platform)}
                    disabled={busy}
                    data-testid={`social-disconnect-${c.platform}`}
                    className="text-[11px] px-2 py-1 rounded-md transition disabled:opacity-50"
                    style={{ color: "var(--nxt-error)" }}
                  >
                    {busy ? <Loader2 size={11} className="animate-spin" /> : "Disconnect"}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => onConnect(c.platform)}
                    disabled={!isConfigured || busy}
                    data-testid={`social-connect-${c.platform}`}
                    className="text-[11px] px-2.5 py-1 rounded-md transition disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{
                      background: "var(--nxt-accent)",
                      color: "#0F1117",
                      fontWeight: 500,
                    }}
                  >
                    {busy ? <Loader2 size={11} className="animate-spin" /> : "Connect"}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* AUTOPILOT */}
      {ap && (
        <section>
          <div className="flex items-center justify-between mb-2">
            <span className="mono text-[10.5px] tracking-[0.2em] uppercase"
                  style={{ color: "var(--nxt-text-3)" }}>
              <Sparkles size={10} className="inline mr-1" /> Weekly autopilot
            </span>
            {apSaving && <Loader2 size={11} className="animate-spin opacity-70" />}
          </div>
          <div
            className="rounded-lg p-3 space-y-3"
            style={{
              background: "var(--nxt-surface)",
              border: "1px solid var(--nxt-border)",
            }}
          >
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={!!ap.enabled}
                onChange={(e) => updateAp({ enabled: e.target.checked })}
                data-testid="autopilot-toggle"
                className="accent-current h-4 w-4"
              />
              <span className="text-[12.5px]" style={{ color: "var(--nxt-fg)" }}>
                Auto-generate a week of content every week
              </span>
            </label>

            <div>
              <span className="block text-[10px] mb-1 mono tracking-[0.16em] uppercase"
                    style={{ color: "var(--nxt-text-3)" }}>Brief</span>
              <textarea
                rows={2}
                value={ap.brief || ""}
                onChange={(e) => setAp((p) => ({ ...p, brief: e.target.value }))}
                onBlur={() => updateAp({})}
                placeholder="What kind of content should auto-pilot create each week?"
                data-testid="autopilot-brief"
                className="w-full bg-transparent outline-none text-[12.5px] py-2 px-2.5 rounded resize-none"
                style={{
                  background: "var(--nxt-bg-2)",
                  border: "1px solid var(--nxt-border)",
                  color: "var(--nxt-fg)",
                }}
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="block text-[10px] mb-1 mono tracking-[0.16em] uppercase"
                      style={{ color: "var(--nxt-text-3)" }}>Day</span>
                <select
                  value={ap.cadence_day ?? 1}
                  onChange={(e) => updateAp({ cadence_day: e.target.value })}
                  data-testid="autopilot-day"
                  className="w-full text-[12px] py-1.5 px-2 rounded outline-none"
                  style={{
                    background: "var(--nxt-bg-2)",
                    border: "1px solid var(--nxt-border)",
                    color: "var(--nxt-fg)",
                  }}
                >
                  {DAY_NAMES.map((n, i) => <option key={i} value={i}>{n}</option>)}
                </select>
              </div>
              <div>
                <span className="block text-[10px] mb-1 mono tracking-[0.16em] uppercase"
                      style={{ color: "var(--nxt-text-3)" }}>Hour</span>
                <select
                  value={ap.cadence_hour ?? 9}
                  onChange={(e) => updateAp({ cadence_hour: e.target.value })}
                  data-testid="autopilot-hour"
                  className="w-full text-[12px] py-1.5 px-2 rounded outline-none"
                  style={{
                    background: "var(--nxt-bg-2)",
                    border: "1px solid var(--nxt-border)",
                    color: "var(--nxt-fg)",
                  }}
                >
                  {Array.from({ length: 24 }, (_, h) => (
                    <option key={h} value={h}>
                      {String(h).padStart(2, "0")}:00 UTC
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {ap.last_run_at && (
              <div className="text-[10.5px] flex items-center gap-1.5"
                   style={{ color: "var(--nxt-text-3)" }}>
                <Clock size={10} /> Last run: {new Date(ap.last_run_at).toLocaleString()}
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
