/**
 * AccessRequestsPanel — admin inbox for the public Request Access form.
 * Lists submissions, supports status updates (new/contacted/closed) and
 * inline notes. Mounted inside the /dashboard page as a collapsible
 * section so admins see new leads without leaving the workspace.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ChevronDown,
  ChevronUp,
  Loader2,
  Mail,
  Trash2,
  RefreshCw,
  Inbox,
} from "lucide-react";
import {
  deleteAccessRequest,
  listAccessRequests,
  updateAccessRequest,
} from "@/lib/api";

const STATUS_TABS = [
  { id: "new", label: "New" },
  { id: "contacted", label: "Contacted" },
  { id: "closed", label: "Closed" },
];

const STATUS_COLOR = {
  new: "text-amber-300 border-amber-400/30 bg-amber-500/10",
  contacted: "text-sky-300 border-sky-400/30 bg-sky-500/10",
  closed: "text-zinc-500 border-white/10 bg-white/5",
};

function fmt(ts) {
  try {
    const d = new Date(ts);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

export default function AccessRequestsPanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("new");
  const [expanded, setExpanded] = useState(true);
  const [openId, setOpenId] = useState(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const { data } = await listAccessRequests();
      setItems(data || []);
    } catch (e) {
      toast.error("Could not load access requests");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const visible = items.filter((r) => (r.status || "new") === tab);
  const counts = STATUS_TABS.reduce((acc, t) => {
    acc[t.id] = items.filter((r) => (r.status || "new") === t.id).length;
    return acc;
  }, {});

  const setStatus = async (id, status) => {
    try {
      await updateAccessRequest(id, { status });
      setItems((arr) => arr.map((r) => (r.id === id ? { ...r, status } : r)));
      toast.success(`Marked ${status}`);
    } catch (e) {
      toast.error("Update failed");
    }
  };

  const saveNotes = async (id, notes) => {
    try {
      await updateAccessRequest(id, { notes });
      setItems((arr) => arr.map((r) => (r.id === id ? { ...r, notes } : r)));
      toast.success("Notes saved");
    } catch {
      toast.error("Save failed");
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this access request?")) return;
    try {
      await deleteAccessRequest(id);
      setItems((arr) => arr.filter((r) => r.id !== id));
      toast.success("Deleted");
    } catch {
      toast.error("Delete failed");
    }
  };

  return (
    <section
      className="border border-white/10 surface-1 rounded-sm mb-8"
      data-testid="access-requests-panel"
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/[0.02] transition"
        data-testid="access-requests-toggle"
      >
        <div className="flex items-center gap-3">
          <Inbox size={15} className="text-zinc-400" />
          <div className="text-left">
            <div className="text-sm font-medium text-white">Access requests</div>
            <div className="text-[12px] text-zinc-500">
              {counts.new || 0} new · {counts.contacted || 0} contacted ·{" "}
              {counts.closed || 0} closed
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {counts.new > 0 && (
            <span className="mono text-[10px] tracking-wider px-2 py-0.5 border border-amber-400/30 text-amber-300 bg-amber-500/10 rounded-sm">
              {counts.new} NEW
            </span>
          )}
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-white/5">
          <div className="flex items-center justify-between px-5 py-3 border-b border-white/5">
            <div className="flex gap-1.5">
              {STATUS_TABS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`text-[11px] mono uppercase tracking-wider px-2.5 py-1 rounded-sm transition ${
                    tab === t.id
                      ? "bg-white/10 text-white border border-white/15"
                      : "text-zinc-500 hover:text-zinc-300 border border-transparent"
                  }`}
                  data-testid={`access-tab-${t.id}`}
                >
                  {t.label}
                  {counts[t.id] > 0 && (
                    <span className="ml-1.5 opacity-70">({counts[t.id]})</span>
                  )}
                </button>
              ))}
            </div>
            <button
              onClick={refresh}
              className="text-[11px] mono text-zinc-500 hover:text-white inline-flex items-center gap-1"
              data-testid="access-refresh"
            >
              <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
              refresh
            </button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center gap-2 px-5 py-8 text-zinc-500 text-sm">
              <Loader2 size={13} className="animate-spin" />
              Loading…
            </div>
          ) : visible.length === 0 ? (
            <div className="px-5 py-12 text-center text-zinc-500 text-sm">
              No {tab} requests.
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {visible.map((r) => (
                <RequestRow
                  key={r.id}
                  r={r}
                  open={openId === r.id}
                  onToggle={() => setOpenId(openId === r.id ? null : r.id)}
                  onStatus={(s) => setStatus(r.id, s)}
                  onNotes={(n) => saveNotes(r.id, n)}
                  onDelete={() => remove(r.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function RequestRow({ r, open, onToggle, onStatus, onNotes, onDelete }) {
  const [notes, setNotesState] = useState(r.notes || "");
  const status = r.status || "new";

  return (
    <div className="px-5 py-3.5" data-testid={`access-row-${r.id}`}>
      <button
        onClick={onToggle}
        className="w-full flex items-start gap-3 text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="text-sm text-white font-medium truncate">
              {r.name}
            </span>
            <span
              className={`mono text-[10px] tracking-wider px-1.5 py-0.5 border rounded-sm ${STATUS_COLOR[status]}`}
            >
              {status.toUpperCase()}
            </span>
            {r.project_type && (
              <span className="text-[11px] mono text-zinc-500 uppercase tracking-wide">
                {r.project_type}
              </span>
            )}
          </div>
          <div className="text-[12px] text-zinc-500 mt-1 truncate">
            {r.email}
            {r.company ? ` · ${r.company}` : ""}
          </div>
          <div className="text-[13px] text-zinc-300 mt-1 line-clamp-2">
            {r.description}
          </div>
        </div>
        <div className="text-[11px] mono text-zinc-600 shrink-0 text-right">
          <div>{fmt(r.created_at)}</div>
          {open ? (
            <ChevronUp size={12} className="ml-auto mt-1" />
          ) : (
            <ChevronDown size={12} className="ml-auto mt-1" />
          )}
        </div>
      </button>

      {open && (
        <div className="mt-3 pt-3 border-t border-white/5 space-y-3 nxt-fade-up">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[12px]">
            <Field label="Email">
              <a
                href={`mailto:${r.email}`}
                className="text-emerald-300 hover:text-emerald-200 inline-flex items-center gap-1"
                data-testid={`access-email-link-${r.id}`}
              >
                <Mail size={11} />
                {r.email}
              </a>
            </Field>
            {r.company && <Field label="Company">{r.company}</Field>}
            {r.budget && <Field label="Budget">{r.budget}</Field>}
            {r.timeline && <Field label="Timeline">{r.timeline}</Field>}
          </div>
          <Field label="Description">
            <p className="text-zinc-300 text-[13px] leading-relaxed whitespace-pre-wrap">
              {r.description}
            </p>
          </Field>
          <div>
            <div className="mono text-[10px] tracking-[0.24em] uppercase text-zinc-500 mb-1.5">
              Internal notes
            </div>
            <textarea
              value={notes}
              onChange={(e) => setNotesState(e.target.value)}
              onBlur={() => {
                if (notes !== (r.notes || "")) onNotes(notes);
              }}
              rows={2}
              placeholder="Reminders, lead score, follow-up date…"
              className="nxt-input w-full resize-y text-[13px]"
              data-testid={`access-notes-${r.id}`}
            />
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            {status !== "contacted" && (
              <button
                onClick={() => onStatus("contacted")}
                className="nxt-btn !py-1.5 !px-3 text-[11px]"
                data-testid={`access-mark-contacted-${r.id}`}
              >
                Mark contacted
              </button>
            )}
            {status !== "closed" && (
              <button
                onClick={() => onStatus("closed")}
                className="nxt-btn !py-1.5 !px-3 text-[11px]"
                data-testid={`access-mark-closed-${r.id}`}
              >
                Close
              </button>
            )}
            {status !== "new" && (
              <button
                onClick={() => onStatus("new")}
                className="nxt-btn !py-1.5 !px-3 text-[11px]"
              >
                Reopen
              </button>
            )}
            <button
              onClick={onDelete}
              className="nxt-btn !py-1.5 !px-3 text-[11px] text-red-300 hover:text-red-200 ml-auto"
              data-testid={`access-delete-${r.id}`}
            >
              <Trash2 size={11} /> Delete
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <div className="mono text-[10px] tracking-[0.24em] uppercase text-zinc-500 mb-1">
        {label}
      </div>
      <div className="text-zinc-300">{children}</div>
    </div>
  );
}
