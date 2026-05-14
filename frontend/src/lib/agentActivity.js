/**
 * AgentActivityWatcher — mounts once at app root and polls
 *   GET /api/agents/conversations/active every 8s.
 *
 * When an agent transitions from running → finished:
 *   - shows a Sonner toast: "Agent <Name> finished"
 *   - if the browser tab is hidden AND the user granted permission,
 *     fires a native Notification so the result shows up on the lock
 *     screen / notification center.
 *
 * The watcher is intentionally cheap (<1KB JSON, light query, no
 * dependencies on tab focus) so it can run alongside any page.
 *
 * To enable native push: call `requestAgentNotificationPermission()`
 * once from a user gesture (we wire this into a "Notify me" button on
 * the AgentOS Chat tab).
 */
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import api from "@/lib/api";

const POLL_MS = 8_000;

export function useAgentActivityWatcher(enabled = true) {
  const lastRunning = useRef(new Set());
  useEffect(() => {
    if (!enabled) return;
    let cancel = false;
    let token = (() => {
      try { return JSON.parse(localStorage.getItem("nxt1-auth") || "{}").token; }
      catch { return null; }
    })();
    if (!token) return; // not logged in, skip

    const poll = async () => {
      try {
        const { data } = await api.get("/agents/conversations/active");
        if (cancel) return;
        const nowRunning = new Set((data || []).map((c) => c.id));
        // Detect transitions: id was in lastRunning but is no longer running
        for (const id of lastRunning.current) {
          if (!nowRunning.has(id)) {
            // Need to fetch the conversation to learn its name
            api.get(`/agents/conversations/${id}`).then(({ data: conv }) => {
              const name = conv?.item_name || "Agent";
              notifyDone(name);
            }).catch(() => notifyDone("Agent"));
          }
        }
        lastRunning.current = nowRunning;
      } catch { /* network blip, ignore */ }
    };
    poll();
    const t = setInterval(poll, POLL_MS);
    return () => { cancel = true; clearInterval(t); };
  }, [enabled]);
}

function notifyDone(name) {
  // In-app toast (always shown)
  toast.success(`${name} finished`, {
    description: "Tap to open the conversation",
    duration: 6000,
  });
  // Native OS notification (only when tab is hidden + permission granted)
  if (typeof document !== "undefined" && document.hidden &&
      typeof Notification !== "undefined" && Notification.permission === "granted") {
    try {
      new Notification("Agent finished", {
        body: `${name} is done — open NXT1 to see the result.`,
        icon: "/favicon.ico",
        tag: `agent-${name}`,
      });
    } catch { /* some browsers throw if quota exceeded; ignore */ }
  }
}

export async function requestAgentNotificationPermission() {
  if (typeof Notification === "undefined") return "unsupported";
  if (Notification.permission === "granted") return "granted";
  if (Notification.permission === "denied") return "denied";
  try {
    const result = await Notification.requestPermission();
    return result;
  } catch { return "denied"; }
}
