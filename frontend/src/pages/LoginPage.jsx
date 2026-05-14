/**
 * NXT1 workspace access — minimalist redo (2026-05-13)
 *
 * Single dark surface, a small wordmark, one input, one button. No gradient
 * backdrop, no tagline, no glass card chrome, no public footer. The page is
 * a gate — its job is to disappear once you're through it.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowRight, Loader2 } from "lucide-react";
import Brand from "@/components/Brand";
import { login } from "@/lib/api";
import { clearToken, isAuthenticated, setToken } from "@/lib/auth";

export default function LoginPage() {
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) return;
    fetch(`${process.env.REACT_APP_BACKEND_URL}/api/users/me`, {
      headers: { Authorization: `Bearer ${localStorage.getItem("nxt1.token") || ""}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.role === "admin") navigate("/admin", { replace: true });
        else clearToken();
      })
      .catch(() => clearToken());
  }, [navigate]);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!password.trim()) return;
    setSubmitting(true);
    try {
      clearToken();
      const { data } = await login(password);
      setToken(data.token);
      navigate("/admin", { replace: true });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Wrong passkey");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="relative min-h-screen w-full flex flex-col items-center justify-center px-6 text-white"
      style={{ background: "#0B0B0C" }}
      data-testid="login-page"
    >
      {/* Tiny brand anchor */}
      <Link
        to="/"
        className="absolute top-6 left-6 opacity-80 hover:opacity-100 transition-opacity"
        aria-label="Back to home"
        data-testid="login-back"
      >
        <Brand size="sm" gradient />
      </Link>

      {/* Centerpiece: one input, one button, nothing else. */}
      <form
        onSubmit={onSubmit}
        className="w-full max-w-[320px] flex flex-col items-stretch gap-4"
        data-testid="login-form"
      >
        <h1
          className="text-center text-[13px] mono tracking-[0.32em] uppercase font-medium mb-2"
          style={{ color: "rgba(255,255,255,0.55)" }}
        >
          Workspace
        </h1>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Passkey"
          className="w-full h-12 rounded-xl bg-transparent border border-white/10 px-4 text-[15px] tracking-wider text-white placeholder:text-white/30 focus:border-white/30 focus:outline-none transition-colors"
          style={{ fontVariant: "tabular-nums" }}
          autoFocus
          autoComplete="current-password"
          data-testid="login-password-input"
        />
        <button
          type="submit"
          disabled={submitting || !password.trim()}
          className="w-full inline-flex items-center justify-center gap-2 h-12 rounded-xl bg-white text-black text-[14px] font-medium tracking-tight transition-all disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/95 active:scale-[0.99]"
          data-testid="login-submit-button"
        >
          {submitting ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <>
              Enter
              <ArrowRight size={14} strokeWidth={2.2} />
            </>
          )}
        </button>
      </form>

      {/* Micro-footer */}
      <div
        className="absolute bottom-6 left-0 right-0 flex items-center justify-center gap-5 text-[11px] mono tracking-wider"
        style={{ color: "rgba(255,255,255,0.30)" }}
      >
        <Link to="/signin" className="hover:text-white/70 transition-colors" data-testid="login-go-to-signin">
          User sign in
        </Link>
        <span aria-hidden>·</span>
        <Link to="/signup" className="hover:text-white/70 transition-colors" data-testid="login-request-access-link">
          Request access
        </Link>
      </div>
    </div>
  );
}
