/**
 * EditableKeysPanel — admin-only inline editor for backend env vars.
 * Fully drives the .env file through /api/admin/secrets. Each key is masked
 * by default; click the eye to reveal, type to update, save persists to
 * `/app/backend/.env` and live-patches `os.environ` so the change takes
 * effect on the next request without a hard restart.
 *
 * Protected keys (MONGO_URL, DB_NAME, JWT_SECRET, APP_PASSWORD) are NOT
 * exposed.
 */
import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  RefreshCw,
  Save,
} from "lucide-react";
import { toast } from "sonner";
import {
  adminListSecrets,
  adminUpdateSecrets,
  adminReloadEnv,
} from "@/lib/api";
import GithubStatusBanner from "./GithubStatusBanner";

export default function EditableKeysPanel({ gh }) {
  const [items, setItems] = useState([]);
  const [drafts, setDrafts] = useState({}); // key -> string (uncommitted)
  const [reveal, setReveal] = useState({});  // key -> bool
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const refresh = () => {
    setLoading(true);
    adminListSecrets()
      .then(({ data }) => {
        setItems(data.items || []);
        setDrafts({});
      })
      .catch((e) => toast.error(e?.response?.data?.detail || "Couldn't load secrets"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
  }, []);

  const dirty = Object.keys(drafts).length > 0;

  const save = async () => {
    if (!dirty) return;
    setSaving(true);
    try {
      await adminUpdateSecrets(drafts);
      try { await adminReloadEnv(); } catch { /* ignore */ }
      toast.success(`Saved ${Object.keys(drafts).length} secret(s) to .env`);
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-3xl" data-testid="admin-keys-tab">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <div className="mono text-[10px] tracking-[0.32em] uppercase text-zinc-500 mb-1.5">
            // keys & secrets
          </div>
          <h1
            className="text-2xl sm:text-3xl font-black tracking-tighter text-white"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
          >
            Backend env, editable in place.
          </h1>
        </div>
        <button
          onClick={refresh}
          disabled={loading || saving}
          className="h-9 w-9 flex items-center justify-center rounded-full text-zinc-400 hover:text-white hover:bg-white/5 transition disabled:opacity-50"
          title="Refresh"
          data-testid="keys-refresh"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <p className="text-[12.5px] text-zinc-500 leading-relaxed mb-4 max-w-2xl">
        Stored in <span className="mono text-zinc-300">/app/backend/.env</span>{" "}
        and never sent to the browser. Saving updates the file in place and
        hot-patches the running process. Protected keys
        (MONGO_URL, DB_NAME, JWT_SECRET, APP_PASSWORD) are hidden.
      </p>

      <GithubStatusBanner gh={gh} />

      <div className="mt-3 space-y-1.5">
        {loading && (
          <div className="text-zinc-500 text-[12px]">
            <Loader2 size={14} className="animate-spin inline mr-2" />
            Loading…
          </div>
        )}
        {items.map((s) => {
          const draft = drafts[s.key];
          const isEdited = draft !== undefined;
          const isRevealed = reveal[s.key];
          return (
            <div
              key={s.key}
              className={`rounded-lg border surface-1 px-3.5 py-2.5 ${
                isEdited ? "border-emerald-400/40" : "border-white/8"
              }`}
              data-testid={`admin-secret-${s.key}`}
            >
              <div className="flex items-center justify-between gap-3 mb-1.5">
                <div className="flex items-center gap-2 min-w-0">
                  <KeyRound size={11} className="text-zinc-500 shrink-0" />
                  <span className="mono text-[12px] text-white truncate">{s.key}</span>
                  {s.present && !isEdited && (
                    <CheckCircle2 size={11} className="text-emerald-400 shrink-0" />
                  )}
                  {isEdited && (
                    <span className="text-[10px] mono uppercase tracking-wider text-emerald-300 shrink-0">
                      modified
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setReveal((r) => ({ ...r, [s.key]: !r[s.key] }))}
                  className="text-zinc-500 hover:text-white transition shrink-0"
                  title={isRevealed ? "Hide" : "Show"}
                  data-testid={`secret-toggle-${s.key}`}
                >
                  {isRevealed ? <EyeOff size={12} /> : <Eye size={12} />}
                </button>
              </div>
              <input
                type={isRevealed ? "text" : "password"}
                value={isEdited ? draft : (s.present ? "••••••••••••••••" : "")}
                placeholder={s.present ? `current: ${s.fingerprint}` : "(not set)"}
                onFocus={() => {
                  // First focus → start with empty draft so the user can type
                  // a new value cleanly without erasing the masked dots.
                  if (!isEdited) setDrafts((d) => ({ ...d, [s.key]: "" }));
                }}
                onChange={(e) => setDrafts((d) => ({ ...d, [s.key]: e.target.value }))}
                className="nxt-auth-input mono text-[12.5px]"
                data-testid={`secret-input-${s.key}`}
              />
            </div>
          );
        })}
      </div>

      <div className="sticky bottom-0 -mx-4 sm:-mx-6 mt-5 px-4 sm:px-6 py-3 surface-recessed/95 backdrop-blur border-t border-white/5 flex items-center justify-between gap-3">
        <span className="text-[12px] text-zinc-500">
          {dirty ? `${Object.keys(drafts).length} change(s) staged` : "No changes"}
        </span>
        <div className="flex gap-2">
          {dirty && (
            <button
              onClick={() => setDrafts({})}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-full border border-white/15 text-zinc-300 text-[12px] hover:border-white/30 transition"
              data-testid="keys-discard"
            >
              Discard
            </button>
          )}
          <button
            onClick={save}
            disabled={!dirty || saving}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-400 text-black text-[13px] font-semibold hover:bg-emerald-300 transition disabled:opacity-50"
            data-testid="keys-save"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} strokeWidth={2.5} />}
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
