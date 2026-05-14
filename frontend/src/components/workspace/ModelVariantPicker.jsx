/**
 * NXT1 — ModelVariantPicker (Phase 11 W2-A)
 *
 * Premium model variant picker that reads `/api/ai/models` and renders a
 * grouped, tiered (Fast / Balanced / Reasoning / Coding) selection grid.
 *
 * Used in:
 *   • Workspace → Settings module (per-account default)
 *   • Builder → Tools → Model selector (per-project override) — future
 *
 * Self-contained. Theme-aware. Placeholder-safe (gracefully degrades when
 * a provider has no rich variants).
 */
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import {
  Sparkles,
  Zap,
  Brain,
  Code2,
  Loader2,
  CheckCircle2,
} from "lucide-react";
import { API } from "@/lib/api";
import { getToken } from "@/lib/auth";

const TIER_META = {
  fast:      { label: "Fast",      icon: Zap,      color: "#5EEAD4" },
  balanced:  { label: "Balanced",  icon: Sparkles, color: "#F0D28A" },
  reasoning: { label: "Reasoning", icon: Brain,    color: "#A78BFA" },
  coding:    { label: "Coding",    icon: Code2,    color: "#FB923C" },
};

function TierBadge({ tier }) {
  const meta = TIER_META[tier] || TIER_META.balanced;
  const Icon = meta.icon;
  return (
    <span
      className="nxt-tier-badge inline-flex items-center gap-1 text-[10px] mono tracking-[0.16em] uppercase px-2 py-0.5 rounded-full"
      style={{
        "--tier-color": meta.color,
        background: `${meta.color}1F`,
        border: `1px solid ${meta.color}55`,
        color: meta.color,
      }}
    >
      <Icon size={9} strokeWidth={2.2} />
      {meta.label}
    </span>
  );
}

function ModelTile({ provider, model, selected, onSelect }) {
  return (
    <motion.button
      type="button"
      onClick={() => onSelect(provider, model)}
      whileHover={{ y: -2 }}
      whileTap={{ y: 0 }}
      className="relative flex flex-col gap-2.5 p-4 rounded-2xl text-left transition-all w-full"
      style={{
        background: selected ? "var(--nxt-surface)" : "var(--nxt-surface-soft)",
        border: selected
          ? "1px solid var(--nxt-accent-border)"
          : "1px solid var(--nxt-border-soft)",
        boxShadow: selected
          ? "0 0 0 1px var(--nxt-accent-border), 0 14px 28px -12px rgba(94,234,212,0.20)"
          : "var(--nxt-shadow-sm)",
        color: "var(--nxt-fg)",
      }}
      data-testid={`model-tile-${provider}-${model.id}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div
            className="text-[14px] font-semibold tracking-tight leading-tight truncate"
            style={{ color: "var(--nxt-fg)" }}
          >
            {model.label}
          </div>
          <div
            className="mono text-[10px] tracking-[0.12em] uppercase mt-0.5 truncate"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            {provider}
          </div>
        </div>
        {selected ? (
          <CheckCircle2 size={14} style={{ color: "var(--nxt-accent)" }} />
        ) : (
          model.recommended && (
            <span
              className="text-[9.5px] mono tracking-[0.18em] uppercase px-1.5 py-0.5 rounded-full"
              style={{
                background: "var(--nxt-chip-bg)",
                border: "1px solid var(--nxt-chip-border)",
                color: "var(--nxt-fg-dim)",
              }}
            >
              Recommended
            </span>
          )
        )}
      </div>
      {model.note && (
        <div
          className="text-[11.5px] leading-snug"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          {model.note}
        </div>
      )}
      <div className="flex items-center gap-1.5 flex-wrap">
        <TierBadge tier={model.tier} />
        {model.context && (
          <span
            className="text-[10px] mono tracking-[0.12em]"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            {Math.round(model.context / 1000)}k ctx
          </span>
        )}
      </div>
    </motion.button>
  );
}

export default function ModelVariantPicker({
  value,
  onChange,
  filterTier = null,    // optional: "fast" | "balanced" | "reasoning" | "coding"
}) {
  const [groups, setGroups]   = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const token = getToken();
    fetch(`${API}/ai/models`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then((j) => {
        if (cancelled) return;
        setGroups(j?.providers || []);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        toast.error("Couldn't load model catalogue.");
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  // Flatten into rows grouped by tier when a filter is active, else
  // keep the provider grouping for readability.
  const sections = useMemo(() => {
    if (filterTier) {
      const rows = [];
      groups.forEach((g) =>
        g.variants
          .filter((v) => v.tier === filterTier)
          .forEach((v) => rows.push({ provider: g.provider_id, model: v }))
      );
      return [{ title: TIER_META[filterTier]?.label || filterTier, rows }];
    }
    return groups.map((g) => ({
      title: g.provider_name,
      providerId: g.provider_id,
      rows: g.variants.map((v) => ({ provider: g.provider_id, model: v })),
    }));
  }, [groups, filterTier]);

  const handleSelect = (provider, model) => {
    onChange?.({ provider, model: model.id });
    toast.success(`Default model · ${model.label}`);
  };

  if (loading) {
    return (
      <div
        className="flex items-center gap-2 py-10 justify-center"
        style={{ color: "var(--nxt-fg-faint)" }}
        data-testid="model-picker-loading"
      >
        <Loader2 size={14} className="animate-spin" />
        <span className="text-[12.5px]">Loading models…</span>
      </div>
    );
  }

  if (!sections.length || sections.every((s) => !s.rows.length)) {
    return (
      <div
        className="text-center py-10"
        style={{ color: "var(--nxt-fg-faint)" }}
      >
        <div className="text-[13.5px]" style={{ color: "var(--nxt-fg-dim)" }}>
          No model catalogue available.
        </div>
        <div className="text-[11.5px] mt-1">Configure an LLM provider env key to populate.</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-7" data-testid="model-variant-picker">
      {sections.map((section) => (
        <section key={section.title}>
          <h3
            className="mono text-[10.5px] tracking-[0.30em] uppercase mb-3"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            {section.title}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {section.rows.map(({ provider, model }) => (
              <ModelTile
                key={`${provider}-${model.id}`}
                provider={provider}
                model={model}
                selected={value?.provider === provider && value?.model === model.id}
                onSelect={handleSelect}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
