/**
 * NXT1 — Phase 10 Adaptive Backdrop
 *
 * Two-mode design system (per user direction May 12):
 *   • variant="public"    → Signature teal→amber gradient (NXT1 brand artwork)
 *                           Used ONLY on the public landing/marketing surface.
 *   • variant="workspace" → Carbon-black graphite backdrop (deep charcoal +
 *                           subtle ambient orbs). Used on every internal
 *                           surface: builder, dashboard, admin, auth.
 *   • variant="auth"      → Carbon w/ slightly warmer orb palette for the
 *                           sign-in flow.
 *
 * The export name is preserved (GradientBackdrop) so all existing imports
 * across the codebase swap modes by passing `variant` only.
 */
import { useMemo } from "react";

export default function GradientBackdrop({
  intensity = "medium",
  variant = "public",
}) {
  const overlay = useMemo(() => {
    if (intensity === "soft") return "bg-graphite-scrim-soft";
    if (intensity === "strong") return "bg-graphite-scrim-strong";
    return "bg-graphite-scrim";
  }, [intensity]);

  // ────────────────────────────────────────────────────────────────────
  // PUBLIC LANDING — minimal cinema graphite (Phase 15 rebuild)
  // No more teal→amber image. Just a quiet graphite gradient with a single
  // soft light beam from the top, matching the AI-OS direction.
  //
  // In LIGHT mode, the same shape is preserved but the bottom shelf + accent
  // orbs use cream/jade so the landing page stays cohesive on warm cream.
  // ────────────────────────────────────────────────────────────────────
  if (variant === "cinema" || variant === "public") {
    // Detect current theme from <html data-theme>. Safe on SSR (defaults to dark).
    const isLight =
      typeof document !== "undefined" &&
      document.documentElement.dataset.theme === "light";

    return (
      <>
        {/* Pure base — matte graphite (dark) or warm cream (light) */}
        <div
          className="absolute inset-0"
          style={{ background: "var(--nxt-bg)" }}
          data-testid="gradient-backdrop"
        />
        {/* Soft vertical light beam — premium spotlight effect */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: isLight
              ? "radial-gradient(ellipse 90% 60% at 50% -10%, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0) 60%)"
              : "radial-gradient(ellipse 90% 60% at 50% -10%, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0) 60%)",
          }}
        />
        {/* Accent glow low-left — jade in light mode, cyan in dark */}
        <div
          className="absolute pointer-events-none"
          style={{
            left: "-15%",
            bottom: "-25%",
            width: 760,
            height: 760,
            background: isLight
              ? "radial-gradient(closest-side, rgba(20,130,110,0.12) 0%, rgba(20,130,110,0) 70%)"
              : "radial-gradient(closest-side, rgba(94,234,212,0.10) 0%, rgba(94,234,212,0) 70%)",
            filter: "blur(40px)",
          }}
        />
        {/* Accent glow right — amber in light mode, indigo in dark */}
        <div
          className="absolute pointer-events-none"
          style={{
            right: "-18%",
            top: "10%",
            width: 720,
            height: 720,
            background: isLight
              ? "radial-gradient(closest-side, rgba(245,158,11,0.10) 0%, rgba(245,158,11,0) 70%)"
              : "radial-gradient(closest-side, rgba(99,102,241,0.08) 0%, rgba(99,102,241,0) 70%)",
            filter: "blur(40px)",
          }}
        />
        {/* Bottom fade — graphite shelf in dark, soft warmer-cream shelf in light */}
        <div
          className="absolute inset-x-0 bottom-0 h-[40vh] pointer-events-none"
          style={{
            background: isLight
              ? "linear-gradient(180deg, rgba(231,224,206,0) 0%, rgba(231,224,206,0.7) 100%)"
              : "linear-gradient(180deg, rgba(31,31,35,0) 0%, rgba(31,31,35,0.6) 100%)",
          }}
        />
      </>
    );
  }

  // ────────────────────────────────────────────────────────────────────
  // INTERNAL — carbon-black charcoal w/ ambient orbs
  // ────────────────────────────────────────────────────────────────────
  const palette =
    variant === "auth"
      ? { a: "nxt-orb-indigo", b: "nxt-orb-cyan", c: "nxt-orb-pink" }
      : { a: "nxt-orb-cyan", b: "nxt-orb-indigo", c: "nxt-orb-amber" };

  return (
    <>
      {/* carbon charcoal base — matches user's IMG_4689 reference */}
      <div
        className="absolute inset-0"
        style={{ background: "var(--nxt-bg)" }}
        data-testid="gradient-backdrop"
      />
      {/* drifting ambient orbs */}
      <div
        className={`nxt-orb ${palette.a} nxt-orb-drift`}
        style={{ width: 720, height: 720, top: "-12%", left: "-8%", opacity: 0.32 }}
      />
      <div
        className={`nxt-orb ${palette.b} nxt-orb-drift-2`}
        style={{ width: 640, height: 640, top: "38%", right: "-10%", opacity: 0.28 }}
      />
      <div
        className={`nxt-orb ${palette.c} nxt-orb-drift`}
        style={{
          width: 540,
          height: 540,
          bottom: "-18%",
          left: "24%",
          opacity: 0.18,
          animationDelay: "6s",
        }}
      />
      <div className={`absolute inset-0 ${overlay} pointer-events-none`} />
      <div
        className="absolute inset-x-0 top-0 h-[260px] pointer-events-none"
        style={{
          background:
            "linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0) 100%)",
        }}
      />
      {/* Bottom shelf — masks any orb leak under the footer so the page reads
          as a single calm graphite plane on mobile (no teal strip artefact) */}
      <div
        className="absolute inset-x-0 bottom-0 h-[50vh] pointer-events-none"
        style={{
          background:
            "linear-gradient(180deg, rgba(31,31,35,0) 0%, rgba(31,31,35,0.85) 60%, var(--nxt-bg) 100%)",
        }}
      />
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(31,31,35,0) 35%, rgba(20,20,24,0.6) 100%)",
        }}
      />
    </>
  );
}
