/**
 * Premium UI block — card.magicui.shine-border
 *
 * Card with slow rotating gradient border. Useful for pricing tiers + feature cards.
 */
export default function ShineBorderCard({
  title = "Pro",
  price = "$29",
  cadence = "/mo",
  features = ["Unlimited builds", "Auto-SSL", "Premium support"],
  cta = "Choose Pro",
  ctaHref = "#",
  highlight = false,
}) {
  return (
    <div
      data-testid="block-card-shine"
      className="relative rounded-2xl p-[1.5px] overflow-hidden"
      style={{
        background: highlight
          ? "conic-gradient(from 0deg, #a78bfa, #67e8f9, #fcd34d, #a78bfa)"
          : "linear-gradient(140deg, rgba(255,255,255,0.18), rgba(255,255,255,0.02))",
      }}
    >
      {highlight && (
        <div
          aria-hidden
          className="absolute inset-0 animate-spin-slow"
          style={{
            background:
              "conic-gradient(from 0deg, #a78bfa, #67e8f9, #fcd34d, #a78bfa)",
            animation: "shine-spin 6s linear infinite",
          }}
        />
      )}
      <div
        className="relative rounded-2xl p-6 h-full"
        style={{
          background: "#0a0a0f",
          color: "white",
        }}
      >
        <div className="text-[12px] mono uppercase tracking-[0.22em] mb-3"
             style={{ color: highlight ? "#c4b5fd" : "rgba(255,255,255,0.45)" }}>
          {title}
        </div>
        <div className="flex items-baseline gap-1 mb-5">
          <div className="text-[42px] font-semibold leading-none">{price}</div>
          <div className="text-[14px]" style={{ color: "rgba(255,255,255,0.5)" }}>
            {cadence}
          </div>
        </div>
        <ul className="text-[13px] space-y-2 mb-6" style={{ color: "rgba(255,255,255,0.78)" }}>
          {features.map((f, i) => (
            <li key={i} className="flex items-center gap-2">
              <span style={{ color: "#67e8f9" }}>✓</span>
              {f}
            </li>
          ))}
        </ul>
        <a
          href={ctaHref}
          className="block text-center w-full px-4 py-2.5 rounded-full text-[13px] font-medium transition hover:scale-[1.02]"
          style={{
            background: highlight ? "white" : "rgba(255,255,255,0.06)",
            color: highlight ? "#0a0a0f" : "white",
            border: highlight ? "none" : "1px solid rgba(255,255,255,0.14)",
          }}
        >
          {cta}
        </a>
      </div>
      <style>{`
        @keyframes shine-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
