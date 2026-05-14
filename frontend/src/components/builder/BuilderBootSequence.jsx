/**
 * BuilderBootSequence — cinematic loading sequence when opening an app.
 *
 * Replaces the previously stagnant blank chat surface with a streaming
 * activity feed: each step reveals as the real backend calls progress.
 * If the backend is fast, the sequence still plays a brief paced animation
 * so the user sees what NXT1 is doing — never a frozen empty screen.
 *
 * Visible steps (paced over ~1.2s minimum):
 *   1. Connecting to project
 *   2. Reading N files
 *   3. Detecting framework
 *   4. Mounting preview surface
 *   5. Ready
 *
 * Props:
 *   project   — the project payload (null while loading)
 *   files     — files array (length used for "Reading N files" step)
 *   onReady   — optional callback fired when sequence completes
 */
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, CheckCircle2, FileCode2, Cpu, Sparkles, Layers } from "lucide-react";

const STEPS = [
  { key: "connect",    label: "Connecting to project",  icon: Cpu,        minDelay: 220 },
  { key: "files",      label: "Reading files",          icon: FileCode2,  minDelay: 320 },
  { key: "framework",  label: "Detecting framework",    icon: Layers,     minDelay: 280 },
  { key: "preview",    label: "Mounting preview",       icon: Sparkles,   minDelay: 240 },
];

export default function BuilderBootSequence({ project, files, onReady }) {
  const [stepIdx, setStepIdx] = useState(0);
  const [done, setDone] = useState(false);

  // Drive the sequence forward. We respect minimum per-step delays so even a
  // fast backend feels cinematic; if the backend hasn't returned the project
  // by the time we reach the last step, we wait on it.
  useEffect(() => {
    let cancelled = false;
    let timer;
    const advance = () => {
      if (cancelled) return;
      setStepIdx((i) => {
        const next = i + 1;
        if (next >= STEPS.length) {
          // Wait for the project to actually exist before showing "Ready".
          const waitForProject = () => {
            if (cancelled) return;
            if (project) {
              setDone(true);
              onReady?.();
            } else {
              timer = setTimeout(waitForProject, 120);
            }
          };
          waitForProject();
          return STEPS.length;
        }
        timer = setTimeout(advance, STEPS[next].minDelay);
        return next;
      });
    };
    timer = setTimeout(advance, STEPS[0].minDelay);
    return () => { cancelled = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  // Once done, fade the whole sequence out
  if (done) return null;

  const filesCount = (files || []).length;
  const framework = project?.framework || project?.analysis?.framework || "auto";

  return (
    <div
      className="absolute inset-0 z-20 flex items-center justify-center px-6"
      style={{
        background: "var(--surface-0)",
        backdropFilter: "blur(4px)",
      }}
      data-testid="builder-boot-sequence"
    >
      <div className="w-full max-w-[440px]">
        <div className="mb-6 flex items-center gap-2">
          <span
            className="mono text-[10px] tracking-[0.28em] uppercase"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            // opening project
          </span>
          <span className="h-px flex-1" style={{ background: "var(--hairline)" }} />
          <span
            className="mono text-[10px] tracking-[0.22em] uppercase"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            session
          </span>
        </div>
        <h2
          className="text-[22px] sm:text-[26px] font-semibold tracking-tight leading-tight mb-1"
          style={{ color: "var(--nxt-fg)", fontFamily: "'Cabinet Grotesk', sans-serif" }}
        >
          {project?.name || "Loading project"}
        </h2>
        <p
          className="text-[13px] leading-relaxed mb-7"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          Spinning up the workspace, reading files, and warming the preview.
        </p>

        <ol className="space-y-2.5">
          {STEPS.map((s, i) => {
            const state = i < stepIdx ? "done" : i === stepIdx ? "running" : "pending";
            const Icon = s.icon;
            const detail =
              s.key === "files" && state !== "pending"
                ? filesCount > 0
                  ? `${filesCount} file${filesCount === 1 ? "" : "s"}`
                  : "scanning…"
                : s.key === "framework" && state !== "pending"
                  ? framework
                  : null;
            return (
              <motion.li
                key={s.key}
                initial={{ opacity: 0, x: -8 }}
                animate={{
                  opacity: state === "pending" ? 0.35 : 1,
                  x: 0,
                }}
                transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                className="flex items-center gap-3 text-[13.5px]"
                data-testid={`boot-step-${s.key}`}
              >
                <span
                  className="h-7 w-7 rounded-full flex items-center justify-center shrink-0"
                  style={{
                    background: state === "done"
                      ? "rgba(20, 130, 110, 0.16)"
                      : state === "running"
                        ? "var(--nxt-chip-bg)"
                        : "transparent",
                    border: `1px solid ${
                      state === "done"
                        ? "rgba(20, 130, 110, 0.4)"
                        : state === "running"
                          ? "var(--nxt-border)"
                          : "var(--hairline)"
                    }`,
                  }}
                >
                  {state === "done" ? (
                    <CheckCircle2 size={13} style={{ color: "var(--nxt-accent)" }} />
                  ) : state === "running" ? (
                    <Loader2 size={12} className="animate-spin" style={{ color: "var(--nxt-fg-dim)" }} />
                  ) : (
                    <Icon size={12} style={{ color: "var(--nxt-fg-faint)" }} />
                  )}
                </span>
                <span
                  className="flex-1"
                  style={{
                    color: state === "pending" ? "var(--nxt-fg-faint)" : "var(--nxt-fg)",
                  }}
                >
                  {s.label}
                  {state === "running" && <span className="nxt-cursor"> </span>}
                </span>
                <AnimatePresence>
                  {detail && (
                    <motion.span
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="mono text-[11px] tracking-wide"
                      style={{ color: "var(--nxt-fg-faint)" }}
                    >
                      {detail}
                    </motion.span>
                  )}
                </AnimatePresence>
              </motion.li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
