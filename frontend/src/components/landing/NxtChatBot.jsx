/**
 * NxtChatBot — Claude-powered visitor chat with structured intake.
 *
 * Flow:
 *   Step 0: greet → "What's your first name?"
 *   Step 1: → "Nice to meet you. What's your last name?"
 *   Step 2: → "And the best email or phone to reach you?"
 *   Step 3: contact info posted to /api/public/nxt-chat/lead → free chat
 *           (Claude assistant; messages persisted; admin can browse leads)
 *
 * Used in two surfaces:
 *   - <NxtChatBot inline />     →  inline card (Contact page, landing section)
 *   - <NxtChatBot floating />   →  bubble in the bottom-right that opens a panel
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { Send, Sparkles, Loader2, MessageCircle, X } from "lucide-react";
import axios from "axios";

const BACKEND = process.env.REACT_APP_BACKEND_URL;
const SESSION_KEY  = "nxt1.public-chat.session";
const INTAKE_KEY   = "nxt1.public-chat.intake";

/* ────────────────────────────────────────────────────────────────────────
   Public API: <NxtChatBot inline /> | <NxtChatBot floating />
   ──────────────────────────────────────────────────────────────────────── */
export default function NxtChatBot({ inline = false, floating = false }) {
  if (floating) return <FloatingShell />;
  return <ChatCard inline={inline} />;
}

/* ────────────────────────────────────────────────────────────────────────
   Floating bubble that follows the user across the site.
   ──────────────────────────────────────────────────────────────────────── */
function FloatingShell() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close chat" : "Open chat"}
        data-testid="nxt-chat-bubble"
        className="fixed z-[60] bottom-4 right-4 sm:bottom-6 sm:right-6 h-12 w-12 rounded-full inline-flex items-center justify-center transition-transform hover:scale-105"
        style={{
          background: "linear-gradient(135deg, #5EEAD4 0%, #0E7490 100%)",
          color: "#0F1117",
          boxShadow: "0 18px 38px -12px rgba(94,234,212,0.45), 0 2px 6px rgba(0,0,0,0.30)",
        }}
      >
        {open ? <X size={18} strokeWidth={2.4} /> : <MessageCircle size={18} strokeWidth={2.2} />}
      </button>

      {open && (
        <div
          className="fixed z-[59] bottom-20 right-4 sm:right-6 w-[min(380px,calc(100vw-2rem))]"
          data-testid="nxt-chat-floating-panel"
        >
          <ChatCard compact />
        </div>
      )}
    </>
  );
}

/* ────────────────────────────────────────────────────────────────────────
   The card itself — inline (big) or compact (floating-panel)
   ──────────────────────────────────────────────────────────────────────── */
function ChatCard({ inline = false, compact = false }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(() => {
    try { return localStorage.getItem(SESSION_KEY) || ""; } catch { return ""; }
  });

  // Intake state (lifted out of LLM — deterministic + reliable)
  const [intake, setIntake] = useState(() => {
    try { return JSON.parse(localStorage.getItem(INTAKE_KEY) || "null") || null; } catch { return null; }
  });
  const [intakeStep, setIntakeStep] = useState(() => (
    (() => { try { return JSON.parse(localStorage.getItem(INTAKE_KEY) || "null"); } catch { return null; } })()
      ? "done"
      : "first_name"  // first_name → last_name → contact → done
  ));
  const [draft, setDraft] = useState({ first_name: "", last_name: "", email: "", phone: "" });

  const listRef = useRef(null);

  useEffect(() => {
    if (sessionId) {
      try { localStorage.setItem(SESSION_KEY, sessionId); } catch { /* ignore */ }
    }
  }, [sessionId]);

  useEffect(() => {
    if (intake) {
      try { localStorage.setItem(INTAKE_KEY, JSON.stringify(intake)); } catch { /* ignore */ }
    }
  }, [intake]);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, intakeStep]);

  /* ── Intake message helpers ─────────────────────────────────────────── */
  const introMessages = useCallback(() => {
    if (intake?.first_name) {
      return [{
        id: "a-welcome-back",
        role: "assistant",
        content: `Welcome back, ${intake.first_name}. What can I help you with today?`,
      }];
    }
    return [{
      id: "a-greet",
      role: "assistant",
      content: "Hey — I'm the NXT One assistant. Before we chat, what's your first name?",
    }];
  }, [intake]);

  useEffect(() => {
    if (messages.length === 0) setMessages(introMessages());
  }, [introMessages, messages.length]);

  /* ── Submit handlers ────────────────────────────────────────────────── */
  const submitIntakeStep = (value) => {
    const v = (value || "").trim();
    if (!v) return;
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", content: v }]);

    if (intakeStep === "first_name") {
      setDraft((d) => ({ ...d, first_name: v }));
      setIntakeStep("last_name");
      setTimeout(() => {
        setMessages((m) => [...m, {
          id: `a-ask-last-${Date.now()}`,
          role: "assistant",
          content: `Nice to meet you, ${v}. What's your last name?`,
        }]);
      }, 350);
    } else if (intakeStep === "last_name") {
      setDraft((d) => ({ ...d, last_name: v }));
      setIntakeStep("contact");
      setTimeout(() => {
        setMessages((m) => [...m, {
          id: `a-ask-contact-${Date.now()}`,
          role: "assistant",
          content: "What's the best email or phone number to reach you?",
        }]);
      }, 350);
    } else if (intakeStep === "contact") {
      // Detect email vs phone
      const isEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
      const isPhone = /^[+()\-\s\d]{7,}$/.test(v) && /\d/.test(v);
      if (!isEmail && !isPhone) {
        setMessages((m) => [...m, {
          id: `a-retry-${Date.now()}`,
          role: "assistant",
          content: "That doesn't look quite right — share an email like name@domain.com or a phone number with at least 7 digits.",
        }]);
        return;
      }
      const next = {
        ...draft,
        email: isEmail ? v.toLowerCase() : "",
        phone: isPhone ? v : "",
      };
      setDraft(next);
      // Persist as a lead — fire-and-forget; chatbot continues regardless
      const payload = {
        email: next.email || `${next.first_name.toLowerCase()}.${next.last_name.toLowerCase()}@unknown.placeholder`,
        first_name: next.first_name,
        last_name: next.last_name,
        phone: next.phone,
        note: "Intake captured before free chat began.",
        session_id: sessionId || null,
        source: "nxt-chat-intake",
      };
      axios.post(`${BACKEND}/api/public/nxt-chat/lead`, payload)
        .catch(() => { /* silent — the convo continues */ });
      setIntake(next);
      setIntakeStep("done");
      setTimeout(() => {
        setMessages((m) => [...m, {
          id: `a-onboarded-${Date.now()}`,
          role: "assistant",
          content: `Got it — thanks, ${next.first_name}. Ask me anything about NXT One, what we build, or how access works.`,
        }]);
      }, 400);
    }
  };

  const submitFreeChat = async (textOverride) => {
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
        body: JSON.stringify({
          message: text,
          session_id: sessionId || null,
          // Server-side system prompt is enough; the intake context is embedded in the convo history.
        }),
      });
      if (!res.ok) throw new Error(await res.text());
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
            if (ev.type === "session" && ev.session_id) setSessionId(ev.session_id);
            else if (ev.type === "chunk" && ev.delta) {
              accumulated += ev.delta;
              const visible = accumulated.replace(/<LEAD>[\s\S]*?(<\/LEAD>|$)/, "");
              setMessages((m) => m.map((x) => (x.id === placeholder.id ? { ...x, content: visible } : x)));
            } else if (ev.type === "done") {
              const cleaned = accumulated.replace(/<LEAD>[\s\S]*?<\/LEAD>/, "").trim();
              setMessages((m) => m.map((x) => (x.id === placeholder.id ? { ...x, content: cleaned, streaming: false } : x)));
            }
          } catch { /* malformed line */ }
        }
      }
    } catch {
      setMessages((m) => m.map((x) => (
        x.id === placeholder.id
          ? { ...x, content: "I couldn't reach the assistant. Try again in a moment.", streaming: false, error: true }
          : x
      )));
    } finally {
      setStreaming(false);
    }
  };

  const onSend = () => {
    if (intakeStep === "done") submitFreeChat();
    else submitIntakeStep(input), setInput("");
  };
  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); }
  };

  /* ── Render ─────────────────────────────────────────────────────────── */
  const cardMaxHeight = compact ? "min(560px, calc(100vh - 140px))" : (inline ? "70vh" : "440px");
  const listMinHeight = compact ? 280 : 260;

  return (
    <section
      id="contact"
      className={inline ? "relative px-6 sm:px-12 py-20 sm:py-28 scroll-mt-20" : "relative"}
      data-testid="nxt-chat"
    >
      <div className={inline ? "mx-auto max-w-[920px]" : ""}>
        {inline && (
          <div className="text-center mb-9">
            <div className="mono text-[10.5px] tracking-[0.28em] uppercase mb-3"
                 style={{ color: "var(--nxt-fg-faint)" }}>
              // talk to nxt
            </div>
            <h2 className="text-[28px] sm:text-[36px] font-semibold tracking-tight leading-[1.05]"
                style={{ color: "var(--nxt-fg)" }}>
              Ask the NXT One assistant
            </h2>
            <p className="mt-3 text-[13.5px] sm:text-[14.5px] leading-relaxed max-w-[480px] mx-auto"
               style={{ color: "var(--nxt-fg-dim)" }}>
              Real conversation — no contact form. Ask about access, what we build, or anything else.
            </p>
          </div>
        )}

        <div
          className="rounded-3xl overflow-hidden flex flex-col"
          style={{
            background: "var(--nxt-surface)",
            border: "1px solid var(--nxt-border-strong)",
            boxShadow: "0 30px 70px -28px rgba(0,0,0,0.55), inset 0 1px 0 var(--nxt-border-soft)",
            backdropFilter: "blur(18px) saturate(140%)",
            WebkitBackdropFilter: "blur(18px) saturate(140%)",
            maxHeight: cardMaxHeight,
          }}
        >
          {/* Header */}
          <div className="flex items-center gap-3 px-5 py-3.5 shrink-0"
               style={{ borderBottom: "1px solid var(--nxt-border)" }}>
            <span className="h-2 w-2 rounded-full"
                  style={{ background: "#34D399", boxShadow: "0 0 10px #34D39980" }} />
            <span className="text-[12.5px] font-medium" style={{ color: "var(--nxt-fg)" }}>
              NXT One Assistant
            </span>
            <span className="ml-auto mono text-[10px] tracking-[0.22em] uppercase"
                  style={{ color: "var(--nxt-fg-faint)" }}>
              Live
            </span>
          </div>

          {/* Messages */}
          <div ref={listRef}
               className="px-5 sm:px-7 py-6 flex-1 overflow-y-auto space-y-4"
               style={{ minHeight: listMinHeight }}
               data-testid="nxt-chat-messages">
            {messages.map((m) => <MessageRow key={m.id} m={m} />)}
            {streaming && (
              <div className="flex items-center gap-2 mono text-[10.5px] tracking-[0.22em] uppercase opacity-60"
                   style={{ color: "var(--nxt-fg-faint)" }}>
                <Loader2 size={11} className="animate-spin" /> Thinking…
              </div>
            )}
          </div>

          {/* Composer */}
          <div className="px-3 sm:px-4 py-3 flex items-center gap-2 shrink-0"
               style={{
                 borderTop: "1px solid var(--nxt-border)",
                 background: "var(--nxt-surface-soft)",
               }}>
            <input
              type={intakeStep === "contact" ? "text" : "text"}
              inputMode={intakeStep === "contact" ? "email" : "text"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={
                intakeStep === "first_name" ? "Your first name…"
                : intakeStep === "last_name" ? "Your last name…"
                : intakeStep === "contact"   ? "Email or phone number…"
                : "Ask anything…"
              }
              disabled={streaming}
              className="flex-1 px-3 py-3 bg-transparent outline-none text-[14px] placeholder:opacity-60"
              style={{ color: "var(--nxt-fg)" }}
              data-testid="nxt-chat-input"
            />
            <button
              type="button"
              onClick={onSend}
              disabled={!input.trim() || streaming}
              className="inline-flex items-center justify-center h-10 w-10 rounded-full transition disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: input.trim() && !streaming ? "var(--nxt-accent)" : "var(--nxt-chip-bg)",
                color: input.trim() && !streaming ? "var(--nxt-bg)" : "var(--nxt-fg-faint)",
                boxShadow: input.trim() && !streaming ? "0 10px 22px -8px rgba(94,234,212,0.40)" : "none",
              }}
              aria-label="Send"
              data-testid="nxt-chat-send"
            >
              {streaming ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} strokeWidth={2.2} />}
            </button>
          </div>
        </div>

        {inline && (
          <p className="text-center mono text-[10.5px] tracking-[0.22em] uppercase mt-5"
             style={{ color: "var(--nxt-fg-faint)" }}>
            Conversations are private · we use them only to improve NXT One
          </p>
        )}
      </div>
    </section>
  );
}

/* ── Atomic bits ──────────────────────────────────────────────────────── */
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
        data-testid={`nxt-chat-msg-${m.role}`}
      >
        {m.content || (m.streaming ? "…" : "")}
      </div>
    </div>
  );
}

function AvatarA() {
  return (
    <div className="shrink-0 h-8 w-8 rounded-full inline-flex items-center justify-center"
         style={{
           background: "linear-gradient(135deg, #5EEAD4 0%, #0E7490 100%)",
           boxShadow: "0 6px 18px -8px rgba(94,234,212,0.55)",
         }} aria-hidden>
      <Sparkles size={14} style={{ color: "#0F1117" }} />
    </div>
  );
}

function AvatarU() {
  return (
    <div className="shrink-0 h-8 w-8 rounded-full inline-flex items-center justify-center"
         style={{
           background: "var(--nxt-chip-bg)",
           border: "1px solid var(--nxt-border-soft)",
           color: "var(--nxt-fg-dim)",
           fontSize: 11,
           fontWeight: 600,
           letterSpacing: "0.04em",
         }} aria-hidden>
      YOU
    </div>
  );
}
