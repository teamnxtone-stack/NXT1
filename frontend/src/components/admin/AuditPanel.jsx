/**
 * AuditPanel — unified audit log of every meaningful action on NXT1.
 * Filters by tool. Each row shows tool · action · target · status · ts.
 */
import { useEffect, useState } from "react";
import { Activity, Loader2, RefreshCw, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { adminAuditList, adminAuditRollback } from "@/lib/api";

const TOOL_FILTERS = [
  { id: "", label: "All" },
  { id: "site-editor", label: "Site editor" },
  { id: "deploy", label: "Deploys" },
  { id: "env", label: "Env" },
  { id: "secrets", label: "Secrets" },
  { id: "db", label: "Database" },
  { id: "github", label: "GitHub" },
];

const STATUS_COLORS = {
  ok: "border-emerald-400/25 bg-emerald-500/[0.06] text-emerald-200",
  failed: "border-red-400/25 bg-red-500/[0.06] text-red-200",
  partial: "border-amber-400/25 bg-amber-500/[0.06] text-amber-200",
  rolled_back: "border-zinc-400/25 bg-zinc-500/[0.06] text-zinc-300",
};

export default function AuditPanel() {
  const [items, setItems] = useState([]);
  const [tool, setTool] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = async (t = tool) => {
    setLoading(true);
    try {
      const { data } = await adminAuditList({ tool: t || undefined, limit: 100 });
      setItems(data.items || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load audit");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh(tool);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tool]);

  const rollback = async (id) => {
    if (!window.confirm("Roll back this entry?")) return;
    try {
      const { data } = await adminAuditRollback(id);
      if (data.ok) {
        toast.success("Rolled back");
      } else {
        toast.warning("Manual rollback required", { description: data.reason });
      }
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  return (
    <div className="p-4 sm:p-6" data-testid="audit-panel">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <div className="mono text-[10px] tracking-[0.32em] uppercase text-zinc-500 mb-1.5">
            // audit log
          </div>
          <h1
            className="text-2xl sm:text-3xl font-black tracking-tighter text-white"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
          >
            Every action, traced.
          </h1>
          <p className="text-zinc-400 text-[12.5px] mt-1.5 max-w-2xl">
            Tool-contract log of file edits, deploys, env changes, secret
            updates, DB provisioning + migrations. Newest first.
          </p>
        </div>
        <button
          onClick={() => refresh()}
          className="h-9 w-9 flex items-center justify-center rounded-full text-zinc-400 hover:text-white hover:bg-white/5 transition"
          data-testid="audit-refresh"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3" data-testid="audit-filters">
        {TOOL_FILTERS.map((f) => (
          <button
            key={f.id || "all"}
            onClick={() => setTool(f.id)}
            className={`px-3 py-1.5 rounded-full text-[11.5px] mono uppercase tracking-wider border transition ${
              tool === f.id
                ? "bg-white text-black border-white"
                : "border-white/15 text-zinc-300 hover:border-white/30 hover:text-white"
            }`}
            data-testid={`audit-filter-${f.id || "all"}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-zinc-500 text-[12px]">
          <Loader2 size={14} className="animate-spin inline mr-2" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-white/8 surface-1 p-6 text-center">
          <Activity size={20} className="mx-auto text-zinc-600 mb-2" />
          <div className="text-[13px] text-zinc-400">No audit entries{tool ? ` for ${tool}` : ""}.</div>
          <div className="text-[11.5px] text-zinc-600 mt-1">
            New activity is logged automatically as you use NXT1.
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          {items.map((it) => (
            <div
              key={it.id}
              className="rounded-lg border border-white/8 surface-1 px-3.5 py-2.5"
              data-testid={`audit-row-${it.id}`}
            >
              <div className="flex items-center gap-2 flex-wrap">
                <span className="mono text-[10.5px] tracking-wider uppercase text-zinc-500">
                  {fmtTs(it.ts)}
                </span>
                <span className="px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/10 mono text-[10.5px] uppercase tracking-wider text-zinc-300">
                  {it.tool}
                </span>
                <span className="text-[12px] text-zinc-300">{it.action}</span>
                {it.status && (
                  <span className={`px-2 py-0.5 rounded-full mono text-[10px] uppercase tracking-wider border ${STATUS_COLORS[it.status] || "border-white/10 text-zinc-400"}`}>
                    {it.status}
                  </span>
                )}
                {it.rolled_back && (
                  <span className="px-2 py-0.5 rounded-full mono text-[10px] uppercase tracking-wider border border-zinc-400/30 text-zinc-400">
                    rolled back
                  </span>
                )}
                <span className="text-[10.5px] text-zinc-600 ml-auto">{it.actor}</span>
              </div>
              <div className="text-[12.5px] text-zinc-300 mono mt-1 break-all">{it.target}</div>
              {it.tool === "site-editor" && !it.rolled_back && (
                <button
                  onClick={() => rollback(it.id)}
                  className="inline-flex items-center gap-1.5 mt-2 px-2.5 py-1 rounded-full border border-white/15 text-zinc-300 text-[11px] hover:border-white/30 hover:text-white transition"
                  data-testid={`audit-rollback-${it.id}`}
                >
                  <Undo2 size={11} /> Rollback
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function fmtTs(ts) {
  try {
    const d = new Date(ts);
    return d.toISOString().slice(5, 16).replace("T", " ");
  } catch {
    return ts || "";
  }
}
