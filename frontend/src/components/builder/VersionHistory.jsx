import { useEffect, useState } from "react";
import { History, RotateCcw, Loader2, GitCompare, X } from "lucide-react";
import { listVersions, restoreVersion, getVersion } from "@/lib/api";
import { toast } from "sonner";
import { CodeDiffViewer, langOf } from "@/components/builder/CodeEditor";

export default function VersionHistory({ projectId, currentFiles, onRestored }) {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState(null);
  const [diffOpen, setDiffOpen] = useState(false);
  const [diffVersion, setDiffVersion] = useState(null);
  const [diffPath, setDiffPath] = useState("index.html");
  const [diffLoading, setDiffLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const { data } = await listVersions(projectId);
      setVersions(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (projectId) refresh();
  }, [projectId]);

  const restore = async (vid) => {
    setRestoring(vid);
    try {
      await restoreVersion(projectId, vid);
      toast.success("Restored");
      await refresh();
      onRestored?.();
    } catch {
      toast.error("Restore failed");
    } finally {
      setRestoring(null);
    }
  };

  const openDiff = async (v) => {
    setDiffLoading(true);
    setDiffOpen(true);
    try {
      const { data } = await getVersion(projectId, v.id);
      setDiffVersion(data);
      setDiffPath((data.files?.[0]?.path) || "index.html");
    } catch {
      toast.error("Could not load version");
      setDiffOpen(false);
    } finally {
      setDiffLoading(false);
    }
  };

  const allPaths = (() => {
    const set = new Set();
    (currentFiles || []).forEach((f) => set.add(f.path));
    (diffVersion?.files || []).forEach((f) => set.add(f.path));
    return Array.from(set).sort();
  })();

  const originalContent =
    diffVersion?.files?.find((f) => f.path === diffPath)?.content ?? "";
  const modifiedContent =
    (currentFiles || []).find((f) => f.path === diffPath)?.content ?? "";

  return (
    <div className="flex flex-col h-full surface-recessed border-t border-white/5" data-testid="version-history-panel">
      <div className="h-10 shrink-0 flex items-center px-3 border-b border-white/5 justify-between">
        <span className="nxt-overline flex items-center gap-2">
          <History size={11} /> // history
        </span>
        <span className="nxt-overline text-zinc-600">{versions.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading ? (
          <div className="text-zinc-600 text-xs px-2 py-1 mono">loading…</div>
        ) : versions.length === 0 ? (
          <div className="text-zinc-600 text-xs px-2 py-1 mono">no versions yet</div>
        ) : (
          versions.map((v) => (
            <div
              key={v.id}
              className="group p-2 border border-white/5 rounded-sm hover:border-white/15 transition"
              data-testid={`version-${v.id}`}
            >
              <div className="text-[11px] mono text-zinc-500">
                {new Date(v.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </div>
              <div className="text-xs text-zinc-300 truncate mt-0.5">{v.label}</div>
              <div className="mt-1.5 flex items-center gap-3">
                <button
                  onClick={() => openDiff(v)}
                  className="inline-flex items-center gap-1 text-[11px] mono text-zinc-500 hover:text-white transition"
                  data-testid={`version-diff-${v.id}`}
                >
                  <GitCompare size={10} /> diff
                </button>
                <button
                  onClick={() => restore(v.id)}
                  disabled={restoring === v.id}
                  className="inline-flex items-center gap-1 text-[11px] mono text-zinc-500 hover:text-white transition"
                  data-testid={`version-restore-${v.id}`}
                >
                  {restoring === v.id ? <Loader2 size={10} className="animate-spin" /> : <RotateCcw size={10} />} restore
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {diffOpen && (
        <div className="fixed inset-0 z-50 bg-graphite-scrim-strong backdrop-blur-sm flex items-center justify-center p-4" data-testid="diff-modal">
          <div className="nxt-panel rounded-sm w-[1280px] max-w-[95vw] h-[85vh] flex flex-col bg-[#1F1F23]">
            <div className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-white/5">
              <div className="flex items-center gap-3">
                <GitCompare size={14} className="text-white" />
                <div className="text-sm font-medium">Version diff</div>
                <span className="nxt-overline">{diffVersion?.label}</span>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={diffPath}
                  onChange={(e) => setDiffPath(e.target.value)}
                  className="bg-[#1F1F23] border border-white/10 rounded-sm text-xs mono px-2 py-1 text-zinc-300 outline-none focus:border-white/30"
                  data-testid="diff-path-select"
                >
                  {allPaths.map((p) => <option key={p} value={p} className="bg-[#1F1F23]">{p}</option>)}
                </select>
                <button onClick={() => setDiffOpen(false)} className="p-1 text-zinc-500 hover:text-white" aria-label="Close">
                  <X size={16} />
                </button>
              </div>
            </div>
            <div className="px-4 py-1.5 nxt-overline text-zinc-500 border-b border-white/5 flex justify-between">
              <span>← snapshot ({new Date(diffVersion?.created_at || Date.now()).toLocaleString()})</span>
              <span>current →</span>
            </div>
            <div className="flex-1 min-h-0">
              {diffLoading ? (
                <div className="h-full flex items-center justify-center text-zinc-500"><Loader2 size={14} className="animate-spin mr-2" /> loading…</div>
              ) : (
                <CodeDiffViewer original={originalContent} modified={modifiedContent} language={langOf(diffPath)} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
