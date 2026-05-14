import { useEffect, useState } from "react";
import {
  Activity,
  CheckCircle2,
  Cloud,
  Copy,
  Database,
  Eye,
  EyeOff,
  Loader2,
  Play,
  Plus,
  Sparkles,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import {
  addDatabase,
  dbGenerateSchema,
  dbMigrate,
  dbProviders,
  dbSchemaTemplate,
  dbTest,
  listDatabases,
  provisionDatabase,
  removeDatabase,
} from "@/lib/api";
import { toast } from "sonner";

const KINDS = [
  { value: "postgres", label: "PostgreSQL" },
  { value: "supabase", label: "Supabase" },
  { value: "mongodb", label: "MongoDB / Atlas" },
  { value: "mysql", label: "MySQL" },
  { value: "sqlite", label: "SQLite (file)" },
];

export default function DatabasePanel({ projectId }) {
  const [items, setItems] = useState([]);
  const [providers, setProviders] = useState(null);
  const [loading, setLoading] = useState(true);
  const [provisionOpen, setProvisionOpen] = useState(false);
  const [registerOpen, setRegisterOpen] = useState(false);
  const [activeDb, setActiveDb] = useState(null); // { id, kind, name }
  const [activeMode, setActiveMode] = useState(null); // "schema" | "migrate"

  const refresh = async () => {
    try {
      const [{ data: dbs }, { data: prov }] = await Promise.all([
        listDatabases(projectId),
        dbProviders().catch(() => ({ data: null })),
      ]);
      setItems(dbs);
      setProviders(prov);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const remove = async (id, label) => {
    if (!window.confirm(`Disconnect ${label}? This unlinks NXT1's record only — the database itself is not deleted.`)) return;
    try {
      await removeDatabase(projectId, id);
      toast.success("Disconnected");
      await refresh();
    } catch {
      toast.error("Failed");
    }
  };

  const test = async (db) => {
    toast.message("Pinging…", { id: `t-${db.id}` });
    try {
      const { data } = await dbTest(projectId, db.id);
      if (data.ok) {
        toast.success(`Connected · ${db.name}`, {
          id: `t-${db.id}`,
          description: data.version?.split(" on ")[0],
        });
      } else {
        toast.error(`Connection failed`, { id: `t-${db.id}`, description: data.error });
      }
    } catch (e) {
      toast.error("Test failed", { id: `t-${db.id}`, description: e?.response?.data?.detail });
    }
  };

  return (
    <div className="flex flex-col h-full surface-recessed" data-testid="database-panel">
      <div className="shrink-0 px-4 py-3 border-b border-white/5 flex items-center gap-3 flex-wrap">
        <Database size={14} className="text-white" />
        <div className="flex-1 min-w-[200px]">
          <div className="text-sm font-medium">Database</div>
          <div className="nxt-overline">
            // provision · connect · migrate · auto-inject DATABASE_URL
          </div>
        </div>
        <button
          onClick={() => setProvisionOpen(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-400 text-black text-[12px] font-semibold hover:bg-emerald-300 transition"
          data-testid="db-provision-button"
        >
          <Zap size={12} strokeWidth={2.5} /> Provision
        </button>
        <button
          onClick={() => setRegisterOpen(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-white/15 text-zinc-300 text-[12px] hover:border-white/30 hover:text-white transition"
          data-testid="db-register-button"
        >
          <Plus size={12} /> Connect existing
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-zinc-500 text-sm mono">loading…</div>
        ) : items.length === 0 ? (
          <EmptyState providers={providers} onProvision={() => setProvisionOpen(true)} onRegister={() => setRegisterOpen(true)} />
        ) : (
          <div className="divide-y divide-white/5">
            {items.map((d) => (
              <DbRow
                key={d.id}
                db={d}
                onRemove={() => remove(d.id, d.name)}
                onTest={() => test(d)}
                onSchema={() => { setActiveDb(d); setActiveMode("schema"); }}
                onMigrate={() => { setActiveDb(d); setActiveMode("migrate"); }}
              />
            ))}
          </div>
        )}
      </div>

      {provisionOpen && (
        <ProvisionModal
          providers={providers}
          projectId={projectId}
          onClose={() => setProvisionOpen(false)}
          onDone={async () => { setProvisionOpen(false); await refresh(); }}
        />
      )}
      {registerOpen && (
        <RegisterModal
          projectId={projectId}
          onClose={() => setRegisterOpen(false)}
          onDone={async () => { setRegisterOpen(false); await refresh(); }}
        />
      )}
      {activeDb && (
        <SchemaMigrateModal
          mode={activeMode}
          db={activeDb}
          projectId={projectId}
          onClose={() => { setActiveDb(null); setActiveMode(null); }}
        />
      )}
    </div>
  );
}

// ---------- empty state ----------
function EmptyState({ providers, onProvision, onRegister }) {
  return (
    <div className="p-6">
      <div className="rounded-2xl border border-white/8 surface-1 p-6">
        <div className="flex items-start gap-3 mb-4">
          <span className="h-10 w-10 rounded-xl bg-emerald-500/10 border border-emerald-400/30 flex items-center justify-center shrink-0">
            <Database size={16} className="text-emerald-300" />
          </span>
          <div>
            <div className="text-[15px] font-semibold text-white">No databases yet.</div>
            <div className="text-[12.5px] text-zinc-400 mt-1 leading-relaxed">
              Provision a fresh Neon Postgres or Supabase project in one click. NXT1 wires the
              connection URL into <span className="mono text-zinc-200">DATABASE_URL</span> on
              this project and points the AI at it for the next build.
            </div>
          </div>
        </div>
        <div className="grid sm:grid-cols-2 gap-2.5">
          <button
            onClick={onProvision}
            className="text-left rounded-xl border border-emerald-400/30 bg-gradient-to-br from-[#0d1614] to-[#1F1F23] p-3 hover:border-emerald-400/50 transition"
            data-testid="db-empty-provision"
          >
            <div className="flex items-center gap-2 mb-1">
              <Zap size={12} className="text-emerald-300" />
              <span className="text-[12.5px] font-semibold text-emerald-100">Provision new</span>
            </div>
            <div className="text-[11.5px] text-zinc-400">Neon · Supabase · auto env injection</div>
          </button>
          <button
            onClick={onRegister}
            className="text-left rounded-xl border border-white/10 surface-1 p-3 hover:border-white/25 transition"
            data-testid="db-empty-register"
          >
            <div className="flex items-center gap-2 mb-1">
              <Plus size={12} className="text-zinc-300" />
              <span className="text-[12.5px] font-semibold text-white">Connect existing</span>
            </div>
            <div className="text-[11.5px] text-zinc-500">Postgres · Mongo · MySQL · SQLite</div>
          </button>
        </div>
        {providers && (
          <div className="mt-4 flex flex-wrap gap-1.5 text-[10.5px] mono uppercase tracking-wider">
            {Object.entries(providers).map(([k, p]) => (
              <span
                key={k}
                className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full border ${
                  p.ready
                    ? "border-emerald-400/25 bg-emerald-500/[0.06] text-emerald-200"
                    : "border-white/8 bg-white/[0.02] text-zinc-500"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${p.ready ? "bg-emerald-400" : "bg-zinc-600"}`} />
                {p.label}
                {!p.ready && <span className="text-zinc-600">· needs {p.missing.join(",")}</span>}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------- row ----------
function DbRow({ db, onRemove, onTest, onSchema, onMigrate }) {
  return (
    <div
      className="p-4 flex flex-col md:flex-row md:items-center gap-3 hover:bg-white/[0.02]"
      data-testid={`db-row-${db.name}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-white">{db.name}</span>
          <span className="nxt-overline text-emerald-300">{db.kind}</span>
        </div>
        <div className="text-xs mono text-zinc-400 break-all mt-1">{db.url_masked}</div>
        {db.notes && <div className="text-xs text-zinc-500 mt-1">{db.notes}</div>}
      </div>
      <div className="flex items-center gap-1.5">
        {(db.kind === "postgres" || db.kind === "supabase") && (
          <>
            <button
              onClick={onTest}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-full border border-white/10 text-zinc-300 text-[11px] hover:border-white/25 hover:text-white transition"
              title="Test connection"
              data-testid={`db-test-${db.name}`}
            >
              <Activity size={11} /> Test
            </button>
            <button
              onClick={onSchema}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-full border border-emerald-400/25 text-emerald-200 text-[11px] hover:border-emerald-400/50 transition"
              title="AI-generate schema"
              data-testid={`db-schema-${db.name}`}
            >
              <Sparkles size={11} /> Schema
            </button>
            <button
              onClick={onMigrate}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-full border border-white/10 text-zinc-300 text-[11px] hover:border-white/25 hover:text-white transition"
              title="Run SQL"
              data-testid={`db-migrate-${db.name}`}
            >
              <Play size={11} /> Run SQL
            </button>
          </>
        )}
        <button
          onClick={onRemove}
          className="text-zinc-500 hover:text-red-400 p-1.5 transition"
          title="Disconnect"
          data-testid={`db-delete-${db.name}`}
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );
}

// ---------- provision modal ----------
function ProvisionModal({ providers, projectId, onClose, onDone }) {
  const [provider, setProvider] = useState("neon");
  const [name, setName] = useState("");
  const [region, setRegion] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [reveal, setReveal] = useState(false);

  const p = providers?.[provider];
  const regions = p?.regions || [];

  const submit = async () => {
    if (!p?.ready) {
      toast.error(`${p?.label || provider} not configured`, { description: `Missing: ${p?.missing?.join(", ")}` });
      return;
    }
    if (!name.trim()) {
      toast.error("Give the database a name");
      return;
    }
    setBusy(true);
    try {
      const { data } = await provisionDatabase(projectId, {
        provider,
        name: name.trim(),
        region: region || undefined,
      });
      setResult(data);
      toast.success("Database provisioned + DATABASE_URL injected", {
        description: `${p.label} · ${data.provider_meta?.region || ""}`,
      });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Provisioning failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell onClose={onClose} testid="db-provision-modal">
      <div className="flex items-start gap-3 mb-4">
        <span className="h-9 w-9 rounded-full bg-emerald-500/15 border border-emerald-400/30 flex items-center justify-center shrink-0">
          <Cloud size={14} className="text-emerald-300" />
        </span>
        <div>
          <div className="text-[10px] mono uppercase tracking-[0.28em] text-emerald-400 mb-0.5">
            // provision database
          </div>
          <div className="text-[16px] font-semibold text-white">Spin up a fresh DB and wire it in.</div>
          <div className="text-[12px] text-zinc-400 mt-0.5">
            NXT1 calls the provider's admin API and stores the URL as <span className="mono">DATABASE_URL</span>.
          </div>
        </div>
      </div>

      {!result ? (
        <>
          <div className="grid grid-cols-2 gap-2 mb-3">
            {Object.entries(providers || {}).map(([k, info]) => (
              <button
                key={k}
                disabled={!info.ready}
                onClick={() => { setProvider(k); setRegion(""); }}
                className={`text-left rounded-xl p-3 border transition ${
                  provider === k
                    ? "border-emerald-400/50 bg-emerald-500/[0.06]"
                    : "border-white/10 surface-1 hover:border-white/25"
                } ${!info.ready ? "opacity-40 cursor-not-allowed" : ""}`}
                data-testid={`db-provider-${k}`}
              >
                <div className="text-[13px] font-semibold text-white">{info.label}</div>
                <div className="text-[11px] text-zinc-500 mt-0.5">
                  {info.ready ? "ready" : `needs ${info.missing.join(",")}`}
                </div>
              </button>
            ))}
          </div>

          <Field label="Name">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. nxt1-prod"
              className="nxt-auth-input mono"
              data-testid="db-provision-name"
              autoFocus
            />
          </Field>

          <Field label="Region (optional)">
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="nxt-auth-input mono cursor-pointer"
              data-testid="db-provision-region"
            >
              <option value="">— closest / default —</option>
              {regions.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </Field>

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
              disabled={busy || !p?.ready}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-400 text-black text-[12.5px] font-semibold hover:bg-emerald-300 transition disabled:opacity-50"
              data-testid="db-provision-submit"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} strokeWidth={2.5} />}
              {busy ? "Provisioning…" : `Provision ${p?.label || ""}`}
            </button>
          </div>
        </>
      ) : (
        <ProvisionResult result={result} reveal={reveal} setReveal={setReveal} onDone={onDone} />
      )}
    </ModalShell>
  );
}

function ProvisionResult({ result, reveal, setReveal, onDone }) {
  const url = result.connection_url || "";
  return (
    <div data-testid="db-provision-result">
      <div className="rounded-xl border border-emerald-400/30 bg-emerald-500/[0.05] p-4 mb-3">
        <div className="flex items-center gap-2 text-emerald-200 text-[13px] font-semibold mb-1">
          <CheckCircle2 size={14} /> Provisioned + injected
        </div>
        <div className="text-[12px] text-zinc-300 leading-relaxed">
          <span className="mono">{(result.env_injected || []).join(" · ")}</span> set on this
          project. The connection URL is shown once below — copy if needed (it's stored masked
          and revealed via the runtime env).
        </div>
      </div>
      <div className="flex items-stretch gap-2 mb-3">
        <input
          type={reveal ? "text" : "password"}
          readOnly
          value={url}
          className="nxt-auth-input flex-1 mono text-[11.5px]"
          data-testid="db-provision-url"
        />
        <button
          onClick={() => setReveal((v) => !v)}
          className="h-10 w-10 rounded-xl border border-white/15 text-zinc-300 hover:border-white/30 hover:text-white transition flex items-center justify-center"
          title={reveal ? "Hide" : "Reveal"}
        >
          {reveal ? <EyeOff size={13} /> : <Eye size={13} />}
        </button>
        <button
          onClick={() => { navigator.clipboard.writeText(url); toast.success("Copied"); }}
          className="h-10 w-10 rounded-xl border border-white/15 text-zinc-300 hover:border-white/30 hover:text-white transition flex items-center justify-center"
          title="Copy"
        >
          <Copy size={13} />
        </button>
      </div>
      <pre className="rounded-xl border border-white/8 bg-graphite-scrim-soft p-3 mono text-[11px] text-zinc-400 mb-3 overflow-x-auto">
        {JSON.stringify(result.provider_meta, null, 2)}
      </pre>
      <div className="flex justify-end">
        <button
          onClick={onDone}
          className="px-4 py-2 rounded-full bg-emerald-400 text-black text-[12.5px] font-semibold hover:bg-emerald-300 transition"
          data-testid="db-provision-done"
        >
          Done
        </button>
      </div>
    </div>
  );
}

// ---------- register existing modal ----------
function RegisterModal({ projectId, onClose, onDone }) {
  const [kind, setKind] = useState("postgres");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!name.trim() || !url.trim()) return;
    setBusy(true);
    try {
      await addDatabase(projectId, kind, name.trim(), url.trim(), notes.trim());
      toast.success(`Connected ${name}`);
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell onClose={onClose} testid="db-register-modal">
      <div className="flex items-start gap-3 mb-4">
        <span className="h-9 w-9 rounded-full bg-white/[0.04] border border-white/15 flex items-center justify-center shrink-0">
          <Plus size={14} className="text-white" />
        </span>
        <div>
          <div className="text-[10px] mono uppercase tracking-[0.28em] text-zinc-500 mb-0.5">
            // connect existing
          </div>
          <div className="text-[16px] font-semibold text-white">Register a database you already have.</div>
        </div>
      </div>
      <Field label="Kind">
        <select value={kind} onChange={(e) => setKind(e.target.value)} className="nxt-auth-input mono cursor-pointer" data-testid="db-kind-select">
          {KINDS.map((k) => (<option key={k.value} value={k.value}>{k.label}</option>))}
        </select>
      </Field>
      <Field label="Name">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="main" className="nxt-auth-input mono" data-testid="db-name-input" />
      </Field>
      <Field label="Connection URL">
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="postgres://user:password@host:5432/db" className="nxt-auth-input mono" data-testid="db-url-input" />
      </Field>
      <Field label="Notes (optional)">
        <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="prod read-replica · region eu-west-1" className="nxt-auth-input mono" />
      </Field>
      <div className="flex justify-end gap-2 mt-3">
        <button onClick={onClose} disabled={busy} className="px-4 py-2 rounded-full border border-white/15 text-zinc-300 text-[12.5px] hover:border-white/30 transition">Cancel</button>
        <button
          onClick={submit}
          disabled={busy || !name.trim() || !url.trim()}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-400 text-black text-[12.5px] font-semibold hover:bg-emerald-300 transition disabled:opacity-50"
          data-testid="db-add-button"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
          Connect
        </button>
      </div>
    </ModalShell>
  );
}

// ---------- AI schema / run-SQL modal ----------
function SchemaMigrateModal({ mode, db, projectId, onClose }) {
  const [prompt, setPrompt] = useState("");
  const [sql, setSql] = useState("");
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (mode === "schema") {
      // Pre-fill with the static template so the user has something to start from.
      dbSchemaTemplate(projectId, db.id).then(({ data }) => setSql(data.schema || "")).catch(() => {});
    }
  }, [mode, db.id, projectId]);

  const generate = async () => {
    if (!prompt.trim()) return toast.error("Describe what you want.");
    setBusy(true);
    try {
      const { data } = await dbGenerateSchema(projectId, db.id, prompt);
      setSql(data.sql || "");
      toast.success("Schema generated — review and run.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Generation failed");
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    if (!sql.trim()) return;
    if (!window.confirm("Run this SQL on the database?")) return;
    setRunning(true);
    setResult(null);
    try {
      const { data } = await dbMigrate(projectId, db.id, sql, mode === "schema" ? "schema" : "manual");
      setResult(data);
      if (data.ok) toast.success("SQL executed");
      else toast.error("Execution failed", { description: data.result?.result });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Run failed");
    } finally {
      setRunning(false);
    }
  };

  const isSchema = mode === "schema";

  return (
    <ModalShell onClose={onClose} testid="db-sql-modal" wide>
      <div className="flex items-start gap-3 mb-4">
        <span className={`h-9 w-9 rounded-full flex items-center justify-center shrink-0 border ${
          isSchema ? "bg-emerald-500/15 border-emerald-400/30" : "bg-white/[0.04] border-white/15"
        }`}>
          {isSchema ? <Sparkles size={14} className="text-emerald-300" /> : <Play size={14} className="text-white" />}
        </span>
        <div>
          <div className="text-[10px] mono uppercase tracking-[0.28em] text-zinc-500 mb-0.5">
            // {isSchema ? "ai-generate schema" : "run SQL"} · {db.name}
          </div>
          <div className="text-[16px] font-semibold text-white">
            {isSchema ? "Describe it. Get migration-ready SQL." : "Execute SQL on the database."}
          </div>
        </div>
      </div>

      {isSchema && (
        <Field label="What should it support?">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            placeholder="e.g. Users, projects, and a many-to-many tags table. Each project belongs to one user, has a title, description, and a status (draft/published)."
            className="nxt-auth-input resize-y"
            data-testid="db-schema-prompt"
          />
          <div className="mt-2">
            <button
              onClick={generate}
              disabled={busy || !prompt.trim()}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-400 text-black text-[12.5px] font-semibold hover:bg-emerald-300 transition disabled:opacity-50"
              data-testid="db-schema-generate"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
              {busy ? "Drafting…" : "Generate SQL"}
            </button>
          </div>
        </Field>
      )}

      <Field label="SQL">
        <textarea
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          rows={12}
          className="nxt-auth-input mono text-[12px] resize-y"
          placeholder="CREATE TABLE IF NOT EXISTS …"
          data-testid="db-sql-input"
        />
      </Field>

      {result && (
        <pre className={`rounded-xl border p-3 mono text-[11px] mb-3 overflow-x-auto ${
          result.ok ? "border-emerald-400/30 bg-emerald-500/[0.05] text-emerald-100" : "border-red-400/30 bg-red-500/[0.05] text-red-100"
        }`}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}

      <div className="flex justify-end gap-2 mt-2">
        <button
          onClick={onClose}
          className="px-4 py-2 rounded-full border border-white/15 text-zinc-300 text-[12.5px] hover:border-white/30 transition"
        >
          Close
        </button>
        <button
          onClick={() => { navigator.clipboard.writeText(sql); toast.success("Copied"); }}
          disabled={!sql.trim()}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-full border border-white/15 text-zinc-300 text-[12.5px] hover:border-white/30 transition disabled:opacity-40"
        >
          <Copy size={12} /> Copy
        </button>
        <button
          onClick={run}
          disabled={running || !sql.trim()}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-400 text-black text-[12.5px] font-semibold hover:bg-emerald-300 transition disabled:opacity-50"
          data-testid="db-sql-run"
        >
          {running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} strokeWidth={2.5} />}
          {running ? "Executing…" : "Run on database"}
        </button>
      </div>
    </ModalShell>
  );
}

// ---------- shared ----------
function Field({ label, children }) {
  return (
    <label className="block mb-3">
      {label && (
        <span className="block mono text-[10px] tracking-[0.24em] uppercase text-white/55 mb-1.5">
          {label}
        </span>
      )}
      {children}
    </label>
  );
}

function ModalShell({ children, onClose, testid, wide = false }) {
  return (
    <div
      className="fixed inset-0 z-50 bg-graphite-scrim-strong backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
      data-testid={testid}
    >
      <div
        className={`bg-[#1F1F23] border border-white/10 rounded-2xl ${wide ? "w-[820px]" : "w-[560px]"} max-w-[95vw] max-h-[88vh] overflow-y-auto p-5 sm:p-6`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-end mb-1">
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white transition"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
