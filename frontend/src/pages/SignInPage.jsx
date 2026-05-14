/**
 * NXT1 sign-in — minimalist redo (2026-05-13)
 *
 * Theme-aware: pure dark `#0B0B0C` in dark mode, tan/cream surface in light
 * mode. No glass-card chrome, no gradient backdrop, no public footer —
 * matches the new `/access` style.
 *
 * Keeps every prior capability: ?prompt= persistence, ?return= routing,
 * social row (Google · GitHub · Apple via SocialAuthRow), OAuth callback.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import Brand from "@/components/Brand";
import SocialAuthRow from "@/components/auth/SocialAuthRow";
import OAuthCallbackInterceptor from "@/components/auth/OAuthCallback";
import { useTheme } from "@/components/theme/ThemeProvider";
import { userSignin } from "@/lib/api";
import { setToken } from "@/lib/auth";

export default function SignInPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [form, setForm] = useState({ email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);
  const { theme } = useTheme();
  const isLight = theme === "light";
  const promptParam = params.get("prompt") || "";
  const returnTo = params.get("return") || "";

  useEffect(() => {
    if (promptParam) {
      try { window.localStorage.setItem("nxt1_draft_prompt", promptParam); }
      catch { /* ignore */ }
    }
  }, [promptParam]);

  const buildReturnUrl = (user) => {
    if (returnTo) {
      const draft = (() => {
        try { return window.localStorage.getItem("nxt1_draft_prompt") || ""; }
        catch { return ""; }
      })();
      if (draft && !returnTo.includes("?")) {
        return `${returnTo}?prompt=${encodeURIComponent(draft)}`;
      }
      return returnTo;
    }
    return user?.onboarded ? "/workspace" : "/onboarding";
  };

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { data } = await userSignin(form);
      setToken(data.token);
      toast.success(`Welcome back, ${data.user.name || data.user.email}.`);
      navigate(buildReturnUrl(data.user));
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Sign in failed");
    } finally {
      setSubmitting(false);
    }
  };

  const signupHref = `/signup${
    promptParam
      ? `?prompt=${encodeURIComponent(promptParam)}${returnTo ? `&return=${encodeURIComponent(returnTo)}` : ""}`
      : ""
  }`;

  return (
    <OAuthCallbackInterceptor>
      <div
        className="relative min-h-screen w-full flex flex-col items-center justify-center px-6"
        style={{
          background: isLight ? "#F4EFE3" : "#0B0B0C",
          color: "var(--nxt-fg)",
          fontFamily: "'IBM Plex Sans', sans-serif",
        }}
        data-testid="signin-page"
      >
        {/* Tiny brand top-left */}
        <Link
          to="/"
          className="absolute top-6 left-6 opacity-80 hover:opacity-100 transition-opacity"
          aria-label="Back to home"
          data-testid="signin-back"
        >
          <Brand size="sm" gradient />
        </Link>

        {/* Top-right: Sign up */}
        <Link
          to={signupHref}
          className="absolute top-6 right-6 mono text-[11px] tracking-[0.28em] uppercase transition-colors"
          style={{ color: "var(--nxt-fg-dim)" }}
          data-testid="link-to-signup"
        >
          Request access
        </Link>

        <div className="w-full max-w-[360px] flex flex-col gap-5" data-testid="signin-card">
          {/* Overline */}
          <div className="text-center">
            <span
              className="mono text-[10.5px] tracking-[0.32em] uppercase font-medium"
              style={{ color: "var(--nxt-fg-faint)" }}
            >
              Sign in
            </span>
          </div>

          {/* Headline */}
          <h1
            className="text-[26px] sm:text-[30px] leading-[1.05] font-medium tracking-[-0.02em] text-center"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif", color: "var(--nxt-fg)" }}
          >
            Welcome back.
          </h1>

          {/* Social row */}
          <SocialAuthRow returnTo={returnTo || "/workspace"} prompt={promptParam} />

          {/* Divider */}
          <div className="flex items-center gap-3">
            <div
              className="h-px flex-1"
              style={{ background: "var(--nxt-border-soft)" }}
            />
            <span
              className="mono text-[9.5px] tracking-[0.28em] uppercase"
              style={{ color: "var(--nxt-fg-faint)" }}
            >
              or
            </span>
            <div
              className="h-px flex-1"
              style={{ background: "var(--nxt-border-soft)" }}
            />
          </div>

          {/* Email + password */}
          <form onSubmit={submit} className="flex flex-col gap-3">
            <input
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="you@company.com"
              autoComplete="email"
              className="w-full h-12 rounded-xl px-4 text-[14px] transition-colors"
              style={{
                background: "transparent",
                border: `1px solid ${isLight ? "rgba(31,31,35,0.18)" : "rgba(255,255,255,0.10)"}`,
                color: "var(--nxt-fg)",
              }}
              data-testid="signin-email-input"
            />
            <input
              type="password"
              required
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="Password"
              autoComplete="current-password"
              className="w-full h-12 rounded-xl px-4 text-[14px] transition-colors"
              style={{
                background: "transparent",
                border: `1px solid ${isLight ? "rgba(31,31,35,0.18)" : "rgba(255,255,255,0.10)"}`,
                color: "var(--nxt-fg)",
              }}
              data-testid="signin-password-input"
            />
            <button
              type="submit"
              disabled={submitting || !form.email || !form.password}
              className="w-full inline-flex items-center justify-center gap-2 h-12 rounded-xl text-[14px] font-medium tracking-tight transition-all disabled:opacity-30 disabled:cursor-not-allowed active:scale-[0.99]"
              style={{
                background: isLight ? "#1F1F23" : "#FFFFFF",
                color: isLight ? "#FAFAFA" : "#0B0B0C",
              }}
              data-testid="signin-submit-button"
            >
              {submitting ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <>
                  Sign in
                  <ArrowRight size={13} strokeWidth={2.2} />
                </>
              )}
            </button>
          </form>

          {/* Footer */}
          <p
            className="text-center text-[12.5px]"
            style={{ color: "var(--nxt-fg-dim)" }}
          >
            New here?{" "}
            <Link
              to={signupHref}
              className="font-medium transition-colors"
              style={{ color: "var(--nxt-fg)" }}
              data-testid="signin-go-to-signup"
            >
              Request access
            </Link>
          </p>
        </div>
      </div>
    </OAuthCallbackInterceptor>
  );
}
