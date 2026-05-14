/**
 * NXT1 — HostingPicker (Phase 10C)
 *
 * Reusable hosting/domains catalogue. Pulls from `/api/deploy/providers`
 * (which composes services/hosting + deployment_service) and renders a
 * premium grid of provider tiles. Placeholder-safe: providers without
 * required env vars show a "Connect" affordance and the missing keys.
 *
 * Used from:
 *   • Workspace → Domains module (full-page catalogue)
 *   • Builder → Tools → Deploy panel (compact picker — future)
 */
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import {
  Rocket,
  Cloud,
  Server,
  Globe,
  Triangle,
  Zap,
  Layers,
  CheckCircle2,
  KeyRound,
} from "lucide-react";
import { API } from "@/lib/api";

/* Provider id → icon. Stable mapping the API catalogue keys against. */
const ICONS = {
  internal: Rocket,
  vercel: Triangle,
  netlify: Globe,
  railway: Server,
  "cloudflare-pages": Cloud,
  "cloudflare-workers": Zap,
  custom: Layers,
};

function ProviderTile({ p, onPick }) {
  const Icon = ICONS[p.id] || Cloud;
  const isReady = !!p.configured;
  return (
    <motion.button
      type="button"
      onClick={() => onPick(p)}
      whileHover={{ y: -2 }}
      whileTap={{ y: 0 }}
      className="relative flex flex-col gap-3 p-5 rounded-2xl text-left transition-all w-full"
      style={{
        background: "var(--nxt-surface)",
        border: "1px solid var(--nxt-border)",
        boxShadow: "var(--nxt-shadow-sm)",
        color: "var(--nxt-fg)",
      }}
      data-testid={`hosting-provider-${p.id}`}
    >
      <div className="flex items-start justify-between gap-2">
        <span
          className="h-9 w-9 inline-flex items-center justify-center rounded-xl shrink-0"
          style={{
            background: "var(--nxt-chip-bg)",
            border: "1px solid var(--nxt-chip-border)",
            color: "var(--nxt-accent)",
          }}
        >
          <Icon size={16} strokeWidth={1.9} />
        </span>
        <span
          className="text-[10px] mono tracking-[0.22em] uppercase font-medium inline-flex items-center gap-1"
          style={{
            color: isReady ? "var(--nxt-accent)" : "var(--nxt-fg-faint)",
          }}
        >
          {isReady ? (
            <>
              <CheckCircle2 size={11} /> Connected
            </>
          ) : (
            <>
              <KeyRound size={11} /> Connect
            </>
          )}
        </span>
      </div>
      <div>
        <div
          className="text-[15px] font-semibold tracking-tight mb-1"
          style={{ color: "var(--nxt-fg)" }}
        >
          {p.label}
        </div>
        <div
          className="text-[12.5px] leading-snug"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          {p.blurb}
        </div>
      </div>
      {/* Capability chips */}
      <div className="flex flex-wrap gap-1.5">
        {(p.capabilities || []).slice(0, 3).map((c) => (
          <span
            key={c}
            className="text-[10px] mono tracking-[0.12em] px-2 py-0.5 rounded-full"
            style={{
              background: "var(--nxt-chip-bg)",
              border: "1px solid var(--nxt-chip-border)",
              color: "var(--nxt-fg-dim)",
            }}
          >
            {c}
          </span>
        ))}
      </div>
      {/* Missing env vars hint (placeholder-safe) */}
      {!isReady && p.missing_env?.length > 0 && (
        <div
          className="text-[10.5px] mono leading-tight pt-2 mt-1 border-t"
          style={{ color: "var(--nxt-fg-faint)", borderColor: "var(--nxt-border-soft)" }}
        >
          Add to backend env: {p.missing_env.join(" · ")}
        </div>
      )}
    </motion.button>
  );
}

export default function HostingPicker({ onPick }) {
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/deploy/providers`)
      .then((r) => r.json())
      .then((j) => {
        if (!cancelled) {
          setProviders(j?.providers || []);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          toast.error("Couldn't load hosting providers.");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handlePick = (p) => {
    if (onPick) {
      onPick(p);
      return;
    }
    if (!p.configured) {
      toast.message(`${p.label} not yet connected`, {
        description: p.missing_env?.length
          ? `Add ${p.missing_env.join(", ")} to enable.`
          : "Provider configuration coming online soon.",
      });
      return;
    }
    toast.success(`${p.label} selected. Open a project to deploy.`);
  };

  if (loading) {
    return (
      <div
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
        data-testid="hosting-picker-loading"
      >
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="h-[160px] rounded-2xl nxt-shimmer"
            style={{ background: "var(--nxt-surface-soft)" }}
          />
        ))}
      </div>
    );
  }

  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
      data-testid="hosting-picker"
    >
      {providers.map((p) => (
        <ProviderTile key={p.id} p={p} onPick={handlePick} />
      ))}
    </div>
  );
}
