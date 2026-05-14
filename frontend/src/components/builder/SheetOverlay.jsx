/**
 * SheetOverlay — generic full-screen overlay used by the redesigned chat-first
 * builder for hosting "advanced" surfaces (Preview, Files, Overview, Runtime,
 * Env, DB, Domains, History, Deploy) without giving them permanent tab real-
 * estate. On mobile it slides up from the bottom (bottom-sheet pattern); on
 * desktop it slides in from the right (drawer pattern). Either way the chat
 * remains the always-on primary surface underneath.
 */
import { useEffect } from "react";
import { X } from "lucide-react";

export default function SheetOverlay({
  open,
  onClose,
  title,
  children,
  side = "auto", // "auto" | "right" | "bottom" — auto = bottom on mobile, right on desktop
  size = "lg", // "sm" | "md" | "lg" | "full"
  testId,
  rightAccessory,
}) {
  // Esc to close
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const widthMap = {
    sm: "lg:w-[440px]",
    md: "lg:w-[640px]",
    lg: "lg:w-[860px]",
    full: "lg:w-[100vw]",
  };
  const heightMap = {
    sm: "h-[55vh]",
    md: "h-[75vh]",
    lg: "h-[90vh]",
    full: "h-[100dvh]",
  };

  // Mobile = always full-screen for premium iOS feel. Desktop = drawer or
  // bottom sheet per `side`.
  const mobileFullCls =
    "left-0 right-0 top-0 bottom-0 h-[100dvh] w-full rounded-none nxt-slide-up";

  const layoutCls =
    side === "right"
      ? `${mobileFullCls} lg:left-auto lg:top-0 lg:bottom-0 lg:h-auto lg:w-auto ${widthMap[size]} lg:max-w-full lg:rounded-none lg:nxt-slide-in-right`
      : side === "bottom"
        ? `${mobileFullCls} lg:left-0 lg:right-0 lg:top-auto lg:bottom-0 lg:w-auto lg:${heightMap[size]} lg:rounded-t-xl`
        : // auto = full-screen on mobile, right-drawer on desktop
          `${mobileFullCls} lg:left-auto lg:top-0 lg:bottom-0 lg:h-auto lg:w-auto lg:rounded-none lg:nxt-slide-in-right ${widthMap[size]}`;

  return (
    <div
      className="fixed inset-0 z-50 bg-graphite-scrim backdrop-blur-sm"
      onClick={onClose}
      data-testid={testId ? `${testId}-overlay` : "sheet-overlay"}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        className={`absolute ${layoutCls} bg-[#1F1F23] lg:border lg:border-white/10 shadow-2xl flex flex-col nxt-safe-top`}
        data-testid={testId || "sheet"}
      >
        <header className="h-14 lg:h-12 shrink-0 flex items-center justify-between px-5 lg:px-4 border-b border-white/10">
          <div className="mono text-[11px] tracking-[0.28em] uppercase text-zinc-300 truncate">
            {title}
          </div>
          <div className="flex items-center gap-2">
            {rightAccessory}
            <button
              onClick={onClose}
              className="h-9 w-9 lg:h-8 lg:w-8 -mr-2 lg:mr-0 flex items-center justify-center rounded-full text-zinc-300 hover:text-white hover:bg-white/[0.06] transition"
              data-testid="sheet-close"
              aria-label="Close"
            >
              <X size={16} />
            </button>
          </div>
        </header>
        <div className="flex-1 min-h-0 overflow-hidden nxt-safe-bottom">{children}</div>
      </aside>
    </div>
  );
}
