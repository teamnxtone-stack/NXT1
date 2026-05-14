/**
 * NXT1 — Activity Stream
 *
 * Premium, Apple-grade orchestration feed used while the AI is building.
 * Newest event appears near bottom-center, older events drift upward with
 * fade + soft blur. Each step shows a tiny status dot (pending / active /
 * done) and an elegant label — no logs, no emojis, no terminal spam.
 *
 * Visual language:
 *   • graphite glass surface
 *   • type-led hierarchy (no harsh outlines)
 *   • subtle pulse on the active step
 *   • calm, controlled motion (220-260ms)
 *
 * Steps are deduplicated by id so the same backend phase doesn't spam.
 */
import React, { useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";

const MAX_VISIBLE = 7;          // older steps get popped off the top
const SPRING = { type: "spring", stiffness: 280, damping: 28 };

// Per-agent palette — distinct color identity so the user can SEE which AI
// is currently running. Calm, on-brand hues; never raw blues/reds.
const AGENT_PALETTE = {
  router:     { label: "Router",    color: "#A5B4FC", bg: "rgba(165,180,252,0.12)" },
  analyst:    { label: "Analyst",   color: "#5EEAD4", bg: "rgba(94,234,212,0.12)" },
  scaffold:   { label: "Scaffold",  color: "#FCD34D", bg: "rgba(252,211,77,0.12)" },
  architect:  { label: "Architect", color: "#C4B5FD", bg: "rgba(196,181,253,0.12)" },
  coder:      { label: "Coder",     color: "#86EFAC", bg: "rgba(134,239,172,0.12)" },
  integrator: { label: "Integrator",color: "#7DD3FC", bg: "rgba(125,211,252,0.12)" },
  tester:     { label: "Tester",    color: "#FCA5A5", bg: "rgba(252,165,165,0.14)" },
  debugger:   { label: "Debugger",  color: "#F9A8D4", bg: "rgba(249,168,212,0.14)" },
  preview:    { label: "Preview",   color: "#5EEAD4", bg: "rgba(94,234,212,0.12)" },
  devops:     { label: "DevOps",    color: "#FDBA74", bg: "rgba(253,186,116,0.14)" },
};

function AgentBadge({ agent }) {
  if (!agent) return null;
  const p = AGENT_PALETTE[agent] || AGENT_PALETTE.coder;
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full mono text-[9.5px] tracking-[0.18em] uppercase shrink-0"
      style={{
        background: p.bg,
        color: p.color,
        border: `1px solid ${p.color}33`,
      }}
      data-testid={`agent-badge-${agent}`}
    >
      <span
        className="h-1 w-1 rounded-full"
        style={{ background: p.color }}
      />
      {p.label}
    </span>
  );
}

export function ActivityStream({ steps = [] }) {
  // Keep only the most recent N visible steps. Earlier ones already faded.
  const visible = useMemo(() => steps.slice(-MAX_VISIBLE), [steps]);
  if (!visible.length) return null;

  // The active step is the last non-"done" one. If all are done, the very
  // last step is treated as active (so the final "Ready to preview" line
  // gets its glow before fading out).
  const activeIdx = (() => {
    for (let i = visible.length - 1; i >= 0; i--) {
      if (visible[i].state !== "done") return i;
    }
    return visible.length - 1;
  })();

  return (
    <div
      className="relative w-full"
      style={{ minHeight: 220 }}
      data-testid="activity-stream"
      aria-live="polite"
    >
      {/* Top fade scrim — older steps melt away cinematically. */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-16 z-10"
        style={{
          background:
            "linear-gradient(180deg, rgba(31,31,35,0.96) 0%, rgba(31,31,35,0) 100%)",
        }}
        aria-hidden
      />

      <ol
        className="flex flex-col items-stretch gap-1.5 pt-1 pb-1"
        // Bottom-anchored stack so newest is always near the composer.
        style={{ display: "flex", flexDirection: "column", justifyContent: "flex-end" }}
      >
        <AnimatePresence initial={false} mode="popLayout">
          {visible.map((s, i) => {
            const distanceFromActive = activeIdx - i;
            // The deeper the step is in the history (large distanceFromActive),
            // the more we fade + soften it. 0 = current, 1–7+ = aging out.
            const opacity = Math.max(0.18, 1 - distanceFromActive * 0.16);
            const blur = Math.min(2.4, distanceFromActive * 0.55);
            const translateY = Math.min(4, distanceFromActive * 1.4);
            const isActive = i === activeIdx && s.state !== "done";
            const palette = AGENT_PALETTE[s.agent] || null;
            const activeColor = palette?.color || "rgba(94,234,212,1)";
            return (
              <motion.li
                key={s.id}
                layout
                initial={{ opacity: 0, y: 14, filter: "blur(4px)" }}
                animate={{
                  opacity,
                  y: translateY,
                  filter: blur > 0.1 ? `blur(${blur}px)` : "blur(0px)",
                }}
                exit={{ opacity: 0, y: -10, filter: "blur(4px)" }}
                transition={SPRING}
                className="flex items-center gap-3 px-3.5 py-2 rounded-xl"
                style={{
                  background: isActive
                    ? "linear-gradient(180deg, rgba(48,48,56,0.55) 0%, rgba(36,36,40,0.55) 100%)"
                    : "transparent",
                  border: isActive
                    ? `1px solid ${activeColor}30`
                    : "1px solid transparent",
                  boxShadow: isActive
                    ? `0 12px 32px -16px ${activeColor}30, inset 0 1px 0 rgba(255,255,255,0.03)`
                    : "none",
                  backdropFilter: isActive ? "blur(14px) saturate(140%)" : undefined,
                  WebkitBackdropFilter: isActive ? "blur(14px) saturate(140%)" : undefined,
                }}
                data-testid={`activity-step-${s.id}`}
                data-state={s.state}
              >
                <StatusDot state={s.state} color={palette?.color} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="text-[13.5px] leading-tight truncate"
                      style={{
                        color: isActive ? "rgba(255,255,255,0.96)" : "rgba(255,255,255,0.72)",
                        fontWeight: isActive ? 500 : 400,
                        letterSpacing: "-0.005em",
                      }}
                    >
                      {s.label}
                    </span>
                    {isActive && <AgentBadge agent={s.agent} />}
                  </div>
                  {s.detail ? (
                    <div
                      className="text-[11.5px] mono mt-0.5 truncate"
                      style={{ color: "rgba(255,255,255,0.4)", letterSpacing: "0.01em" }}
                    >
                      {s.detail}
                    </div>
                  ) : null}
                </div>
                {s.note ? (
                  <span
                    className="mono text-[10px] tracking-[0.18em] uppercase shrink-0"
                    style={{ color: "rgba(94,234,212,0.7)" }}
                  >
                    {s.note}
                  </span>
                ) : null}
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ol>
    </div>
  );
}

function StatusDot({ state, color }) {
  const active = color || "rgba(94,234,212,1)";
  // Compose translucent variants so the soft halo always matches the active hue
  const halo = active.startsWith("#")
    ? `${active}59` // ~35% alpha
    : active.replace(/[\d.]+\)$/, "0.35)");
  const glow = active.startsWith("#")
    ? `${active}1f`
    : active.replace(/[\d.]+\)$/, "0.08)");
  if (state === "done") {
    return (
      <span
        className="relative h-2 w-2 shrink-0 rounded-full"
        style={{
          background: active.startsWith("#") ? `${active}d9` : active.replace(/[\d.]+\)$/, "0.85)"),
          boxShadow: `0 0 0 3px ${glow}`,
        }}
        aria-hidden
      />
    );
  }
  if (state === "active") {
    return (
      <span className="relative inline-flex h-2 w-2 shrink-0" aria-hidden>
        <motion.span
          className="absolute inset-0 rounded-full"
          style={{ background: halo }}
          animate={{ scale: [1, 2.2, 1], opacity: [0.55, 0, 0.55] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
        />
        <span
          className="absolute inset-0 rounded-full"
          style={{ background: active.startsWith("#") ? `${active}e6` : active }}
        />
      </span>
    );
  }
  // pending
  return (
    <span
      className="h-2 w-2 shrink-0 rounded-full"
      style={{
        background: "rgba(255,255,255,0.12)",
        boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.08)",
      }}
      aria-hidden
    />
  );
}

export default ActivityStream;
