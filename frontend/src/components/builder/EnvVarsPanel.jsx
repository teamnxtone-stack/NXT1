import { useEffect, useState } from "react";
import { Key, Plus, Trash2, Loader2, Eye, EyeOff, Pencil, Check, X } from "lucide-react";
import { listEnv, upsertEnv, deleteEnv } from "@/lib/api";
import { toast } from "sonner";

export default function EnvVarsPanel({ projectId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [k, setK] = useState("");
  const [v, setV] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editingKey, setEditingKey] = useState(null);
  const [editVal, setEditVal] = useState("");
  const [editShow, setEditShow] = useState(false);

  const refresh = async () => {
    try {
      const { data } = await listEnv(projectId);
      setItems(data);
    } catch { /* ignore */ } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [projectId]);

  const add = async (e) => {
    e.preventDefault();
    if (!k.trim() || !v) return;
    setBusy(true);
    try {
      await upsertEnv(projectId, k.trim().toUpperCase(), v);
      toast.success(`Set ${k}`);
      setK(""); setV("");
      await refresh();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally { setBusy(false); }
  };

  const remove = async (key) => {
    if (!window.confirm(`Delete ${key}?`)) return;
    try {
      await deleteEnv(projectId, key);
      toast.success("Deleted");
      await refresh();
    } catch { toast.error("Delete failed"); }
  };

  const startEdit = (key) => {
    setEditingKey(key);
    setEditVal("");
    setEditShow(false);
  };
  const cancelEdit = () => { setEditingKey(null); setEditVal(""); };
  const saveEdit = async (key) => {
    if (!editVal) { cancelEdit(); return; }
    try {
      await upsertEnv(projectId, key, editVal);
      toast.success(`Updated ${key}`);
      cancelEdit();
      await refresh();
    } catch { toast.error("Update failed"); }
  };

  return (
    <div className="flex flex-col h-full surface-recessed" data-testid="env-panel">
      <div className="shrink-0 px-4 py-3 border-b border-white/5 flex items-center gap-3 flex-wrap">
        <Key size={14} className="text-white" />
        <div className="flex-1 min-w-[200px]">
          <div className="text-sm font-medium">Environment variables</div>
          <div className="nxt-overline">// backend-only · injected into runtime · never exposed to frontend</div>
        </div>
      </div>

      <form onSubmit={add} className="shrink-0 px-4 py-3 border-b border-white/5 flex items-end gap-2 flex-wrap">
        <div className="flex-1 min-w-[180px]">
          <label className="nxt-overline block mb-1">key</label>
          <input
            value={k}
            onChange={(e) => setK(e.target.value)}
            placeholder="DATABASE_URL"
            className="nxt-input mono uppercase"
            data-testid="env-key-input"
          />
        </div>
        <div className="flex-[2] min-w-[280px]">
          <label className="nxt-overline block mb-1">value</label>
          <div className="relative">
            <input
              type={show ? "text" : "password"}
              value={v}
              onChange={(e) => setV(e.target.value)}
              placeholder="••••••"
              className="nxt-input mono pr-9"
              data-testid="env-value-input"
            />
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white"
            >
              {show ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
          </div>
        </div>
        <button
          type="submit"
          disabled={busy || !k.trim() || !v}
          className="nxt-btn-primary !py-2 !px-4"
          data-testid="env-add-button"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Save
        </button>
      </form>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-zinc-500 text-sm mono">loading…</div>
        ) : items.length === 0 ? (
          <div className="p-6 text-zinc-500 text-sm">
            No environment variables yet. Add one above — it will be injected into your runtime sandbox.
          </div>
        ) : (
          <table className="w-full text-sm mono">
            <thead className="text-zinc-500 sticky top-0 surface-recessed border-b border-white/5">
              <tr>
                <th className="text-left p-3 font-normal nxt-overline">key</th>
                <th className="text-left p-3 font-normal nxt-overline">value (masked)</th>
                <th className="text-left p-3 font-normal nxt-overline hidden md:table-cell">scope</th>
                <th className="text-left p-3 font-normal nxt-overline hidden lg:table-cell">updated</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.key} className="border-b border-white/5 hover:bg-white/[0.03]" data-testid={`env-row-${e.key}`}>
                  <td className="p-3 text-zinc-200">{e.key}</td>
                  <td className="p-3 text-zinc-400">
                    {editingKey === e.key ? (
                      <div className="relative">
                        <input
                          type={editShow ? "text" : "password"}
                          autoFocus
                          value={editVal}
                          onChange={(ev) => setEditVal(ev.target.value)}
                          onKeyDown={(ev) => {
                            if (ev.key === "Enter") saveEdit(e.key);
                            if (ev.key === "Escape") cancelEdit();
                          }}
                          placeholder="new value"
                          className="nxt-input mono !py-1.5 !px-2 w-full pr-8"
                          data-testid={`env-edit-input-${e.key}`}
                        />
                        <button
                          type="button"
                          onClick={() => setEditShow((s) => !s)}
                          className="absolute right-1.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white"
                        >
                          {editShow ? <EyeOff size={11} /> : <Eye size={11} />}
                        </button>
                      </div>
                    ) : (
                      e.value_masked
                    )}
                  </td>
                  <td className="p-3 text-zinc-500 hidden md:table-cell">{e.scope}</td>
                  <td className="p-3 text-zinc-600 text-xs hidden lg:table-cell">
                    {e.updated_at ? new Date(e.updated_at).toLocaleString() : "—"}
                  </td>
                  <td className="p-3">
                    <div className="flex items-center gap-1.5 justify-end">
                      {editingKey === e.key ? (
                        <>
                          <button
                            onClick={() => saveEdit(e.key)}
                            className="text-emerald-400 hover:text-emerald-300 p-1"
                            data-testid={`env-save-${e.key}`}
                            title="Save"
                          >
                            <Check size={13} />
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="text-zinc-500 hover:text-white p-1"
                            data-testid={`env-cancel-${e.key}`}
                            title="Cancel"
                          >
                            <X size={13} />
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => startEdit(e.key)}
                            className="text-zinc-500 hover:text-white p-1 transition"
                            data-testid={`env-edit-${e.key}`}
                            title="Edit value"
                          >
                            <Pencil size={12} />
                          </button>
                          <button
                            onClick={() => remove(e.key)}
                            className="text-zinc-500 hover:text-red-400 p-1 transition"
                            data-testid={`env-delete-${e.key}`}
                            title="Delete"
                          >
                            <Trash2 size={13} />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
