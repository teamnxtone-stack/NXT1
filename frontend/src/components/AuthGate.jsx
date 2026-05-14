/**
 * AuthGate — wraps protected app routes. Loads `/users/me`, then:
 *   - redirects to /signin if no token / 401
 *   - renders <RequestAccessWall /> if user.access_status !== "approved"
 *   - renders children for admin OR approved users
 *
 * `requireAdmin` further restricts to admin-only routes (Site Editor, etc).
 */
import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { userMe } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";
import RequestAccessWall from "@/pages/RequestAccessWall";

export default function AuthGate({ children, requireAdmin = false, allowOnboardingPending = false }) {
  const [state, setState] = useState({ loading: true, user: null, error: null });
  const location = useLocation();

  // Only fetch /users/me on initial mount + on auth-token changes (via storage).
  // Refetching on every pathname change caused users to bounce back to /signin
  // during fast navigation while the request was in flight.
  useEffect(() => {
    let cancelled = false;
    function loadMe() {
      if (!isAuthenticated()) {
        if (!cancelled) setState({ loading: false, user: null });
        return;
      }
      userMe()
        .then(({ data }) => { if (!cancelled) setState({ loading: false, user: data }); })
        .catch((e) => {
          // Only clear the user on real auth failures (401/403); other errors
          // (transient 5xx, network blips) should NOT bounce the user out.
          const status = e?.response?.status;
          if (status === 401 || status === 403) {
            if (!cancelled) setState({ loading: false, user: null, error: status });
          } else if (!cancelled) {
            setState((s) => ({ loading: false, user: s.user, error: status }));
          }
        });
    }
    loadMe();
    function onStorage(ev) {
      if (ev.key === "nxt1_token") loadMe();
    }
    window.addEventListener("storage", onStorage);
    return () => { cancelled = true; window.removeEventListener("storage", onStorage); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (state.loading) {
    return (
      <div className="h-[100dvh] w-full surface-recessed flex items-center justify-center text-zinc-500">
        <Loader2 size={20} className="animate-spin" />
      </div>
    );
  }

  // Not signed in → bounce to user sign-in (admin can still hit /access directly)
  if (!state.user) {
    return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
  }

  const role = state.user.role;

  // Admin always passes
  if (role === "admin") return children;

  // Admin-only routes block non-admin users
  if (requireAdmin) {
    return <Navigate to="/workspace" replace />;
  }

  // Pending / denied access wall
  if (state.user.access_status !== "approved") {
    return <RequestAccessWall user={state.user} />;
  }

  return children;
}
