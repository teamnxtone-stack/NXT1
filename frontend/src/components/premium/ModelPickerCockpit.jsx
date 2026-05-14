/**
 * NXT1 — Model Picker Cockpit (Phase 17 rewrite)
 *
 * Apple-like, compact, tactile. On desktop it opens as a soft floating
 * cockpit; on mobile it slides up as a bottom-sheet so it never clips.
 *
 * Direction:
 *   • Lead order: Claude • GPT • Gemini • Grok • DeepSeek
 *   • OpenRouter is backend-only routing infrastructure, not a top-level pick
 *   • Real brand-color spots replace abstract icons (compact, scannable)
 *   • Smooth open/close, no clipping, premium spacing, mobile-first
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Check, X } from "lucide-react";
import { ProviderLogo } from "./ProviderLogos";

const PROVIDER_META = {
  anthropic: {
    label: "Claude",
    sub: "Sonnet 4.5",
    description: "Anthropic's most capable model",
    accent: "#D97706",
    tile: "#FAF9F5",        // claude paper-tan tile so the orange splat reads cleanly
    invert: false,
    badge: "DEFAULT",
  },
  openai: {
    label: "ChatGPT",
    sub: "GPT-4o class",
    description: "OpenAI's flagship multimodal",
    accent: "#10A37F",
    tile: "#202021",        // dark tile, white logo
    invert: true,
  },
  gemini: {
    label: "Gemini",
    sub: "2.0 Pro",
    description: "Google's long-context multimodal",
    accent: "#4285F4",
    tile: "#FFFFFF",        // white tile so the blue gradient sparkle pops
    invert: false,
  },
  grok: {
    label: "Grok",
    sub: "3 / Mini",
    description: "xAI · realtime web-aware",
    accent: "#9CA3AF",
    tile: "#0F0F10",        // black-on-white grok → invert to white-on-graphite
    invert: true,
  },
  deepseek: {
    label: "DeepSeek",
    sub: "R1 / V3",
    description: "Reasoning & code specialist",
    accent: "#4D6BFE",
    tile: "#FFFFFF",        // white tile for the blue whale
    invert: false,
  },
  emergent: {
    label: "Auto",
    sub: "Smart routing",
    description: "NXT1 picks the best engine per task",
    accent: "#5EEAD4",
    tile: "linear-gradient(135deg, #5EEAD4 0%, #0E7490 100%)",
    invert: false,
    badge: "AUTO",
  },
};

const ORDER = ["anthropic", "openai", "gemini", "grok", "deepseek", "emergent"];

export default function ModelPickerCockpit({
  value,
  onChange,
  providers = {},
  disabled = false,
  compact = false,
  iconOnly = false,           // pristine: just the provider tile, no label/chevron
  className = "",
}) {
  const [open, setOpen] = useState(false);
  const [focusIdx, setFocusIdx] = useState(0);
  const containerRef = useRef(null);
  const sheetRef = useRef(null);
  const isMobile = typeof window !== "undefined" && window.matchMedia("(max-width: 640px)").matches;

  // Visible providers — keep order strict per direction
  const visible = useMemo(() => {
    return ORDER.filter((k) => k in PROVIDER_META).map((key) => ({
      key,
      ...PROVIDER_META[key],
      connected: !!providers[key] || key === "emergent" || key === "anthropic",
    }));
  }, [providers]);

  const activeKey = value && PROVIDER_META[value] ? value : "anthropic";
  const active = PROVIDER_META[activeKey];

  // Outside-click + ESC + arrow-key navigation
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
      if (e.key === "ArrowDown") { e.preventDefault(); setFocusIdx((f) => Math.min(visible.length - 1, f + 1)); }
      if (e.key === "ArrowUp")   { e.preventDefault(); setFocusIdx((f) => Math.max(0, f - 1)); }
      if (e.key === "Enter")     {
        e.preventDefault();
        const tgt = visible[focusIdx];
        if (tgt) { onChange?.(tgt.key); setOpen(false); }
      }
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, focusIdx, visible, onChange]);

  return (
    <div ref={containerRef} className={`relative inline-block ${className}`}>
      {/* ─────────── Trigger — pill (default) or icon-only (composer) ─────────── */}
      {iconOnly ? (
        <button
          type="button"
          disabled={disabled}
          onClick={() => setOpen((v) => !v)}
          data-testid="model-cockpit-trigger"
          title={`Model: ${active.label}`}
          aria-label={`Active model: ${active.label}. Click to change.`}
          className={`group inline-flex items-center justify-center rounded-full transition-all duration-200 ${
            disabled ? "opacity-50 cursor-not-allowed" : "hover:opacity-90"
          }`}
          style={{
            width: 26,
            height: 26,
            background: "transparent",
            border: "none",
            color: "var(--nxt-fg)",
          }}
        >
          <span
            className="inline-flex items-center justify-center shrink-0 rounded-full overflow-hidden"
            style={{
              width: 22,
              height: 22,
              background: active.tile || active.bg,
              boxShadow: open
                ? "inset 0 0 0 1px rgba(255,255,255,0.20), 0 0 0 2px rgba(200,185,140,0.30)"
                : "inset 0 0 0 1px rgba(255,255,255,0.10)",
              transition: "box-shadow 200ms",
            }}
          >
            <ProviderLogo provider={activeKey} size={13} invert={active.invert} />
          </span>
        </button>
      ) : (
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        data-testid="model-cockpit-trigger"
        className={`group inline-flex items-center rounded-full transition-all duration-200 ${
          disabled ? "opacity-50 cursor-not-allowed" : ""
        } ${compact ? "gap-2 pl-1 pr-2.5 py-0.5" : "gap-2 pl-1.5 pr-3 py-1"}`}
        style={{
          background: "var(--nxt-chip-bg)",
          border: "1px solid var(--nxt-border-soft)",
          color: "var(--nxt-fg)",
        }}
      >
        <span
          className="inline-flex items-center justify-center shrink-0 rounded-full overflow-hidden"
          style={{
            width: compact ? 22 : 26,
            height: compact ? 22 : 26,
            background: active.tile || active.bg,
            boxShadow: `inset 0 0 0 1px rgba(255,255,255,0.10)`,
          }}
        >
          <ProviderLogo provider={activeKey} size={compact ? 13 : 15} invert={active.invert} />
        </span>
        <span
          className={`font-semibold tracking-tight ${compact ? "text-[12px]" : "text-[13px]"}`}
          style={{
            color: "var(--nxt-fg)",
            fontFamily: "'Cabinet Grotesk', 'Inter', sans-serif",
          }}
        >
          {active.label}
        </span>
        <ChevronDown
          size={11}
          strokeWidth={2.2}
          className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          style={{ color: "var(--nxt-fg-faint)" }}
        />
      </button>
      )}

      {/* ─────────── Floating panel (desktop) or sheet (mobile) ─────────── */}
      {open && (
        <>
          {/* Mobile scrim */}
          {isMobile && (
            <div
              className="fixed inset-0 z-[80] scrim-soft"
              onClick={() => setOpen(false)}
              data-testid="model-cockpit-scrim"
            />
          )}
          <div
            ref={sheetRef}
            className={
              isMobile
                ? "fixed left-3 right-3 bottom-4 z-[85] nxt-slide-up nxt-safe-bottom"
                : "absolute bottom-full mb-2 right-0 z-50 w-[320px] sm:w-[360px] nxt-fade-up"
            }
            data-testid="model-cockpit-panel"
            role="listbox"
          >
            <div
              className={`rounded-2xl overflow-hidden`}
              style={{
                background: "linear-gradient(180deg, rgba(48,48,56,0.96) 0%, rgba(36,36,40,0.98) 100%)",
                border: "1px solid rgba(255,255,255,0.08)",
                boxShadow: "var(--elev-3, 0 30px 80px -20px rgba(0,0,0,0.65))",
                backdropFilter: "blur(32px) saturate(160%)",
                WebkitBackdropFilter: "blur(32px) saturate(160%)",
              }}
            >
              {/* Sheet handle (mobile only) */}
              {isMobile && (
                <div className="flex items-center justify-center pt-2 pb-0.5">
                  <span className="h-1 w-9 rounded-full bg-white/15" />
                </div>
              )}

              {/* Header — compact on mobile */}
              <div className={`flex items-center justify-between px-4 ${isMobile ? "pt-3 pb-2" : "pt-4 pb-3"}`}>
                <div>
                  <div className="mono text-[9.5px] tracking-[0.26em] uppercase text-white/35">AI MODEL</div>
                  <div className={`font-semibold tracking-tight text-white mt-0.5 ${isMobile ? "text-[13px]" : "text-[15px]"}`}
                    style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
                  >
                    Pick your engine
                  </div>
                </div>
                {isMobile ? (
                  <button
                    onClick={() => setOpen(false)}
                    className="rail-btn"
                    style={{ width: 30, height: 30 }}
                    aria-label="Close"
                  >
                    <X size={13} />
                  </button>
                ) : (
                  <span className="mono text-[9.5px] tracking-wider text-white/25">↑↓ ⏎ ESC</span>
                )}
              </div>

              {/* Rows — small premium iOS-style on mobile, larger touch rows on desktop */}
              <div className={`px-2 pb-2 ${isMobile ? "max-h-[50vh]" : "max-h-[60vh]"} overflow-y-auto no-scrollbar`}>
                {visible.map((p, i) => {
                  const isActive = p.key === activeKey;
                  const isFocused = i === focusIdx;
                  return (
                    <button
                      key={p.key}
                      type="button"
                      onMouseEnter={() => setFocusIdx(i)}
                      onClick={() => { onChange?.(p.key); setOpen(false); }}
                      className={`w-full text-left ${isMobile ? "rounded-xl px-2.5 py-2 gap-2.5" : "rounded-2xl px-3 py-3 gap-3.5"} mb-0.5 flex items-center transition-colors ${
                        isActive
                          ? "bg-white/[0.07]"
                          : isFocused
                            ? "bg-white/[0.04]"
                            : "hover:bg-white/[0.03]"
                      }`}
                      data-testid={`model-card-${p.key}`}
                      role="option"
                      aria-selected={isActive}
                    >
                      {/* Real provider logo tile */}
                      <span
                        className="inline-flex items-center justify-center shrink-0 rounded-xl overflow-hidden"
                        style={{
                          width: isMobile ? 30 : 40,
                          height: isMobile ? 30 : 40,
                          background: p.tile || p.bg,
                          boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.06)",
                        }}
                      >
                        <ProviderLogo provider={p.key} size={isMobile ? 16 : 22} invert={p.invert} />
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap leading-tight">
                          <span
                            className={`font-semibold text-white tracking-tight ${isMobile ? "text-[13px]" : "text-[15px]"}`}
                            style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
                          >
                            {p.label}
                          </span>
                          <span className={`mono text-white/35 tracking-tight ${isMobile ? "text-[9.5px]" : "text-[10.5px]"}`}>{p.sub}</span>
                          {p.badge && (
                            <span
                              className="mono text-[8.5px] tracking-[0.18em] px-1.5 py-0.5 rounded-md uppercase font-semibold"
                              style={{
                                background: `${p.accent}1F`,
                                color: p.accent,
                              }}
                            >
                              {p.badge}
                            </span>
                          )}
                        </div>
                        {!isMobile && (
                          <div className="text-[11.5px] text-white/40 truncate mt-0.5">
                            {p.description}
                          </div>
                        )}
                      </div>
                      {isActive && (
                        <span className={`shrink-0 rounded-full grid place-items-center ${isMobile ? "h-5 w-5" : "h-7 w-7"}`}
                          style={{ background: "rgba(94,234,212,0.18)" }}
                        >
                          <Check size={isMobile ? 11 : 14} className="text-[#5EEAD4]" strokeWidth={2.6} />
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Footer hint — only on desktop; mobile stays minimal */}
              {!isMobile && (
                <div className="px-4 pt-2 pb-4 mono text-[10px] tracking-[0.20em] text-white/30 uppercase border-t border-white/5">
                  Tip · connect a direct key in Settings for cheaper runs
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* ─────────── Internal: orphaned helper removed (now using ProviderLogo) ─────────── */
