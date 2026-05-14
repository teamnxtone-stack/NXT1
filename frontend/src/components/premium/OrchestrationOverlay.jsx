/**
 * NXT1 — Orchestration Overlay
 *
 * Cinematic AI-native state display used by the builder while a build is
 * streaming. Shows:
 *   • Active phase label with a soft glow pulse
 *   • Inferred foundation card (when inference fires)
 *   • Scaffold receipts as files animate in
 *   • Final "build ready" state hands off to the post-build action row
 *
 * Designed to feel like an OS process inspector — NOT a chat spinner.
 * Mobile-first: stacks cleanly under 640px, uses 44px+ touch targets.
 */
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Sparkles, Layers, CheckCircle2 } from "lucide-react";

const PHASE_ICON = {
  default: Activity,
  "Inferring foundation": Layers,
  "Foundation loaded": Sparkles,
  "Planning app structure": Sparkles,
  "Editing files": Activity,
  "Validating output": CheckCircle2,
  "Finalizing": CheckCircle2,
};

function phaseIcon(label) {
  if (!label) return Activity;
  for (const key of Object.keys(PHASE_ICON)) {
    if (label.startsWith(key)) return PHASE_ICON[key];
  }
  return Activity;
}

export function OrchestrationOverlay({ phase, inference, scaffoldFiles = [] }) {
  const Icon = phaseIcon(phase);
  return (
    <div
      className="rounded-2xl border border-white/8 overflow-hidden"
      style={{
        background: "linear-gradient(180deg, rgba(48,48,56,0.45) 0%, rgba(36,36,40,0.55) 100%)",
        backdropFilter: "blur(18px) saturate(140%)",
        WebkitBackdropFilter: "blur(18px) saturate(140%)",
      }}
      data-testid="orchestration-overlay"
    >
      <div className="flex items-center gap-3 px-3.5 py-3 border-b border-white/5">
        <motion.span
          className="h-7 w-7 rounded-full flex items-center justify-center"
          style={{
            background: "rgba(94, 234, 212, 0.12)",
            border: "1px solid rgba(94, 234, 212, 0.35)",
          }}
          animate={{ scale: [1, 1.08, 1] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
        >
          <Icon size={13} className="text-[#5EEAD4]" />
        </motion.span>
        <div className="flex-1 min-w-0">
          <div className="mono text-[9.5px] tracking-[0.28em] uppercase text-white/40">
            NXT1 · ORCHESTRATING
          </div>
          <div className="text-[13.5px] text-white font-medium truncate">
            {phase || "Preparing build…"}
          </div>
        </div>
      </div>

      <AnimatePresence>
        {inference && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="px-3.5 py-3 border-b border-white/5"
            data-testid="orchestration-inference"
          >
            <div className="flex items-start gap-2.5">
              <Layers size={13} className="text-[#5EEAD4] mt-0.5 shrink-0" />
              <div className="min-w-0">
                <div className="text-[12.5px] text-white">
                  Foundation —{" "}
                  <span className="text-[#5EEAD4] font-medium">
                    {inference.framework}
                  </span>
                </div>
                <div className="text-[11.5px] text-white/45 mt-0.5 leading-relaxed">
                  {inference.rationale}
                </div>
                <div className="flex items-center gap-1.5 mt-1.5">
                  <span className="mono text-[10px] tracking-[0.18em] uppercase text-white/35">
                    confidence
                  </span>
                  <div className="flex-1 max-w-[110px] h-1 rounded-full bg-white/8 overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.round((inference.confidence || 0) * 100)}%` }}
                      transition={{ duration: 0.6, ease: "easeOut" }}
                      className="h-full bg-[#5EEAD4]"
                    />
                  </div>
                  <span className="mono text-[10px] text-white/55">
                    {Math.round((inference.confidence || 0) * 100)}%
                  </span>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {scaffoldFiles.length > 0 && (
        <div
          className="px-3.5 py-2.5 max-h-44 overflow-y-auto"
          data-testid="orchestration-scaffold-receipts"
        >
          <div className="mono text-[9.5px] tracking-[0.24em] uppercase text-white/35 mb-1.5">
            Loading foundation files
          </div>
          <ul className="space-y-1">
            <AnimatePresence initial={false}>
              {scaffoldFiles.map((p, i) => (
                <motion.li
                  key={p + i}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.18, delay: Math.min(0.04 * i, 0.6) }}
                  className="flex items-center gap-2 text-[12px] mono"
                >
                  <span className="text-[#5EEAD4]">+</span>
                  <span className="text-zinc-300 truncate">{p}</span>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        </div>
      )}
    </div>
  );
}

export default OrchestrationOverlay;
