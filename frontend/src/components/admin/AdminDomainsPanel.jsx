/**
 * AdminDomainsPanel — connect a domain DIRECTLY to NXT1 itself (not to a
 * per-project app). For when you've detached from Emergent and want
 * nxtone.tech / app.nxtone.tech / api.nxtone.tech to point at this stack.
 */
import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Globe2,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

const ROLES = [
  { value: "primary", label: "Primary (app)" },
  { value: "api", label: "API endpoint" },
  { value: "preview", label: "Preview / share links" },
  { value: "other", label: "Other" },
];

export default function AdminDomainsPanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/domains");
      setItems(data.items || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const remove = async (id, host) => {
    if (!window.confirm(`Disconnect ${host} from NXT1?`)) return;
    try {
      await api.delete(`/admin/domains/${id}`);
      toast.success("Disconnected");
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const verify = async (id) => {
    try {
      const { data } = await api.post(`/admin/domains/${id}/verify`);
      toast[data.status === "verified" ? "success" : "warning"](
        `Status: ${data.status}`,
        { description: data.detail?.cname ? `CNAME → ${data.detail.cname}` : undefined }
      );
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-3xl" data-testid="admin-domains-panel">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <div className="mono text-[10px] tracking-[0.32em] uppercase text-zinc-500 mb-1.5">
            // nxt1 domains
          </div>
          <h1 className="text-2xl sm:text-3xl font-black tracking-tighter text-white"
              style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}>
            Point a domain at NXT1.
          </h1>
          <p className="text-zinc-400 text-[12.5px] mt-1.5 max-w-2xl">
            For when NXT1 runs on your own stack. Domains added here connect to
            the platform itself — Cloudflare-managed ones auto-CNAME; others
            show the DNS records to set manually.
          </p>
        </div>
        <button
          onClick={refresh}
          className="h-9 w-9 flex items-center justify-center rounded-full text-zinc-400 hover:text-white hover:bg-white/5 transition"
          data-testid="admin-domains-refresh"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-400 text-black text-[12px] font-semibold hover:bg-emerald-300 transition mb-4"
        data-testid="admin-domains-add"
      >
        <Plus size={12} strokeWidth={2.5} /> Connect domain
      </button>

      {loading ? (
        <div className="text-zinc-500 text-[12px]">
          <Loader2 size={14} className="animate-spin inline mr-2" />Loading…
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-white/8 surface-1 p-6 text-center">
          <Globe2 size={20} className="mx-auto text-zinc-600 mb-2" />
          <div className="text-[13px] text-zinc-400">No domains connected.</div>
          <div className="text-[11.5px] text-zinc-600 mt-1">
            Add your apex (nxtone.tech) plus app/api subdomains as needed.
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          {items.map((d) => (
            <DomainRow key={d.id} d={d} onVerify={() => verify(d.id)} onRemove={() => remove(d.id, d.hostname)} />
          ))}
        </div>
      )}

      {open && <AddModal onClose={() => setOpen(false)} onDone={async () => { setOpen(false); await refresh(); }} />}
    </div>
  );
}

function DomainRow({ d, onVerify, onRemove }) {
  return (
    <div
      className="rounded-xl border border-white/8 surface-1 p-3.5 sm:p-4"
      data-testid={`admin-domain-${d.hostname}`}
    >
      <div className="flex items-start gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[14px] font-semibold text-white mono">{d.hostname}</span>
            <span className="nxt-overline text-emerald-300">{d.role}</span>
          </div>
          <div className="text-[11.5px] text-zinc-500 mt-1 mono uppercase tracking-wider">
            {d.managed ? (
              <span className="text-emerald-300">cloudflare · auto-managed</span>
            ) : (
              <span>manual DNS · {d.instructions?.length || 0} record(s)</span>
            )}
            {" · "}
            <span className={d.status === "verified" ? "text-emerald-300" : "text-amber-300"}>
              {d.status || "pending"}
            </span>
            {d.ssl_status && d.ssl_status !== "unknown" && (
              <> · ssl: <span className="text-zinc-400">{d.ssl_status}</span></>
            )}
          </div>
          {!d.managed && (d.instructions || []).length > 0 && (
            <div className="mt-2 space-y-1">
              {d.instructions.map((rec, i) => (
                <div key={i} className="text-[11.5px] mono text-zinc-400 break-all">
                  {rec.type} · {rec.name} → {rec.value}
                </div>
              ))}
            </div>
          )}
          {d.error && <div className="text-[11.5px] text-red-400 mt-1">{d.error}</div>}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={onVerify}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-full border border-white/10 text-zinc-300 text-[11px] hover:border-white/25 hover:text-white transition"
            data-testid={`admin-domain-verify-${d.hostname}`}
          >
            Verify
          </button>
          <button
            onClick={onRemove}
            className="text-zinc-500 hover:text-red-400 p-1.5 transition"
            data-testid={`admin-domain-delete-${d.hostname}`}
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}

function AddModal({ onClose, onDone }) {
  const [host, setHost] = useState("");
  const [role, setRole] = useState("primary");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!host.trim()) return;
    setBusy(true);
    try {
      const { data } = await api.post("/admin/domains", { hostname: host.trim(), role });
      if (data.managed) {
        toast.success(`Connected ${data.hostname}`, { description: `Auto-managed via ${data.zone_name}` });
      } else {
        toast.warning(`Added ${data.hostname}`, { description: "Set the DNS records shown to verify." });
      }
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-graphite-scrim-strong backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-[#1F1F23] border border-white/10 rounded-2xl w-[480px] max-w-[95vw] p-5 sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-end mb-1">
          <button onClick={onClose} className="text-zinc-400 hover:text-white transition">
            <X size={16} />
          </button>
        </div>
        <div className="flex items-start gap-3 mb-4">
          <span className="h-9 w-9 rounded-full bg-emerald-500/15 border border-emerald-400/30 flex items-center justify-center shrink-0">
            <Sparkles size={14} className="text-emerald-300" />
          </span>
          <div>
            <div className="text-[10px] mono uppercase tracking-[0.28em] text-emerald-400 mb-0.5">
              // connect to nxt1
            </div>
            <div className="text-[16px] font-semibold text-white">Add a domain.</div>
            <div className="text-[12px] text-zinc-400 mt-0.5">
              NXT1 will auto-detect if it can manage DNS for you.
            </div>
          </div>
        </div>

        <label className="block mb-3">
          <span className="block mono text-[10px] tracking-[0.24em] uppercase text-white/55 mb-1.5">Hostname</span>
          <input
            value={host}
            onChange={(e) => setHost(e.target.value)}
            placeholder="e.g. nxtone.tech or app.nxtone.tech"
            className="nxt-auth-input mono"
            autoFocus
            data-testid="admin-domain-host-input"
          />
        </label>
        <label className="block mb-3">
          <span className="block mono text-[10px] tracking-[0.24em] uppercase text-white/55 mb-1.5">Role</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="nxt-auth-input mono cursor-pointer"
            data-testid="admin-domain-role-select"
          >
            {ROLES.map((r) => (<option key={r.value} value={r.value}>{r.label}</option>))}
          </select>
        </label>

        <div className="flex justify-end gap-2 mt-3">
          <button
            onClick={onClose}
            disabled={busy}
            className="px-4 py-2 rounded-full border border-white/15 text-zinc-300 text-[12.5px] hover:border-white/30 transition"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={busy || !host.trim()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-400 text-black text-[12.5px] font-semibold hover:bg-emerald-300 transition disabled:opacity-50"
            data-testid="admin-domain-submit"
          >
            {busy ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
            Connect
          </button>
        </div>
      </div>
    </div>
  );
}
