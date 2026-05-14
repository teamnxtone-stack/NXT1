/**
 * NXT1 brand wordmark.
 *
 * Renders as a colorful gradient on dark mode (cyan→amber→orange) and as
 * a deeper, higher-contrast gradient on light mode so the wordmark stays
 * readable on warm cream surfaces. The plain (non-gradient) variant uses
 * the active theme's foreground token.
 */
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

function useThemeAttr() {
  const [theme, setTheme] = useState(() => {
    if (typeof document === "undefined") return "dark";
    return document.documentElement.dataset.theme || "dark";
  });
  useEffect(() => {
    if (typeof MutationObserver === "undefined") return;
    const obs = new MutationObserver(() => {
      setTheme(document.documentElement.dataset.theme || "dark");
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return theme;
}

export default function Brand({ size = "md", gradient = false, className = "" }) {
  const theme = useThemeAttr();
  const isLight = theme === "light";

  const sizes = {
    sm: "text-[15px]",
    md: "text-xl",
    lg: "text-3xl",
    xl: "text-5xl sm:text-6xl",
    xxl: "text-6xl sm:text-7xl lg:text-8xl",
  };

  // Light-mode gradient uses richer, deeper hues so the wordmark stays
  // readable against warm cream backgrounds (the dark-mode pastel
  // teal→amber wash gets washed out on cream).
  const gradientImage = isLight
    ? "linear-gradient(110deg, #0E8C73 0%, #B58320 50%, #C25A1F 100%)"
    : "linear-gradient(110deg, #5EEAD4 0%, #f0d28a 50%, #ff8a3d 100%)";

  return (
    <span
      data-testid="brand-wordmark"
      className={cn(
        "inline-block font-black tracking-tighter leading-none select-none",
        sizes[size] || sizes.md,
        gradient && "bg-clip-text text-transparent",
        className
      )}
      style={{
        fontFamily: "'Cabinet Grotesk', sans-serif",
        ...(gradient
          ? { backgroundImage: gradientImage }
          : { color: "var(--nxt-fg)" }),
        // Subtle text shadow in light mode to add weight on cream surfaces.
        ...(isLight && gradient
          ? { textShadow: "0 1px 0 rgba(255,255,255,0.4)" }
          : {}),
      }}
    >
      NXT<span className="ml-[2px]">1</span>
    </span>
  );
}
