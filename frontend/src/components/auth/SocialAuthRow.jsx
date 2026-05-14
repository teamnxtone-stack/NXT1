/**\n * NXT1 \u2014 Social sign-in button row.\n *\n * Three premium tiles: Google (white), GitHub (graphite), Apple (graphite).\n * Each one calls `/api/oauth/{provider}/start?return=...&prompt=...`. The\n * backend either redirects to the real provider (if configured) or returns\n * a placeholder-safe JSON so we show a friendly toast.\n */
import { toast } from "sonner";
import { useEffect, useState } from "react";
import { API } from "@/lib/api";

function buildStartUrl(provider, ctx) {
  const params = new URLSearchParams();
  if (ctx?.returnTo) params.set("return", ctx.returnTo);
  if (ctx?.prompt) params.set("prompt", ctx.prompt);
  const qs = params.toString();
  return `${API}/oauth/${provider}/start${qs ? `?${qs}` : ""}`;
}

async function launchOAuth(provider, ctx) {
  // We need to check configuration BEFORE leaving the page. If the backend
  // says not_configured, surface that as a toast instead of redirecting.
  try {
    const r = await fetch(`${API}/oauth/status`);
    const status = await r.json();
    if (!status?.[provider]?.configured) {
      toast.message(`${provider.charAt(0).toUpperCase() + provider.slice(1)} sign-in coming online soon`, {
        description: `Add OAUTH_${provider.toUpperCase()}_CLIENT_ID / SECRET to enable.`,
      });
      return;
    }
    window.location.href = buildStartUrl(provider, ctx);
  } catch {
    toast.error("Couldn't reach OAuth backend.");
  }
}

export default function SocialAuthRow({ returnTo = "", prompt = "" }) {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/oauth/status`)
      .then((r) => r.json())
      .then((s) => { if (!cancelled) setStatus(s); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);
  const isReady = (p) => status?.[p]?.configured;
  const labelFor = (p) => (isReady(p) ? "" : " \u2022 soon");
  const ctx = { returnTo, prompt };

  return (
    <div className="space-y-2.5" data-testid="social-auth-row">
      {/* Google \u2014 primary, white tile */}
      <button
        type="button"
        onClick={() => launchOAuth("google", ctx)}
        className="w-full inline-flex items-center justify-center gap-3 h-12 rounded-2xl bg-white text-[#1F1F23] text-[14px] font-semibold tracking-tight hover:bg-white/95 transition-all shadow-[0_10px_28px_-10px_rgba(255,255,255,0.45)] hover:-translate-y-0.5"
        data-testid="social-google"
      >
        <svg width="16" height="16" viewBox="0 0 18 18" aria-hidden>
          <path d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
          <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.836.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>
          <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
          <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
        </svg>
        Continue with Google{labelFor("google")}
      </button>

      {/* GitHub \u2014 graphite tile, white logo */}
      <button
        type="button"
        onClick={() => launchOAuth("github", ctx)}
        className="w-full inline-flex items-center justify-center gap-3 h-12 rounded-2xl text-white text-[14px] font-semibold tracking-tight transition-all hover:-translate-y-0.5"
        style={{
          background: "linear-gradient(180deg, rgba(48,48,56,0.85) 0%, rgba(36,36,40,0.85) 100%)",
          border: "1px solid rgba(255,255,255,0.10)",
          boxShadow: "0 8px 24px -10px rgba(0,0,0,0.5)",
        }}
        data-testid="social-github"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M12 .297a12 12 0 00-3.793 23.39c.6.111.82-.26.82-.578v-2.234c-3.338.726-4.043-1.61-4.043-1.61-.547-1.387-1.336-1.756-1.336-1.756-1.09-.745.085-.73.085-.73 1.205.084 1.84 1.236 1.84 1.236 1.07 1.836 2.806 1.305 3.49.998.108-.775.42-1.305.762-1.605-2.665-.305-5.466-1.333-5.466-5.93 0-1.31.467-2.38 1.235-3.22-.123-.305-.535-1.523.118-3.175 0 0 1.005-.322 3.3 1.23a11.5 11.5 0 016 0c2.295-1.552 3.298-1.23 3.298-1.23.653 1.652.243 2.87.12 3.175.77.84 1.235 1.91 1.235 3.22 0 4.61-2.805 5.62-5.475 5.92.43.37.81 1.102.81 2.222v3.293c0 .322.22.694.825.576A12 12 0 0012 .297z"/>
        </svg>
        Continue with GitHub{labelFor("github")}
      </button>

      {/* Apple \u2014 graphite tile, white logo */}
      <button
        type="button"
        onClick={() => launchOAuth("apple", ctx)}
        className="w-full inline-flex items-center justify-center gap-3 h-12 rounded-2xl text-white text-[14px] font-semibold tracking-tight transition-all hover:-translate-y-0.5"
        style={{
          background: "linear-gradient(180deg, rgba(48,48,56,0.85) 0%, rgba(36,36,40,0.85) 100%)",
          border: "1px solid rgba(255,255,255,0.10)",
          boxShadow: "0 8px 24px -10px rgba(0,0,0,0.5)",
        }}
        data-testid="social-apple"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M17.05 12.04c-.03-3.04 2.49-4.5 2.6-4.57-1.41-2.07-3.62-2.35-4.41-2.38-1.88-.19-3.66 1.1-4.62 1.1-.95 0-2.42-1.07-3.98-1.04-2.05.03-3.94 1.19-4.99 3.02C-.5 12.06 1.1 17.2 3.1 20.04c.98 1.38 2.14 2.93 3.65 2.87 1.47-.06 2.02-.95 3.79-.95 1.78 0 2.27.95 3.82.92 1.58-.03 2.58-1.4 3.55-2.79 1.12-1.6 1.58-3.16 1.61-3.24-.04-.02-3.08-1.18-3.12-4.69-.02-2.94 2.4-4.34 2.51-4.41-1.37-2.03-3.51-2.25-4.27-2.28-.07.02-.04.02-.03.04zM14.45 3.79c.82-.99 1.37-2.36 1.22-3.73-1.18.05-2.6.78-3.45 1.77-.77.88-1.43 2.29-1.25 3.62 1.3.1 2.65-.66 3.48-1.66z"/>
        </svg>
        Continue with Apple{labelFor("apple")}
      </button>
    </div>
  );
}
