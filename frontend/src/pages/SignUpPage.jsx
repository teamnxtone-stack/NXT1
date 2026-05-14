/**
 * SignUpPage — public email + password signup with Google OAuth UI.
 *
 * Phase 13 additions:
 *   • Google Sign In button (UI ready; backend OAuth wires later)
 *   • Honors `?prompt=...&return=...` query so a draft typed on the
 *     landing page is preserved through the signup roundtrip and
 *     restored on the destination page.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, ArrowLeft, Loader2, Lock, Mail, User as UserIcon } from "lucide-react";
import { toast } from "sonner";
import Brand from "@/components/Brand";
import GradientBackdrop from "@/components/GradientBackdrop";
import PublicFooter from "@/components/PublicFooter";
import SocialAuthRow from "@/components/auth/SocialAuthRow";
import { userSignup } from "@/lib/api";
import { setToken } from "@/lib/auth";

export default function SignUpPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const returnTo = params.get("return") || "/onboarding";
  const promptParam = params.get("prompt") || "";

  useEffect(() => {
    if (promptParam) {
      try {
        window.localStorage.setItem("nxt1_draft_prompt", promptParam);
      } catch { /* ignore */ }
    }
  }, [promptParam]);

  const buildReturnUrl = () => {
    const draft = (() => {
      try { return window.localStorage.getItem("nxt1_draft_prompt") || ""; }
      catch { return ""; }
    })();
    if (!draft || returnTo.includes("?")) return returnTo;
    return `${returnTo}?prompt=${encodeURIComponent(draft)}`;
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.email.trim() || form.password.length < 8) {
      toast.error("Email and 8+ character password required.");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await userSignup(form);
      setToken(data.token);
      toast.success(`Welcome to NXT1, ${data.user.name || data.user.email}.`);
      navigate(buildReturnUrl());
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Signup failed");
    } finally {
      setSubmitting(false);
    }
  };

  const onGoogleSignIn = () => {
    toast.info("Google Sign In coming soon — use email signup for now.");
  };

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden text-white flex flex-col"
      data-testid="signup-page"
      style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}
    >
      <GradientBackdrop intensity="medium" variant="auth" />
      <header className="relative z-20 px-5 sm:px-10 pt-5 sm:pt-6 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <Link
            to="/"
            className="rail-btn"
            style={{ width: 36, height: 36 }}
            aria-label="Back to home"
            data-testid="signup-back"
          >
            <ArrowLeft size={15} />
          </Link>
          <Brand size="md" gradient />
        </div>
        <Link
          to={`/signin${promptParam ? `?prompt=${encodeURIComponent(promptParam)}&return=${encodeURIComponent(returnTo)}` : ""}`}
          className="text-[12px] tracking-wider uppercase text-white/55 hover:text-white transition-colors"
          data-testid="link-to-signin"
        >
          Sign in
        </Link>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center px-5 py-8 sm:py-10">
        <div
          className="w-full max-w-[460px] rounded-3xl p-7 sm:p-9 nxt-os-in"
          style={{
            background: "linear-gradient(180deg, rgba(48,48,56,0.62) 0%, rgba(36,36,40,0.78) 100%)",
            border: "1px solid rgba(255, 255, 255, 0.07)",
            boxShadow: "var(--elev-3, 0 30px 80px -20px rgba(0,0,0,0.65))",
            backdropFilter: "blur(28px) saturate(150%)",
            WebkitBackdropFilter: "blur(28px) saturate(150%)",
          }}
          data-testid="signup-card"
        >
          <div className="mono text-[10px] tracking-[0.30em] uppercase text-white/45 mb-4 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-[#5EEAD4] nxt-pulse" />
            Create your NXT1 account
          </div>
          <h1
            className="text-[30px] sm:text-[34px] leading-[1.05] font-semibold tracking-[-0.025em] mb-1.5"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
          >
            <span className="text-white">Start </span>
            <span
              style={{
                background: "linear-gradient(180deg, #E8E8EE 0%, #8A8A93 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              building.
            </span>
          </h1>
          <p className="text-white/45 text-[13.5px] mb-7 leading-relaxed">
            {promptParam
              ? "Your prompt is saved — finish signup and we'll pick up right where you left off."
              : "Free account. Build apps, websites, APIs and dashboards from natural language."}
          </p>

          {/* Social sign-in row — Google · GitHub · Apple */}
          <SocialAuthRow returnTo={returnTo} prompt={promptParam} />
          <div className="flex items-center gap-3 my-6">
            <div className="h-px flex-1 bg-white/8" />
            <span className="mono text-[9.5px] tracking-[0.28em] uppercase text-white/30">or with email</span>
            <div className="h-px flex-1 bg-white/8" />
          </div>

          <form onSubmit={submit} className="space-y-4">
            <Field icon={UserIcon} label="Name (optional)">
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Your name"
                className="nxt-auth-input"
                data-testid="signup-name-input"
              />
            </Field>
            <Field icon={Mail} label="Email" required>
              <input
                type="email"
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="you@company.com"
                className="nxt-auth-input"
                autoComplete="email"
                data-testid="signup-email-input"
              />
            </Field>
            <Field icon={Lock} label="Password" required>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  required
                  minLength={8}
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder="At least 8 characters"
                  className="nxt-auth-input pr-16"
                  autoComplete="new-password"
                  data-testid="signup-password-input"
                />
                <button
                  type="button"
                  onClick={() => setShowPw((s) => !s)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] mono uppercase tracking-wider text-white/50 hover:text-white px-2 py-1"
                >
                  {showPw ? "hide" : "show"}
                </button>
              </div>
            </Field>

            <button
              type="submit"
              disabled={submitting}
              className="w-full inline-flex items-center justify-center gap-2 h-12 rounded-2xl bg-white text-[#1F1F23] text-[14px] font-semibold tracking-tight hover:bg-white/95 transition-all shadow-[0_10px_28px_-10px_rgba(255,255,255,0.45)] hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 group mt-3"
              data-testid="signup-submit-button"
            >
              {submitting ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <>
                  Create account
                  <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </button>
          </form>

          <p className="text-[12.5px] text-white/40 mt-7 text-center">
            Already have an account?{" "}
            <Link
              to={`/signin${promptParam ? `?prompt=${encodeURIComponent(promptParam)}&return=${encodeURIComponent(returnTo)}` : ""}`}
              className="text-white/85 hover:text-white transition-colors font-medium"
              data-testid="signup-go-to-signin"
            >
              Sign in
            </Link>
          </p>
        </div>
      </main>
      <PublicFooter />
    </div>
  );
}

function GoogleGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
      <path d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.836.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>
      <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
    </svg>
  );
}

function Field({ icon: Icon, label, required, children }) {
  return (
    <label className="block">
      <span className="block mono text-[10px] tracking-[0.26em] uppercase text-white/45 mb-2">
        {label}
        {required && <span className="text-[#ff8a3d] ml-1">*</span>}
      </span>
      <div className="relative">
        {Icon && (
          <Icon
            size={15}
            className="absolute left-4 top-1/2 -translate-y-1/2 text-white/35 pointer-events-none z-10"
          />
        )}
        <div className={Icon ? "[&_input]:!pl-12" : ""}>{children}</div>
      </div>
    </label>
  );
}
