/**
 * Premium UI block — hero.aceternity.spotlight
 *
 * Spotlight hero with a beam of light that tracks the cursor.
 * Pure framer-motion + tailwind. No CDNs. Inspired by Aceternity UI.
 *
 * Usage:
 *   import { SpotlightHero } from "@/components/ui/blocks";
 *   <SpotlightHero headline="Ship in days, not months." cta="Get started" />
 */
import { useEffect, useRef } from "react";
import { motion } from "framer-motion";

export default function SpotlightHero({
  eyebrow = "Premium · curated",
  headline = "Build software. Host it. Ship it.",
  subline = "An AI-native platform for founders and serious teams.",
  cta = "Get started",
  ctaHref = "#",
  secondaryCta = "See how it works",
  secondaryHref = "#",
}) {
  const ref = useRef(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const handler = (e) => {
      const r = node.getBoundingClientRect();
      const x = ((e.clientX - r.left) / r.width) * 100;
      const y = ((e.clientY - r.top) / r.height) * 100;
      node.style.setProperty("--mx", `${x}%`);
      node.style.setProperty("--my", `${y}%`);
    };
    node.addEventListener("mousemove", handler);
    return () => node.removeEventListener("mousemove", handler);
  }, []);

  return (
    <section
      ref={ref}
      data-testid="block-hero-spotlight"
      className="relative isolate overflow-hidden bg-[#0a0a0f] text-white min-h-[78vh] flex items-center justify-center px-6"
      style={{
        backgroundImage:
          "radial-gradient(600px circle at var(--mx, 50%) var(--my, 50%), rgba(139,92,246,0.18), transparent 40%)",
      }}
    >
      {/* Grid backdrop */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 opacity-20"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
          maskImage:
            "radial-gradient(ellipse at center, black 30%, transparent 70%)",
        }}
      />
      <div className="max-w-[820px] mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mono uppercase tracking-[0.3em] text-[10px] mb-5"
          style={{ color: "rgba(167,139,250,0.9)" }}
        >
          {eyebrow}
        </motion.div>
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="text-[clamp(34px,7vw,72px)] font-semibold leading-[1.05] tracking-tight mb-5 bg-clip-text text-transparent"
          style={{
            backgroundImage:
              "linear-gradient(180deg, #ffffff 0%, rgba(255,255,255,0.55) 100%)",
          }}
        >
          {headline}
        </motion.h1>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="text-[clamp(14px,1.6vw,17px)] mb-8 max-w-[560px] mx-auto"
          style={{ color: "rgba(255,255,255,0.6)" }}
        >
          {subline}
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.45 }}
          className="flex items-center justify-center gap-3 flex-wrap"
        >
          <a
            href={ctaHref}
            data-testid="hero-spotlight-cta"
            className="px-5 py-2.5 rounded-full text-[13px] font-medium transition hover:scale-[1.02]"
            style={{
              background: "white",
              color: "#0a0a0f",
            }}
          >
            {cta}
          </a>
          {secondaryCta && (
            <a
              href={secondaryHref}
              className="px-5 py-2.5 rounded-full text-[13px] transition"
              style={{
                color: "rgba(255,255,255,0.8)",
                border: "1px solid rgba(255,255,255,0.14)",
              }}
            >
              {secondaryCta}
            </a>
          )}
        </motion.div>
      </div>
    </section>
  );
}
