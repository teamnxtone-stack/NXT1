/**
 * NXT1 — OAuthCallback page.
 *
 * The backend OAuth callback redirects here with one of:
 *   /signin?oauth=error&provider=...&reason=...
 *   /workspace?oauth=success&provider=...&token=...&prompt=...
 *
 * Workspace handles the success case via this component: it pulls the
 * token out of the URL, stores it in localStorage, optionally restores
 * the saved draft prompt, and then navigates onward.
 *
 * If the URL doesn't contain an OAuth payload, this component is inert
 * and the wrapped page renders normally. It's mounted as a wrapper around
 * SignInPage / WorkspaceRouter to catch both success/error landings.
 */
import { useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { setToken } from "@/lib/auth";

export default function OAuthCallbackInterceptor({ children }) {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const oauth = params.get("oauth");
    if (!oauth) return;
    const provider = params.get("provider") || "";
    if (oauth === "success") {
      const token = params.get("token");
      if (token) {
        setToken(token);
        toast.success(`Signed in with ${provider || "OAuth"}.`);
        // Restore draft prompt if any
        const prompt = params.get("prompt") || "";
        if (prompt) {
          try {
            window.localStorage.setItem("nxt1_draft_prompt", prompt);
          } catch { /* ignore */ }
        }
        // Strip OAuth params from the URL while keeping the destination.
        const dest = window.location.pathname;
        navigate(dest, { replace: true });
      } else {
        toast.error("OAuth succeeded but no token returned.");
      }
    } else if (oauth === "error") {
      const reason = params.get("reason") || "unknown";
      toast.error(`${provider || "OAuth"} sign-in failed: ${reason}`);
      navigate(window.location.pathname, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return children;
}
