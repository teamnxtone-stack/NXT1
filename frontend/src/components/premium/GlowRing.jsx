/**
 * NXT1 Glow Ring — animated rotating conic gradient ring used to highlight
 * the active provider/model in the cockpit selector, and other premium
 * accents (active deploy card, etc.). Pure CSS, GPU-accelerated.
 */
export default function GlowRing({
  size = 56,
  className = "",
  intensity = 0.7,
  color = "cyan",
  children,
}) {
  const palette = {
    cyan: "conic-gradient(from 0deg at 50% 50%, rgba(94,234,212,0.0) 0deg, rgba(94,234,212,0.6) 60deg, rgba(99,102,241,0.6) 200deg, rgba(94,234,212,0.0) 360deg)",
    warm: "conic-gradient(from 0deg at 50% 50%, rgba(245,158,11,0.0) 0deg, rgba(245,158,11,0.6) 60deg, rgba(236,72,153,0.6) 200deg, rgba(245,158,11,0.0) 360deg)",
  }[color] || color;
  return (
    <div
      className={`relative rounded-full ${className}`}
      style={{ width: size, height: size }}
    >
      <div
        className="absolute inset-0 rounded-full animate-spin"
        style={{ background: palette, opacity: intensity, animationDuration: "6s" }}
      />
      <div
        className="absolute inset-[2px] rounded-full"
        style={{ background: "var(--nxt-surface-2)" }}
      />
      <div className="absolute inset-0 grid place-items-center">{children}</div>
    </div>
  );
}
