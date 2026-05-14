/**
 * ProtocolModeChip — minimalist composer footer pill.
 *
 * Lets a power-user pin the AI output protocol:
 *   • Auto  (default — server decides: tag for incremental, JSON for blank)
 *   • Tags  (always stream surgical actions — cheapest per edit)
 *   • JSON  (always re-emit the full file set — most reliable for blank builds)
 *
 * Design intent: invisible until needed.
 *   - When value === "auto" the chip renders as a 2px caret + thin label,
 *     hugging the model picker on the right.
 *   - When value !== "auto" the active label becomes the chip face so the
 *     user knows they've departed from defaults — without shouting.
 *   - Tan accent only on the dot when non-auto is set. No background fills,
 *     no gradients, no icons-with-strokes. Pure typographic minimalism.
 */
import { useEffect, useRef, useState } from "react";

const OPTIONS = [
  { value: "auto", label: "Auto",
    hint: "Smart default — tag protocol for incremental edits, JSON for blank-canvas builds." },
  { value: "tag",  label: "Tags",
    hint: "Force the streaming tag protocol. ~10–100× cheaper for surgical edits." },
  { value: "json", label: "JSON",
    hint: "Force the JSON-blob protocol. Most reliable for blank-canvas full builds." },
];

export default function ProtocolModeChip({ value, onChange, disabled }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const current = OPTIONS.find((o) => o.value === value) || OPTIONS[0];
  const isAuto = value === "auto";

  return (
    <div className="relative" ref={ref} data-testid="protocol-mode-chip">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        title={current.hint}
        data-testid="protocol-mode-trigger"
        className={[
          "group inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full",
          "text-[11px] tracking-[0.04em] uppercase select-none",
          "border transition-colors",
          isAuto
            ? "border-white/[0.06] text-white/40 hover:text-white/70 hover:border-white/10"
            : "border-[#C8B98C]/40 text-[#C8B98C] hover:border-[#C8B98C]/60",
          disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer",
        ].join(" ")}
      >
        <span
          className={[
            "h-1.5 w-1.5 rounded-full",
            isAuto ? "bg-white/30" : "bg-[#C8B98C]",
          ].join(" ")}
          aria-hidden
        />
        <span className="leading-none">{current.label}</span>
      </button>

      {open ? (
        <div
          role="menu"
          className={[
            "absolute right-0 bottom-full mb-2 w-56 z-30",
            "rounded-lg border border-white/[0.06]",
            "bg-[#16161A]/95 backdrop-blur-md",
            "shadow-[0_24px_60px_-20px_rgba(0,0,0,0.6)]",
            "p-1",
          ].join(" ")}
          data-testid="protocol-mode-menu"
        >
          <div className="px-2 pt-1.5 pb-1 text-[10px] tracking-[0.12em] uppercase text-white/30">
            Output protocol
          </div>
          {OPTIONS.map((o) => {
            const active = o.value === value;
            return (
              <button
                key={o.value}
                role="menuitemradio"
                aria-checked={active}
                type="button"
                onClick={() => { onChange(o.value); setOpen(false); }}
                data-testid={`protocol-mode-option-${o.value}`}
                className={[
                  "w-full text-left px-2.5 py-2 rounded-md",
                  "flex items-start gap-2 transition-colors",
                  active ? "bg-white/[0.04]" : "hover:bg-white/[0.03]",
                ].join(" ")}
              >
                <span
                  className={[
                    "mt-1 h-1.5 w-1.5 rounded-full shrink-0",
                    active ? "bg-[#C8B98C]" : "bg-white/15",
                  ].join(" ")}
                  aria-hidden
                />
                <span className="flex-1 min-w-0">
                  <span className="block text-[12.5px] text-white/85 leading-none mb-1">
                    {o.label}
                  </span>
                  <span className="block text-[11px] text-white/40 leading-snug">
                    {o.hint}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
