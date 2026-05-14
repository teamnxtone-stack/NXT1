/**
 * BuildTimeline — cinematic vertical timeline for a completed build.
 *
 * Rendered beneath an assistant message bubble when the persisted message
 * carries a `timeline:[{phase, at, ms_since_start}, …]` array. Stays calm
 * by default (one line of mono text, no chrome) and reveals the full
 * per-phase strip on tap/click.
 *
 * Design:
 *   - Minimalist: thin 1px tan rail with circular dot markers at each phase.
 *   - Mobile-first: full width, generous tap-target (h-8 row).
 *   - No icons. Just label + ms.
 *   - Tan accent only on the active/final dot; the rest are zinc.
 */
import { useState } from "react";

const fmt = (ms) => {
  if (ms == null) return "";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}m ${s % 60}s`;
};

export default function BuildTimeline({ timeline, validation, protocolUsed }) {
  const [open, setOpen] = useState(false);
  if (!Array.isArray(timeline) || timeline.length === 0) return null;

  const total = timeline[timeline.length - 1]?.ms_since_start ?? 0;
  const errs = validation?.error_count ?? 0;
  const warns = validation?.warn_count ?? 0;
  const repaired = (timeline || []).some(
    (p) => (p.phase || "").toLowerCase().includes("self-healing"),
  );

  return (
    <div
      className="mt-1.5 -mx-0.5"
      data-testid="build-timeline"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={[
          "group inline-flex items-center gap-1.5",
          "h-7 px-2 -ml-2 rounded-md",
          "text-[10.5px] tracking-[0.08em] uppercase",
          "text-white/35 hover:text-white/65 transition-colors",
        ].join(" ")}
        aria-expanded={open}
        data-testid="build-timeline-trigger"
      >
        <span className="h-1 w-1 rounded-full bg-[#C8B98C]/70" aria-hidden />
        <span>
          {timeline.length} step{timeline.length === 1 ? "" : "s"}
          {total > 0 ? ` · ${fmt(total)}` : ""}
          {protocolUsed ? ` · ${protocolUsed}` : ""}
          {repaired ? " · self-healed" : ""}
          {errs > 0 ? ` · ${errs} err` : ""}
          {warns > 0 ? ` · ${warns} warn` : ""}
        </span>
        <span
          className={[
            "h-[1px] w-3 transition-all",
            open ? "bg-[#C8B98C]/70" : "bg-white/15 group-hover:bg-white/30",
          ].join(" ")}
          aria-hidden
        />
      </button>

      {open ? (
        <div
          className="mt-2 pl-3 relative"
          data-testid="build-timeline-panel"
        >
          {/* Vertical rail */}
          <span
            className="absolute left-1 top-1.5 bottom-1.5 w-[1px] bg-white/10"
            aria-hidden
          />
          <ul className="space-y-1.5">
            {timeline.map((t, i) => {
              const last = i === timeline.length - 1;
              return (
                <li
                  key={`${t.phase}-${t.at || i}`}
                  className="relative flex items-center gap-2"
                >
                  <span
                    className={[
                      "absolute -left-[10px] top-1/2 -translate-y-1/2",
                      "h-1.5 w-1.5 rounded-full",
                      last ? "bg-[#C8B98C]" : "bg-white/30",
                    ].join(" ")}
                    aria-hidden
                  />
                  <span className="flex-1 min-w-0 text-[12px] text-white/70 truncate">
                    {t.phase}
                  </span>
                  <span className="text-[10.5px] mono text-white/30">
                    {fmt(t.ms_since_start)}
                  </span>
                </li>
              );
            })}
          </ul>
          {/* Validation footer (if any issues) */}
          {validation && (errs > 0 || warns > 0) ? (
            <div className="mt-2 pl-0 text-[11px] text-white/45">
              <span className="mono uppercase tracking-[0.08em] text-[10px] text-white/30">
                validation
              </span>{" "}
              · {errs} error{errs === 1 ? "" : "s"}, {warns} warning
              {warns === 1 ? "" : "s"}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
