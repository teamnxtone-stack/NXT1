/**
 * NXT1 — ThemedToaster
 *
 * A Sonner Toaster that follows the global NXT1 theme (dark graphite ↔
 * warm cream). Forces a single graphite/cream surface style across every
 * toast type (success / error / info / warning) so we never get a jarring
 * white bubble on dark mode or a graphite bubble on light mode.
 */
import { Toaster } from "sonner";
import { useTheme } from "@/components/theme/ThemeProvider";

export default function ThemedToaster() {
  const { theme } = useTheme();
  const isLight = theme === "light";

  const surface = isLight
    ? "#FBF8EF"                       // warm off-white cream
    : "#1F1F23";                      // recessed graphite

  const border = isLight
    ? "rgba(26, 26, 31, 0.14)"
    : "rgba(255, 255, 255, 0.08)";

  const fg = isLight ? "#1A1A1F" : "#FAFAFA";
  const fgDim = isLight ? "rgba(26,26,31,0.65)" : "rgba(255,255,255,0.65)";

  return (
    <Toaster
      theme={isLight ? "light" : "dark"}
      position="bottom-right"
      richColors={false}
      toastOptions={{
        unstyled: false,
        style: {
          background: surface,
          border: `1px solid ${border}`,
          color: fg,
          borderRadius: "14px",
          fontFamily: "'IBM Plex Sans', 'Inter', sans-serif",
          boxShadow: isLight
            ? "0 18px 40px -18px rgba(60, 50, 30, 0.30)"
            : "0 18px 40px -18px rgba(0, 0, 0, 0.55)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
        },
        classNames: {
          description: "nxt-toast-desc",
        },
        descriptionClassName: "nxt-toast-desc",
      }}
      style={{
        // CSS-vars Sonner reads internally so success/error variants
        // also inherit our surface instead of defaulting to white/red bgs.
        "--normal-bg": surface,
        "--normal-text": fg,
        "--normal-border": border,
        "--success-bg": surface,
        "--success-text": fg,
        "--success-border": border,
        "--error-bg": surface,
        "--error-text": fg,
        "--error-border": border,
        "--info-bg": surface,
        "--info-text": fg,
        "--info-border": border,
        "--warning-bg": surface,
        "--warning-text": fg,
        "--warning-border": border,
        // dim helpers
        "--gray12": fg,
        "--gray11": fgDim,
      }}
    />
  );
}
