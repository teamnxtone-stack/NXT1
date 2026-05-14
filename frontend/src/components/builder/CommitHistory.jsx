import { useEffect, useState } from "react";
import { GitCommit, Search, Rocket, RotateCcw, GitCompare, Pencil, Loader2, X } from "lucide-react";
import { listCommits, restoreVersion, labelVersion, getVersion } from "@/lib/api";
import { toast } from "sonner";
import { CodeDiffViewer, langOf } from "@/components/builder/CodeEditor";

export default function CommitHistory({ projectId, currentFiles, onRestored }) {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [editLabel, setEditLabel] = useState("");
  const [editMsg, setEditMsg] = useState("");
  const [diffOpen, setDiffOpen] = useState(false);
  const [diffVersion, setDiffVersion] = useState(null);
  const [diffPath, setDiffPath] = useState("index.html");
  const [diffLoading, setDiffLoading] = useState(false);

  const refresh = async (query = "") => {
    setLoading(true);
    try {
      const { data } = await listCommits(projectId, query);
      setItems(data);
    } catch { /* ignore */ } finally { setLoading(false); }
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [projectId]);

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => refresh(q), 200);
    return () => clearTimeout(t);
    // eslint-disable-next-line
  }, [q]);

  const restore = async (id) => {
    if (!window.confirm("Restore this commit? Current state is auto-snapshotted before restore.")) return;
    try {
      await restoreVersion(projectId, id);
      toast.success("Restored");
      onRestored?.();
      await refresh(q);
    } catch { toast.error("Restore failed"); }
  };

  const startEdit = (v) => {
    setEditing(v.id);
    setEditLabel(v.label || "");
    setEditMsg(v.commit_message || "");
  };

  const saveLabel = async () => {
    try {
      await labelVersion(projectId, editing, editLabel, editMsg);
      toast.success("Updated");
      setEditing(null);
      await refresh(q);
    } catch { toast.error("Update failed"); }
  };

  const openDiff = async (id) => {
    setDiffLoading(true);
    setDiffOpen(true);
    try {
      const { data } = await getVersion(projectId, id);
      setDiffVersion(data);
      setDiffPath((data.files?.[0]?.path) || "index.html");
    } catch {
      toast.error("Could not load");
      setDiffOpen(false);
    } finally { setDiffLoading(false); }
  };

  const allPaths = (() => {
    const set = new Set();
    (currentFiles || []).forEach((f) => set.add(f.path));
    (diffVersion?.files || []).forEach((f) => set.add(f.path));
    return Array.from(set).sort();
  })();
  const original = diffVersion?.files?.find((f) => f.path === diffPath)?.content ?? "";
  const modified = (currentFiles || []).find((f) => f.path === diffPath)?.content ?? "";

  return (
    <div className="flex flex-col h-full surface-recessed" data-testid="commit-history">
      <div className="shrink-0 px-4 py-3 border-b border-white/5 flex items-center gap-3 flex-wrap">
        <GitCommit size={14} className="text-white" />
        <div className="flex-1 min-w-[200px]">
          <div className="text-sm font-medium">AI commit history</div>
          <div className="nxt-overline">// every accepted change is a labeled, searchable snapshot</div>
        </div>
        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="search commits…"
            className="nxt-input !py-1.5 pl-7 mono text-xs w-[220px]"
            data-testid="commit-search"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-zinc-500 text-sm mono">loading…</div>
        ) : items.length === 0 ? (
          <div className="p-6 text-zinc-500 text-sm">No commits yet. Start a chat to create your first AI commit.</div>
        ) : (
          <div className="relative">
            {/* Vertical timeline rail */}
            <div className="absolute left-7 top-0 bottom-0 w-px bg-white/10" />
            {items.map((c) => (
              <div key={c.id} className="relative flex gap-4 px-4 py-4 border-b border-white/5 hover:bg-white/[0.02] group" data-testid={`commit-${c.id}`}>
                <div className="relative shrink-0 mt-1">
                  <div className={`relative z-10 h-3 w-3 rounded-full border-2 ${
                    c.type === "ai" ? "bg-emerald-500/30 border-emerald-400"
                    : c.type === "restore" ? "bg-amber-500/30 border-amber-400"
                    : "bg-zinc-500/30 border-zinc-400"
                  }`} />
                </div>
                <div className="flex-1 min-w-0">
                  {editing === c.id ? (
                    <div className="space-y-2">
                      <input
                        value={editLabel}
                        onChange={(e) => setEditLabel(e.target.value)}
                        className="nxt-input !py-1.5 text-sm"
                        placeholder="Commit label"
                      />
                      <textarea
                        rows={2}
                        value={editMsg}
                        onChange={(e) => setEditMsg(e.target.value)}
                        className="nxt-input !py-1.5 text-sm resize-none"
                        placeholder="Longer description"
                      />
                      <div className="flex gap-2">
                        <button onClick={saveLabel} className="nxt-btn-primary !py-1 !px-2 !text-xs">Save</button>
                        <button onClick={() => setEditing(null)} className="nxt-btn !py-1 !px-2 !text-xs">Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-white truncate">{c.label || "(unlabeled)"}</span>
                        <span className="nxt-overline">{c.type}</span>
                        {c.deploy_id && (
                          <span className="inline-flex items-center gap-1 nxt-overline text-emerald-300">
                            <Rocket size={9} /> deployed
                          </span>
                        )}
                      </div>
                      {c.commit_message && (
                        <div className="text-sm text-zinc-400 mt-0.5 leading-relaxed">{c.commit_message}</div>
                      )}
                      <div className="mt-1 nxt-overline text-zinc-600">
                        {new Date(c.created_at).toLocaleString()}
                      </div>
                      <div className="mt-2 flex items-center gap-3 text-xs mono opacity-0 group-hover:opacity-100 transition">
                        <button onClick={() => openDiff(c.id)} className="text-zinc-500 hover:text-white inline-flex items-center gap-1" data-testid={`commit-diff-${c.id}`}>
                          <GitCompare size={11} /> diff
                        </button>
                        <button onClick={() => restore(c.id)} className="text-zinc-500 hover:text-white inline-flex items-center gap-1" data-testid={`commit-restore-${c.id}`}>
                          <RotateCcw size={11} /> restore
                        </button>
                        <button onClick={() => startEdit(c)} className="text-zinc-500 hover:text-white inline-flex items-center gap-1" data-testid={`commit-edit-${c.id}`}>
                          <Pencil size={11} /> rename
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {diffOpen && (
        <div className="fixed inset-0 z-50 bg-graphite-scrim-strong backdrop-blur-sm flex items-center justify-center p-4" data-testid="commit-diff-modal">
          <div className="nxt-panel rounded-sm w-[1280px] max-w-[95vw] h-[85vh] flex flex-col bg-[#1F1F23]">
            <div className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-white/5">
              <div className="flex items-center gap-3 min-w-0">
                <GitCompare size={14} className="text-white" />
                <div className="text-sm font-medium truncate">{diffVersion?.label}</div>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={diffPath}
                  onChange={(e) => setDiffPath(e.target.value)}
                  className="bg-[#1F1F23] border border-white/10 rounded-sm text-xs mono px-2 py-1 text-zinc-300 outline-none focus:border-white/30"
                >
                  {allPaths.map((p) => <option key={p} value={p} className="bg-[#1F1F23]">{p}</option>)}
                </select>
                <button onClick={() => setDiffOpen(false)} className="p-1 text-zinc-500 hover:text-white"><X size={16} /></button>
              </div>
            </div>
            <div className="px-4 py-1.5 nxt-overline text-zinc-500 border-b border-white/5 flex justify-between">
              <span>← snapshot · {new Date(diffVersion?.created_at || Date.now()).toLocaleString()}</span>
              <span>current →</span>
            </div>
            <div className="flex-1 min-h-0">
              {diffLoading ? (
                <div className="h-full flex items-center justify-center text-zinc-500"><Loader2 size={14} className="animate-spin mr-2" /> loading…</div>
              ) : (
                <CodeDiffViewer original={original} modified={modified} language={langOf(diffPath)} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
