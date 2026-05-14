/**
 * NXT1 — Deploy & Domain Sheet
 *
 * One unified modal that opens from Share / Preview / Deploy and walks
 * the user through:
 *
 *   1. Domain        — pick existing, attach via Cloudflare auto, or manual
 *   2. Environment   — readiness checks + missing env vars
 *   3. Deploy        — target picker + one-tap launch
 *
 * Designed to replace the scattered "Domains panel" + "Deployment panel"
 * + "Hosting OS" surfaces with a single flow the user can finish in <60s.
 */
import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  X, Globe, Cloud, ShieldCheck, Rocket, ExternalLink,
  CheckCircle2, AlertTriangle, Loader2, Plus, Copy, ChevronRight, KeyRound,
} from "lucide-react";
import api, {
  hostingReadiness, cfStatus, cfConnect, cfZones, cfAttachDNS,
  generateCaddyfile, getReadiness,
} from "@/lib/api";

const STEPS = [
  { id: "domain", label: "Domain",       icon: Globe },
  { id: "env",    label: "Environment",  icon: ShieldCheck },
  { id: "deploy", label: "Deploy",       icon: Rocket },
];

export default function DeployAndDomainSheet({
  open,
  projectId,
  onClose,
  onDeployed,
}) {
  const [step, setStep] = useState("domain");

  if (!open) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[80] flex items-stretch sm:items-center sm:justify-center p-0 sm:p-6"
        style={{ background: "rgba(0,0,0,0.78)", backdropFilter: "blur(8px)" }}
        onClick={onClose}
        data-testid="deploy-domain-sheet"
      >
        <motion.div
          initial={{ y: 24, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 24, opacity: 0 }}
          transition={{ type: "spring", stiffness: 380, damping: 32 }}
          onClick={(e) => e.stopPropagation()}
          className="relative w-full sm:max-w-[760px] sm:max-h-[88vh] sm:rounded-2xl overflow-hidden flex flex-col"
          style={{
            background: "var(--nxt-bg)",
            border: "1px solid var(--nxt-border)",
            boxShadow: "0 30px 80px -20px rgba(0,0,0,0.6)",
          }}
        >
          <Header step={step} setStep={setStep} onClose={onClose} />
          <div className="flex-1 overflow-y-auto px-5 sm:px-6 py-5 sm:py-6">
            {step === "domain" && (
              <DomainStep
                projectId={projectId}
                onNext={() => setStep("env")}
              />
            )}
            {step === "env" && (
              <EnvStep
                projectId={projectId}
                onBack={() => setStep("domain")}
                onNext={() => setStep("deploy")}
              />
            )}
            {step === "deploy" && (
              <DeployStep
                projectId={projectId}
                onBack={() => setStep("env")}
                onDeployed={(url) => {
                  onDeployed?.(url);
                  onClose?.();
                }}
              />
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function Header({ step, setStep, onClose }) {
  return (
    <div
      className="flex-shrink-0 px-5 sm:px-6 py-4 flex items-center gap-3 border-b"
      style={{
        borderColor: "var(--nxt-border)",
        background: "var(--nxt-surface)",
      }}
    >
      <div className="flex items-center gap-2">
        <div
          className="w-8 h-8 rounded-xl flex items-center justify-center"
          style={{ background: "rgba(94,234,212,0.12)", color: "#5eead4" }}
        >
          <Rocket className="w-4 h-4" />
        </div>
        <div>
          <div className="mono text-[10px] tracking-[0.3em] uppercase"
               style={{ color: "var(--nxt-fg-faint)" }}>
            Publish flow
          </div>
          <div className="text-[14px] font-medium"
               style={{ color: "var(--nxt-fg)" }}>
            Deploy & Domain
          </div>
        </div>
      </div>
      <div className="flex-1" />
      <div className="hidden sm:flex items-center gap-1.5">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const isActive = s.id === step;
          const isDone = STEPS.findIndex((x) => x.id === step) > i;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => setStep(s.id)}
              className="flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-full transition"
              style={{
                background: isActive ? "var(--nxt-fg)" : "transparent",
                color: isActive ? "var(--nxt-bg)" : (isDone ? "#5eead4" : "var(--nxt-fg-dim)"),
                border: `1px solid ${isActive ? "var(--nxt-fg)" : "var(--nxt-border)"}`,
              }}
              data-testid={`ddsheet-step-${s.id}`}
            >
              <Icon className="w-3 h-3" />
              <span className="mono tracking-wider">{s.label}</span>
              {isDone && <CheckCircle2 className="w-3 h-3" />}
            </button>
          );
        })}
      </div>
      <button
        type="button"
        onClick={onClose}
        data-testid="ddsheet-close"
        className="w-8 h-8 rounded-full flex items-center justify-center transition"
        style={{
          color: "var(--nxt-fg-dim)",
          background: "var(--nxt-surface-hi)",
        }}
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

// ─────────────────────────── Step 1: Domain ─────────────────────────────
function DomainStep({ projectId, onNext }) {
  const [domains, setDomains] = useState([]);
  const [cf, setCf] = useState({ connected: false });
  const [zones, setZones] = useState([]);
  const [tab, setTab] = useState("auto");      // auto | manual | existing
  const [token, setToken] = useState("");
  const [hostname, setHostname] = useState("");
  const [zoneId, setZoneId] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [d, s] = await Promise.all([
        api.get(`/projects/${projectId}/domains`).catch(() => ({ data: [] })),
        cfStatus().catch(() => ({ data: { connected: false } })),
      ]);
      setDomains(Array.isArray(d.data) ? d.data : (d.data?.items || []));
      setCf(s.data);
      if (s.data.connected) {
        try { const z = await cfZones(); setZones(z.data?.zones || []); }
        catch { setZones([]); }
      }
      if ((Array.isArray(d.data) ? d.data : (d.data?.items || [])).length) {
        setTab("existing");
      }
    } catch { /* ignore */ }
  }, [projectId]);

  useEffect(() => { refresh(); }, [refresh]);

  const handleConnectCF = async () => {
    if (!token.trim()) {
      toast.error("Paste your Cloudflare API token");
      return;
    }
    setBusy(true);
    try {
      const r = await cfConnect(token.trim());
      toast.success(`Cloudflare connected — ${r.data.zones?.length || 0} zone(s)`);
      setToken("");
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't connect Cloudflare");
    } finally {
      setBusy(false);
    }
  };

  const handleAttachAuto = async () => {
    if (!zoneId || !hostname.trim()) {
      toast.error("Pick a zone and enter a hostname");
      return;
    }
    setBusy(true);
    try {
      await cfAttachDNS(hostname.trim(), zoneId);
      // Also register the domain on the project so it shows in the existing list
      try {
        await api.post(`/projects/${projectId}/domains`, { hostname: hostname.trim() });
      } catch { /* domain creation might already be implicit; ignore conflicts */ }
      toast.success(`Auto-DNS attached for ${hostname.trim()}`);
      setHostname("");
      await refresh();
      onNext?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "DNS attach failed");
    } finally {
      setBusy(false);
    }
  };

  const handleAddManual = async () => {
    if (!hostname.trim()) {
      toast.error("Enter a hostname");
      return;
    }
    setBusy(true);
    try {
      await api.post(`/projects/${projectId}/domains`, { hostname: hostname.trim() });
      toast.success(`Manual domain registered — finish DNS in your registrar.`);
      setHostname("");
      await refresh();
      onNext?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't register domain");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="ddsheet-domain-step">
      <div>
        <h3 className="text-[18px] font-semibold mb-1"
            style={{ color: "var(--nxt-fg)" }}>
          Where should this live?
        </h3>
        <p className="text-[13px]" style={{ color: "var(--nxt-fg-dim)" }}>
          Pick an existing domain, auto-attach one via Cloudflare, or wire it manually.
        </p>
      </div>

      <Tabs
        tabs={[
          { id: "auto",     label: "Auto · Cloudflare", icon: Cloud },
          { id: "manual",   label: "Manual",            icon: ShieldCheck },
          { id: "existing", label: `Existing (${domains.length})`, icon: Globe },
        ]}
        active={tab}
        onChange={setTab}
        testIdPrefix="ddsheet-domain-tab"
      />

      {tab === "auto" && (
        <div className="space-y-3" data-testid="ddsheet-tab-auto">
          {!cf.connected ? (
            <>
              <p className="text-[12px]" style={{ color: "var(--nxt-fg-dim)" }}>
                Paste a Cloudflare API token with <strong>Zone:DNS:Edit</strong>{" "}
                permission. We encrypt it at rest.{" "}
                <a href="https://dash.cloudflare.com/profile/api-tokens"
                   target="_blank" rel="noopener noreferrer"
                   style={{ color: "#22d3ee" }}>
                  Create one
                </a>{" "}<ExternalLink className="w-2.5 h-2.5 inline" />
              </p>
              <div className="flex gap-2">
                <input
                  type="password"
                  placeholder="cf-token-..."
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  data-testid="ddsheet-cf-token-input"
                  className="flex-1 text-[13px] px-3 py-2 rounded-lg outline-none"
                  style={{
                    background: "var(--nxt-surface-hi)",
                    border: "1px solid var(--nxt-border)",
                    color: "var(--nxt-fg)",
                  }}
                />
                <PrimaryButton
                  onClick={handleConnectCF}
                  busy={busy}
                  testId="ddsheet-cf-connect"
                >
                  Connect
                </PrimaryButton>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 text-[12px]"
                   style={{ color: "#86efac" }}>
                <CheckCircle2 className="w-3.5 h-3.5" />
                Cloudflare connected · {zones.length} zone{zones.length === 1 ? "" : "s"}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <select
                  value={zoneId}
                  onChange={(e) => setZoneId(e.target.value)}
                  data-testid="ddsheet-zone-select"
                  className="text-[13px] px-3 py-2 rounded-lg outline-none"
                  style={{
                    background: "var(--nxt-surface-hi)",
                    border: "1px solid var(--nxt-border)",
                    color: "var(--nxt-fg)",
                  }}
                >
                  <option value="">— pick a zone —</option>
                  {zones.map((z) => (
                    <option key={z.id} value={z.id}>{z.name}</option>
                  ))}
                </select>
                <input
                  placeholder="app.yourdomain.com"
                  value={hostname}
                  onChange={(e) => setHostname(e.target.value)}
                  data-testid="ddsheet-hostname-input"
                  className="text-[13px] px-3 py-2 rounded-lg outline-none"
                  style={{
                    background: "var(--nxt-surface-hi)",
                    border: "1px solid var(--nxt-border)",
                    color: "var(--nxt-fg)",
                  }}
                />
              </div>
              <PrimaryButton
                onClick={handleAttachAuto}
                busy={busy}
                disabled={!zoneId || !hostname.trim()}
                testId="ddsheet-attach-auto"
                fullWidth
              >
                Attach + continue
                <ChevronRight className="w-3.5 h-3.5 ml-1" />
              </PrimaryButton>
            </>
          )}
        </div>
      )}

      {tab === "manual" && (
        <div className="space-y-3" data-testid="ddsheet-tab-manual">
          <p className="text-[12px]" style={{ color: "var(--nxt-fg-dim)" }}>
            Register the hostname here; finish the CNAME in your DNS provider.
            We'll generate a Caddy config you can drop on your edge server for auto-SSL.
          </p>
          <input
            placeholder="app.yourdomain.com"
            value={hostname}
            onChange={(e) => setHostname(e.target.value)}
            data-testid="ddsheet-manual-hostname"
            className="w-full text-[13px] px-3 py-2 rounded-lg outline-none"
            style={{
              background: "var(--nxt-surface-hi)",
              border: "1px solid var(--nxt-border)",
              color: "var(--nxt-fg)",
            }}
          />
          <PrimaryButton
            onClick={handleAddManual}
            busy={busy}
            disabled={!hostname.trim()}
            testId="ddsheet-attach-manual"
            fullWidth
          >
            Register + continue
            <ChevronRight className="w-3.5 h-3.5 ml-1" />
          </PrimaryButton>
        </div>
      )}

      {tab === "existing" && (
        <div className="space-y-2" data-testid="ddsheet-tab-existing">
          {domains.length === 0 ? (
            <div className="text-[12px] text-center py-6"
                 style={{ color: "var(--nxt-fg-dim)" }}>
              No domains yet — use Auto or Manual.
            </div>
          ) : (
            domains.map((d) => (
              <div
                key={d.id || d.hostname}
                data-testid={`ddsheet-domain-${d.hostname}`}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg"
                style={{
                  background: "var(--nxt-surface)",
                  border: "1px solid var(--nxt-border)",
                }}
              >
                <Globe className="w-3.5 h-3.5 flex-shrink-0"
                       style={{ color: "#22d3ee" }} />
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] truncate"
                       style={{ color: "var(--nxt-fg)" }}>{d.hostname}</div>
                  <div className="mono text-[10px] uppercase tracking-wider"
                       style={{ color: "var(--nxt-fg-faint)" }}>
                    {d.status || "pending"} {d.is_primary ? "· primary" : ""}
                  </div>
                </div>
              </div>
            ))
          )}
          <PrimaryButton onClick={onNext} fullWidth testId="ddsheet-existing-next">
            Continue
            <ChevronRight className="w-3.5 h-3.5 ml-1" />
          </PrimaryButton>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────── Step 2: Environment ─────────────────────────
function EnvStep({ projectId, onBack, onNext }) {
  const [hostReady, setHostReady] = useState(null);
  const [projectReady, setProjectReady] = useState(null);
  const [envVars, setEnvVars] = useState([]);
  const [newKey, setNewKey] = useState("");
  const [newVal, setNewVal] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [hr, pr, ev] = await Promise.all([
        hostingReadiness().catch(() => ({ data: null })),
        getReadiness(projectId).catch(() => ({ data: null })),
        api.get(`/projects/${projectId}/env`).catch(() => ({ data: { items: [] } })),
      ]);
      setHostReady(hr.data);
      setProjectReady(pr.data);
      setEnvVars(ev.data?.items || ev.data?.env || []);
    } catch { /* ignore */ }
  }, [projectId]);
  useEffect(() => { refresh(); }, [refresh]);

  const addVar = async () => {
    if (!newKey.trim()) return;
    setBusy(true);
    try {
      await api.post(`/projects/${projectId}/env`,
        { key: newKey.trim(), value: newVal });
      setNewKey(""); setNewVal("");
      toast.success("Env var saved");
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't save env var");
    } finally { setBusy(false); }
  };

  const checks = [
    ...(hostReady?.checklist || []),
    ...(projectReady?.checklist || []).map((c) => ({ ...c, scope: "project" })),
  ];

  return (
    <div className="space-y-5" data-testid="ddsheet-env-step">
      <div>
        <h3 className="text-[18px] font-semibold mb-1"
            style={{ color: "var(--nxt-fg)" }}>
          Environment & readiness
        </h3>
        <p className="text-[13px]" style={{ color: "var(--nxt-fg-dim)" }}>
          We'll verify infra is healthy and any required env vars are set before deploying.
        </p>
      </div>

      <div className="space-y-1.5">
        {checks.length === 0 && (
          <div className="text-[12px]"
               style={{ color: "var(--nxt-fg-dim)" }}>
            No readiness checks reported — proceeding will skip pre-flight.
          </div>
        )}
        {checks.map((c) => (
          <div key={`${c.scope || "host"}-${c.key}`}
               data-testid={`ddsheet-check-${c.key}`}
               className="flex items-center gap-2 text-[12px]">
            {c.ok
              ? <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" style={{ color: "#10b981" }} />
              : <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: "#f59e0b" }} />}
            <span style={{ color: "var(--nxt-fg-dim)" }}>{c.label}</span>
            {c.scope && (
              <span className="mono text-[9px] uppercase tracking-wider ml-1"
                    style={{ color: "var(--nxt-fg-faint)" }}>
                {c.scope}
              </span>
            )}
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <KeyRound className="w-3.5 h-3.5" style={{ color: "var(--nxt-fg-faint)" }} />
          <span className="mono text-[10px] uppercase tracking-[0.3em]"
                style={{ color: "var(--nxt-fg-faint)" }}>
            Env vars · {envVars.length}
          </span>
        </div>
        <div className="space-y-1">
          {envVars.map((v) => (
            <div key={v.key}
                 data-testid={`ddsheet-env-row-${v.key}`}
                 className="flex items-center gap-2 px-2.5 py-1.5 rounded text-[12px]"
                 style={{ background: "var(--nxt-surface)" }}>
              <span className="mono"
                    style={{ color: "var(--nxt-fg)" }}>{v.key}</span>
              <span className="mono opacity-60 truncate flex-1"
                    style={{ color: "var(--nxt-fg-faint)" }}>
                {v.preview || "•••"}
              </span>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-[1fr_1fr_auto] gap-2">
          <input
            placeholder="KEY"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value.toUpperCase())}
            data-testid="ddsheet-env-key"
            className="mono text-[12px] px-2.5 py-1.5 rounded outline-none"
            style={{
              background: "var(--nxt-surface-hi)",
              border: "1px solid var(--nxt-border)",
              color: "var(--nxt-fg)",
            }}
          />
          <input
            placeholder="value"
            value={newVal}
            type="password"
            onChange={(e) => setNewVal(e.target.value)}
            data-testid="ddsheet-env-val"
            className="text-[12px] px-2.5 py-1.5 rounded outline-none"
            style={{
              background: "var(--nxt-surface-hi)",
              border: "1px solid var(--nxt-border)",
              color: "var(--nxt-fg)",
            }}
          />
          <button
            type="button"
            onClick={addVar}
            disabled={busy || !newKey.trim()}
            data-testid="ddsheet-env-add"
            className="text-[12px] px-3 py-1.5 rounded transition"
            style={{
              background: "var(--nxt-surface-hi)",
              border: "1px solid var(--nxt-border)",
              color: "var(--nxt-fg-dim)",
              opacity: busy || !newKey.trim() ? 0.5 : 1,
            }}
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="flex gap-2 justify-end pt-2">
        <SecondaryButton onClick={onBack} testId="ddsheet-env-back">Back</SecondaryButton>
        <PrimaryButton onClick={onNext} testId="ddsheet-env-next">
          Continue
          <ChevronRight className="w-3.5 h-3.5 ml-1" />
        </PrimaryButton>
      </div>
    </div>
  );
}

// ─────────────────────────── Step 3: Deploy ─────────────────────────────
function DeployStep({ projectId, onBack, onDeployed }) {
  const [providers, setProviders] = useState([]);
  const [target, setTarget] = useState("internal");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState(null);
  const [liveUrl, setLiveUrl] = useState(null);

  useEffect(() => {
    api.get("/deploy/providers")
      .then((r) => {
        const items = Array.isArray(r.data) ? r.data : (r.data?.items || []);
        setProviders(items);
        const defaultTarget = items.find((p) => p.id === "internal")?.id
                              || items[0]?.id || "internal";
        setTarget(defaultTarget);
      })
      .catch(() => setProviders([{ id: "internal", label: "NXT1 internal" }]));
  }, []);

  const launch = async () => {
    setBusy(true);
    setPhase("starting");
    try {
      const { data } = await api.post(`/projects/${projectId}/deploy`,
        { target });
      setPhase("running");
      // Poll the deployment until we have a URL or terminal status.
      const depId = data?.deployment_id || data?.id;
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts += 1;
        try {
          const dep = await api.get(
            `/projects/${projectId}/deployments/${depId}`);
          const st = dep.data?.status;
          if (st === "live" || st === "completed" || dep.data?.url) {
            clearInterval(poll);
            setLiveUrl(dep.data?.url || data?.url);
            setPhase("live");
            setBusy(false);
            toast.success("Deployment live");
            onDeployed?.(dep.data?.url || data?.url);
          } else if (st === "failed" || attempts > 40) {
            clearInterval(poll);
            setPhase(st === "failed" ? "failed" : "timeout");
            setBusy(false);
            toast.error(`Deploy ${st || "timed out"}`);
          }
        } catch {
          // ignore intermittent fetch failures
        }
      }, 1500);
    } catch (e) {
      setPhase("failed");
      setBusy(false);
      toast.error(e?.response?.data?.detail || "Couldn't start deployment");
    }
  };

  return (
    <div className="space-y-5" data-testid="ddsheet-deploy-step">
      <div>
        <h3 className="text-[18px] font-semibold mb-1"
            style={{ color: "var(--nxt-fg)" }}>
          Where should we ship it?
        </h3>
        <p className="text-[13px]" style={{ color: "var(--nxt-fg-dim)" }}>
          Pick a target. Internal hosting gets you a live URL instantly.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2"
           data-testid="ddsheet-targets">
        {providers.map((p) => {
          const isActive = p.id === target;
          return (
            <button
              type="button"
              key={p.id}
              onClick={() => setTarget(p.id)}
              data-testid={`ddsheet-target-${p.id}`}
              className="text-left rounded-xl px-3 py-3 transition"
              style={{
                background: isActive ? "rgba(94,234,212,0.08)" : "var(--nxt-surface)",
                border: `1px solid ${isActive ? "rgba(94,234,212,0.4)" : "var(--nxt-border)"}`,
              }}
            >
              <div className="text-[13px] font-medium"
                   style={{ color: "var(--nxt-fg)" }}>
                {p.label || p.id}
              </div>
              <div className="text-[11px] mt-0.5"
                   style={{ color: "var(--nxt-fg-faint)" }}>
                {p.description || p.id}
              </div>
            </button>
          );
        })}
      </div>

      {phase && (
        <div className="rounded-xl p-3 flex items-center gap-2 text-[12px]"
             data-testid="ddsheet-deploy-status"
             style={{
               background: phase === "live"   ? "rgba(16,185,129,0.08)" :
                           phase === "failed" ? "rgba(239,68,68,0.08)" :
                                                "rgba(245,158,11,0.06)",
               color:      phase === "live"   ? "#86efac" :
                           phase === "failed" ? "#fca5a5" :
                                                "#fcd34d",
             }}>
          {phase === "live"   ? <CheckCircle2 className="w-3.5 h-3.5" /> :
           phase === "failed" ? <AlertTriangle className="w-3.5 h-3.5" /> :
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          <span className="capitalize">{phase}</span>
          {liveUrl && (
            <a href={liveUrl} target="_blank" rel="noopener noreferrer"
               className="ml-auto flex items-center gap-1 underline"
               data-testid="ddsheet-live-link">
              Open <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
      )}

      <div className="flex gap-2 justify-end pt-2">
        <SecondaryButton onClick={onBack} testId="ddsheet-deploy-back">Back</SecondaryButton>
        <PrimaryButton
          onClick={launch}
          busy={busy}
          disabled={!!liveUrl}
          testId="ddsheet-launch"
        >
          <Rocket className="w-3.5 h-3.5 mr-1" />
          {liveUrl ? "Live" : "Deploy now"}
        </PrimaryButton>
      </div>
    </div>
  );
}

// ─────────────────────────── Shared bits ────────────────────────────────
function Tabs({ tabs, active, onChange, testIdPrefix }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {tabs.map((t) => {
        const Icon = t.icon;
        const isActive = t.id === active;
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            data-testid={`${testIdPrefix}-${t.id}`}
            className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-full transition"
            style={{
              background: isActive ? "var(--nxt-fg)" : "var(--nxt-surface-hi)",
              color: isActive ? "var(--nxt-bg)" : "var(--nxt-fg-dim)",
              border: `1px solid ${isActive ? "var(--nxt-fg)" : "var(--nxt-border)"}`,
            }}
          >
            <Icon className="w-3 h-3" />
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

function PrimaryButton({ onClick, children, busy, disabled, fullWidth, testId }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy || disabled}
      data-testid={testId}
      className="text-[13px] font-medium px-4 py-2 rounded-full transition flex items-center justify-center"
      style={{
        background: "white",
        color: "#0a0a0f",
        border: "1px solid white",
        opacity: busy || disabled ? 0.5 : 1,
        width: fullWidth ? "100%" : "auto",
      }}
    >
      {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : null}
      {children}
    </button>
  );
}

function SecondaryButton({ onClick, children, testId }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className="text-[13px] px-4 py-2 rounded-full transition"
      style={{
        background: "var(--nxt-surface-hi)",
        color: "var(--nxt-fg-dim)",
        border: "1px solid var(--nxt-border)",
      }}
    >
      {children}
    </button>
  );
}
