/**
 * NotificationCenter — bell icon + slide-down panel.
 *
 * Replaces the legacy `agentActivity.js` global toast spammer. Polls
 * /api/notifications/list?unread=true every 30s, shows unread count badge,
 * opens a panel on click with the full list. Each notification can be
 * marked-read individually or all at once. Clicking a notification with a
 * `link` navigates to that route.
 *
 * Lives in the workspace header so it's reachable from every page without
 * blocking content (unlike the previous random bottom toasts).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, X, Check, CheckCheck, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";

const POLL_MS = 30_000;

export default function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const panelRef = useRef(null);

  const fetch = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await api.get("/notifications/list", { params: { limit: 30 } });
      setItems(data?.items || []);
      setUnread(data?.unread || 0);
    } catch { /* not signed in or transient */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    fetch();
    const t = setInterval(fetch, POLL_MS);
    return () => clearInterval(t);
  }, [fetch]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const markRead = async (id) => {
    setItems((curr) => curr.map((n) => (n.id === id ? { ...n, read: true } : n)));
    setUnread((u) => Math.max(0, u - 1));
    try { await api.post(`/notifications/${id}/read`); } catch { /* ignore */ }
  };

  const markAllRead = async () => {
    setItems((curr) => curr.map((n) => ({ ...n, read: true })));
    setUnread(0);
    try { await api.post("/notifications/read-all"); } catch { /* ignore */ }
  };

  const onItemClick = async (n) => {
    if (!n.read) await markRead(n.id);
    if (n.link) {
      setOpen(false);
      navigate(n.link);
    }
  };

  return (
    <div className="relative" data-testid="notification-center">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
        data-testid="notification-bell"
        className="relative h-9 w-9 rounded-full inline-flex items-center justify-center transition"
        style={{
          color: "var(--nxt-fg-dim)",
          border: "1px solid var(--nxt-border)",
          background: open ? "var(--nxt-surface)" : "transparent",
        }}
      >
        <Bell size={15} />
        {unread > 0 && (
          <span
            className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] px-1 rounded-full text-[9px] font-bold flex items-center justify-center"
            style={{ background: "var(--nxt-accent)", color: "#0F1117" }}
            data-testid="notification-unread-count"
          >
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          ref={panelRef}
          className="absolute right-0 mt-2 w-[min(380px,calc(100vw-2rem))] rounded-2xl overflow-hidden shadow-2xl z-50"
          style={{
            background: "var(--nxt-bg-2)",
            border: "1px solid var(--nxt-border-strong)",
            maxHeight: "calc(100vh - 100px)",
          }}
          data-testid="notification-panel"
        >
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ borderBottom: "1px solid var(--nxt-border)" }}
          >
            <div className="flex items-center gap-2">
              <Bell size={14} style={{ color: "var(--nxt-fg)" }} />
              <span className="text-[13px] font-semibold" style={{ color: "var(--nxt-fg)" }}>
                Notifications
              </span>
              {unread > 0 && (
                <span className="text-[10px] mono opacity-60">({unread} unread)</span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {unread > 0 && (
                <button
                  type="button"
                  onClick={markAllRead}
                  className="text-[11px] px-2 py-1 rounded-md hover:opacity-80 transition flex items-center gap-1"
                  style={{ color: "var(--nxt-fg-dim)" }}
                  data-testid="notification-mark-all-read"
                  title="Mark all as read"
                >
                  <CheckCheck size={11} />
                </button>
              )}
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="h-7 w-7 rounded-md inline-flex items-center justify-center hover:opacity-80"
                style={{ color: "var(--nxt-fg-dim)" }}
                aria-label="Close"
              >
                <X size={13} />
              </button>
            </div>
          </div>

          <div className="overflow-y-auto" style={{ maxHeight: "calc(100vh - 180px)" }}>
            {loading && items.length === 0 && (
              <div className="px-4 py-8 text-center text-[12px]" style={{ color: "var(--nxt-fg-faint)" }}>
                Loading…
              </div>
            )}
            {!loading && items.length === 0 && (
              <div className="px-4 py-10 text-center" style={{ color: "var(--nxt-fg-faint)" }}>
                <Bell size={20} className="mx-auto mb-2 opacity-40" />
                <p className="text-[12px]">No notifications yet.</p>
                <p className="text-[11px] mt-1 opacity-70">Build, deploy, and social events show up here.</p>
              </div>
            )}
            {items.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => onItemClick(n)}
                data-testid={`notification-item-${n.id}`}
                className="w-full text-left px-4 py-3 flex items-start gap-3 transition hover:opacity-90"
                style={{
                  background: n.read ? "transparent" : "var(--nxt-accent-bg)",
                  borderBottom: "1px solid var(--nxt-border-soft)",
                }}
              >
                <KindDot kind={n.kind} read={n.read} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="text-[12.5px] font-medium truncate"
                      style={{ color: "var(--nxt-fg)" }}
                    >
                      {n.title}
                    </span>
                    {n.link && <ExternalLink size={10} style={{ color: "var(--nxt-fg-faint)" }} />}
                  </div>
                  {n.body && (
                    <p
                      className="text-[11.5px] mt-0.5 line-clamp-2"
                      style={{ color: "var(--nxt-fg-dim)" }}
                    >
                      {n.body}
                    </p>
                  )}
                  <span
                    className="text-[10px] mono mt-1 inline-block opacity-60"
                    style={{ color: "var(--nxt-fg-faint)" }}
                  >
                    {formatRelative(n.created_at)}
                  </span>
                </div>
                {!n.read && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); markRead(n.id); }}
                    className="opacity-0 group-hover:opacity-100 transition h-6 w-6 rounded inline-flex items-center justify-center"
                    style={{ color: "var(--nxt-fg-faint)" }}
                    aria-label="Mark as read"
                    title="Mark as read"
                  >
                    <Check size={11} />
                  </button>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function KindDot({ kind, read }) {
  const colors = {
    build_complete: "#34D399",
    deploy_ready: "#5EEAD4",
    social_generated: "#A78BFA",
    social_posted: "#60A5FA",
    social_failed: "#FB7185",
    build_failed: "#FB7185",
    agent_done: "#FCD34D",
    url_imported: "#7DD3FC",
    system: "var(--nxt-fg-dim)",
  };
  const color = colors[kind] || "var(--nxt-fg-dim)";
  return (
    <span
      className="mt-1 shrink-0 h-2 w-2 rounded-full"
      style={{
        background: color,
        boxShadow: read ? "none" : `0 0 8px ${color}80`,
        opacity: read ? 0.5 : 1,
      }}
    />
  );
}

function formatRelative(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const sec = Math.floor((now - then) / 1000);
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  if (sec < 604800) return `${Math.floor(sec / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}
