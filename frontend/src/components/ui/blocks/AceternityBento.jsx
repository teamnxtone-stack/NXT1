/**
 * Premium UI block — feature.aceternity.bento-grid
 *
 * Bento grid with hover lift, color tinting and motion-preview tiles.
 * Variant of BentoGridHero tuned for "how it works" sections (2 large + 4 small).
 */
import { motion } from "framer-motion";

const DEFAULT_TILES = [
  { title: "1. Describe",  blurb: "Tell NXT1 what to build in plain English.",            large: true,  tint: "rgba(167,139,250,0.18)" },
  { title: "2. Generate",  blurb: "Multi-agent pipeline writes the code.",                tint: "rgba(34,211,238,0.18)" },
  { title: "3. Preview",   blurb: "Live sandbox renders in seconds.",                     tint: "rgba(110,231,183,0.18)" },
  { title: "4. Heal",      blurb: "Self-heal loop fixes build errors.",                   tint: "rgba(252,211,77,0.18)" },
  { title: "5. Domain",    blurb: "Auto-SSL + Cloudflare DNS in one click.",              large: true,  tint: "rgba(244,114,182,0.18)" },
  { title: "6. Ship",      blurb: "Vercel / Cloudflare / your own server.",               tint: "rgba(125,211,252,0.18)" },
];

export default function AceternityBento({ tiles = DEFAULT_TILES, eyebrow = "How it works", headline = "Six steps. One place." }) {
  return (
    <section
      data-testid="block-feature-acet-bento"
      className="bg-[#0a0a0f] text-white py-20 px-6"
    >
      <div className="max-w-[1100px] mx-auto">
        <div className="mb-10 text-center">
          <div className="mono uppercase tracking-[0.3em] text-[10px] mb-3"
               style={{ color: "rgba(167,139,250,0.9)" }}>
            {eyebrow}
          </div>
          <h2 className="text-[clamp(28px,5vw,44px)] font-semibold tracking-tight">
            {headline}
          </h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 auto-rows-[170px]">
          {tiles.map((t, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.45, delay: i * 0.06 }}
              whileHover={{ y: -4 }}
              className={`relative rounded-2xl p-5 sm:p-6 overflow-hidden cursor-default transition-shadow hover:shadow-[0_20px_40px_-15px_rgba(167,139,250,0.4)] ${
                t.large ? "sm:col-span-2" : ""
              }`}
              style={{
                background: "rgba(255,255,255,0.025)",
                border: "1px solid rgba(255,255,255,0.06)",
              }}
            >
              <div
                aria-hidden
                className="absolute inset-0 opacity-60 transition-opacity"
                style={{
                  background: `radial-gradient(circle at 30% 30%, ${t.tint}, transparent 60%)`,
                }}
              />
              <div className="relative z-10">
                <div className="text-[18px] sm:text-[22px] font-semibold mb-1">
                  {t.title}
                </div>
                <div className="text-[13px]" style={{ color: "rgba(255,255,255,0.6)" }}>
                  {t.blurb}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
