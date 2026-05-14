/**
 * Premium UI block — hero.magicui.bento
 *
 * Bento-grid hero with one large feature card + smaller capability cells.
 * Inspired by Magic UI.
 */
import { motion } from "framer-motion";

const DEFAULT_CELLS = [
  { title: "AI generation",  blurb: "Claude · GPT · Gemini, auto-routed", tone: "violet", large: true },
  { title: "Live preview",   blurb: "WebContainers + Sandpack",           tone: "cyan" },
  { title: "Auto-SSL",       blurb: "Caddy · Cloudflare",                 tone: "amber" },
  { title: "Self-heal",      blurb: "Bounded retry loop",                 tone: "emerald" },
  { title: "Premium UI",     blurb: "17 curated blocks",                  tone: "rose" },
  { title: "Durable agents", blurb: "LangGraph workflows",                tone: "sky" },
];

const TONES = {
  violet:  { bg: "rgba(139,92,246,0.10)", fg: "#c4b5fd" },
  cyan:    { bg: "rgba(34,211,238,0.08)", fg: "#67e8f9" },
  amber:   { bg: "rgba(245,158,11,0.08)", fg: "#fcd34d" },
  emerald: { bg: "rgba(16,185,129,0.08)", fg: "#6ee7b7" },
  rose:    { bg: "rgba(244,63,94,0.08)",  fg: "#fda4af" },
  sky:     { bg: "rgba(14,165,233,0.08)", fg: "#7dd3fc" },
};

export default function BentoGridHero({
  eyebrow = "What you get",
  headline = "Everything you need. Nothing you don't.",
  cells = DEFAULT_CELLS,
}) {
  return (
    <section
      data-testid="block-hero-bento"
      className="relative bg-[#0a0a0f] text-white py-20 px-6 overflow-hidden"
    >
      <div
        aria-hidden
        className="absolute inset-0 -z-10 opacity-60"
        style={{
          background:
            "radial-gradient(800px circle at 50% 0%, rgba(139,92,246,0.12), transparent 60%)",
        }}
      />
      <div className="max-w-[1180px] mx-auto">
        <div className="mb-10 text-center">
          <div className="mono uppercase tracking-[0.3em] text-[10px] mb-3"
               style={{ color: "rgba(167,139,250,0.9)" }}>
            {eyebrow}
          </div>
          <h2 className="text-[clamp(28px,5vw,46px)] font-semibold tracking-tight leading-tight">
            {headline}
          </h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 auto-rows-[180px]">
          {cells.map((c, i) => {
            const tone = TONES[c.tone] || TONES.violet;
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.45, delay: i * 0.06 }}
                className={`relative rounded-2xl p-5 sm:p-6 overflow-hidden ${
                  c.large ? "lg:col-span-2 lg:row-span-2" : ""
                }`}
                style={{
                  background: "rgba(255,255,255,0.025)",
                  border: "1px solid rgba(255,255,255,0.06)",
                }}
              >
                <div
                  aria-hidden
                  className="absolute -top-12 -right-12 w-48 h-48 rounded-full blur-3xl"
                  style={{ background: tone.bg }}
                />
                <div className="relative z-10 flex flex-col h-full">
                  <div
                    className="mono uppercase tracking-[0.22em] text-[10px] mb-3"
                    style={{ color: tone.fg }}
                  >
                    0{i + 1}
                  </div>
                  <div className="text-[18px] sm:text-[22px] font-semibold mb-1">
                    {c.title}
                  </div>
                  <div className="text-[13px]" style={{ color: "rgba(255,255,255,0.55)" }}>
                    {c.blurb}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
