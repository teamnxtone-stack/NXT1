/**
 * Track A — Premium UI Block Gallery
 *
 * Lets users browse curated Magic UI / Aceternity / Origin UI / shadcn blocks
 * and pin favourites. The same registry is what biases AI generation.
 */
import { useEffect, useMemo, useState } from "react";
import { getUIRegistry } from "@/lib/api";
import { Sparkles, Layers, ExternalLink, Filter, Eye, X, CheckCircle2 } from "lucide-react";
import { getBlockComponent, blockIsImplemented } from "@/components/ui/blocks";

const KIND_LABELS = {
  hero: "Heroes",
  feature: "Feature grids",
  card: "Cards",
  text: "Typography",
  background: "Backgrounds",
  input: "Inputs",
  scene: "3D / Motion",
};

const PACK_COLORS = {
  magicui: "#8b5cf6",
  aceternity: "#22d3ee",
  originui: "#10b981",
  shadcn: "#f59e0b",
  "framer-motion": "#ec4899",
  r3f: "#f97316",
};

export default function UIBlockGallery() {
  const [data, setData] = useState({ packs: [], blocks: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [kindFilter, setKindFilter] = useState(null);
  const [packFilter, setPackFilter] = useState(null);
  const [error, setError] = useState(null);
  const [previewBlock, setPreviewBlock] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getUIRegistry({ kind: kindFilter, pack: packFilter })
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch((e) => { if (!cancelled) setError(e?.response?.data?.detail || e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [kindFilter, packFilter]);

  const kinds = useMemo(() => Object.keys(KIND_LABELS), []);

  return (
    <div data-testid="ui-gallery" className="space-y-6">
      {/* Header */}
      <div
        className="rounded-2xl p-5 sm:p-6 border"
        style={{
          background: "linear-gradient(135deg, rgba(34,211,238,0.06) 0%, rgba(139,92,246,0.06) 100%)",
          borderColor: "var(--nxt-border)",
        }}
      >
        <div className="flex items-center gap-3 mb-2">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: "rgba(139,92,246,0.12)", color: "#a78bfa" }}
          >
            <Sparkles className="w-5 h-5" />
          </div>
          <div className="mono text-[10px] tracking-[0.30em] uppercase"
               style={{ color: "var(--nxt-fg-faint)" }}>
            Premium UI · Curated Registry
          </div>
        </div>
        <h2 className="text-[20px] sm:text-[22px] font-semibold tracking-tight mb-1"
            style={{ color: "var(--nxt-fg)" }}>
          {data.total} premium blocks across {data.packs.length} packs.
        </h2>
        <p className="text-[13px] leading-relaxed max-w-[640px]"
           style={{ color: "var(--nxt-fg-dim)" }}>
          NXT1's build agent retrieves from this registry so generated apps default to
          Magic UI / Aceternity / Origin UI blocks instead of raw Tailwind.
          Cite a block id in a comment and the editor can hot-swap it.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center" data-testid="ui-gallery-filters">
        <Filter className="w-3.5 h-3.5" style={{ color: "var(--nxt-fg-faint)" }} />
        <Chip
          active={!kindFilter}
          onClick={() => setKindFilter(null)}
          label="All kinds"
          testId="filter-kind-all"
        />
        {kinds.map((k) => (
          <Chip
            key={k}
            active={kindFilter === k}
            onClick={() => setKindFilter(kindFilter === k ? null : k)}
            label={KIND_LABELS[k]}
            testId={`filter-kind-${k}`}
          />
        ))}
        <div className="w-2" />
        <Chip
          active={!packFilter}
          onClick={() => setPackFilter(null)}
          label="All packs"
          testId="filter-pack-all"
        />
        {data.packs.map((p) => (
          <Chip
            key={p.id}
            active={packFilter === p.id}
            onClick={() => setPackFilter(packFilter === p.id ? null : p.id)}
            label={p.name}
            color={PACK_COLORS[p.id]}
            testId={`filter-pack-${p.id}`}
          />
        ))}
      </div>

      {/* Packs row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
           data-testid="ui-gallery-packs">
        {data.packs.map((p) => (
          <a
            key={p.id}
            href={p.homepage}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={`pack-card-${p.id}`}
            className="group rounded-xl p-4 border transition-all hover:translate-y-[-2px]"
            style={{
              borderColor: "var(--nxt-border)",
              background: "var(--nxt-surface)",
            }}
          >
            <div className="flex items-start justify-between mb-2">
              <span
                className="mono text-[10px] tracking-[0.20em] uppercase px-2 py-0.5 rounded"
                style={{
                  color: PACK_COLORS[p.id] || "var(--nxt-fg-dim)",
                  background: `${PACK_COLORS[p.id] || "#666"}1a`,
                }}
              >
                {p.id}
              </span>
              <ExternalLink className="w-3 h-3 opacity-40 group-hover:opacity-100 transition-opacity"
                            style={{ color: "var(--nxt-fg-dim)" }} />
            </div>
            <div className="text-[14px] font-medium mb-1"
                 style={{ color: "var(--nxt-fg)" }}>{p.name}</div>
            <div className="text-[12px] leading-snug"
                 style={{ color: "var(--nxt-fg-dim)" }}>{p.tagline}</div>
          </a>
        ))}
      </div>

      {/* Blocks grid */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Layers className="w-3.5 h-3.5" style={{ color: "var(--nxt-fg-faint)" }} />
          <span className="mono text-[10px] tracking-[0.30em] uppercase"
                style={{ color: "var(--nxt-fg-faint)" }}>
            Blocks · {loading ? "loading…" : `${data.blocks.length} match`}
          </span>
        </div>
        {error && (
          <div className="text-[12px] p-3 rounded-lg" data-testid="ui-gallery-error"
               style={{ background: "rgba(239,68,68,0.08)", color: "#fca5a5" }}>
            {String(error)}
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
             data-testid="ui-gallery-blocks">
          {(data.blocks || []).map((b) => (
            <div
              key={b.id}
              data-testid={`block-card-${b.id}`}
              className="rounded-xl p-4 border flex flex-col"
              style={{
                borderColor: "var(--nxt-border)",
                background: "var(--nxt-surface)",
              }}
            >
              <div className="flex items-start justify-between mb-2 gap-2">
                <span
                  className="mono text-[10px] tracking-[0.15em] uppercase px-1.5 py-0.5 rounded"
                  style={{
                    color: PACK_COLORS[b.pack] || "var(--nxt-fg-dim)",
                    background: `${PACK_COLORS[b.pack] || "#666"}1a`,
                  }}
                >
                  {b.pack}
                </span>
                <span className="mono text-[9px] uppercase tracking-wider"
                      style={{ color: "var(--nxt-fg-faint)" }}>
                  {b.kind}
                </span>
              </div>
              <div className="text-[14px] font-medium mb-1"
                   style={{ color: "var(--nxt-fg)" }}>{b.name}</div>
              <div className="text-[12px] leading-snug mb-2"
                   style={{ color: "var(--nxt-fg-dim)" }}>{b.summary}</div>
              {b.ai_hint && (
                <div
                  className="text-[11px] p-2 rounded mt-auto"
                  style={{
                    background: "rgba(34,211,238,0.05)",
                    color: "var(--nxt-fg-dim)",
                    borderLeft: "2px solid rgba(34,211,238,0.4)",
                  }}
                >
                  <span className="mono uppercase tracking-wider text-[9px] opacity-60">
                    AI HINT ·
                  </span>{" "}
                  {b.ai_hint}
                </div>
              )}
              <div className="mt-2 flex flex-wrap gap-1">
                {(b.tags || []).slice(0, 4).map((t) => (
                  <span
                    key={t}
                    className="mono text-[9px] px-1.5 py-0.5 rounded"
                    style={{
                      color: "var(--nxt-fg-faint)",
                      background: "rgba(255,255,255,0.03)",
                    }}
                  >
                    {t}
                  </span>
                ))}
              </div>
              <code className="mono text-[10px] mt-2 opacity-60"
                    style={{ color: "var(--nxt-fg-faint)" }}>
                {b.id}
              </code>
              {blockIsImplemented(b.id) && (
                <button
                  onClick={() => setPreviewBlock(b)}
                  data-testid={`block-preview-${b.id}`}
                  className="mt-2 text-[10px] flex items-center gap-1 px-2 py-1 rounded-full self-start"
                  style={{
                    color: "#10b981",
                    background: "rgba(16,185,129,0.08)",
                    border: "1px solid rgba(16,185,129,0.25)",
                  }}
                >
                  <Eye className="w-3 h-3" />
                  Live preview
                  <CheckCircle2 className="w-2.5 h-2.5 opacity-60" />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
      {previewBlock && (
        <BlockPreviewModal block={previewBlock} onClose={() => setPreviewBlock(null)} />
      )}
    </div>
  );
}

function BlockPreviewModal({ block, onClose }) {
  const Component = getBlockComponent(block.id);
  return (
    <div
      data-testid="block-preview-modal"
      className="fixed inset-0 z-[60] flex items-stretch p-3 sm:p-6"
      style={{ background: "rgba(0,0,0,0.78)", backdropFilter: "blur(6px)" }}
      onClick={onClose}
    >
      <div
        className="relative flex-1 rounded-2xl overflow-hidden flex flex-col"
        style={{
          background: "#0a0a0f",
          border: "1px solid rgba(255,255,255,0.08)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center justify-between px-4 py-2.5 border-b"
          style={{ borderColor: "rgba(255,255,255,0.06)" }}
        >
          <div className="flex items-center gap-2">
            <code className="mono text-[11px]" style={{ color: "#a78bfa" }}>
              {block.id}
            </code>
            <span className="text-[12px]" style={{ color: "rgba(255,255,255,0.6)" }}>
              · {block.name}
            </span>
          </div>
          <button
            onClick={onClose}
            data-testid="block-preview-close"
            className="w-8 h-8 rounded-full flex items-center justify-center"
            style={{
              color: "rgba(255,255,255,0.6)",
              background: "rgba(255,255,255,0.04)",
            }}
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-auto relative">
          {Component ? (
            // Some blocks (DotPattern, Meteors, ParticleField, WavyBackground)
            // are absolutely-positioned overlays — wrap them in a sized stage
            // so they have a backdrop to render against.
            ["background", "scene"].includes(block.kind) ? (
              <div className="relative w-full h-full min-h-[420px] bg-[#0a0a0f] flex items-center justify-center">
                <Component />
                <div className="relative z-10 text-center px-6">
                  <div className="mono uppercase tracking-[0.3em] text-[10px] mb-3"
                       style={{ color: "rgba(167,139,250,0.7)" }}>
                    Preview · {block.kind}
                  </div>
                  <div className="text-[20px] font-semibold text-white">
                    {block.name}
                  </div>
                </div>
              </div>
            ) : block.kind === "text" ? (
              <div className="w-full h-full min-h-[300px] flex items-center justify-center bg-[#0a0a0f] text-white">
                <div className="text-[clamp(28px,5vw,48px)] font-semibold">
                  <Component>{block.name === "Animated Gradient Text" ? "Magic" : "Building your app..."}</Component>
                </div>
              </div>
            ) : block.kind === "input" ? (
              <div className="w-full h-full min-h-[300px] flex items-center justify-center bg-[#0a0a0f] p-6">
                <div className="w-full max-w-[360px]">
                  <Component />
                </div>
              </div>
            ) : block.kind === "card" ? (
              <div className="w-full h-full min-h-[420px] flex items-center justify-center bg-[#0a0a0f] p-6">
                <div className="w-full max-w-[320px]">
                  <Component highlight />
                </div>
              </div>
            ) : (
              <Component />
            )
          ) : (
            <div className="p-10 text-center text-white">Component not vendored yet.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function Chip({ active, onClick, label, color, testId }) {
  return (
    <button
      onClick={onClick}
      data-testid={testId}
      className="text-[11px] px-2.5 py-1 rounded-full transition-all"
      style={{
        background: active
          ? (color ? `${color}22` : "var(--nxt-fg)")
          : "var(--nxt-surface-hi)",
        color: active
          ? (color || "var(--nxt-bg)")
          : "var(--nxt-fg-dim)",
        border: `1px solid ${active ? (color || "var(--nxt-fg)") : "var(--nxt-border)"}`,
      }}
    >
      {label}
    </button>
  );
}
