/**
 * NXT1 — ThemeSwitcher
 *
 * Compact icon button that toggles dark ↔ light. Drop it anywhere.
 * Mobile-first: 40px target.
 */
import { Sun, Moon } from "lucide-react";
import { useTheme } from "./ThemeProvider";

export default function ThemeSwitcher({ size = 14, className = "" }) {
  const { theme, toggle } = useTheme();
  const isLight = theme === "light";
  return (
    <button
      type="button"
      onClick={toggle}
      className={`inline-flex items-center justify-center h-10 w-10 rounded-full transition ${className}`}
      style={{
        background: "var(--nxt-chip-bg)",
        border: "1px solid var(--nxt-border-soft)",
        color: "var(--nxt-fg-dim)",
      }}
      aria-label={isLight ? "Switch to dark mode" : "Switch to light mode"}
      title={isLight ? "Switch to dark mode" : "Switch to light mode"}
      data-testid="theme-switcher"
    >
      {isLight ? <Moon size={size} /> : <Sun size={size} />}
    </button>
  );
}
