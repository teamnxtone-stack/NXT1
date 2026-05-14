/**
 * Premium UI block — feature.magicui.orbiting-circles
 *
 * Logos/icons orbiting around a central element. Great for "Connect to X, Y, Z".
 */
import { motion } from "framer-motion";

const DEFAULT_ORBITS = [
  { label: "Claude",  color: "#f59e0b", radius: 110, duration: 18, offset: 0 },
  { label: "OpenAI",  color: "#10b981", radius: 110, duration: 18, offset: 90 },
  { label: "Gemini",  color: "#60a5fa", radius: 110, duration: 18, offset: 180 },
  { label: "Grok",    color: "#a78bfa", radius: 110, duration: 18, offset: 270 },
  { label: "Stripe",  color: "#22d3ee", radius: 170, duration: 26, offset: 45 },
  { label: "GitHub",  color: "#fcd34d", radius: 170, duration: 26, offset: 135 },
  { label: "Vercel",  color: "#f472b6", radius: 170, duration: 26, offset: 225 },
  { label: "CF",      color: "#fb923c", radius: 170, duration: 26, offset: 315 },
];

export default function OrbitingCircles({
  centerLabel = "NXT1",
  orbits = DEFAULT_ORBITS,
}) {
  return (
    <section
      data-testid="block-feature-orbits"
      className="relative bg-[#0a0a0f] text-white py-20 px-6 overflow-hidden"
    >
      <div className="max-w-[820px] mx-auto text-center mb-12">
        <h2 className="text-[clamp(28px,5vw,42px)] font-semibold tracking-tight">
          Everything connects.
        </h2>
        <p className="text-[14px] mt-3" style={{ color: "rgba(255,255,255,0.55)" }}>
          AI providers, payments, hosting, version control — wired in once and routed automatically.
        </p>
      </div>
      <div className="relative mx-auto" style={{ width: 400, height: 400 }}>
        {/* Center */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-20 h-20 rounded-full flex items-center justify-center text-[14px] font-semibold z-10"
          style={{
            background: "linear-gradient(140deg, #a78bfa, #22d3ee)",
            color: "#0a0a0f",
            boxShadow: "0 0 60px rgba(139,92,246,0.4)",
          }}
        >
          {centerLabel}
        </div>
        {/* Orbit rings */}
        {[110, 170].map((r, i) => (
          <div
            key={i}
            aria-hidden
            className="absolute top-1/2 left-1/2 rounded-full border"
            style={{
              width: r * 2,
              height: r * 2,
              marginLeft: -r,
              marginTop: -r,
              borderColor: "rgba(255,255,255,0.08)",
            }}
          />
        ))}
        {/* Orbiting items */}
        {orbits.map((o, i) => (
          <motion.div
            key={i}
            className="absolute top-1/2 left-1/2 w-12 h-12"
            style={{ marginLeft: -24, marginTop: -24 }}
            animate={{ rotate: 360 }}
            transition={{ duration: o.duration, repeat: Infinity, ease: "linear" }}
          >
            <div
              className="absolute top-1/2 left-1/2 flex items-center justify-center text-[10px] font-medium rounded-full"
              style={{
                width: 44,
                height: 44,
                marginLeft: -22,
                marginTop: -22 - o.radius,
                background: "rgba(255,255,255,0.04)",
                border: `1px solid ${o.color}66`,
                color: o.color,
                transform: `rotate(${o.offset}deg)`,
              }}
            >
              <span style={{ transform: `rotate(-${o.offset}deg)` }}>{o.label}</span>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
