/**
 * NXT1 — Homepage Demos (Browser frames, consistent dimensions).
 *
 * All slides render in a SINGLE desktop browser frame (16:10) so size never
 * jumps. Rotates through realistic software archetypes:
 *   • SaaS dashboard
 *   • Marketing site
 *   • AI chat app
 *   • Admin / analytics console
 *   • Portfolio site
 *   • Project tracker
 *
 * Subtle cinematic motion, no loud transitions, no giant gradients.
 */
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Cpu, Sparkles, Layers } from "lucide-react";
import DeviceFrame from "@/components/premium/DeviceFrame";

const CYCLES = [
  { prompt: "Build a SaaS subscription dashboard",       archetype: "dashboard",  tag: "FULL-STACK" },
  { prompt: "Build a streaming AI chat with markdown",    archetype: "chat",       tag: "AI APP" },
  { prompt: "Build a marketing site for our new product", archetype: "marketing",  tag: "WEBSITE" },
  { prompt: "Build an analytics console for revenue",     archetype: "analytics",  tag: "ADMIN" },
  { prompt: "Build a poetic portfolio site",              archetype: "portfolio",  tag: "PORTFOLIO" },
  { prompt: "Build a project tracker like Linear",        archetype: "tracker",    tag: "PRODUCTIVITY" },
];

export default function HomepageDemos() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((v) => (v + 1) % CYCLES.length), 4200);
    return () => clearInterval(t);
  }, []);
  const cur = CYCLES[i];

  return (
    <section
      className="relative mx-auto max-w-[1180px] px-4 sm:px-6 py-10 sm:py-20"
      data-testid="homepage-demos"
    >
      <div className="text-center mb-7 sm:mb-12">
        <span
          className="mono text-[9.5px] sm:text-[10px] tracking-[0.32em] uppercase"
          style={{ color: "var(--nxt-fg-faint)" }}
        >
          DISCOVER · DEVELOP · DELIVER
        </span>
        <h2
          className="mt-2.5 text-2xl sm:text-5xl font-semibold tracking-tight leading-[1.05] max-w-[820px] mx-auto"
          style={{
            background: "linear-gradient(120deg, var(--nxt-fg), var(--nxt-accent))",
            WebkitBackgroundClip: "text",
            backgroundClip: "text",
            color: "transparent",
          }}
        >
          NXT1 builds real software.
        </h2>
      </div>

      {/* Browser frame — fixed dimensions, content swaps inside. */}
      <div
        className="relative mx-auto"
        style={{ maxWidth: 880, aspectRatio: "16 / 10" }}
      >
        <DeviceFrame variant="desktop" url={`preview.nxt1 · ${cur.archetype}`}>
          <AnimatePresence mode="wait">
            <motion.div
              key={cur.archetype}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              className="absolute inset-0"
            >
              <ArchetypeContent kind={cur.archetype} />
            </motion.div>
          </AnimatePresence>
        </DeviceFrame>

        {/* Floating prompt + tag overlay (responsive) */}
        <motion.div
          layout
          className="absolute z-30 left-3 right-3 sm:left-4 sm:right-auto bottom-3 sm:bottom-4 max-w-[460px]"
        >
          <div
            className="rounded-xl px-3 py-2.5 flex items-center gap-3"
            style={{
              background: "rgba(31,31,35,0.85)",
              border: "1px solid rgba(255,255,255,0.08)",
              backdropFilter: "blur(18px) saturate(140%)",
              WebkitBackdropFilter: "blur(18px) saturate(140%)",
            }}
          >
            <Sparkles size={12} style={{ color: "var(--nxt-accent)" }} />
            <AnimatePresence mode="wait">
              <motion.div
                key={cur.prompt}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.3 }}
                className="flex-1 min-w-0 text-[12.5px] sm:text-[13.5px] text-white/90 truncate"
              >
                {cur.prompt}
              </motion.div>
            </AnimatePresence>
            <AnimatePresence mode="wait">
              <motion.span
                key={cur.tag}
                initial={{ opacity: 0, x: 4 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -4 }}
                transition={{ duration: 0.25 }}
                className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded-md mono text-[9.5px] tracking-[0.18em] uppercase"
                style={{
                  background: "rgba(94,234,212,0.10)",
                  border: "1px solid rgba(94,234,212,0.22)",
                  color: "#5EEAD4",
                }}
              >
                <Layers size={10} /> {cur.tag}
              </motion.span>
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Progress dots beneath frame */}
        <div className="absolute z-30 -bottom-7 left-0 right-0 flex items-center justify-center gap-1.5">
          {CYCLES.map((_, j) => (
            <span
              key={j}
              className="h-1 rounded-full transition-all"
              style={{
                width: j === i ? 22 : 6,
                background: j === i ? "var(--nxt-accent)" : "var(--nxt-border)",
              }}
              aria-hidden
            />
          ))}
        </div>
      </div>

      <div
        className="mt-12 flex items-center justify-center gap-1.5 text-[11.5px] sm:text-[12.5px]"
        style={{ color: "var(--nxt-fg-dim)" }}
      >
        <Cpu size={11} style={{ color: "var(--nxt-accent)", opacity: 0.8 }} />
        <span>Routes across Claude, GPT, Gemini, Grok, DeepSeek — automatically.</span>
      </div>
    </section>
  );
}

/* ---------- Archetype previews (all fill the same frame) ---------- */
function ArchetypeContent({ kind }) {
  if (kind === "dashboard")  return <DashboardPreview />;
  if (kind === "chat")       return <ChatPreview />;
  if (kind === "marketing")  return <MarketingPreview />;
  if (kind === "analytics")  return <AnalyticsPreview />;
  if (kind === "portfolio")  return <PortfolioPreview />;
  return <TrackerPreview />;
}

function Stripe() { return <div className="h-px w-full bg-zinc-100" />; }

function DashboardPreview() {
  return (
    <div className="h-full w-full flex" style={{ background: "#F7F8FA" }}>
      <aside className="w-[120px] shrink-0 bg-white border-r border-zinc-100 p-3 hidden sm:block">
        <div className="h-2 w-12 bg-zinc-900 rounded mb-4" />
        {["Overview", "Revenue", "Subscribers", "Settings"].map((it, i) => (
          <div key={it} className={`text-[10.5px] py-1.5 px-2 rounded ${i === 1 ? "bg-zinc-100 text-zinc-900" : "text-zinc-500"}`}>{it}</div>
        ))}
      </aside>
      <div className="flex-1 p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-[14px] font-semibold tracking-tight text-zinc-900">Revenue</div>
          <div className="mono text-[10px] text-zinc-500">Q3 · 2026</div>
        </div>
        <div className="grid grid-cols-3 gap-2 mb-3">
          {[["$48.2K", "+12%"], ["$12.8K", "+3%"], ["94%", "+0.4"]].map(([v, d], i) => (
            <div key={i} className="bg-white rounded-xl p-2.5 border border-zinc-100">
              <div className="text-[15px] font-semibold text-zinc-900">{v}</div>
              <div className="text-[10.5px] text-emerald-600 mt-0.5">{d}</div>
            </div>
          ))}
        </div>
        <div className="bg-white rounded-xl p-3 border border-zinc-100 h-[44%]">
          <svg viewBox="0 0 200 60" className="w-full h-full" preserveAspectRatio="none" aria-hidden>
            <polyline points="0,50 18,42 36,46 54,30 72,32 90,18 108,22 126,12 144,16 162,8 180,12 200,4" fill="none" stroke="#14826E" strokeWidth="2" />
            <polyline points="0,55 18,50 36,52 54,40 72,42 90,30 108,34 126,24 144,28 162,20 180,24 200,16" fill="none" stroke="#7F7FA0" strokeWidth="1" strokeOpacity="0.4" />
          </svg>
        </div>
      </div>
    </div>
  );
}

function ChatPreview() {
  return (
    <div className="h-full w-full flex flex-col" style={{ background: "#FAFAFA" }}>
      <div className="px-4 py-3 border-b border-zinc-100 flex items-center gap-2">
        <div className="h-6 w-6 rounded-full bg-zinc-900" />
        <div className="text-[12px] font-semibold tracking-tight text-zinc-900">Concierge</div>
      </div>
      <div className="flex-1 p-4 space-y-2 overflow-hidden">
        <div className="ml-auto max-w-[60%] bg-zinc-100 rounded-2xl rounded-br-md px-3 py-2 text-[12.5px] text-zinc-900">
          Explain quantum entanglement like I'm five
        </div>
        <div className="max-w-[78%] text-[12.5px] text-zinc-700 px-1">
          Imagine two coins glued by an invisible thread. Spin one — the other lands the same way. Even from across the room.
        </div>
        <div className="flex items-center gap-1.5 text-[10.5px] text-zinc-400 pl-1">
          <span className="h-1 w-1 rounded-full bg-emerald-500 animate-pulse" /> streaming
        </div>
      </div>
      <div className="p-3 border-t border-zinc-100 flex items-center gap-2">
        <div className="flex-1 h-9 bg-zinc-100 rounded-xl px-3 text-[11.5px] text-zinc-400 flex items-center">Ask anything…</div>
        <div className="h-9 w-9 rounded-xl bg-zinc-900 grid place-items-center text-white text-[14px]">↑</div>
      </div>
    </div>
  );
}

function MarketingPreview() {
  return (
    <div className="h-full w-full flex flex-col" style={{ background: "linear-gradient(180deg,#FFF8F0,#F8EBD7)" }}>
      <div className="px-6 py-3 flex items-center justify-between">
        <div className="font-serif text-[16px] text-zinc-900">Atlas</div>
        <div className="flex gap-4 text-[11px] text-zinc-700">
          <span>Product</span><span>Pricing</span><span>About</span><span>Sign in</span>
        </div>
      </div>
      <div className="flex-1 px-6 flex flex-col justify-center">
        <div className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500">SPRING / 26</div>
        <div className="text-[28px] sm:text-[34px] font-serif tracking-tight text-zinc-900 leading-[1.05] mt-1 max-w-[80%]">
          Calm software for thoughtful teams.
        </div>
        <div className="text-[12.5px] text-zinc-600 mt-2 max-w-[60%]">No noise, no clutter — just the tools that matter.</div>
        <div className="mt-3 flex gap-2">
          <div className="h-8 px-3 bg-zinc-900 text-white text-[11px] flex items-center rounded-lg">Get Atlas</div>
          <div className="h-8 px-3 border border-zinc-300 text-zinc-900 text-[11px] flex items-center rounded-lg">Watch demo</div>
        </div>
      </div>
    </div>
  );
}

function AnalyticsPreview() {
  return (
    <div className="h-full w-full p-4 flex flex-col" style={{ background: "#0F1117" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-[13px] font-semibold tracking-tight text-white">Revenue · daily</div>
        <div className="mono text-[10px] text-zinc-400">LIVE</div>
      </div>
      <div className="grid grid-cols-4 gap-2 mb-3">
        {[["MRR", "$48.2K"], ["ARR", "$578K"], ["Churn", "1.2%"], ["NPS", "61"]].map(([k, v], i) => (
          <div key={i} className="rounded-lg p-2.5" style={{ background: "#1A1D26" }}>
            <div className="text-[9.5px] mono uppercase tracking-[0.18em] text-zinc-500">{k}</div>
            <div className="text-[14px] font-semibold text-white mt-1">{v}</div>
          </div>
        ))}
      </div>
      <div className="flex-1 rounded-xl p-3" style={{ background: "#1A1D26" }}>
        <svg viewBox="0 0 200 80" className="w-full h-full" preserveAspectRatio="none" aria-hidden>
          <defs>
            <linearGradient id="g1" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#5EEAD4" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#5EEAD4" stopOpacity="0" />
            </linearGradient>
          </defs>
          <polyline points="0,68 14,54 28,58 42,40 56,48 70,30 84,38 98,22 112,28 126,14 140,18 154,8 168,12 182,4 200,8" fill="none" stroke="#5EEAD4" strokeWidth="1.5" />
          <polygon points="0,68 14,54 28,58 42,40 56,48 70,30 84,38 98,22 112,28 126,14 140,18 154,8 168,12 182,4 200,8 200,80 0,80" fill="url(#g1)" />
        </svg>
      </div>
    </div>
  );
}

function PortfolioPreview() {
  return (
    <div className="h-full w-full p-6 flex" style={{ background: "linear-gradient(180deg,#F5F2EC 0%,#ECE6DA 100%)" }}>
      <div className="flex-1 flex flex-col justify-center">
        <div className="mono text-[10px] tracking-[0.32em] uppercase text-zinc-500">PORTFOLIO · 26</div>
        <div className="text-[40px] sm:text-[52px] font-serif text-zinc-900 leading-[0.98] mt-1">Sterling Vale</div>
        <div className="text-[12.5px] text-zinc-600 mt-2 max-w-[200px]">Type, brand and editorial design for thoughtful companies.</div>
      </div>
      <div className="w-[42%] grid grid-cols-2 gap-2 self-center">
        <div className="aspect-square rounded-xl bg-zinc-900" />
        <div className="aspect-square rounded-xl bg-amber-700/80" />
        <div className="aspect-square rounded-xl bg-emerald-900/70" />
        <div className="aspect-square rounded-xl bg-rose-900/60" />
      </div>
    </div>
  );
}

function TrackerPreview() {
  const cols = [
    { title: "Backlog",   count: 12, items: ["Onboard Q4 hires", "Refresh landing copy", "Audit asset bundle"] },
    { title: "In Progress", count: 4, items: ["Multi-provider router", "Workspace shell", "Demo cycler"] },
    { title: "Review",    count: 3, items: ["Drawer animations", "Theme tokens", "USA badge"] },
  ];
  return (
    <div className="h-full w-full p-4 flex flex-col" style={{ background: "#F7F8FA" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-[13px] font-semibold tracking-tight text-zinc-900">Sprint 26.W19</div>
        <div className="mono text-[10px] text-zinc-500">5 days left</div>
      </div>
      <div className="flex-1 grid grid-cols-3 gap-2 min-h-0">
        {cols.map((c) => (
          <div key={c.title} className="flex flex-col bg-white rounded-xl border border-zinc-100 p-2.5">
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-[10.5px] mono uppercase tracking-[0.18em] text-zinc-500">{c.title}</div>
              <div className="text-[10px] text-zinc-400">{c.count}</div>
            </div>
            <div className="flex-1 flex flex-col gap-1.5 overflow-hidden">
              {c.items.map((t, i) => (
                <div key={t} className="px-2 py-1.5 rounded-lg bg-zinc-50 border border-zinc-100">
                  <div className="text-[10.5px] text-zinc-900 truncate">{t}</div>
                  <div className="flex items-center gap-1 mt-0.5 text-[9.5px] text-zinc-400">
                    <span className={`h-1.5 w-1.5 rounded-full ${i === 0 ? "bg-emerald-500" : i === 1 ? "bg-amber-500" : "bg-zinc-300"}`} />
                    NXT-{200 + i}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
