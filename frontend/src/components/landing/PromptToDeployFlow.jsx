/**
 * NXT1 — Prompt → App → Preview → Deploy flow (2026-05-13)
 *
 * Lightweight 4-stage horizontal "tape" that animates left-to-right with a
 * realistic simulated mouse pointer, prompt typing, build progress, preview
 * paint, and deploy ping. No real builds run here — this is product
 * storytelling, not a live integration. The point is to convey the loop
 * NXT1 actually provides: prompt → working app → preview URL → deploy.
 *
 * Each stage is a self-contained card (~280px wide on desktop, stacked on
 * mobile). Cards are joined by an arrow that fills as the cycle progresses.
 *
 * One cycle ≈ 7s. Loops forever, restarts on viewport leave/return via
 * IntersectionObserver to avoid burning CPU when off-screen.
 */
import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Cpu, Eye, Rocket, ArrowRight, Sparkles, Check } from "lucide-react";

const PROMPTS = [
  "Build a SaaS dashboard with billing",
  "Ship a portfolio with smooth motion",
  "Build a mobile habit tracker",
  "Build an AI chat app with streaming",
];

// Stage timings (ms). Total cycle ≈ 6.8s.
const TIMINGS = {
  prompt:  1700,   // typing the prompt
  build:   2200,   // bar fills, files stream
  preview: 1700,   // preview repaints
  deploy:  1200,   // deploy ping + live url
  rest:    700,    // breath before next cycle
};

export default function PromptToDeployFlow() {
  const [stage, setStage] = useState("prompt"); // prompt | build | preview | deploy | rest
  const [cycle, setCycle] = useState(0);
  const [typed, setTyped] = useState("");
  const [paused, setPaused] = useState(false);
  const ref = useRef(null);

  // Pause when off-screen — saves CPU on long marketing scrolls.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => setPaused(!entry.isIntersecting),
      { threshold: 0.1 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Type the current prompt char-by-char during stage="prompt".
  useEffect(() => {
    if (paused || stage !== "prompt") return;
    const target = PROMPTS[cycle % PROMPTS.length];
    let i = 0;
    setTyped("");
    const step = Math.max(20, TIMINGS.prompt / Math.max(1, target.length));
    const t = setInterval(() => {
      i += 1;
      setTyped(target.slice(0, i));
      if (i >= target.length) clearInterval(t);
    }, step);
    return () => clearInterval(t);
  }, [stage, cycle, paused]);

  // Stage scheduler.
  useEffect(() => {
    if (paused) return;
    const next = {
      prompt:  () => setStage("build"),
      build:   () => setStage("preview"),
      preview: () => setStage("deploy"),
      deploy:  () => setStage("rest"),
      rest:    () => { setCycle((c) => c + 1); setStage("prompt"); },
    };
    const t = setTimeout(next[stage], TIMINGS[stage]);
    return () => clearTimeout(t);
  }, [stage, paused]);

  const stageIdx = ["prompt", "build", "preview", "deploy"].indexOf(stage);

  return (
    <section
      ref={ref}
      className="relative mx-auto max-w-[1080px] px-5 sm:px-6 py-16 sm:py-24"
      data-testid="prompt-to-deploy-flow"
    >
      {/* Section overline */}
      <div className="text-center mb-10 sm:mb-14">
        <span
          className="mono text-[10.5px] sm:text-[11px] tracking-[0.42em] uppercase font-medium"
          style={{ color: "var(--nxt-fg-faint)" }}
        >
          THE NXT1 LOOP
        </span>
        <h2
          className="mt-4 text-[28px] sm:text-[38px] lg:text-[44px] leading-[1.05] tracking-[-0.025em] font-medium"
          style={{ fontFamily: "'Cabinet Grotesk', sans-serif", color: "var(--nxt-fg)" }}
        >
          Prompt → App → Preview → Deploy.
        </h2>
        <p
          className="mt-3 text-[13.5px] sm:text-[15px] max-w-[520px] mx-auto"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          One uninterrupted loop. From a sentence to a live URL — without leaving NXT1.
        </p>
      </div>

      {/* Tape */}
      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] gap-3 sm:gap-4 items-stretch">
        <StageCard
          icon={Sparkles}
          tag="PROMPT"
          active={stageIdx >= 0}
          done={stageIdx > 0}
        >
          <div
            className="font-mono text-[12px] sm:text-[13px] leading-relaxed min-h-[3.4em]"
            style={{ color: "var(--nxt-fg)" }}
          >
            {stage === "prompt" ? typed : PROMPTS[cycle % PROMPTS.length]}
            {stage === "prompt" && (
              <motion.span
                className="inline-block w-[8px] h-[14px] ml-0.5 -mb-0.5 bg-current"
                animate={{ opacity: [1, 0, 1] }}
                transition={{ duration: 0.7, repeat: Infinity }}
              />
            )}
          </div>
        </StageCard>

        <FlowArrow active={stageIdx >= 1} />

        <StageCard
          icon={Cpu}
          tag="APP"
          active={stageIdx >= 1}
          done={stageIdx > 1}
        >
          <BuildProgress running={stage === "build"} done={stageIdx > 1} />
        </StageCard>

        <FlowArrow active={stageIdx >= 2} />

        <StageCard
          icon={Eye}
          tag="PREVIEW"
          active={stageIdx >= 2}
          done={stageIdx > 2}
        >
          <PreviewPaint show={stageIdx >= 2} />
        </StageCard>

        <FlowArrow active={stageIdx >= 3} />

        <StageCard
          icon={Rocket}
          tag="DEPLOY"
          active={stageIdx >= 3}
          done={stage === "rest"}
        >
          <DeployPing show={stageIdx >= 3} />
        </StageCard>
      </div>

      {/* Foot strip — what's actually happening behind the curtain */}
      <ul
        className="mt-10 sm:mt-14 grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11.5px] mono tracking-wider"
        style={{ color: "var(--nxt-fg-faint)" }}
      >
        {[
          "Scaffolds pre-baked",
          "WebContainer preview",
          "GitHub Actions deploy",
          "Mongo + APIs wired",
        ].map((t) => (
          <li key={t} className="flex items-center gap-2">
            <Check size={11} style={{ color: "var(--nxt-accent, #5EEAD4)" }} />
            <span>{t}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* ---------- internals ---------- */

function StageCard({ icon: Icon, tag, active, done, children }) {
  return (
    <motion.div
      animate={{
        opacity: active ? 1 : 0.45,
        scale:   active ? 1 : 0.985,
      }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="relative rounded-2xl p-4 sm:p-5 flex flex-col gap-3 min-h-[148px]"
      style={{
        background: "var(--nxt-surface-soft)",
        border: `1px solid ${active ? "var(--nxt-accent-border, rgba(94,234,212,0.30))" : "var(--nxt-border-soft)"}`,
        transition: "border-color 0.4s ease",
      }}
    >
      <div className="flex items-center justify-between">
        <span
          className="mono text-[10px] tracking-[0.32em] uppercase font-medium"
          style={{ color: active ? "var(--nxt-fg-dim)" : "var(--nxt-fg-faint)" }}
        >
          {tag}
        </span>
        <span
          className="h-7 w-7 rounded-lg flex items-center justify-center"
          style={{
            background: active ? "rgba(94,234,212,0.10)" : "var(--nxt-chip-bg)",
            border: "1px solid var(--nxt-border-soft)",
          }}
        >
          <Icon size={12} style={{ color: active ? "var(--nxt-accent, #5EEAD4)" : "var(--nxt-fg-faint)" }} />
        </span>
      </div>
      <div className="flex-1">{children}</div>
      {done && (
        <motion.div
          initial={{ opacity: 0, scale: 0.7 }}
          animate={{ opacity: 1, scale: 1 }}
          className="absolute top-3 right-3"
        >
          <Check size={11} style={{ color: "var(--nxt-accent, #5EEAD4)" }} />
        </motion.div>
      )}
    </motion.div>
  );
}

function FlowArrow({ active }) {
  return (
    <div
      className="hidden md:flex items-center justify-center px-1"
      style={{
        color: active ? "var(--nxt-accent, #5EEAD4)" : "var(--nxt-fg-faint)",
        transition: "color 0.4s ease",
      }}
    >
      <ArrowRight size={16} strokeWidth={1.6} />
    </div>
  );
}

function BuildProgress({ running, done }) {
  const target = done ? 100 : running ? 92 : 0;
  return (
    <div className="space-y-2">
      <div className="text-[11px] mono" style={{ color: "var(--nxt-fg-faint)" }}>
        {done ? "16 files written · ready" : running ? "scaffold · edit · validate" : "idle"}
      </div>
      <div
        className="h-1 rounded-full overflow-hidden"
        style={{ background: "var(--nxt-chip-bg)" }}
      >
        <motion.div
          className="h-full"
          style={{ background: "var(--nxt-accent, #5EEAD4)" }}
          animate={{ width: `${target}%` }}
          transition={{ duration: 1.6, ease: "easeOut" }}
        />
      </div>
      <div className="text-[10.5px] mono opacity-70 truncate" style={{ color: "var(--nxt-fg-dim)" }}>
        package.json → app/page.jsx → api/route.js
      </div>
    </div>
  );
}

function PreviewPaint({ show }) {
  return (
    <div
      className="relative h-[88px] rounded-md overflow-hidden"
      style={{
        background: "#0E0E10",
        border: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      {/* Topbar */}
      <div
        className="flex items-center gap-1.5 px-2 h-5"
        style={{
          background: "rgba(255,255,255,0.03)",
          borderBottom: "1px solid rgba(255,255,255,0.04)",
        }}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-rose-400/70" />
        <span className="h-1.5 w-1.5 rounded-full bg-amber-300/70" />
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/70" />
      </div>
      {/* Animated paint */}
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={show ? { opacity: 1, y: 0 } : { opacity: 0, y: 6 }}
        transition={{ duration: 0.5 }}
        className="p-2.5 space-y-1.5"
      >
        <div className="h-2 w-3/5 rounded bg-white/15" />
        <div className="h-1.5 w-4/5 rounded bg-white/8" />
        <div className="h-1.5 w-2/5 rounded bg-white/8" />
        <div className="flex gap-1.5 pt-1">
          <div className="h-3 w-12 rounded bg-emerald-400/30" />
          <div className="h-3 w-8 rounded bg-white/10" />
        </div>
      </motion.div>
    </div>
  );
}

function DeployPing({ show }) {
  return (
    <div className="space-y-2">
      <div
        className="font-mono text-[11.5px] truncate px-2 py-1.5 rounded"
        style={{
          background: "var(--nxt-chip-bg)",
          border: "1px solid var(--nxt-border-soft)",
          color: "var(--nxt-fg-dim)",
        }}
      >
        https://app.nxt1.dev/_/p/n8x2…
      </div>
      <div className="flex items-center gap-1.5 text-[11px]" style={{ color: "var(--nxt-fg-dim)" }}>
        <motion.span
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ background: show ? "var(--nxt-accent, #5EEAD4)" : "var(--nxt-fg-faint)" }}
          animate={show ? { opacity: [1, 0.4, 1] } : {}}
          transition={{ duration: 1.4, repeat: Infinity }}
        />
        <span className="mono tracking-wider">{show ? "Live · 99ms" : "Pending"}</span>
      </div>
    </div>
  );
}
