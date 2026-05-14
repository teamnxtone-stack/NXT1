/**
 * NXT1 Premium Card — frosted glass surface with optional active glow.
 * Used everywhere a panel needs the "high-end developer tooling" feel.
 */
export default function PremiumCard({
  active = false,
  glow = "cyan",
  hoverable = true,
  className = "",
  children,
  ...rest
}) {
  const activeRing = active
    ? glow === "warm"
      ? "nxt-glow-ring-warm"
      : "nxt-glow-ring"
    : "";
  return (
    <div
      className={`nxt-card-premium ${activeRing} ${hoverable ? "" : "hover:!transform-none hover:!shadow-none"} ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
