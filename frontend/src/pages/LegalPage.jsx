/**
 * NXT1 — LegalPage (Phase 19)
 *
 * Canonical wrapper for /privacy and /terms. Premium carbon graphite card,
 * mobile-safe spacing, working back nav, unified footer, /contact CTA at
 * the bottom of every page (so legal queries always have a clear next step).
 */
import { Link } from "react-router-dom";
import { ArrowLeft, Mail } from "lucide-react";
import Brand from "@/components/Brand";
import GradientBackdrop from "@/components/GradientBackdrop";
import PublicFooter from "@/components/PublicFooter";

export default function LegalPage({ title, lastUpdated, body }) {
  return (
    <div
      className="relative min-h-screen w-full flex flex-col text-white overflow-hidden"
      style={{ background: "var(--surface-0)" }}
      data-testid={`legal-page-${title.toLowerCase()}`}
    >
      <GradientBackdrop intensity="soft" variant="auth" />

      <header className="relative z-20 px-5 sm:px-10 pt-5 sm:pt-6 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <Link
            to="/"
            className="rail-btn"
            style={{ width: 36, height: 36 }}
            aria-label="Back to home"
            data-testid="legal-back"
          >
            <ArrowLeft size={15} />
          </Link>
          <Brand size="md" gradient />
        </div>
        <Link
          to="/contact"
          className="inline-flex items-center gap-1.5 text-[12px] tracking-wider uppercase text-white/55 hover:text-white transition-colors"
          data-testid="legal-contact"
        >
          <Mail size={12} /> Contact
        </Link>
      </header>

      <main className="relative z-10 flex-1 px-5 sm:px-8 py-8 sm:py-12">
        <div className="max-w-[760px] mx-auto nxt-os-in">
          <div className="mono text-[10px] tracking-[0.30em] uppercase text-white/45 mb-4 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-[#5EEAD4] nxt-pulse" />
            {title}
          </div>
          <h1
            className="text-[40px] sm:text-[56px] leading-[1.02] font-semibold tracking-[-0.025em] mb-3"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
          >
            <span
              style={{
                background: "linear-gradient(180deg, #FFFFFF 0%, #9A9AA3 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              {title}
            </span>
          </h1>
          {lastUpdated && (
            <p className="mono text-[10.5px] tracking-[0.20em] uppercase text-white/35 mb-8">
              Last updated · {lastUpdated}
            </p>
          )}

          <div
            className="rounded-3xl p-6 sm:p-10"
            style={{
              background: "linear-gradient(180deg, rgba(48,48,56,0.55) 0%, rgba(36,36,40,0.65) 100%)",
              border: "1px solid rgba(255,255,255,0.06)",
              boxShadow: "var(--elev-2)",
              backdropFilter: "blur(20px) saturate(140%)",
              WebkitBackdropFilter: "blur(20px) saturate(140%)",
            }}
          >
            <div
              className="text-white/75 text-[14.5px] leading-[1.72] space-y-5"
              style={{
                // Inline prose styling — we don't ship @tailwindcss/typography
                "--tw-prose-headings": "rgba(255,255,255,0.95)",
              }}
              data-testid="legal-body"
            >
              {body}
            </div>
          </div>

          <div className="mt-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-[12px] text-white/50">
            <span className="mono tracking-[0.20em] uppercase">NXT1 · Jwood Technologies</span>
            <Link
              to="/contact"
              className="inline-flex items-center gap-1.5 hover:text-white transition-colors"
            >
              Have questions? <span className="text-white/85 font-medium">Contact us</span> →
            </Link>
          </div>
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}

/* Small helpers — inline section headings + lists used inside body content */
export function Section({ title: t, children }) {
  return (
    <section className="space-y-3" data-testid="legal-section">
      <h2
        className="text-[18px] sm:text-[20px] font-semibold tracking-tight text-white pt-2"
        style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
      >
        {t}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

export function Bullets({ items }) {
  return (
    <ul className="space-y-2 pl-1">
      {items.map((i, idx) => (
        <li key={idx} className="flex items-start gap-2.5">
          <span className="mt-2 h-1 w-1 rounded-full bg-[#5EEAD4] shrink-0" />
          <span className="text-white/75">{i}</span>
        </li>
      ))}
    </ul>
  );
}
