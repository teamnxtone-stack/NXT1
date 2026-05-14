/**
 * NXT1 — LandingShowcase
 *
 * Quiet, premium visual storytelling sections that live below the hero
 * on the landing page. Three sections + a CTA strip:
 *
 *   1. "From a sentence" — three step cards: Describe → Generate → Ship
 *   2. "Live preview" — mockup of phone + browser frames
 *   3. "Built on the best models" — provider logo wall
 *
 * Designed to read like a Base44 / Roark visual feature flow — minimal
 * copy, generous spacing, carbon graphite material everywhere. No marketing
 * fluff, no walls of text.
 */
import { Link } from "react-router-dom";
import { ArrowRight, Sparkles, Layers, MonitorSmartphone } from "lucide-react";
import { ProviderLogo } from "@/components/premium/ProviderLogos";
import { useTheme } from "@/components/theme/ThemeProvider";

const STEPS = [
  {
    n: "01",
    title: "Describe",
    body: "Type what you want to build. One sentence is enough.",
    icon: Sparkles,
  },
  {
    n: "02",
    title: "Generate",
    body: "Watch the workspace stream code, copy, and design in real time.",
    icon: Layers,
  },
  {
    n: "03",
    title: "Ship",
    body: "Preview on phone, tablet, or desktop, then deploy in one click.",
    icon: MonitorSmartphone,
  },
];

const PROVIDERS = [
  { key: "anthropic", label: "Claude",   tile: "#FAF9F5", invert: false },
  { key: "openai",    label: "ChatGPT",  tile: "#202021", invert: true  },
  { key: "gemini",    label: "Gemini",   tile: "#FFFFFF", invert: false },
  { key: "grok",      label: "Grok",     tile: "#0F0F10", invert: true  },
  { key: "deepseek",  label: "DeepSeek", tile: "#FFFFFF", invert: false },
];

export default function LandingShowcase() {
  const { theme } = useTheme();
  const isLight = theme === "light";
  // Stable colour tokens for the showcase. Light mode uses warm graphite
  // text on cream; dark mode keeps the existing soft-white scheme. The
  // previous version hardcoded `text-white` everywhere, which made the
  // entire section invisible against the tan background (user bug report
  // 2026-05-13).
  const c = isLight
    ? {
        cardBg:    "var(--nxt-surface-soft)",
        cardBorder:"1px solid var(--nxt-border-soft)",
        titleColor:"#1A1A1F",
        bodyColor: "#5A5650",
        mutedColor:"#8A857C",
        iconColor: "#2A2A2F",
        chipBg:    "linear-gradient(135deg, rgba(31,31,35,0.06) 0%, rgba(31,31,35,0.02) 100%)",
        chipRing:  "inset 0 0 0 1px rgba(31,31,35,0.08)",
        ctaBtnBg:  "#1F1F23",
        ctaBtnFg:  "#FAFAFA",
        providerWallBg: "linear-gradient(180deg, rgba(31,31,35,0.04) 0%, rgba(31,31,35,0.02) 100%)",
        providerWallBorder: "1px solid rgba(31,31,35,0.08)",
        previewBg: "linear-gradient(180deg, rgba(31,31,35,0.04) 0%, rgba(31,31,35,0.02) 100%)",
        previewBorder: "1px solid rgba(31,31,35,0.08)",
        skeletonStrong:"rgba(31,31,35,0.15)",
        skeletonSoft:  "rgba(31,31,35,0.08)",
        skeletonExtra: "rgba(31,31,35,0.05)",
      }
    : {
        cardBg:    "linear-gradient(180deg, var(--surface-2) 0%, var(--surface-1) 100%)",
        cardBorder:"1px solid rgba(255,255,255,0.06)",
        titleColor:"#FFFFFF",
        bodyColor: "rgba(255,255,255,0.50)",
        mutedColor:"rgba(255,255,255,0.35)",
        iconColor: "rgba(255,255,255,0.85)",
        chipBg:    "linear-gradient(135deg, var(--surface-3) 0%, var(--surface-1) 100%)",
        chipRing:  "inset 0 0 0 1px rgba(255,255,255,0.07)",
        ctaBtnBg:  "#FFFFFF",
        ctaBtnFg:  "#1F1F23",
        providerWallBg: "linear-gradient(180deg, var(--surface-1) 0%, var(--surface-recessed) 100%)",
        providerWallBorder: "1px solid rgba(255,255,255,0.04)",
        previewBg: "linear-gradient(180deg, rgba(48,48,56,0.62) 0%, rgba(36,36,40,0.45) 100%)",
        previewBorder: "1px solid rgba(255,255,255,0.06)",
        skeletonStrong:"rgba(255,255,255,0.15)",
        skeletonSoft:  "rgba(255,255,255,0.10)",
        skeletonExtra: "rgba(255,255,255,0.06)",
      };
  return (
    <section
      className="relative z-10 px-5 sm:px-6 pt-10 sm:pt-16 pb-16"
      data-testid="landing-showcase"
    >
      <div className="mx-auto max-w-[1080px] space-y-16 sm:space-y-24">

        {/* ─────────── 1. "From a sentence" — 3 step cards ─────────── */}
        <div>
          <SectionHeader
            overline="HOW IT WORKS"
            title="From a sentence."
            sub="Three quiet steps. The AI does the heavy lifting."
          />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4 mt-8 sm:mt-10">
            {STEPS.map((s) => {
              const Icon = s.icon;
              return (
                <div
                  key={s.n}
                  className="rounded-3xl p-5 sm:p-6 glow-hover"
                  style={{
                    background: c.cardBg,
                    border: c.cardBorder,
                    boxShadow: "var(--elev-1)",
                  }}
                  data-testid={`showcase-step-${s.n}`}
                >
                  <div className="flex items-center justify-between mb-5">
                    <span className="mono text-[10px] tracking-[0.30em] uppercase" style={{ color: c.mutedColor }}>{s.n}</span>
                    <span
                      className="h-9 w-9 rounded-2xl flex items-center justify-center"
                      style={{
                        background: c.chipBg,
                        boxShadow: c.chipRing,
                      }}
                    >
                      <Icon size={14} style={{ color: c.iconColor }} />
                    </span>
                  </div>
                  <h3
                    className="text-[20px] sm:text-[22px] font-semibold tracking-tight mb-1.5"
                    style={{ fontFamily: "'Cabinet Grotesk', sans-serif", color: c.titleColor }}
                  >
                    {s.title}
                  </h3>
                  <p className="text-[13.5px] leading-relaxed" style={{ color: c.bodyColor }}>{s.body}</p>
                </div>
              );
            })}
          </div>
        </div>

        {/* ─────────── 2. Live preview mockup ─────────── */}
        <div>
          <SectionHeader
            overline="PREVIEW · LIVE"
            title="See it before you ship it."
            sub="Every change reflows the preview across phone, tablet, and desktop."
          />
          <div
            className="relative mt-8 sm:mt-10 rounded-3xl overflow-hidden p-5 sm:p-8"
            style={{
              background: c.previewBg,
              border: c.previewBorder,
              boxShadow: "var(--elev-2)",
              minHeight: 280,
            }}
            data-testid="showcase-preview-mockup"
          >
            <div className="flex items-end justify-center gap-4 sm:gap-6 flex-wrap">
              <DesktopFrame skel={c} isLight={isLight} />
              <PhoneFrame skel={c} isLight={isLight} />
            </div>
            {/* Ambient drift glow */}
            <div
              aria-hidden
              className="absolute inset-0 pointer-events-none nxt-ambient-drift"
              style={{
                background:
                  "radial-gradient(60% 60% at 50% 100%, rgba(94,234,212,0.10) 0%, rgba(94,234,212,0) 70%)",
              }}
            />
          </div>
        </div>

        {/* ─────────── 3. Provider wall ─────────── */}
        <div>
          <SectionHeader
            overline="POWERED BY"
            title="The best models. Always."
            sub="Switch providers in a tap. Tiered routing keeps you fast and cheap."
          />
          <div
            className="mt-8 sm:mt-10 rounded-3xl p-6 sm:p-8 grid grid-cols-5 gap-3 sm:gap-5 items-center justify-items-center"
            style={{
              background: c.providerWallBg,
              boxShadow: "var(--elev-1)",
              border: c.providerWallBorder,
            }}
            data-testid="showcase-provider-wall"
          >
            {PROVIDERS.map((p) => (
              <div key={p.key} className="flex flex-col items-center gap-2 sm:gap-3 group">
                <span
                  className="inline-flex items-center justify-center rounded-2xl overflow-hidden transition-transform duration-200 group-hover:-translate-y-0.5"
                  style={{
                    width: 48,
                    height: 48,
                    background: p.tile,
                    boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.05), 0 8px 18px -10px rgba(0,0,0,0.6)",
                  }}
                >
                  <ProviderLogo provider={p.key} size={28} invert={p.invert} />
                </span>
                <span
                  className="mono text-[10px] sm:text-[10.5px] tracking-[0.18em] uppercase transition-colors"
                  style={{ color: c.mutedColor }}
                >
                  {p.label}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* ─────────── CTA strip ─────────── */}
        <div
          className="relative rounded-3xl overflow-hidden p-7 sm:p-10 text-center"
          style={{
            background: isLight
              ? "radial-gradient(80% 80% at 50% 0%, rgba(94,234,212,0.10) 0%, rgba(94,234,212,0) 60%), var(--nxt-surface-soft)"
              : "radial-gradient(80% 80% at 50% 0%, rgba(94,234,212,0.08) 0%, rgba(94,234,212,0) 60%), var(--surface-1)",
            border: c.cardBorder,
            boxShadow: "var(--elev-2)",
          }}
          data-testid="showcase-cta"
        >
          <div
            className="mono text-[10.5px] tracking-[0.36em] uppercase font-medium bg-clip-text text-transparent mb-3"
            style={{
              backgroundImage: isLight
                ? "linear-gradient(110deg, #0E8C73 0%, #B58320 50%, #C25A1F 100%)"
                : "linear-gradient(110deg, #5EEAD4 0%, #F0D28A 50%, #FF8A3D 100%)",
            }}
          >
            DISCOVER · DEVELOP · DELIVER
          </div>
          <h2
            className="text-[28px] sm:text-[40px] leading-[1.05] font-semibold tracking-[-0.025em] mb-5"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
          >
            <span style={{ color: c.titleColor }}>Ready to build </span>
            <span
              style={{
                background: isLight
                  ? "linear-gradient(180deg, #1A1A1F 0%, #6A6259 100%)"
                  : "linear-gradient(180deg, #E8E8EE 0%, #8A8A93 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              your next idea?
            </span>
          </h2>
          <Link
            to="/signup"
            className="inline-flex items-center gap-2 h-12 px-6 rounded-full text-[14px] font-semibold tracking-tight hover:-translate-y-0.5 transition-all group"
            style={{
              background: c.ctaBtnBg,
              color: c.ctaBtnFg,
              boxShadow: isLight ? "0 10px 28px -10px rgba(31,31,35,0.35)" : "0 10px 28px -10px rgba(255,255,255,0.45)",
            }}
            data-testid="showcase-cta-button"
          >
            Request access
            <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>

      </div>
    </section>
  );
}

/* ─────────── Section header helper ─────────── */
function SectionHeader({ overline, title, sub }) {
  const { theme } = useTheme();
  const isLight = theme === "light";
  return (
    <div className="text-center max-w-2xl mx-auto">
      <div
        className="mono text-[10px] tracking-[0.30em] uppercase mb-3 flex items-center justify-center gap-2"
        style={{ color: "var(--nxt-fg-faint)" }}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-[#5EEAD4]" />
        {overline}
      </div>
      <h2
        className="text-[28px] sm:text-[40px] leading-[1.05] font-semibold tracking-[-0.025em]"
        style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
      >
        <span
          style={{
            background: isLight
              ? "linear-gradient(180deg, #1A1A1F 0%, #6A6259 100%)"
              : "linear-gradient(180deg, #FFFFFF 0%, #9A9AA3 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          {title}
        </span>
      </h2>
      {sub && (
        <p
          className="text-[14px] mt-2 leading-relaxed"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          {sub}
        </p>
      )}
    </div>
  );
}

/* ─────────── Desktop browser frame ─────────── */
function DesktopFrame({ skel, isLight }) {
  return (
    <div
      className="rounded-2xl overflow-hidden shrink-0"
      style={{
        width: "min(520px, 88vw)",
        background: isLight ? "#1F1F23" : "var(--surface-recessed)",
        boxShadow: "var(--elev-3)",
        border: isLight ? "1px solid rgba(31,31,35,0.20)" : "1px solid rgba(255,255,255,0.05)",
      }}
    >
      {/* Browser chrome */}
      <div className="flex items-center gap-2 px-3 py-2" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        <span className="h-2 w-2 rounded-full bg-rose-400/70" />
        <span className="h-2 w-2 rounded-full bg-amber-400/70" />
        <span className="h-2 w-2 rounded-full bg-emerald-400/70" />
        <span className="ml-3 mono text-[10px] tracking-wider truncate" style={{ color: "rgba(255,255,255,0.45)" }}>
          nxt1.app/preview
        </span>
      </div>
      {/* Page mock — always renders on the dark device surface for contrast */}
      <div className="p-5 sm:p-6 aspect-[16/9] sm:aspect-[16/10] flex flex-col gap-3">
        <span className="h-2 w-32 rounded-full" style={{ background: "rgba(255,255,255,0.18)" }} />
        <span className="h-2 w-48 rounded-full" style={{ background: "rgba(255,255,255,0.10)" }} />
        <div className="grid grid-cols-3 gap-2 mt-2 flex-1">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-xl flex flex-col gap-1.5 p-2"
                 style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <span className="h-1.5 w-3/4 rounded-full" style={{ background: "rgba(255,255,255,0.18)" }} />
              <span className="h-1.5 w-1/2 rounded-full" style={{ background: "rgba(255,255,255,0.10)" }} />
              <span className="mt-auto h-5 w-12 rounded-md" style={{ background: "linear-gradient(135deg, rgba(94,234,212,0.40) 0%, rgba(14,116,144,0.30) 100%)" }} />
            </div>
          ))}
        </div>
      </div>
      {/* Suppress unused-prop lint */}
      {skel && null}
    </div>
  );
}

/* ─────────── Phone frame ─────────── */
function PhoneFrame({ skel, isLight }) {
  return (
    <div
      className="rounded-[28px] overflow-hidden shrink-0 hidden sm:block"
      style={{
        width: 160,
        height: 320,
        background: isLight ? "#1F1F23" : "var(--surface-recessed)",
        boxShadow: "var(--elev-3)",
        border: isLight ? "1px solid rgba(31,31,35,0.22)" : "1px solid rgba(255,255,255,0.08)",
      }}
    >
      <div className="h-5 flex items-center justify-center">
        <span className="h-1 w-12 rounded-full" style={{ background: "rgba(255,255,255,0.18)" }} />
      </div>
      <div className="px-3 pt-2 pb-4 flex flex-col gap-2">
        <span className="h-1.5 w-16 rounded-full" style={{ background: "rgba(255,255,255,0.18)" }} />
        <span className="h-1.5 w-24 rounded-full" style={{ background: "rgba(255,255,255,0.10)" }} />
        <div className="mt-2 grid grid-cols-2 gap-2">
          {[0,1,2,3].map((i) => (
            <div key={i} className="aspect-square rounded-lg flex items-center justify-center"
                 style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <span className="h-3 w-3 rounded-md" style={{ background: "linear-gradient(135deg, rgba(94,234,212,0.60) 0%, rgba(14,116,144,0.40) 100%)" }} />
            </div>
          ))}
        </div>
        <span className="mt-3 h-1.5 w-full rounded-full" style={{ background: "rgba(255,255,255,0.08)" }} />
        <span className="h-1.5 w-3/4 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }} />
      </div>
      {skel && null}
    </div>
  );
}
