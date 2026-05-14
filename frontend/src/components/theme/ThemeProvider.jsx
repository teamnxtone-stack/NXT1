/**
 * NXT1 — ThemeProvider
 *
 * Global theme with two modes:
 *   - dark: Carbon Graphite (default)
 *   - light: warm off-white / tan / cream tones
 *
 * Both apply via CSS variables on the <html> element. Switching is instant
 * and motion-free per Apple's HIG guidance. Persists to localStorage.
 *
 * Consumed via the `useTheme()` hook.
 */
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

const ThemeCtx = createContext({ theme: "dark", setTheme: () => {} });

export function useTheme() {
  return useContext(ThemeCtx);
}

function readInitial() {
  try {
    const stored = window.localStorage.getItem("nxt1_theme");
    if (stored === "light" || stored === "dark") return stored;
  } catch { /* ignore */ }
  return "dark";
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => (typeof window === "undefined" ? "dark" : readInitial()));

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.dataset.theme = theme;
    try { window.localStorage.setItem("nxt1_theme", theme); } catch { /* ignore */ }
  }, [theme]);

  const value = useMemo(() => ({
    theme,
    setTheme: (t) => setThemeState(t === "light" ? "light" : "dark"),
    toggle: () => setThemeState((t) => (t === "light" ? "dark" : "light")),
  }), [theme]);

  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export default ThemeProvider;
