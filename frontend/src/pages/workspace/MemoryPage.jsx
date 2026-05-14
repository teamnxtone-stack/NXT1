/**
 * NXT1 — Agent Memory
 *
 * Per-user, NXT1-wide memory bank. Every agent auto-loads this on every run.
 * This page lets the user list, add, edit, pin, and forget memory items.
 *
 * Memory is what makes the agents get smarter over time without explaining
 * the same context every week.
 */
import { useEffect, useMemo, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain, Plus, Pin, PinOff, Trash2, Edit2, Check, X, Loader2, Filter,
} from "lucide-react";
import {
  memoryList, memoryAdd, memoryUpdate, memoryDelete,
} from "@/lib/api";

const SCOPES = [
  { id: "all",    label: "All" },
  { id: "global", label: "Global" },
  { id: "social", label: "Social" },
  { id: "studio", label: "Studio" },
  { id: "agents", label: "Agents" },
];

const KINDS = ["fact", "preference", "example", "feedback", "image", "system"];

export default function MemoryPage() {
  const [items, setItems] = useState([]);
  const [scope, setScope] = useState("all");
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ scope: "global", kind: "fact", summary: "", pinned: false });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params = scope === "all" ? {} : { scope };
      const { data } = await memoryList(params);
      setItems(data.items || []);
    } finally {
      setLoading(false);
    }
  }, [scope]);

  useEffect(() => { refresh(); }, [refresh]);

  const pinned = useMemo(() => items.filter((i) => i.pinned), [items]);
  const regular = useMemo(() => items.filter((i) => !i.pinned), [items]);

  const onAdd = async () => {
    if (!draft.summary.trim()) return;
    try {
      await memoryAdd(draft);
      setDraft({ scope: draft.scope, kind: "fact", summary: "", pinned: false });
      setAdding(false);
      refresh();
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed to add memory");
    }
  };

  const onPin = async (id, pinned) => {
    await memoryUpdate(id, { pinned });
    refresh();
  };
  const onDelete = async (id) => {
    if (!confirm("Forget this memory?")) return;
    await memoryDelete(id);
    refresh();
  };
  const onEditSummary = async (id, summary) => {
    await memoryUpdate(id, { summary });
    refresh();
  };

  return (
    <div
      className="flex flex-col h-full min-h-0 w-full"
      data-testid="memory-page"
      style={{ background: "var(--nxt-bg)", color: "var(--nxt-fg)" }}
    >
      {/* Header */}
      <header
        className="shrink-0 px-5 sm:px-7 py-4 flex items-center justify-between gap-3 flex-wrap"
        style={{ borderBottom: "1px solid var(--nxt-border)" }}
      >
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <Brain size={16} style={{ color: "var(--nxt-accent)" }} />
            <span className="mono text-[10px] tracking-[0.28em] uppercase"
                  style={{ color: "var(--nxt-text-3)" }}>NXT1 · Memory</span>
          </div>
          <h1 className="text-[20px] sm:text-[22px] font-medium tracking-tight">
            What your agents remember
          </h1>
          <p className="text-[12px] mt-0.5" style={{ color: "var(--nxt-text-3)" }}>
            Auto-loaded into every Social, Studio, and Agent run. Pinned items always inject.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-full p-0.5"
               style={{ background: "var(--nxt-surface)", border: "1px solid var(--nxt-border)" }}>
            {SCOPES.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setScope(s.id)}
                data-testid={`memory-scope-${s.id}`}
                className="px-3 py-1.5 rounded-full text-[11.5px] transition"
                style={{
                  background: scope === s.id ? "var(--nxt-accent)" : "transparent",
                  color: scope === s.id ? "#0F1117" : "var(--nxt-fg-dim)",
                }}
              >
                {s.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setAdding((a) => !a)}
            data-testid="memory-add-btn"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12.5px] font-medium transition"
            style={{ background: "var(--nxt-accent)", color: "#0F1117" }}
          >
            <Plus size={12} /> Add
          </button>
        </div>
      </header>

      {/* Add form */}
      <AnimatePresence>
        {adding && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
            style={{ borderBottom: "1px solid var(--nxt-border)" }}
          >
            <div className="px-5 sm:px-7 py-4 grid grid-cols-1 sm:grid-cols-[1fr_auto_auto_auto] gap-2">
              <input
                value={draft.summary}
                onChange={(e) => setDraft({ ...draft, summary: e.target.value })}
                placeholder="What should your agents remember?"
                data-testid="memory-new-summary"
                className="bg-transparent outline-none text-[13px] px-3 py-2 rounded-lg"
                style={{
                  background: "var(--nxt-surface)",
                  border: "1px solid var(--nxt-border)",
                  color: "var(--nxt-fg)",
                }}
              />
              <select
                value={draft.scope}
                onChange={(e) => setDraft({ ...draft, scope: e.target.value })}
                data-testid="memory-new-scope"
                className="text-[12px] py-2 px-2 rounded-lg outline-none capitalize"
                style={{
                  background: "var(--nxt-surface)",
                  border: "1px solid var(--nxt-border)",
                  color: "var(--nxt-fg)",
                }}
              >
                {SCOPES.filter((s) => s.id !== "all").map((s) =>
                  <option key={s.id} value={s.id}>{s.label}</option>
                )}
              </select>
              <select
                value={draft.kind}
                onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
                data-testid="memory-new-kind"
                className="text-[12px] py-2 px-2 rounded-lg outline-none capitalize"
                style={{
                  background: "var(--nxt-surface)",
                  border: "1px solid var(--nxt-border)",
                  color: "var(--nxt-fg)",
                }}
              >
                {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
              <div className="flex items-center gap-2">
                <label className="inline-flex items-center gap-1.5 text-[11px]"
                       style={{ color: "var(--nxt-fg-dim)" }}>
                  <input
                    type="checkbox"
                    checked={draft.pinned}
                    onChange={(e) => setDraft({ ...draft, pinned: e.target.checked })}
                    data-testid="memory-new-pinned"
                  /> Pin
                </label>
                <button
                  type="button"
                  onClick={onAdd}
                  disabled={!draft.summary.trim()}
                  data-testid="memory-new-save"
                  className="px-3 py-1.5 rounded-full text-[12px] font-medium disabled:opacity-50"
                  style={{ background: "var(--nxt-accent)", color: "#0F1117" }}
                >
                  Save
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex-1 min-h-0 overflow-y-auto p-5 sm:p-7 space-y-6">
        {loading && (
          <div className="text-center py-12" style={{ color: "var(--nxt-text-3)" }}>
            <Loader2 size={20} className="animate-spin inline mr-2" /> Loading memory…
          </div>
        )}
        {!loading && items.length === 0 && (
          <div className="text-center py-16" style={{ color: "var(--nxt-text-3)" }}>
            <Brain size={28} className="mx-auto mb-3 opacity-40" />
            <p className="text-[13px]">No memory yet — the Social agent will start adding entries
            automatically as you generate content. Or pin one yourself above.</p>
          </div>
        )}

        {pinned.length > 0 && (
          <Section title="Pinned" count={pinned.length}>
            {pinned.map((m) => (
              <MemoryRow key={m.id} m={m}
                         onPin={() => onPin(m.id, false)}
                         onDelete={() => onDelete(m.id)}
                         onEdit={(s) => onEditSummary(m.id, s)} />
            ))}
          </Section>
        )}
        {regular.length > 0 && (
          <Section title="Recent" count={regular.length}>
            {regular.map((m) => (
              <MemoryRow key={m.id} m={m}
                         onPin={() => onPin(m.id, true)}
                         onDelete={() => onDelete(m.id)}
                         onEdit={(s) => onEditSummary(m.id, s)} />
            ))}
          </Section>
        )}
      </div>
    </div>
  );
}

function Section({ title, count, children }) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-2">
        <span className="mono text-[10.5px] tracking-[0.22em] uppercase"
              style={{ color: "var(--nxt-text-3)" }}>{title}</span>
        <span className="text-[11px]" style={{ color: "var(--nxt-text-3)" }}>· {count}</span>
      </div>
      <div className="space-y-1.5">{children}</div>
    </section>
  );
}

function MemoryRow({ m, onPin, onDelete, onEdit }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(m.summary);
  const KIND_COLORS = {
    fact: "var(--nxt-fg-dim)",
    preference: "var(--nxt-accent)",
    example: "#a78bfa",
    feedback: "#fbbf24",
    image: "#34d399",
    system: "#60a5fa",
  };
  const SCOPE_BG = {
    global: "rgba(255,255,255,0.04)",
    social: "rgba(251, 191, 36, 0.10)",
    studio: "rgba(167, 139, 250, 0.10)",
    agents: "rgba(96, 165, 250, 0.10)",
  };

  const save = async () => {
    if (val.trim() && val !== m.summary) {
      await onEdit(val);
    }
    setEditing(false);
  };

  return (
    <div
      className="flex items-start gap-2 px-3 py-2.5 rounded-lg"
      style={{
        background: SCOPE_BG[m.scope] || "var(--nxt-surface)",
        border: "1px solid var(--nxt-border)",
      }}
      data-testid={`memory-row-${m.id}`}
    >
      <div className="flex flex-col items-center gap-0.5 pt-0.5 shrink-0 w-14">
        <span className="mono text-[8.5px] uppercase tracking-wider"
              style={{ color: KIND_COLORS[m.kind] || "var(--nxt-fg-dim)" }}>
          {m.kind}
        </span>
        <span className="mono text-[8.5px] uppercase tracking-wider opacity-60"
              style={{ color: "var(--nxt-text-3)" }}>
          {m.scope}
        </span>
      </div>
      <div className="flex-1 min-w-0">
        {editing ? (
          <input
            value={val}
            onChange={(e) => setVal(e.target.value)}
            onBlur={save}
            onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEditing(false); }}
            autoFocus
            data-testid={`memory-edit-${m.id}`}
            className="w-full bg-transparent outline-none text-[12.5px] px-2 py-1 rounded"
            style={{ background: "var(--nxt-bg-2)", border: "1px solid var(--nxt-border-strong)", color: "var(--nxt-fg)" }}
          />
        ) : (
          <p className="text-[12.5px] leading-relaxed break-words"
             style={{ color: "var(--nxt-fg)" }}>
            {m.summary}
          </p>
        )}
        <p className="text-[10px] mt-0.5" style={{ color: "var(--nxt-text-3)" }}>
          {new Date(m.created_at).toLocaleString()}
        </p>
      </div>
      <div className="flex items-center gap-0.5 shrink-0">
        <button
          type="button"
          onClick={() => setEditing((e) => !e)}
          data-testid={`memory-edit-btn-${m.id}`}
          className="h-7 w-7 grid place-items-center rounded-md transition hover:opacity-80"
          style={{ color: "var(--nxt-fg-dim)" }}
          title="Edit"
        >
          <Edit2 size={11} />
        </button>
        <button
          type="button"
          onClick={onPin}
          data-testid={`memory-pin-${m.id}`}
          className="h-7 w-7 grid place-items-center rounded-md transition hover:opacity-80"
          style={{ color: m.pinned ? "var(--nxt-accent)" : "var(--nxt-fg-dim)" }}
          title={m.pinned ? "Unpin" : "Pin"}
        >
          {m.pinned ? <PinOff size={11} /> : <Pin size={11} />}
        </button>
        <button
          type="button"
          onClick={onDelete}
          data-testid={`memory-delete-${m.id}`}
          className="h-7 w-7 grid place-items-center rounded-md transition hover:opacity-80"
          style={{ color: "var(--nxt-error)" }}
          title="Forget"
        >
          <Trash2 size={11} />
        </button>
      </div>
    </div>
  );
}
