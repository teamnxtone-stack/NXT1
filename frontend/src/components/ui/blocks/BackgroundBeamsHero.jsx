/**
 * Premium UI block — hero.aceternity.background-beams
 *
 * Animated SVG light beams behind tight headline + CTA.
 */
import { motion } from "framer-motion";

export default function BackgroundBeamsHero({
  headline = "The fastest way to ship.",
  subline = "AI-native. Zero config. Production ready.",
  cta = "Start building",
  ctaHref = "#",
}) {
  return (
    <section
      data-testid="block-hero-bg-beams"
      className="relative isolate overflow-hidden bg-[#05050a] text-white min-h-[70vh] flex items-center justify-center px-6"
    >
      {/* SVG beams */}
      <svg
        aria-hidden
        className="absolute inset-0 w-full h-full -z-10 opacity-50"
        viewBox="0 0 1200 800"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="beam-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#60a5fa" stopOpacity="0" />
            <stop offset="50%" stopColor="#60a5fa" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#a78bfa" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <motion.path
            key={i}
            d={`M ${-200 + i * 50},${100 + i * 80} Q ${600},${400 + i * 30} ${1400},${200 + i * 50}`}
            stroke="url(#beam-grad)"
            strokeWidth="1"
            fill="none"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 0.9 }}
            transition={{
              duration: 3 + i * 0.4,
              delay: i * 0.2,
              repeat: Infinity,
              repeatType: "reverse",
              ease: "easeInOut",
            }}
          />
        ))}
      </svg>
      <div className="max-w-[720px] text-center">
        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="text-[clamp(36px,7vw,68px)] font-semibold leading-[1.05] tracking-tight mb-4"
        >
          {headline}
        </motion.h1>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="text-[clamp(14px,1.6vw,17px)] mb-8"
          style={{ color: "rgba(255,255,255,0.6)" }}
        >
          {subline}
        </motion.p>
        <motion.a
          href={ctaHref}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.35 }}
          className="inline-block px-5 py-2.5 rounded-full text-[13px] font-medium transition hover:scale-[1.02]"
          style={{ background: "white", color: "#05050a" }}
          data-testid="hero-bg-beams-cta"
        >
          {cta}
        </motion.a>
      </div>
    </section>
  );
}
