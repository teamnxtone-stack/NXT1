/**
 * NXT1 — Live view (deployed apps).
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ExternalLink, Radio } from "lucide-react";
import { listProjects } from "@/lib/api";
import { deployUrl } from "@/lib/api";

export default function WorkspaceLive() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listProjects()
      .then(({ data }) => setItems((data || []).filter((p) => p.deployed || p.deploy_slug)))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="px-4 sm:px-8 pt-8 sm:pt-12 max-w-[1180px] mx-auto" data-testid="workspace-live">
      <h1 className="text-2xl sm:text-[28px] font-semibold tracking-tight mb-1">Live</h1>
      <p className="text-[13px] text-white/45 mb-6">Apps currently deployed and reachable.</p>

      {loading ? (
        <div className="text-[13px] text-white/45">Loading…</div>
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {items.map((p) => {
            const url = p.deploy_slug ? deployUrl(p.deploy_slug) : null;
            return (
              <div
                key={p.id}
                className="rounded-2xl p-4 transition group"
                style={{
                  background: "rgba(255,255,255,0.025)",
                  border: "1px solid rgba(255,255,255,0.05)",
                }}
                data-testid={`live-card-${p.id}`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="flex items-center gap-1.5 text-[10.5px] mono uppercase tracking-[0.22em] text-emerald-400">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    LIVE
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => navigate(`/builder/${p.id}`)}
                  className="text-left w-full"
                >
                  <div className="text-[15px] text-white font-medium truncate group-hover:text-[#5EEAD4] transition">
                    {p.name || "Untitled"}
                  </div>
                </button>
                {url && (
                  <a
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-[12px] text-white/55 hover:text-white truncate"
                  >
                    {url.replace(/^https?:\/\//, "")} <ExternalLink size={10} />
                  </a>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div
      className="rounded-2xl py-12 px-6 text-center"
      style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.05)" }}
    >
      <div className="mx-auto h-11 w-11 rounded-2xl flex items-center justify-center mb-3"
           style={{ background: "rgba(94,234,212,0.08)", border: "1px solid rgba(94,234,212,0.18)" }}>
        <Radio size={18} className="text-[#5EEAD4]" />
      </div>
      <div className="text-[14px] text-white font-medium">No live apps yet</div>
      <div className="text-[12.5px] text-white/45 mt-1">Deploy a build to make it publicly accessible.</div>
    </div>
  );
}
