/**
 * NXT1 — DeviceFrame
 *
 * Premium device shells for the preview panel. Wraps any iframe in a
 * realistic phone / tablet / desktop browser chrome. Built to feel like
 * looking at a real device, not a generic resize.
 *
 * Design language:
 *   • Graphite shells (no pure black)
 *   • Subtle inner shadow + outer glow
 *   • Dynamic island on phone
 *   • Browser chrome with traffic-light buttons on desktop
 *   • Springy transitions
 *
 * Usage:
 *   <DeviceFrame variant="mobile" url="index.html">
 *     <iframe ... />
 *   </DeviceFrame>
 */
import { motion } from "framer-motion";
import React from "react";

const FRAMES = {
  desktop: {
    width: "100%",
    height: "100%",
    radius: 12,
    chrome: "browser",
  },
  tablet: {
    width: 880,
    height: 1180,
    radius: 22,
    chrome: "none",
  },
  mobile: {
    width: 390,
    height: 844,
    radius: 44,
    chrome: "island",
  },
};

export function DeviceFrame({ variant = "desktop", url = "", children }) {
  const cfg = FRAMES[variant] || FRAMES.desktop;
  const isFull = cfg.width === "100%";

  return (
    <motion.div
      layout
      transition={{ type: "spring", stiffness: 320, damping: 32 }}
      className="mx-auto relative"
      style={{
        width: isFull ? "100%" : `${cfg.width}px`,
        height: isFull ? "100%" : `${cfg.height}px`,
        maxWidth: "100%",
        borderRadius: cfg.radius,
        overflow: "hidden",
        background: "#1F1F23",
        border: variant === "desktop" ? "1px solid rgba(255,255,255,0.08)" : "1px solid rgba(255,255,255,0.12)",
        boxShadow:
          variant === "desktop"
            ? "0 16px 36px -16px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.04)"
            : variant === "mobile"
            ? "0 28px 60px -18px rgba(0,0,0,0.65), 0 6px 18px -10px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.05)"
            : "0 22px 50px -18px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.04)",
      }}
      data-testid={`device-frame-${variant}`}
    >
      {cfg.chrome === "browser" && <BrowserChrome url={url} />}
      {cfg.chrome === "island" && <PhoneIsland />}

      <div
        className="absolute inset-0"
        style={{
          top: cfg.chrome === "browser" ? 36 : 0,
          background: "#fff",
        }}
      >
        {children}
      </div>

      {cfg.chrome === "island" && <PhoneHomeIndicator />}
    </motion.div>
  );
}

/* ---------- Chrome bits ---------- */
function BrowserChrome({ url }) {
  return (
    <div
      className="absolute top-0 left-0 right-0 z-10 flex items-center gap-2 px-3"
      style={{
        height: 36,
        background: "linear-gradient(180deg, #303038 0%, #2A2A2F 100%)",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <span className="flex gap-1.5" aria-hidden>
        <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
      </span>
      <div
        className="flex-1 mx-2 px-3 h-6 rounded-md flex items-center text-[11px] mono text-zinc-400 truncate"
        style={{
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 mr-2 shrink-0" />
        <span className="truncate">{url || "localhost / preview"}</span>
      </div>
    </div>
  );
}

function PhoneIsland() {
  return (
    <div
      className="absolute z-20 left-1/2 -translate-x-1/2"
      style={{
        top: 10,
        width: 110,
        height: 28,
        borderRadius: 18,
        background: "#1F1F23",
        boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.06), 0 3px 8px rgba(0,0,0,0.45)",
      }}
      aria-hidden
    />
  );
}

function PhoneHomeIndicator() {
  return (
    <div
      className="absolute z-20 left-1/2 -translate-x-1/2"
      style={{
        bottom: 8,
        width: 130,
        height: 5,
        borderRadius: 999,
        background: "rgba(255,255,255,0.85)",
      }}
      aria-hidden
    />
  );
}

export default DeviceFrame;
