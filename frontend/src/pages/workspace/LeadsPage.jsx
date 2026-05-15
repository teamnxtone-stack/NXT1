/**
 * Workspace → Leads
 *
 * Lists everyone who started a chat with the public NXT One assistant.
 * Shows first/last name, contact, intake note, when, and click → transcript.
 * Lives at /workspace/leads (mounted in App.js routes).
 */
import { useEffect, useState } from "react";
import { Loader2, Mail, Phone, MessageSquare, Search, X } from "lucide-react";
import api from "@/lib/api";

export default function LeadsPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [transcript, setTranscript] = useState([]);
  const [loadingTx, setLoadingTx] = useState(false);

  const load = async (q = "") => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/nxt-chat/leads", { params: { q, limit: 200 } });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch { /* not signed in */ }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const onSearch = (e) => {
    e.preventDefault();
    load(query);
  };

  const openTranscript = async (lead) => {
    setSelected(lead);
    setLoadingTx(true);
    try {
      const { data } = await api.get(`/admin/nxt-chat/leads/${lead.id}/transcript`);
      setTranscript(data.transcript || []);
    } catch { setTranscript([]); }
    finally { setLoadingTx(false); }
  };

  return (
    <div className="px-5 sm:px-8 py-6 sm:py-8 max-w-[1080px] mx-auto" data-testid="leads-page">
      <div className="flex items-end justify-between gap-4 mb-6 flex-wrap">
        <div>
          <div className="mono text-[10px] tracking-[0.28em] uppercase mb-1"
               style={{ color: "var(--nxt-fg-faint)" }}>
            // leads
          </div>
          <h1 className="text-[26px] sm:text-[30px] font-semibold tracking-tight"
              style={{ color: "var(--nxt-fg)" }}>
            Chat leads
          </h1>
          <p className="text-[13px] mt-1" style={{ color: "var(--nxt-fg-dim)" }}>
            {total} total · everyone who talked to the public assistant.
          </p>
        </div>
        <form onSubmit={onSearch} className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 h-10 rounded-full"
               style={{ background: "var(--nxt-chip-bg)", border: "1px solid var(--nxt-border-soft)" }}>
            <Search size={13} style={{ color: "var(--nxt-fg-faint)" }} />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search email, name, note…"
              className="bg-transparent outline-none text-[13px] w-44 sm:w-64"
              style={{ color: "var(--nxt-fg)" }}
              data-testid="leads-search-input"
            />
          </div>
        </form>
      </div>

      {loading && items.length === 0 ? (
        <div className="py-20 text-center" style={{ color: "var(--nxt-fg-faint)" }}>
          <Loader2 size={18} className="animate-spin inline-block mr-2" /> loading
        </div>
      ) : items.length === 0 ? (
        <div className="py-20 text-center" style={{ color: "var(--nxt-fg-faint)" }}>
          <MessageSquare size={28} className="mx-auto mb-3 opacity-40" />
          <p className="text-[13px]">No leads yet. They'll show up here once someone chats with the assistant.</p>
        </div>
      ) : (
        <div className="rounded-2xl overflow-hidden"
             style={{ background: "var(--nxt-surface)", border: "1px solid var(--nxt-border)" }}>
          {items.map((l, idx) => (
            <button
              key={l.id}
              type="button"
              onClick={() => openTranscript(l)}
              data-testid={`leads-row-${l.id}`}
              className="w-full text-left px-5 py-4 flex items-start gap-3 transition hover:opacity-95"
              style={{
                borderTop: idx === 0 ? "none" : "1px solid var(--nxt-border-soft)",
                background: "transparent",
              }}
            >
              <div className="shrink-0 h-9 w-9 rounded-full inline-flex items-center justify-center text-[11px] font-semibold"
                   style={{
                     background: "var(--nxt-chip-bg)",
                     color: "var(--nxt-fg-dim)",
                     border: "1px solid var(--nxt-border-soft)",
                   }} aria-hidden>
                {(l.first_name?.[0] || l.email?.[0] || "?").toUpperCase()}
                {(l.last_name?.[0] || "").toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="text-[14px] font-medium" style={{ color: "var(--nxt-fg)" }}>
                    {[l.first_name, l.last_name].filter(Boolean).join(" ") || "Unknown"}
                  </span>
                  <span className="mono text-[10.5px] opacity-60" style={{ color: "var(--nxt-fg-faint)" }}>
                    {new Date(l.created_at).toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center gap-4 mt-1 text-[12px] flex-wrap"
                     style={{ color: "var(--nxt-fg-dim)" }}>
                  {l.email && !l.email.endsWith("@unknown.placeholder") && (
                    <span className="inline-flex items-center gap-1.5">
                      <Mail size={11} /> {l.email}
                    </span>
                  )}
                  {l.phone && (
                    <span className="inline-flex items-center gap-1.5">
                      <Phone size={11} /> {l.phone}
                    </span>
                  )}
                </div>
                {l.note && (
                  <p className="mt-1 text-[12px] line-clamp-2"
                     style={{ color: "var(--nxt-fg-faint)" }}>
                    {l.note}
                  </p>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.55)" }}
          onClick={() => setSelected(null)}
        >
          <div
            className="rounded-2xl overflow-hidden w-full max-w-[640px] max-h-[80vh] flex flex-col"
            style={{
              background: "var(--nxt-bg-2)",
              border: "1px solid var(--nxt-border-strong)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-3.5"
                 style={{ borderBottom: "1px solid var(--nxt-border)" }}>
              <div>
                <div className="text-[13px] font-medium" style={{ color: "var(--nxt-fg)" }}>
                  {[selected.first_name, selected.last_name].filter(Boolean).join(" ") || selected.email}
                </div>
                <div className="mono text-[10px] opacity-60" style={{ color: "var(--nxt-fg-faint)" }}>
                  {selected.email} {selected.phone ? ` · ${selected.phone}` : ""}
                </div>
              </div>
              <button onClick={() => setSelected(null)}
                      className="h-8 w-8 rounded-md inline-flex items-center justify-center"
                      style={{ color: "var(--nxt-fg-dim)" }} aria-label="Close">
                <X size={14} />
              </button>
            </div>
            <div className="px-5 py-4 overflow-y-auto space-y-3">
              {loadingTx ? (
                <div className="text-center py-10" style={{ color: "var(--nxt-fg-faint)" }}>
                  <Loader2 size={16} className="animate-spin inline-block mr-2" /> loading transcript
                </div>
              ) : transcript.length === 0 ? (
                <p className="text-center text-[12px] py-8"
                   style={{ color: "var(--nxt-fg-faint)" }}>
                  No transcript yet — intake captured but no free-chat messages.
                </p>
              ) : transcript.map((m, i) => (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className="rounded-xl px-3 py-2 max-w-[80%] text-[13px] whitespace-pre-wrap"
                       style={
                         m.role === "user"
                           ? { background: "var(--nxt-accent)", color: "var(--nxt-bg)" }
                           : {
                               background: "var(--nxt-surface)",
                               color: "var(--nxt-fg)",
                               border: "1px solid var(--nxt-border-soft)",
                             }
                       }>
                    {m.content}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
