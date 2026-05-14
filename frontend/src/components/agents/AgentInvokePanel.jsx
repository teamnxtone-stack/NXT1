/**
 * AgentInvokePanel — persistent chat with one agent.
 *
 * 2026-05-13: rewritten to use the new server-side conversation
 * persistence (`/api/agents/conversations/...`). Every turn is saved
 * to Mongo immediately; nothing is lost on refresh, page-leave, or
 * Stop. A left rail lists every prior thread for the same agent so
 * the user can jump back to anything.
 */
import { useEffect, useRef, useState } from "react";
import {
  X, Send, Loader2, Cpu, Sparkles, Copy, Check, MessageSquare,
  Plus, Square, Trash2,
} from "lucide-react";
import api from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";

export default function AgentInvokePanel({ open, item, onClose }) {
  const { theme } = useTheme();
  const isLight = theme === "light";

  // Catalog item with system_prompt (fetched once per open).
  const [detail, setDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Threads for this agent (left rail).
  const [threads, setThreads] = useState([]);
  const [loadingThreads, setLoadingThreads] = useState(false);

  // Currently-open thread.
  const [conv, setConv] = useState(null);          // {id, title, messages: [...]}
  const [loadingConv, setLoadingConv] = useState(false);

  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [copied, setCopied] = useState(false);
  const abortRef = useRef(null);
  const bottomRef = useRef(null);

  const Icon = item?.kind === "agent" ? Cpu : Sparkles;
  const accent = isLight ? "#0E7C66" : "#5EEAD4";

  // Boot — fetch catalog detail + thread list when opened.
  useEffect(() => {
    if (!open || !item) return;
    setConv(null);
    setInput("");
    setDetail(null);
    setLoadingDetail(true);
    setLoadingThreads(true);

    api.get(`/agents/catalog/item/${item.id}`)
      .then((r) => setDetail(r.data))
      .catch(() => setDetail({ ...item, system_prompt: "" }))
      .finally(() => setLoadingDetail(false));

    api.get(`/agents/conversations/by-agent/${item.id}`)
      .then((r) => {
        setThreads(r.data || []);
        // Auto-open the most recent thread; if none, leave conv=null
        // so the empty state shows.
        if (r.data?.length) openThread(r.data[0].id);
      })
      .catch(() => setThreads([]))
      .finally(() => setLoadingThreads(false));

    return () => {
      try { abortRef.current?.abort(); } catch { /* ignore */ }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, item?.id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conv?.messages, streaming]);

  if (!open || !item) return null;

  const openThread = async (cid) => {
    setLoadingConv(true);
    try {
      const r = await api.get(`/agents/conversations/${cid}`);
      setConv(r.data);
    } catch {
      setConv(null);
    } finally {
      setLoadingConv(false);
    }
  };

  const newThread = async () => {
    try {
      const r = await api.post("/agents/conversations", { item_id: item.id });
      setConv({ ...r.data, messages: [] });
      setThreads((prev) => [r.data, ...prev]);
    } catch { /* ignore */ }
  };

  const deleteThread = async (cid) => {
    try {
      await api.delete(`/agents/conversations/${cid}`);
      setThreads((prev) => prev.filter((t) => t.id !== cid));
      if (conv?.id === cid) setConv(null);
    } catch { /* ignore */ }
  };

  const stop = () => {
    try { abortRef.current?.abort(); } catch { /* ignore */ }
    setStreaming(false);
  };

  const submit = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    // Ensure we have a conversation. If not, create one inline first.
    let activeConv = conv;
    if (!activeConv) {
      try {
        const r = await api.post("/agents/conversations", {
          item_id: item.id,
          // First-line of the user's prompt becomes the thread title.
          title: text.split(/\n+/)[0].slice(0, 60),
        });
        activeConv = { ...r.data, messages: [] };
        setConv(activeConv);
        setThreads((prev) => [r.data, ...prev]);
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn("create conversation failed", e);
        return;
      }
    }

    setInput("");
    // Optimistic: push user + a placeholder assistant message.
    setConv((c) => ({
      ...c,
      messages: [
        ...(c?.messages || []),
        { id: `tmp-u-${Date.now()}`, role: "user", content: text },
        { id: `tmp-a-${Date.now()}`, role: "assistant", content: "" },
      ],
    }));
    setStreaming(true);

    abortRef.current = new AbortController();
    let buf = "";
    try {
      const token = localStorage.getItem("nxt1.token") || "";
      const r = await fetch(
        `${api.defaults.baseURL}/agents/conversations/${activeConv.id}/invoke`,
        {
          method: "POST",
          signal: abortRef.current.signal,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ message: text }),
        },
      );
      if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`);
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        setConv((c) => {
          if (!c) return c;
          const out = c.messages.slice();
          out[out.length - 1] = { ...out[out.length - 1], content: buf };
          return { ...c, messages: out };
        });
      }
    } catch (e) {
      if (e?.name !== "AbortError") {
        setConv((c) => {
          if (!c) return c;
          const out = c.messages.slice();
          out[out.length - 1] = {
            ...out[out.length - 1],
            content: (out[out.length - 1]?.content || "") + `\n\n[Failed: ${e?.message || e}]`,
          };
          return { ...c, messages: out };
        });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
      // Refresh the canonical conversation from the server — guarantees
      // the persisted messages have their real ids + timestamps even
      // if we stopped mid-stream.
      if (activeConv?.id) {
        try {
          const r = await api.get(`/agents/conversations/${activeConv.id}`);
          setConv(r.data);
        } catch { /* ignore */ }
        // And refresh the thread list (updated_at moved this thread up).
        try {
          const r = await api.get(`/agents/conversations/by-agent/${item.id}`);
          setThreads(r.data || []);
        } catch { /* ignore */ }
      }
    }
  };

  const onCopyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(detail?.system_prompt || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* ignore */ }
  };

  const messages = conv?.messages || [];

  return (
    <div
      className="fixed inset-0 z-50 flex"
      role="dialog"
      aria-modal="true"
      data-testid="agent-invoke-panel"
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0"
        style={{ background: "rgba(0,0,0,0.55)", backdropFilter: "blur(2px)" }}
        data-testid="agent-invoke-backdrop"
      />
      {/* Sheet */}
      <aside
        className="ml-auto h-full w-full sm:w-[760px] flex relative"
        style={{
          background: isLight ? "#F4EFE3" : "#0B0B0C",
          color: "var(--nxt-fg)",
          boxShadow: "0 0 60px rgba(0,0,0,0.5)",
        }}
        data-testid="agent-invoke-sheet"
      >
        {/* ─── Threads rail ─── */}
        <div
          className="hidden sm:flex flex-col w-[200px] shrink-0"
          style={{ borderRight: "1px solid var(--nxt-border-soft)" }}
        >
          <div className="px-3 py-3" style={{ borderBottom: "1px solid var(--nxt-border-soft)" }}>
            <button
              type="button"
              onClick={newThread}
              className="w-full inline-flex items-center justify-center gap-2 h-9 rounded-lg transition"
              style={{
                background: isLight ? "#1F1F23" : "#FFFFFF",
                color: isLight ? "#FAFAFA" : "#1F1F23",
              }}
              data-testid="agent-invoke-new-thread"
            >
              <Plus size={12} />
              <span className="text-[12px] font-medium tracking-tight">New chat</span>
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-2 py-2">
            <div
              className="mono text-[9.5px] tracking-[0.30em] uppercase px-2 mb-1"
              style={{ color: "var(--nxt-fg-faint)" }}
            >
              History · {threads.length}
            </div>
            {loadingThreads ? (
              <div className="px-2 py-3 mono text-[11px] flex items-center gap-2"
                   style={{ color: "var(--nxt-fg-dim)" }}>
                <Loader2 size={11} className="animate-spin" /> Loading…
              </div>
            ) : threads.length === 0 ? (
              <p
                className="px-2 py-3 text-[11.5px] leading-snug"
                style={{ color: "var(--nxt-fg-faint)" }}
              >
                No prior chats. Type below to start one.
              </p>
            ) : (
              <ul className="space-y-0.5">
                {threads.map((t) => {
                  const active = t.id === conv?.id;
                  return (
                    <li key={t.id}>
                      <div className="group relative">
                        <button
                          type="button"
                          onClick={() => openThread(t.id)}
                          className="w-full text-left px-2 py-1.5 rounded-md transition truncate"
                          style={{
                            background: active ? "var(--nxt-surface-soft)" : "transparent",
                            border: `1px solid ${active ? "var(--nxt-border-soft)" : "transparent"}`,
                            color: active ? "var(--nxt-fg)" : "var(--nxt-fg-dim)",
                          }}
                          data-testid={`agent-invoke-thread-${t.id}`}
                        >
                          <div className="text-[12px] font-medium truncate">{t.title}</div>
                          <div className="text-[10px] mt-0.5 mono opacity-60">
                            {new Date(t.updated_at).toLocaleString(undefined, {
                              month: "short", day: "numeric",
                              hour: "2-digit", minute: "2-digit",
                            })}
                          </div>
                        </button>
                        <button
                          type="button"
                          onClick={() => deleteThread(t.id)}
                          aria-label="Delete thread"
                          className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 h-6 w-6 rounded-md flex items-center justify-center transition"
                          style={{ color: "var(--nxt-fg-faint)" }}
                          data-testid={`agent-invoke-delete-${t.id}`}
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        {/* ─── Main column ─── */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header */}
          <header
            className="px-5 py-4 flex items-start gap-3"
            style={{ borderBottom: "1px solid var(--nxt-border-soft)" }}
          >
            <span
              className="h-9 w-9 shrink-0 rounded-xl flex items-center justify-center"
              style={{
                background: "var(--nxt-chip-bg)",
                border: "1px solid var(--nxt-border-soft)",
              }}
            >
              <Icon size={14} style={{ color: accent }} />
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-[15px] font-medium truncate" style={{ color: "var(--nxt-fg)" }}>
                  {item.name}
                </h2>
                <span className="mono text-[10px] tracking-[0.22em] uppercase shrink-0"
                      style={{ color: "var(--nxt-fg-faint)" }}>
                  {item.kind === "agent" ? "Agent" : "Skill"}
                </span>
              </div>
              <p className="text-[12.5px] mt-0.5 line-clamp-2" style={{ color: "var(--nxt-fg-dim)" }}>
                {item.description}
              </p>
            </div>
            <button
              onClick={onClose}
              className="h-8 w-8 rounded-lg flex items-center justify-center transition hover:bg-white/[0.04]"
              data-testid="agent-invoke-close"
            >
              <X size={14} style={{ color: "var(--nxt-fg-dim)" }} />
            </button>
          </header>

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            {(loadingDetail || loadingConv) && (
              <div className="flex items-center gap-2 py-6 justify-center text-[12px]"
                   style={{ color: "var(--nxt-fg-dim)" }}>
                <Loader2 size={12} className="animate-spin" />
                <span className="mono tracking-wider">
                  {loadingDetail ? "Loading prompt…" : "Loading thread…"}
                </span>
              </div>
            )}

            {!loadingDetail && !loadingConv && messages.length === 0 && (
              <div
                className="rounded-2xl p-4 text-[12.5px] leading-relaxed"
                style={{
                  background: "var(--nxt-surface-soft)",
                  border: "1px solid var(--nxt-border-soft)",
                  color: "var(--nxt-fg-dim)",
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="mono text-[10px] tracking-[0.28em] uppercase"
                        style={{ color: "var(--nxt-fg-faint)" }}>
                    <MessageSquare size={10} className="inline mr-1 -mt-0.5" />
                    System prompt · {detail?.system_prompt?.length || 0} chars
                  </span>
                  <button
                    type="button"
                    onClick={onCopyPrompt}
                    className="mono text-[10px] tracking-wider px-2 py-1 rounded-md transition hover:bg-white/[0.04]"
                    style={{ color: "var(--nxt-fg-dim)" }}
                    data-testid="agent-invoke-copy-prompt"
                  >
                    {copied ? (
                      <span className="inline-flex items-center gap-1"><Check size={10} /> Copied</span>
                    ) : (
                      <span className="inline-flex items-center gap-1"><Copy size={10} /> Copy</span>
                    )}
                  </button>
                </div>
                <p className="m-0">
                  Tell {item.name} what you want it to do — it answers using
                  its baked-in system prompt and whichever provider you have
                  wired. Every reply is saved to your account automatically.
                </p>
              </div>
            )}

            {messages.map((m, i) => (
              <div
                key={m.id || i}
                className="rounded-2xl p-4"
                style={{
                  background: m.role === "user"
                    ? (isLight ? "rgba(31,31,35,0.04)" : "rgba(255,255,255,0.03)")
                    : "var(--nxt-surface-soft)",
                  border: "1px solid var(--nxt-border-soft)",
                }}
                data-testid={`agent-msg-${m.role}-${i}`}
              >
                <div className="mono text-[10px] tracking-[0.28em] uppercase mb-1.5"
                     style={{ color: "var(--nxt-fg-faint)" }}>
                  {m.role === "user" ? "You" : item.name}
                </div>
                <div
                  className="text-[13.5px] leading-relaxed whitespace-pre-wrap"
                  style={{ color: "var(--nxt-fg)", fontFamily: "'IBM Plex Sans', sans-serif" }}
                >
                  {m.content || (
                    streaming && i === messages.length - 1 && (
                      <span className="inline-flex items-center gap-2 mono text-[11px]"
                            style={{ color: "var(--nxt-fg-dim)" }}>
                        <Loader2 size={11} className="animate-spin" />
                        Thinking…
                      </span>
                    )
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Composer */}
          <form
            onSubmit={(e) => { e.preventDefault(); submit(); }}
            className="p-4"
            style={{ borderTop: "1px solid var(--nxt-border-soft)" }}
          >
            <div
              className="flex items-end gap-2 rounded-2xl p-2"
              style={{
                background: "var(--nxt-surface-soft)",
                border: "1px solid var(--nxt-border-soft)",
              }}
            >
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit();
                  }
                }}
                rows={1}
                placeholder={`Ask ${item.name}…`}
                className="flex-1 resize-none bg-transparent outline-none text-[13.5px] leading-relaxed py-2 px-2 placeholder:opacity-50"
                style={{ color: "var(--nxt-fg)" }}
                data-testid="agent-invoke-input"
                disabled={loadingDetail}
              />
              {streaming ? (
                <button
                  type="button"
                  onClick={stop}
                  className="h-9 w-9 rounded-xl flex items-center justify-center transition"
                  style={{
                    background: isLight ? "#1F1F23" : "#FFFFFF",
                    color: isLight ? "#FAFAFA" : "#0B0B0C",
                  }}
                  data-testid="agent-invoke-stop"
                  aria-label="Stop"
                >
                  <Square size={11} fill="currentColor" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!input.trim() || loadingDetail}
                  className="h-9 w-9 rounded-xl flex items-center justify-center transition disabled:opacity-30"
                  style={{
                    background: isLight ? "#1F1F23" : "#FFFFFF",
                    color: isLight ? "#FAFAFA" : "#0B0B0C",
                  }}
                  data-testid="agent-invoke-send"
                  aria-label="Send"
                >
                  <Send size={13} />
                </button>
              )}
            </div>
            <p
              className="mt-2 mono text-[10px] tracking-wider text-center opacity-50"
              style={{ color: "var(--nxt-fg-faint)" }}
            >
              ↵ to send · ⇧↵ for newline · saved to your account
            </p>
          </form>
        </div>
      </aside>
    </div>
  );
}
