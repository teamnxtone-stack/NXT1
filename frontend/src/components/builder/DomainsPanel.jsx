import { useEffect, useMemo, useState } from "react";
import {
  Globe,
  Plus,
  Trash2,
  Check,
  X,
  Loader2,
  Star,
  Copy,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import {
  addDomain,
  listDomains,
  removeDomain,
  verifyDomain,
  setPrimaryDomain,
} from "@/lib/api";
import { toast } from "sonner";

const STATUS_STYLE = {
  pending: { color: "text-amber-300", dot: "bg-amber-400 animate-pulse", label: "Pending DNS" },
  verified: { color: "text-emerald-300", dot: "bg-emerald-400", label: "Verified" },
  active: { color: "text-emerald-300", dot: "bg-emerald-400", label: "Active" },
  failed: { color: "text-red-300", dot: "bg-red-500", label: "Failed" },
};

function StatusBadge({ status }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 mono text-[11px] ${s.color}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label.toUpperCase()}
    </span>
  );
}

export default function DomainsPanel({ projectId }) {
  const [domains, setDomains] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hostname, setHostname] = useState("");
  const [adding, setAdding] = useState(false);
  const [verifying, setVerifying] = useState(null);
  const [activeId, setActiveId] = useState(null);

  const refresh = async () => {
    try {
      const { data } = await listDomains(projectId);
      setDomains(data);
      if (!activeId && data.length > 0) setActiveId(data[0].id);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const onAdd = async (e) => {
    e.preventDefault();
    const h = hostname.trim().toLowerCase();
    if (!h) return;
    setAdding(true);
    try {
      const { data } = await addDomain(projectId, h);
      toast.success(`Added ${data.hostname}`);
      setHostname("");
      setActiveId(data.id);
      await refresh();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to add domain");
    } finally {
      setAdding(false);
    }
  };

  const onRemove = async (id, host) => {
    if (!window.confirm(`Remove ${host}?`)) return;
    try {
      await removeDomain(projectId, id);
      toast.success("Removed");
      if (activeId === id) setActiveId(null);
      await refresh();
    } catch {
      toast.error("Failed to remove");
    }
  };

  const onVerify = async (id) => {
    setVerifying(id);
    try {
      const { data } = await verifyDomain(projectId, id);
      toast.success(`Status: ${data.status}`);
      await refresh();
    } catch {
      toast.error("Verify failed");
    } finally {
      setVerifying(null);
    }
  };

  const onSetPrimary = async (id) => {
    try {
      await setPrimaryDomain(projectId, id);
      toast.success("Primary set");
      await refresh();
    } catch {
      toast.error("Failed");
    }
  };

  const active = useMemo(
    () => domains.find((d) => d.id === activeId) || null,
    [domains, activeId]
  );

  return (
    <div className="flex flex-col h-full surface-recessed" data-testid="domains-panel">
      <div className="shrink-0 px-4 py-3 border-b border-white/5 flex items-center gap-3 flex-wrap">
        <Globe size={14} className="text-white" />
        <div className="flex-1 min-w-[200px]">
          <div className="text-sm font-medium">Custom domains</div>
          <div className="nxt-overline">// connect your domain to this project</div>
        </div>
        <form onSubmit={onAdd} className="flex items-center gap-2 nxt-panel rounded-sm p-1.5">
          <input
            value={hostname}
            onChange={(e) => setHostname(e.target.value)}
            placeholder="yourdomain.com"
            className="bg-transparent border-0 outline-none text-sm px-2 py-1 placeholder:text-zinc-600 mono"
            data-testid="domain-input"
          />
          <button
            type="submit"
            disabled={adding || !hostname.trim()}
            className="nxt-btn-primary !py-1.5 !px-3"
            data-testid="add-domain-button"
          >
            {adding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Add
          </button>
        </form>
      </div>

      <div className="flex-1 grid grid-cols-12 min-h-0">
        <aside className="col-span-4 border-r border-white/5 overflow-y-auto">
          <div className="px-3 py-2 nxt-overline border-b border-white/5">// domains</div>
          {loading ? (
            <div className="p-3 text-zinc-500 text-xs mono">loading…</div>
          ) : domains.length === 0 ? (
            <div className="p-3 text-zinc-500 text-xs">
              No custom domains yet. Add one above to get DNS instructions.
            </div>
          ) : (
            domains.map((d) => (
              <button
                key={d.id}
                onClick={() => setActiveId(d.id)}
                className={`w-full text-left px-3 py-2 border-b border-white/5 transition ${activeId === d.id ? "bg-white/5" : "hover:bg-white/[0.03]"}`}
                data-testid={`domain-item-${d.id}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm mono truncate">{d.hostname}</span>
                  {d.primary && <Star size={11} className="text-amber-300" fill="currentColor" />}
                </div>
                <div className="mt-1 flex items-center justify-between">
                  <StatusBadge status={d.status} />
                </div>
              </button>
            ))
          )}
        </aside>

        <section className="col-span-8 overflow-y-auto">
          {!active ? (
            <div className="p-6 text-zinc-500 text-sm">Select a domain to see DNS instructions.</div>
          ) : (
            <div className="p-4 space-y-4" data-testid="domain-detail">
              <div className="flex items-start justify-between flex-wrap gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-xl font-semibold tracking-tight">{active.hostname}</h3>
                    {active.primary && (
                      <span className="nxt-overline text-amber-300 flex items-center gap-1">
                        <Star size={10} fill="currentColor" /> primary
                      </span>
                    )}
                  </div>
                  <div className="mt-1"><StatusBadge status={active.status} /></div>
                  {active.last_checked_at && (
                    <div className="mt-1 nxt-overline text-zinc-600">
                      last checked: {new Date(active.last_checked_at).toLocaleString()}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {!active.primary && (
                    <button
                      onClick={() => onSetPrimary(active.id)}
                      className="nxt-btn !py-1.5 !px-3"
                      data-testid="set-primary-domain"
                    >
                      <Star size={12} /> Set primary
                    </button>
                  )}
                  <button
                    onClick={() => onVerify(active.id)}
                    disabled={verifying === active.id}
                    className="nxt-btn-primary !py-1.5 !px-3"
                    data-testid="verify-domain-button"
                  >
                    {verifying === active.id ? (
                      <><Loader2 size={12} className="animate-spin" /> Checking</>
                    ) : (
                      <><RefreshCw size={12} /> Verify DNS</>
                    )}
                  </button>
                  <button
                    onClick={() => onRemove(active.id, active.hostname)}
                    className="nxt-btn !py-1.5 !px-3 text-red-300 border-red-500/30"
                    data-testid="remove-domain-button"
                  >
                    <Trash2 size={12} /> Remove
                  </button>
                </div>
              </div>

              {active.error && (
                <div className="nxt-panel rounded-sm p-3 border-red-500/30">
                  <div className="flex items-center gap-2 text-red-300 text-sm">
                    <AlertTriangle size={13} /> {active.error}
                  </div>
                </div>
              )}

              <div className="nxt-panel rounded-sm">
                <div className="px-3 py-2 border-b border-white/5 flex items-center justify-between">
                  <span className="nxt-overline">// dns instructions</span>
                  <span className="nxt-overline text-zinc-600">add these records at your registrar</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs mono">
                    <thead className="text-zinc-500">
                      <tr className="border-b border-white/5">
                        <th className="text-left p-2">Type</th>
                        <th className="text-left p-2">Name</th>
                        <th className="text-left p-2">Value</th>
                        <th className="p-2"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {active.dns_records.map((r, idx) => (
                        <tr key={idx} className="border-b border-white/5 last:border-0 hover:bg-white/[0.03]">
                          <td className="p-2 text-zinc-300">{r.type}</td>
                          <td className="p-2 text-zinc-300">{r.name}</td>
                          <td className="p-2 text-zinc-300 break-all">{r.value}</td>
                          <td className="p-2">
                            <button
                              onClick={() => { navigator.clipboard.writeText(r.value); toast.success("Copied"); }}
                              className="text-zinc-500 hover:text-white transition"
                              title="Copy value"
                            >
                              <Copy size={11} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="p-3 nxt-overline text-zinc-500 leading-relaxed">
                  After updating DNS, click <span className="text-zinc-300">Verify DNS</span>. Propagation can take a few minutes to several hours. Once verified, NXT1 will route traffic from this hostname to your deployed project. SSL/HTTPS provisioning is planned via the Cloudflare API integration.
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
