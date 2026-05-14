/**
 * NXT1 — Contact (Phase 18)
 *
 * Calm, on-brand contact surface. Carbon graphite material, premium spacing,
 * mobile-safe. Single primary action: email us.
 */
import { Link } from "react-router-dom";
import { ArrowLeft, Mail } from "lucide-react";
import Brand from "@/components/Brand";
import GradientBackdrop from "@/components/GradientBackdrop";

const CONTACT_EMAIL = "hello@jwoodtech.io";

export default function ContactPage() {
  return (
    <div
      className="relative min-h-screen w-full overflow-hidden text-white flex flex-col"
      style={{ background: "var(--surface-0, #2B2B31)" }}
      data-testid="contact-page"
    >
      <GradientBackdrop variant="auth" intensity="soft" />

      <header className="relative z-20 px-5 sm:px-10 pt-5 sm:pt-6 flex items-center justify-between">
        <Brand size="md" gradient />
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-[13px] text-white/65 hover:text-white px-3 py-2 transition-colors"
          data-testid="contact-back"
        >
          <ArrowLeft size={13} /> Back
        </Link>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center px-5 py-10">
        <div
          className="w-full max-w-[520px] rounded-3xl p-7 sm:p-10 nxt-os-in"
          style={{
            background: "linear-gradient(180deg, rgba(48,48,56,0.62) 0%, rgba(36,36,40,0.78) 100%)",
            border: "1px solid rgba(255,255,255,0.07)",
            boxShadow: "var(--elev-3, 0 30px 80px -20px rgba(0,0,0,0.65))",
            backdropFilter: "blur(28px) saturate(150%)",
            WebkitBackdropFilter: "blur(28px) saturate(150%)",
          }}
        >
          <div className="mono text-[10px] tracking-[0.30em] uppercase text-white/45 mb-4 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-[#5EEAD4] nxt-pulse" />
            Contact NXT1
          </div>
          <h1
            className="text-[30px] sm:text-[36px] leading-[1.05] font-semibold tracking-[-0.025em] mb-2"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
          >
            <span className="text-white">We'd love to </span>
            <span
              style={{
                background: "linear-gradient(180deg, #E8E8EE 0%, #8A8A93 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              hear from you.
            </span>
          </h1>
          <p className="text-white/50 text-[14px] mb-8 leading-relaxed">
            Press, partnerships, enterprise access, or feedback — drop us a line and a human will reply.
          </p>

          <a
            href={`mailto:${CONTACT_EMAIL}`}
            className="inline-flex w-full items-center justify-center gap-2 h-12 rounded-2xl bg-white text-[#1F1F23] text-[14px] font-semibold tracking-tight hover:bg-white/95 transition-all shadow-[0_10px_28px_-10px_rgba(255,255,255,0.45)] hover:-translate-y-0.5 mb-5"
            data-testid="contact-mailto"
          >
            <Mail size={14} /> {CONTACT_EMAIL}
          </a>

          <div className="text-[12.5px] text-white/35 text-center leading-relaxed mono tracking-[0.18em] uppercase">
            NXT1 · Jwood Technologies
          </div>
        </div>
      </main>

      <footer className="relative z-10 px-5 pb-7 pt-2">
        <div className="mx-auto max-w-[920px] flex flex-col sm:flex-row items-center justify-between gap-3 text-[11px] text-white/40">
          <span className="mono tracking-[0.20em] uppercase">DISCOVER · DEVELOP · DELIVER</span>
          <div className="flex items-center gap-5">
            <Link to="/privacy" className="hover:text-white/85 transition-colors">Privacy</Link>
            <Link to="/terms" className="hover:text-white/85 transition-colors">Terms</Link>
            <Link to="/signin" className="hover:text-white/85 transition-colors">Workspace</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
