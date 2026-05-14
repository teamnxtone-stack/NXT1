/**
 * Premium UI block — scene.r3f.particles (CSS fallback variant)
 * scene.r3f.globe                          (CSS fallback variant)
 *
 * Real implementations require `three` + `@react-three/fiber` +
 * `@react-three/drei`. NXT1's host app doesn't ship those — the AI agent
 * emits real R3F code into the GENERATED apps. These CSS-only fallbacks
 * let the gallery render an in-page preview without adding ~500KB to
 * NXT1's bundle.
 */
import { motion } from "framer-motion";
import { useMemo } from "react";

// ── scene.r3f.particles ─────────────────────────────────────────────────
export function ParticleField({ count = 80, color = "#a78bfa" }) {
  const particles = useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: 1 + Math.random() * 3,
      duration: 8 + Math.random() * 14,
      delay: Math.random() * 5,
    }));
  }, [count]);
  return (
    <div
      data-testid="block-scene-particles"
      aria-hidden
      className="absolute inset-0 pointer-events-none overflow-hidden"
    >
      {particles.map((p) => (
        <motion.span
          key={p.id}
          className="absolute rounded-full"
          style={{
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.size,
            height: p.size,
            background: color,
            opacity: 0,
            filter: "blur(0.4px)",
            boxShadow: `0 0 ${p.size * 4}px ${color}66`,
          }}
          animate={{
            opacity: [0, 0.9, 0],
            y: [0, -30, -60],
            x: [0, (Math.random() - 0.5) * 20, 0],
          }}
          transition={{
            duration: p.duration,
            delay: p.delay,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}

// ── scene.r3f.globe ─────────────────────────────────────────────────────
export function AnimatedGlobe({ size = 320 }) {
  return (
    <div
      data-testid="block-scene-globe"
      className="relative mx-auto"
      style={{ width: size, height: size, perspective: 800 }}
    >
      <motion.div
        className="absolute inset-0 rounded-full"
        style={{
          background:
            "radial-gradient(circle at 35% 35%, rgba(167,139,250,0.6), rgba(34,211,238,0.3) 40%, transparent 70%)",
          boxShadow:
            "inset -20px -30px 60px rgba(0,0,0,0.6), 0 0 80px rgba(139,92,246,0.4)",
          transformStyle: "preserve-3d",
        }}
        animate={{ rotateY: 360 }}
        transition={{ duration: 28, repeat: Infinity, ease: "linear" }}
      >
        {/* Meridian + equator lines for that globe feel */}
        {[0, 30, 60, 90, 120, 150].map((deg) => (
          <div
            key={deg}
            aria-hidden
            className="absolute inset-0 rounded-full"
            style={{
              border: "1px solid rgba(255,255,255,0.06)",
              transform: `rotateY(${deg}deg)`,
            }}
          />
        ))}
        {[-45, 0, 45].map((deg) => (
          <div
            key={`lat-${deg}`}
            aria-hidden
            className="absolute inset-0 rounded-full"
            style={{
              border: "1px solid rgba(255,255,255,0.04)",
              transform: `rotateX(${deg}deg)`,
            }}
          />
        ))}
      </motion.div>
      {/* Connection arcs floating above */}
      <svg
        className="absolute inset-0 pointer-events-none"
        viewBox="0 0 320 320"
        aria-hidden
      >
        {[0, 1, 2].map((i) => (
          <motion.path
            key={i}
            d={`M 60 ${100 + i * 30} Q 160 ${20 + i * 30} 260 ${100 + i * 30}`}
            stroke="rgba(34,211,238,0.6)"
            strokeWidth="1"
            fill="none"
            strokeDasharray="3 4"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: [0, 1, 0] }}
            transition={{
              duration: 3,
              delay: i * 0.7,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />
        ))}
      </svg>
    </div>
  );
}
