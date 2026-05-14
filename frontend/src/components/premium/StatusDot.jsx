/**
 * NXT1 Status Dot — small pulse indicator. Use for CONNECTED, LIVE, BUILDING, etc.
 * Tones map to semantic state: live(cyan), warm(amber), error(pink), idle(gray).
 */
export default function StatusDot({
  tone = "live",
  size = 8,
  label = "",
  className = "",
}) {
  const map = {
    live:  { bg: "#5EEAD4", anim: "nxt-pulse",       text: "text-[#5EEAD4]" },
    warm:  { bg: "#F59E0B", anim: "nxt-pulse-warm",  text: "text-[#FBBF24]" },
    error: { bg: "#FB7185", anim: "nxt-pulse-pink",  text: "text-[#FB7185]" },
    idle:  { bg: "#52525B", anim: "",                text: "text-[#71717A]" },
  };
  const tn = map[tone] || map.live;
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span
        className={`rounded-full ${tn.anim}`}
        style={{ width: size, height: size, background: tn.bg, display: "inline-block" }}
      />
      {label ? (
        <span className={`mono text-[10px] tracking-[0.22em] uppercase ${tn.text}`}>{label}</span>
      ) : null}
    </span>
  );
}
