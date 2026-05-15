/**
 * NXT1 Builder — one integrated app.
 *
 *  ┌────────────────────────────────────────────────────────────────┐
 *  │  NXT1 header (back to workspace · brand · bell · open new tab)│
 *  ├──────────────────────────┬─────────────────────────────────────┤
 *  │                          │                                     │
 *  │   NXT1 chat panel        │     bolt.diy Workbench (headless)   │
 *  │   ────────────────       │     ──────────────────────────────  │
 *  │   our wordmark, our      │     Preview / Code / Terminal tabs  │
 *  │   colors, our font.      │     WebContainer live preview.      │
 *  │                          │     File editor.                    │
 *  │   message bubbles        │     Terminal.                       │
 *  │   composer at bottom     │                                     │
 *  │   ("What will you        │     Bolt chrome (header, sidebar,   │
 *  │   build today?")         │     intro, provider picker, chat    │
 *  │                          │     composer) is HIDDEN — bolt is   │
 *  │                          │     driven via window.__nxt1Bolt-   │
 *  │                          │     Bridge from this panel.         │
 *  │                          │                                     │
 *  └──────────────────────────┴─────────────────────────────────────┘
 *
 *  Chat history persists per project in Mongo via `/api/v1/builder/chat/{id}`.
 *  Provider is locked to Anthropic / claude-sonnet-4 inside the iframe.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, ExternalLink, Send, Paperclip, Loader2, Square, RefreshCw } from "lucide-react";
import Brand from "@/components/Brand";
import NotificationCenter from "@/components/NotificationCenter";
import { getToken } from "@/lib/auth";
import { ensureCoiServiceWorker } from "@/lib/webcontainer";

const BOLT_BASE = "/api/bolt-engine/";
const API = process.env.REACT_APP_BACKEND_URL;

function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export default function BuilderPage() {
  const { projectId } = useParams();
  const iframeRef = useRef(null);
  const [iframeReady, setIframeReady] = useState(false);
  const [bridgeReady, setBridgeReady] = useState(false);
  const [coiState, setCoiState] = useState({ active: false, needsReload: false });

  // Bolt's terminal Worker spawn needs SharedArrayBuffer, which requires the
  // *parent* page to be cross-origin-isolated. We install the COI service
  // worker on mount; if it's the first install the tab needs one reload.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await ensureCoiServiceWorker();
        if (!cancelled) setCoiState(s);
      } catch {
        /* fall through — terminal will warn but preview still works */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // ─── Chat state owned by NXT1 ───────────────────────────────────────────
  const [messages, setMessages] = useState([]); // [{id, role, content}]
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const replayedRef = useRef(false);
  const lastBoltCountRef = useRef(0);
  const composerRef = useRef(null);

  // Replay persisted history on mount.
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(`${API}/api/v1/builder/chat/${projectId}`, {
          headers: { ...authHeaders() },
        });
        if (!r.ok) return;
        const j = await r.json();
        if (cancelled) return;
        setMessages(
          (j.messages || []).map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
          })),
        );
      } catch {
        /* ignore — empty history is fine */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // ─── Bridge wiring ───────────────────────────────────────────────────────
  // Bolt installs `window.__nxt1BoltBridge` inside its iframe and posts
  // `nxt1-bolt-messages` events to the parent whenever its message store
  // changes. We mirror those into our `messages` state so the bubbles on the
  // left always reflect what bolt is actually doing under the hood.
  useEffect(() => {
    function onMessage(ev) {
      const data = ev?.data;
      if (!data || typeof data !== "object") return;
      if (data.type === "nxt1-bolt-bridge-ready") {
        setBridgeReady(true);
        return;
      }
      if (data.type === "nxt1-bolt-messages") {
        setIsStreaming(!!data.isLoading);
        // Bolt's last assistant message is the one currently streaming.
        // We replace any assistant message we previously stored from bolt
        // with bolt's authoritative copy, and leave our optimistic user
        // bubbles alone.
        const boltMsgs = Array.isArray(data.messages) ? data.messages : [];
        setMessages((prev) => {
          // Keep all "user" bubbles from prev that bolt hasn't seen yet.
          // Simpler approach: rebuild the visible list from bolt's messages
          // because every send goes through bolt — bolt knows the full
          // conversation.
          if (boltMsgs.length === 0) return prev;
          const cleaned = boltMsgs.map((m) => ({
            id: m.id,
            role: m.role,
            content: stripBoltMetaHeaders(m.content),
          }));
          // Detect new bolt-side messages and persist them to Mongo
          if (cleaned.length > lastBoltCountRef.current) {
            lastBoltCountRef.current = cleaned.length;
            persistHistory(cleaned).catch(() => {});
          }
          return cleaned;
        });
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [projectId]);

  // Also try direct access — same-origin iframe makes this work too.
  useEffect(() => {
    if (!iframeReady) return;
    let id = setInterval(() => {
      try {
        const w = iframeRef.current?.contentWindow;
        if (w && w.__nxt1BoltBridge) {
          setBridgeReady(true);
          clearInterval(id);
        }
      } catch {
        /* cross-origin during early boot — keep polling */
      }
    }, 250);
    return () => clearInterval(id);
  }, [iframeReady]);

  // Replay persisted history into bolt once the bridge is up.
  useEffect(() => {
    if (!bridgeReady || replayedRef.current || messages.length === 0) return;
    const w = iframeRef.current?.contentWindow;
    const bridge = w?.__nxt1BoltBridge;
    if (!bridge) return;
    replayedRef.current = true;
    // We only need to seed the user prompts — bolt will regenerate or render
    // assistant replies from its own store. To avoid re-running the build
    // pipeline we don't currently re-append; the user can manually re-send
    // from our composer if they want bolt to continue.
  }, [bridgeReady, messages]);

  const persistHistory = useCallback(
    async (msgs) => {
      if (!projectId) return;
      try {
        await fetch(`${API}/api/v1/builder/chat/${projectId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ messages: msgs }),
        });
      } catch {
        /* silently swallow — the in-memory state is still correct */
      }
    },
    [projectId],
  );

  const send = useCallback(() => {
    const text = input.trim();
    if (!text) return;
    const w = iframeRef.current?.contentWindow;
    const bridge = w?.__nxt1BoltBridge;
    if (!bridge) {
      // Bolt not ready yet — buffer it on screen and try again shortly.
      const optimistic = { id: `local_${Date.now()}`, role: "user", content: text };
      setMessages((prev) => [...prev, optimistic]);
      setInput("");
      const retry = setInterval(() => {
        const b = iframeRef.current?.contentWindow?.__nxt1BoltBridge;
        if (b) {
          b.append({ role: "user", content: text });
          clearInterval(retry);
        }
      }, 200);
      return;
    }
    bridge.append({ role: "user", content: text });
    setInput("");
    // Composer height reset
    if (composerRef.current) composerRef.current.style.height = "auto";
  }, [input]);

  const stop = useCallback(() => {
    iframeRef.current?.contentWindow?.__nxt1BoltBridge?.stop?.();
  }, []);

  // Build iframe src once. `?headless=1` flips bolt into chrome-less mode.
  const iframeSrc = `${BOLT_BASE}?headless=1${projectId ? `&project=${encodeURIComponent(projectId)}` : ""}`;

  return (
    <div
      className="fixed inset-0 flex flex-col"
      style={{ background: "var(--nxt-bg)", color: "var(--nxt-fg)" }}
      data-testid="builder-page"
    >
      {/* ─── NXT1 header ─────────────────────────────────────────────── */}
      <header
        className="shrink-0 flex items-center justify-between px-3 sm:px-4 h-12"
        style={{
          background: "var(--nxt-bg-2)",
          borderBottom: "1px solid var(--nxt-border)",
        }}
        data-testid="builder-header"
      >
        <div className="flex items-center gap-3">
          <Link
            to="/workspace"
            className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[12.5px] transition"
            style={{
              color: "var(--nxt-fg-dim)",
              border: "1px solid var(--nxt-border-soft)",
            }}
            data-testid="builder-back"
          >
            <ArrowLeft size={13} /> Workspace
          </Link>
          <span className="hidden sm:inline-flex items-center gap-2">
            <Brand size="sm" gradient />
            <span
              className="mono text-[10px] tracking-[0.22em] uppercase"
              style={{ color: "var(--nxt-fg-faint)" }}
            >
              · Builder
            </span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          {coiState.needsReload && (
            <button
              onClick={() => window.location.reload()}
              className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[12px] transition"
              style={{
                color: "#FBBF24",
                border: "1px solid rgba(251, 191, 36, 0.4)",
                background: "rgba(251, 191, 36, 0.08)",
              }}
              data-testid="builder-coi-reload"
              title="Reload once to enable the live preview terminal"
            >
              <RefreshCw size={12} />
              <span className="hidden sm:inline">Reload to enable terminal</span>
            </button>
          )}
          <NotificationCenter />
          <a
            href={iframeSrc}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[12px] transition"
            style={{
              color: "var(--nxt-fg-dim)",
              border: "1px solid var(--nxt-border-soft)",
            }}
            data-testid="builder-open-new-tab"
            title="Open builder in new tab"
          >
            <ExternalLink size={12} />
            <span className="hidden sm:inline">New tab</span>
          </a>
        </div>
      </header>

      {/* ─── Split body ───────────────────────────────────────────────── */}
      <div className="flex-1 flex min-h-0">
        {/* LEFT — NXT1 chat panel */}
        <section
          className="flex flex-col min-h-0 shrink-0"
          style={{
            width: "min(46%, 540px)",
            borderRight: "1px solid var(--nxt-border)",
            background: "var(--nxt-bg)",
          }}
          data-testid="builder-chat-panel"
        >
          <ChatMessages
            messages={messages}
            isStreaming={isStreaming}
            bridgeReady={bridgeReady}
          />
          <Composer
            value={input}
            onChange={setInput}
            onSend={send}
            onStop={stop}
            isStreaming={isStreaming}
            disabled={!bridgeReady}
            innerRef={composerRef}
          />
        </section>

        {/* RIGHT — bolt Workbench (preview / code / terminal). Bolt's chrome
            is hidden via ?headless=1 + the `data-nxt1-headless='1'` flag on
            the iframe's <html>. */}
        <section
          className="flex-1 min-h-0 relative"
          style={{ background: "#0F1117" }}
          data-testid="builder-workbench-panel"
        >
          {!iframeReady && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="mono text-[11px] tracking-[0.24em] uppercase opacity-60">
                Loading workbench…
              </div>
            </div>
          )}
          <iframe
            ref={iframeRef}
            src={iframeSrc}
            title="NXT1 Builder Workbench"
            allow="cross-origin-isolated; clipboard-read; clipboard-write"
            credentialless="true"
            onLoad={() => setIframeReady(true)}
            className="w-full h-full border-0"
            data-testid="builder-iframe"
          />
        </section>
      </div>
    </div>
  );
}

/**
 * Strip bolt's `[Model: …]\n\n[Provider: …]\n\n` prefix from user messages so
 * the bubbles look clean inside our chat. Bolt embeds those tags so the
 * server can route to the right provider — they're not meant for display.
 */
function stripBoltMetaHeaders(content) {
  if (typeof content !== "string") return content;
  return content
    .replace(/^\[Model: [^\]]+\]\n\n/, "")
    .replace(/^\[Provider: [^\]]+\]\n\n/, "")
    .replace(/^\[Model: [^\]]+\]\n\n\[Provider: [^\]]+\]\n\n/, "");
}

function ChatMessages({ messages, isStreaming, bridgeReady }) {
  const scrollRef = useRef(null);
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming]);

  if (messages.length === 0) {
    return (
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto px-6 py-10"
        data-testid="builder-chat-empty"
      >
        <div className="max-w-md mx-auto text-center mt-[6vh]">
          <div
            className="mono text-[10px] tracking-[0.28em] uppercase mb-3"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            Good morning, admin.
          </div>
          <h1
            className="text-3xl sm:text-4xl font-semibold leading-tight"
            style={{ color: "var(--nxt-fg)" }}
          >
            What will you build today?
          </h1>
          <p
            className="mt-4 text-[13.5px] leading-relaxed"
            style={{ color: "var(--nxt-fg-dim)" }}
          >
            Describe an app, paste a brief, or attach a screenshot. NXT1 will
            scaffold it in the workbench on the right.
          </p>
          {!bridgeReady && (
            <div
              className="mt-6 inline-flex items-center gap-2 text-[11px] mono uppercase tracking-[0.2em]"
              style={{ color: "var(--nxt-fg-faint)" }}
            >
              <Loader2 size={12} className="animate-spin" />
              Booting engine…
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className="flex-1 min-h-0 overflow-y-auto px-4 py-5 space-y-3"
      data-testid="builder-chat-messages"
    >
      {messages.map((m, i) => (
        <Bubble key={m.id || i} role={m.role} content={m.content} />
      ))}
      {isStreaming && (
        <div
          className="flex items-center gap-2 px-1 pt-1"
          style={{ color: "var(--nxt-fg-faint)" }}
          data-testid="builder-chat-streaming"
        >
          <Loader2 size={12} className="animate-spin" />
          <span className="mono text-[10px] tracking-[0.22em] uppercase">
            Thinking…
          </span>
        </div>
      )}
    </div>
  );
}

function Bubble({ role, content }) {
  const isUser = role === "user";
  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
      data-testid={`builder-chat-bubble-${role}`}
    >
      <div
        className="max-w-[88%] rounded-lg px-3 py-2 text-[13.5px] leading-relaxed whitespace-pre-wrap"
        style={
          isUser
            ? {
                background: "var(--nxt-bg-2)",
                border: "1px solid var(--nxt-border)",
                color: "var(--nxt-fg)",
              }
            : {
                background: "transparent",
                color: "var(--nxt-fg-dim)",
              }
        }
      >
        {content}
      </div>
    </div>
  );
}

function Composer({ value, onChange, onSend, onStop, isStreaming, disabled, innerRef }) {
  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };
  const autoResize = (el) => {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  };
  return (
    <div
      className="shrink-0 px-4 pb-4 pt-2"
      style={{
        background: "var(--nxt-bg)",
        borderTop: "1px solid var(--nxt-border)",
      }}
    >
      <div
        className="rounded-xl"
        style={{
          background: "var(--nxt-bg-2)",
          border: "1px solid var(--nxt-border-soft)",
        }}
      >
        <textarea
          ref={(el) => {
            if (innerRef) innerRef.current = el;
          }}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            autoResize(e.target);
          }}
          onKeyDown={handleKey}
          placeholder="What will you build today?"
          rows={2}
          className="w-full bg-transparent resize-none px-3 py-2.5 text-[14px] leading-relaxed focus:outline-none"
          style={{
            color: "var(--nxt-fg)",
            minHeight: "60px",
            maxHeight: "220px",
          }}
          data-testid="builder-composer-input"
          disabled={disabled && !value}
        />
        <div className="flex items-center justify-between px-2.5 pb-2.5 pt-1">
          <button
            type="button"
            className="inline-flex items-center justify-center w-8 h-8 rounded-md transition"
            style={{ color: "var(--nxt-fg-faint)" }}
            title="Attach (coming soon)"
            data-testid="builder-composer-attach"
            disabled
          >
            <Paperclip size={14} />
          </button>
          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              className="inline-flex items-center justify-center w-9 h-9 rounded-md transition"
              style={{
                background: "var(--nxt-border-soft)",
                color: "var(--nxt-fg)",
              }}
              data-testid="builder-composer-stop"
              title="Stop"
            >
              <Square size={14} />
            </button>
          ) : (
            <button
              type="button"
              onClick={onSend}
              disabled={!value.trim() || disabled}
              className="inline-flex items-center justify-center w-9 h-9 rounded-md transition disabled:opacity-40 disabled:cursor-not-allowed"
              style={{
                background:
                  !value.trim() || disabled
                    ? "var(--nxt-border-soft)"
                    : "#3B82F6",
                color: !value.trim() || disabled ? "var(--nxt-fg-dim)" : "#FFFFFF",
              }}
              data-testid="builder-composer-send"
              title="Send"
            >
              <Send size={14} />
            </button>
          )}
        </div>
      </div>
      <div
        className="mt-2 mono text-[9.5px] uppercase tracking-[0.22em] text-center"
        style={{ color: "var(--nxt-fg-faint)" }}
      >
        Claude Sonnet 4 · locked
      </div>
    </div>
  );
}
