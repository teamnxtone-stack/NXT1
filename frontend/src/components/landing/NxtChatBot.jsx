/**
 * NxtChatBot — premium Claude-powered public chat surface on the landing page.
 *
 * Replaces the legacy "contact form" with a real conversation. Visitors can
 * ask anything about NXT One, learn what we build, and request access — the
 * assistant captures their lead inline.
 *
 * Design notes:
 *   • Premium dark surface, glass-morphism card, generous spacing
 *   • Live streaming response (SSE from /api/public/nxt-chat/message)
 *   • Session-stable: session_id stored in localStorage so the convo persists
 *   • Honours the `<LEAD>{...}</LEAD>` machine-readable trailer the model emits
 *     after collecting email + note, and POSTs it to /api/public/nxt-chat/lead
 */
import { useEffect, useRef, useState } from "react";
import { Send, Sparkles, Loader2 } from "lucide-react";
import axios from "axios";

const BACKEND = process.env.REACT_APP_BACKEND_URL;
const SESSION_KEY = "nxt1.public-chat.session";

const STARTERS = [
  "What does NXT One do?",
  "Who is this for?",
  "How does a build actually work?",
  "I want to request access.",
];

export default function NxtChatBot() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(() => {
    try { return localStorage.getItem(SESSION_KEY) || ""; } catch { return ""; }
  });
  const listRef = useRef(null);

  useEffect(() => {
    if (sessionId) {
      try { localStorage.setItem(SESSION_KEY, sessionId); } catch { /* ignore */ }
    }
  }, [sessionId]);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages]);

  // Strip the model's hidden <LEAD>{...}</LEAD> trailer + POST it as a lead.
  const extractLead = async (text) => {
    const m = text.match(/<LEAD>([\s\S]*?)<\/LEAD>/);
    if (!m) return { cleaned: text, lead: null };
    let lead = null;
    try { lead = JSON.parse(m[1]); } catch { /* ignore */ }
    const cleaned = text.replace(/<LEAD>[\s\S]*?<\/LEAD>/, "").trim();
    if (lead && lead.email) {
      try {
        await axios.post(`${BACKEND}/api/public/nxt-chat/lead`, {
          email: lead.email,
          note: lead.note || "",
          session_id: sessionId || null,
          source: "nxt-chat",
        });
      } catch { /* swallow — the model already acknowledged to the user */ }
    }
    return { cleaned, lead };
  };

  const send = async (textOverride) => {
    const text = (textOverride ?? input).trim();
    if (!text || streaming) return;
    setInput("");
    const userMsg = { id: `u-${Date.now()}`, role: "user", content: text };
    const placeholder = { id: `a-${Date.now()}`, role: "assistant", content: "", streaming: true };
    setMessages((m) => [...m, userMsg, placeholder]);
    setStreaming(true);

    try {
      const res = await fetch(`${BACKEND}/api/public/nxt-chat/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId || null }),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || `HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulated = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const ev = JSON.parse(line.slice(6));
            if (ev.type === "session" && ev.session_id) {
              setSessionId(ev.session_id);
            } else if (ev.type === "chunk" && ev.delta) {
              accumulated += ev.delta;
              const visible = accumulated.replace(/<LEAD>[\s\S]*?(<\/LEAD>|$)/, "");
              setMessages((m) => m.map((x) => (
                x.id === placeholder.id ? { ...x, content: visible } : x
              )));
            } else if (ev.type === "done") {
              const { cleaned } = await extractLead(accumulated);
              setMessages((m) => m.map((x) => (
                x.id === placeholder.id ? { ...x, content: cleaned, streaming: false } : x
              )));
            }
          } catch { /* malformed line, ignore */ }
        }
      }
    } catch (e) {
      setMessages((m) => m.map((x) => (
        x.id === placeholder.id
          ? { ...x, content: "I couldn't reach the assistant. Try again in a moment.", streaming: false, error: true }
          : x
      )));
    } finally {
      setStreaming(false);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <section
      id="contact"
      className="relative px-6 sm:px-12 py-20 sm:py-28 scroll-mt-20"
      data-testid="landing-nxt-chat"
    >
      <div className="mx-auto max-w-[920px]">
        <div className="text-center mb-9">
          <div
            className="mono text-[10.5px] tracking-[0.28em] uppercase mb-3"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            // talk to nxt
          </div>
          <h2
            className="text-[28px] sm:text-[36px] font-semibold tracking-tight leading-[1.05]"
            style={{ color: "var(--nxt-fg)" }}
          >
            Ask the NXT One assistant
          </h2>
          <p
            className="mt-3 text-[13.5px] sm:text-[14.5px] leading-relaxed max-w-[480px] mx-auto"
            style={{ color: "var(--nxt-fg-dim)" }}
          >
            Powered by Claude. Ask about the platform, what we build, or request access.
          </p>
        </div>

        <div
          className="rounded-3xl overflow-hidden"
          style={{
            background: "var(--nxt-surface)",
            border: "1px solid var(--nxt-border-strong)",
            boxShadow: "0 30px 70px -28px rgba(0,0,0,0.55), inset 0 1px 0 var(--nxt-border-soft)",
            backdropFilter: "blur(18px) saturate(140%)",
            WebkitBackdropFilter: "blur(18px) saturate(140%)",
          }}
        >
          {/* Header strip */}
          <div
            className="flex items-center gap-3 px-5 py-3.5"
            style={{ borderBottom: "1px solid var(--nxt-border)" }}
          >
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: "#34D399", boxShadow: "0 0 10px #34D39980" }}
            />
            <span
              className="text-[12.5px] font-medium"
              style={{ color: "var(--nxt-fg)" }}
            >
              NXT One Assistant
            </span>
            <span
              className="ml-auto mono text-[10px] tracking-[0.22em] uppercase"
              style={{ color: "var(--nxt-fg-faint)" }}
            >
              Claude · live
            </span>
          </div>

          {/* Message list */}
          <div
            ref={listRef}
            className="px-5 sm:px-7 py-6 min-h-[260px] max-h-[440px] overflow-y-auto space-y-4"
            data-testid="landing-nxt-chat-messages"
          >
            {messages.length === 0 && (
              <div className="flex items-start gap-3">
                <AvatarA />
                <div>
                  <p className="text-[14px] leading-relaxed" style={{ color: "var(--nxt-fg)" }}>
                    Hey — I'm the NXT One assistant. Ask me what we build, who we're built for,
                    or tell me you want access and I'll get you on the list.
                  </p>
                </div>
              </div>
            )}

            {messages.map((m) => (
              <MessageRow key={m.id} m={m} />
            ))}
          </div>

          {/* Starters */}
          {messages.length === 0 && (
            <div
              className="px-5 sm:px-7 pb-4 flex flex-wrap gap-2"
              data-testid="landing-nxt-chat-starters"
            >
              {STARTERS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  className="text-[11.5px] px-3 py-1.5 rounded-full transition hover:-translate-y-0.5"
                  style={{
                    background: "var(--nxt-chip-bg)",
                    border: "1px solid var(--nxt-border-soft)",
                    color: "var(--nxt-fg-dim)",
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Composer */}
          <div
            className="px-3 sm:px-4 py-3 flex items-center gap-2"
            style={{
              borderTop: "1px solid var(--nxt-border)",
              background: "var(--nxt-surface-soft)",
            }}
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask anything…"
              disabled={streaming}
              className="flex-1 px-3 py-3 bg-transparent outline-none text-[14px] placeholder:opacity-60"
              style={{ color: "var(--nxt-fg)" }}
              data-testid="landing-nxt-chat-input"
            />
            <button
              type="button"
              onClick={() => send()}
              disabled={!input.trim() || streaming}
              className="inline-flex items-center justify-center h-10 w-10 rounded-full transition disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: input.trim() && !streaming ? "var(--nxt-accent)" : "var(--nxt-chip-bg)",
                color: input.trim() && !streaming ? "var(--nxt-bg)" : "var(--nxt-fg-faint)",
                boxShadow: input.trim() && !streaming ? "0 10px 22px -8px rgba(94,234,212,0.40)" : "none",
              }}
              aria-label="Send"
              data-testid="landing-nxt-chat-send"
            >
              {streaming ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} strokeWidth={2.2} />}
            </button>
          </div>
        </div>

        <p
          className="text-center mono text-[10.5px] tracking-[0.22em] uppercase mt-5"
          style={{ color: "var(--nxt-fg-faint)" }}
        >
          Conversations are private · we use them only to improve NXT One
        </p>
      </div>
    </section>
  );
}

function MessageRow({ m }) {
  const isUser = m.role === "user";
  return (
    <div className={`flex items-start gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {isUser ? <AvatarU /> : <AvatarA />}
      <div
        className={`rounded-2xl px-4 py-2.5 max-w-[78%] text-[14px] leading-relaxed whitespace-pre-wrap ${m.streaming ? "nxt-cursor" : ""}`}
        style={
          isUser
            ? {
                background: "var(--nxt-accent)",
                color: "var(--nxt-bg)",
                borderTopRightRadius: 6,
              }
            : {
                background: "var(--nxt-surface-soft)",
                color: "var(--nxt-fg)",
                border: "1px solid var(--nxt-border-soft)",
                borderTopLeftRadius: 6,
              }
        }
        data-testid={`landing-nxt-chat-msg-${m.role}`}
      >
        {m.content || (m.streaming ? "…" : "")}
      </div>
    </div>
  );
}

function AvatarA() {
  return (
    <div
      className="shrink-0 h-8 w-8 rounded-full inline-flex items-center justify-center"
      style={{
        background: "linear-gradient(135deg, #5EEAD4 0%, #0E7490 100%)",
        boxShadow: "0 6px 18px -8px rgba(94,234,212,0.55)",
      }}
      aria-hidden
    >
      <Sparkles size={14} style={{ color: "#0F1117" }} />
    </div>
  );
}

function AvatarU() {
  return (
    <div
      className="shrink-0 h-8 w-8 rounded-full inline-flex items-center justify-center"
      style={{
        background: "var(--nxt-chip-bg)",
        border: "1px solid var(--nxt-border-soft)",
        color: "var(--nxt-fg-dim)",
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.04em",
      }}
      aria-hidden
    >
      YOU
    </div>
  );
}
