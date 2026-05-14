/**
 * Track C — Hosting OS panel (Caddy + Cloudflare connect)
 *
 * Two cards:
 *   1. Cloudflare Connect — paste user CF token, verify, list zones, attach DNS
 *   2. Caddy Generator    — generate a portable Caddyfile + docker-compose
 */
import { useEffect, useState } from "react";
import {
  cfConnect, cfStatus, cfZones, cfAttachDNS, cfDisconnect,
  generateCaddyfile, hostingReadiness,
} from "@/lib/api";
import { Cloud, Shield, Copy, CheckCircle2, AlertTriangle, Plug, Unplug, Loader2 } from "lucide-react";

export default function HostingOS() {
  const [readiness, setReadiness] = useState(null);
  const [cf, setCf] = useState({ connected: false, loading: true });
  const [zones, setZones] = useState([]);
  const [token, setToken] = useState("");
  const [host, setHost] = useState("");
  const [zoneId, setZoneId] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [caddyfile, setCaddyfile] = useState("");
  const [compose, setCompose] = useState("");
  const [caddyDomains, setCaddyDomains] = useState("app.example.com, www.example.com");
  const [copyTick, setCopyTick] = useState(null);

  const refresh = async () => {
    try {
      const r = await hostingReadiness();
      setReadiness(r.data);
      const s = await cfStatus();
      setCf({ ...s.data, loading: false });
      if (s.data.connected) {
        try {
          const z = await cfZones();
          setZones(z.data.zones || []);
        } catch { setZones([]); }
      }
    } catch {
      setCf({ connected: false, loading: false });
    }
  };
  useEffect(() => { refresh(); }, []);

  const connect = async () => {
    if (!token.trim()) { setMsg({ kind: "err", text: "Paste your Cloudflare API token." }); return; }
    setBusy(true); setMsg(null);
    try {
      const r = await cfConnect(token.trim());
      setMsg({ kind: "ok", text: `Connected. ${r.data.zones?.length || 0} zones available.` });
      setToken("");
      await refresh();
    } catch (e) {
      setMsg({ kind: "err", text: e?.response?.data?.detail || "Connect failed" });
    } finally { setBusy(false); }
  };

  const disconnect = async () => {
    setBusy(true);
    try { await cfDisconnect(); setZones([]); await refresh(); }
    finally { setBusy(false); }
  };

  const attach = async () => {
    if (!host.trim() || !zoneId) {
      setMsg({ kind: "err", text: "Pick a zone and enter a hostname." }); return;
    }
    setBusy(true); setMsg(null);
    try {
      const r = await cfAttachDNS(host.trim(), zoneId);
      setMsg({ kind: "ok", text: `DNS attached: ${r.data.hostname} → ${r.data.target}` });
      setHost("");
    } catch (e) {
      setMsg({ kind: "err", text: e?.response?.data?.detail || "Attach failed" });
    } finally { setBusy(false); }
  };

  const generate = async () => {
    const list = caddyDomains.split(",").map((s) => s.trim()).filter(Boolean);
    if (!list.length) return;
    setBusy(true);
    try {
      const r = await generateCaddyfile(list, {});
      setCaddyfile(r.data.caddyfile);
      setCompose(r.data.compose_snippet);
    } finally { setBusy(false); }
  };

  const copy = (text, which) => {
    try {
      navigator.clipboard.writeText(text);
      setCopyTick(which);
      setTimeout(() => setCopyTick(null), 1500);
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-6" data-testid="hosting-os-panel">
      {/* Readiness checklist */}
      {readiness && (
        <div className="rounded-xl p-4 border" data-testid="hosting-readiness"
             style={{ borderColor: "var(--nxt-border)", background: "var(--nxt-surface)" }}>
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-3.5 h-3.5" style={{ color: "var(--nxt-fg-faint)" }} />
            <span className="mono text-[10px] tracking-[0.30em] uppercase"
                  style={{ color: "var(--nxt-fg-faint)" }}>
              Hosting Readiness
            </span>
          </div>
          <div className="space-y-1.5">
            {(readiness.checklist || []).map((c) => (
              <div key={c.key} className="flex items-center gap-2 text-[12px]"
                   data-testid={`readiness-${c.key}`}>
                {c.ok
                  ? <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "#10b981" }} />
                  : <AlertTriangle className="w-3.5 h-3.5" style={{ color: "#f59e0b" }} />}
                <span style={{ color: "var(--nxt-fg-dim)" }}>{c.label}</span>
              </div>
            ))}
            <div className="mono text-[10px] pt-2"
                 style={{ color: "var(--nxt-fg-faint)" }}>
              upstream: {readiness.upstream}
            </div>
          </div>
        </div>
      )}

      {/* Cloudflare connect */}
      <div className="rounded-xl p-4 sm:p-5 border" data-testid="cf-connect"
           style={{ borderColor: "var(--nxt-border)", background: "var(--nxt-surface)" }}>
        <div className="flex items-center justify-between mb-3 gap-2">
          <div className="flex items-center gap-2">
            <Cloud className="w-4 h-4" style={{ color: "#f97316" }} />
            <span className="text-[14px] font-medium" style={{ color: "var(--nxt-fg)" }}>
              Cloudflare DNS
            </span>
            {cf.connected && (
              <span
                className="mono text-[9px] px-1.5 py-0.5 rounded uppercase"
                style={{ color: "#10b981", background: "rgba(16,185,129,0.1)" }}
              >
                Connected
              </span>
            )}
          </div>
          {cf.connected && (
            <button
              onClick={disconnect}
              disabled={busy}
              data-testid="cf-disconnect"
              className="text-[11px] px-2.5 py-1 rounded-full flex items-center gap-1"
              style={{
                color: "var(--nxt-fg-dim)",
                background: "var(--nxt-surface-hi)",
                border: "1px solid var(--nxt-border)",
              }}
            >
              <Unplug className="w-3 h-3" /> Disconnect
            </button>
          )}
        </div>

        {!cf.connected ? (
          <div className="space-y-2">
            <p className="text-[12px] leading-relaxed"
               style={{ color: "var(--nxt-fg-dim)" }}>
              Paste a Cloudflare API token with <strong>Zone:DNS:Edit</strong> permission.
              We encrypt it at rest and use it to attach custom-domain DNS records on your behalf.
              Create one at{" "}
              <a href="https://dash.cloudflare.com/profile/api-tokens"
                 target="_blank" rel="noopener noreferrer"
                 style={{ color: "#22d3ee" }}>
                dash.cloudflare.com/profile/api-tokens
              </a>.
            </p>
            <div className="flex gap-2">
              <input
                type="password"
                placeholder="cf-token-..."
                value={token}
                onChange={(e) => setToken(e.target.value)}
                data-testid="cf-token-input"
                className="flex-1 text-[12px] px-3 py-2 rounded-lg outline-none"
                style={{
                  background: "var(--nxt-surface-hi)",
                  border: "1px solid var(--nxt-border)",
                  color: "var(--nxt-fg)",
                }}
              />
              <button
                onClick={connect}
                disabled={busy}
                data-testid="cf-connect-btn"
                className="text-[12px] px-3 py-2 rounded-lg flex items-center gap-1.5"
                style={{
                  color: "#f97316",
                  background: "rgba(249,115,22,0.12)",
                  border: "1px solid rgba(249,115,22,0.3)",
                }}
              >
                {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plug className="w-3.5 h-3.5" />}
                Connect
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-[11px] mono" style={{ color: "var(--nxt-fg-faint)" }}>
              {zones.length} zone{zones.length === 1 ? "" : "s"} available · verified {cf.verified_at?.slice(0,10)}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <select
                value={zoneId}
                onChange={(e) => setZoneId(e.target.value)}
                data-testid="cf-zone-select"
                className="text-[12px] px-3 py-2 rounded-lg outline-none"
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
                value={host}
                onChange={(e) => setHost(e.target.value)}
                data-testid="cf-host-input"
                className="text-[12px] px-3 py-2 rounded-lg outline-none"
                style={{
                  background: "var(--nxt-surface-hi)",
                  border: "1px solid var(--nxt-border)",
                  color: "var(--nxt-fg)",
                }}
              />
            </div>
            <button
              onClick={attach}
              disabled={busy || !zoneId || !host}
              data-testid="cf-attach-btn"
              className="text-[12px] px-3 py-2 rounded-lg"
              style={{
                color: "#10b981",
                background: "rgba(16,185,129,0.12)",
                border: "1px solid rgba(16,185,129,0.3)",
                opacity: busy || !zoneId || !host ? 0.5 : 1,
              }}
            >
              {busy ? "Attaching..." : "Attach DNS record"}
            </button>
          </div>
        )}
        {msg && (
          <div
            className="mt-3 text-[11px] p-2 rounded"
            data-testid="cf-message"
            style={{
              background: msg.kind === "ok" ? "rgba(16,185,129,0.08)" : "rgba(239,68,68,0.08)",
              color: msg.kind === "ok" ? "#86efac" : "#fca5a5",
            }}
          >
            {msg.text}
          </div>
        )}
      </div>

      {/* Caddy generator */}
      <div className="rounded-xl p-4 sm:p-5 border" data-testid="caddy-generator"
           style={{ borderColor: "var(--nxt-border)", background: "var(--nxt-surface)" }}>
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-4 h-4" style={{ color: "#22d3ee" }} />
          <span className="text-[14px] font-medium" style={{ color: "var(--nxt-fg)" }}>
            Caddy · Auto-SSL config generator
          </span>
        </div>
        <p className="text-[12px] mb-3 leading-relaxed" style={{ color: "var(--nxt-fg-dim)" }}>
          Caddy auto-provisions LetsEncrypt certs for any domain pointed at it. Drop the generated
          Caddyfile + docker-compose on your own server to bring your own SSL — zero certbot juggling.
        </p>
        <div className="flex gap-2 mb-3">
          <input
            placeholder="app.example.com, www.example.com"
            value={caddyDomains}
            onChange={(e) => setCaddyDomains(e.target.value)}
            data-testid="caddy-domains-input"
            className="flex-1 text-[12px] px-3 py-2 rounded-lg outline-none"
            style={{
              background: "var(--nxt-surface-hi)",
              border: "1px solid var(--nxt-border)",
              color: "var(--nxt-fg)",
            }}
          />
          <button
            onClick={generate}
            disabled={busy}
            data-testid="caddy-generate-btn"
            className="text-[12px] px-3 py-2 rounded-lg"
            style={{
              color: "#22d3ee",
              background: "rgba(34,211,238,0.12)",
              border: "1px solid rgba(34,211,238,0.3)",
            }}
          >
            {busy ? "Generating..." : "Generate"}
          </button>
        </div>

        {caddyfile && (
          <div className="space-y-3" data-testid="caddy-output">
            <CodeBlock
              title="Caddyfile"
              code={caddyfile}
              onCopy={() => copy(caddyfile, "caddy")}
              copied={copyTick === "caddy"}
              testId="caddy-file-output"
            />
            <CodeBlock
              title="docker-compose.yml"
              code={compose}
              onCopy={() => copy(compose, "compose")}
              copied={copyTick === "compose"}
              testId="caddy-compose-output"
            />
            <ol className="text-[11px] space-y-1 mt-2"
                style={{ color: "var(--nxt-fg-dim)" }}>
              <li>1. Save the Caddyfile and docker-compose.yml side-by-side on your server.</li>
              <li>2. <code className="mono">docker compose up -d</code></li>
              <li>3. Point your DNS at the server (or use Cloudflare connect above).</li>
              <li>4. Wait ~30s — Caddy fetches LetsEncrypt certs on the first request.</li>
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}

function CodeBlock({ title, code, onCopy, copied, testId }) {
  return (
    <div className="rounded-lg overflow-hidden border" data-testid={testId}
         style={{ borderColor: "var(--nxt-border)" }}>
      <div className="flex items-center justify-between px-3 py-1.5"
           style={{ background: "var(--nxt-surface-hi)" }}>
        <span className="mono text-[10px] uppercase tracking-wider"
              style={{ color: "var(--nxt-fg-faint)" }}>{title}</span>
        <button
          onClick={onCopy}
          className="text-[10px] flex items-center gap-1 px-2 py-0.5 rounded"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          {copied ? <CheckCircle2 className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="mono text-[11px] p-3 overflow-x-auto leading-relaxed"
           style={{ background: "var(--nxt-bg)", color: "var(--nxt-fg-dim)" }}>
        {code}
      </pre>
    </div>
  );
}
