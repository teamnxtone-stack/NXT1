/**
 * NXT1 — SystemDiagnosticsPanel (Phase 11 W2-B)
 *
 * Reads `/api/system/diagnostics` and renders an at-a-glance readiness
 * card for the Workspace Settings page. Helps the user (and prepares the
 * eventual self-host detach flow) see exactly which provider keys / OAuth
 * credentials / hosting tokens are wired vs missing.
 *
 * Never displays secret material — only presence flags + missing env-var
 * names. Safe to embed anywhere a workspace user can reach.
 */
import { useEffect, useState } from "react";
import {
  Activity,
  Cpu,
  KeyRound,
  Server,
  Cloud,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { API } from "@/lib/api";
import { getToken } from "@/lib/auth";

function StatusDot({ ok }) {
  return (
    <span
      className="h-1.5 w-1.5 rounded-full inline-block shrink-0"
      style={{ background: ok ? "var(--nxt-accent)" : "rgba(248,113,113,0.85)" }}
    />
  );
}

function Section({ icon: Icon, label, children, testid }) {
  return (
    <section
      className="rounded-2xl p-4 sm:p-5"
      style={{
        background: "var(--nxt-surface)",
        border: "1px solid var(--nxt-border)",
        boxShadow: "var(--nxt-shadow-sm)",
      }}
      data-testid={testid}
    >
      <div className="flex items-center gap-2 mb-3.5">
        <span
          className="h-7 w-7 inline-flex items-center justify-center rounded-lg"
          style={{
            background: "var(--nxt-chip-bg)",
            border: "1px solid var(--nxt-chip-border)",
            color: "var(--nxt-accent)",
          }}
        >
          <Icon size={13} strokeWidth={1.9} />
        </span>
        <h3
          className="mono text-[10.5px] tracking-[0.30em] uppercase"
          style={{ color: "var(--nxt-fg-faint)" }}
        >
          {label}
        </h3>
      </div>
      <div className="flex flex-col gap-2.5">{children}</div>
    </section>
  );
}

function Row({ label, ok, hint }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-start gap-2 min-w-0">
        <StatusDot ok={ok} />
        <span
          className="text-[13px] truncate"
          style={{ color: "var(--nxt-fg)" }}
        >
          {label}
        </span>
      </div>
      <span
        className="text-[10.5px] mono tracking-[0.16em] uppercase shrink-0 text-right"
        style={{ color: ok ? "var(--nxt-accent)" : "var(--nxt-fg-faint)" }}
      >
        {ok ? (
          <span className="inline-flex items-center gap-1"><CheckCircle2 size={11} /> Wired</span>
        ) : (
          <span className="inline-flex items-center gap-1"><KeyRound size={11} /> {hint || "Connect"}</span>
        )}
      </span>
    </div>
  );
}

export default function SystemDiagnosticsPanel() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const token = getToken();
    fetch(`${API}/system/diagnostics`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then((j) => { if (!cancelled) { setData(j); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div
        className="flex items-center gap-2 py-10 justify-center"
        style={{ color: "var(--nxt-fg-faint)" }}
      >
        <Loader2 size={14} className="animate-spin" />
        <span className="text-[12.5px]">Loading diagnostics…</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-10" style={{ color: "var(--nxt-fg-faint)" }}>
        Diagnostics unavailable.
      </div>
    );
  }

  const { ready, portable, ai, oauth, hosting, core } = data;
  const aiList = ai?.providers || [];

  return (
    <div className="flex flex-col gap-4" data-testid="system-diagnostics">
      {/* Top status banner */}
      <div
        className="rounded-2xl p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
        style={{
          background: portable
            ? "linear-gradient(180deg, rgba(94,234,212,0.10), rgba(94,234,212,0.02))"
            : ready
            ? "linear-gradient(180deg, rgba(240,210,138,0.10), rgba(240,210,138,0.02))"
            : "linear-gradient(180deg, rgba(248,113,113,0.10), rgba(248,113,113,0.02))",
          border: `1px solid ${
            portable ? "rgba(94,234,212,0.32)" : ready ? "rgba(240,210,138,0.32)" : "rgba(248,113,113,0.32)"
          }`,
        }}
        data-testid="system-readiness-banner"
      >
        <div className="flex items-center gap-3">
          <span
            className="h-9 w-9 inline-flex items-center justify-center rounded-xl"
            style={{
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.08)",
              color: portable ? "var(--nxt-accent)" : ready ? "#F0D28A" : "#F87171",
            }}
          >
            {portable ? <ShieldCheck size={16} /> : <AlertCircle size={16} />}
          </span>
          <div>
            <div className="text-[14.5px] font-semibold tracking-tight" style={{ color: "var(--nxt-fg)" }}>
              {portable
                ? "Production-ready & portable"
                : ready
                ? "Ready (running on managed dev key)"
                : "Not ready"}
            </div>
            <div className="text-[12px] mt-0.5" style={{ color: "var(--nxt-fg-dim)" }}>
              {portable
                ? "Your own provider keys are wired — safe to detach to your own infrastructure."
                : ready
                ? "Using the Emergent LLM dev fallback. Add your own provider key to become portable."
                : "Mongo and at least one AI provider are required."}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section icon={Cpu} label="AI Providers" testid="diag-ai">
          {aiList.map((p) => (
            <Row
              key={p.id}
              label={p.display_name}
              ok={p.available}
              hint={(p.requires_env || []).join(" · ")}
            />
          ))}
        </Section>
        <Section icon={KeyRound} label="OAuth" testid="diag-oauth">
          {oauth.map((p) => (
            <Row
              key={p.id}
              label={p.label}
              ok={p.configured}
              hint={(p.missing_env || []).join(" · ")}
            />
          ))}
        </Section>
        <Section icon={Cloud} label="Hosting" testid="diag-hosting">
          {hosting.map((p) => (
            <Row
              key={p.id}
              label={p.label}
              ok={p.configured}
              hint={(p.missing_env || []).join(" · ")}
            />
          ))}
        </Section>
        <Section icon={Server} label="Core" testid="diag-core">
          <Row label="MongoDB"        ok={!!core.mongo_configured} hint="MONGO_URL" />
          <Row label="JWT Secret"     ok={!!core.jwt_secret_set}    hint="JWT_SECRET" />
          <Row label="GitHub Token"   ok={!!core.github_token_set}  hint="GITHUB_TOKEN" />
          <Row label="Public App URL" ok={!!core.public_app_url}    hint="PUBLIC_APP_URL" />
          <Row label="Emergent Dev Fallback" ok={!!core.emergent_dev_fallback} hint="EMERGENT_LLM_KEY" />
        </Section>
      </div>

      <div
        className="text-[11px] leading-relaxed mt-2 px-1 inline-flex items-center gap-1.5"
        style={{ color: "var(--nxt-fg-faint)" }}
      >
        <Activity size={12} /> Read-only — NXT1 never shows secret material. Update env on the backend host to wire keys.
      </div>
    </div>
  );
}
