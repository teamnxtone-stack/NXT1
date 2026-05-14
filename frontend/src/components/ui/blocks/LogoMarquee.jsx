/**
 * Premium UI block — feature.magicui.marquee
 *
 * Infinite scrolling row of logos/items with gradient mask edges.
 */
import { motion } from "framer-motion";

const DEFAULT_ITEMS = [
  "Acme", "Quanta", "Northwind", "Initech", "Hooli", "Stark", "Wayne",
  "Umbrella", "Wonka", "Tyrell", "Cyberdyne",
];

export default function LogoMarquee({
  items = DEFAULT_ITEMS,
  duration = 28,
  pauseOnHover = true,
  background = "#0a0a0f",
  textColor = "rgba(255,255,255,0.5)",
}) {
  const doubled = [...items, ...items]; // seamless loop
  return (
    <section
      data-testid="block-feature-marquee"
      className="relative py-12 overflow-hidden"
      style={{ background }}
    >
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none z-10"
        style={{
          background: `linear-gradient(90deg, ${background} 0%, transparent 12%, transparent 88%, ${background} 100%)`,
        }}
      />
      <motion.div
        className={`flex gap-12 whitespace-nowrap will-change-transform ${
          pauseOnHover ? "hover:[animation-play-state:paused]" : ""
        }`}
        animate={{ x: ["0%", "-50%"] }}
        transition={{
          duration,
          repeat: Infinity,
          ease: "linear",
        }}
      >
        {doubled.map((it, i) => (
          <span
            key={i}
            className="mono uppercase tracking-[0.22em] text-[13px] sm:text-[15px] shrink-0"
            style={{ color: textColor }}
          >
            {it}
          </span>
        ))}
      </motion.div>
    </section>
  );
}
