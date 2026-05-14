/**
 * NXT1 — Workspace Account (no credits / plans / upgrade messaging).
 *
 * Avatar + identity. Theme toggle. Connect GitHub. Domains. Help. Sign out.
 * Admin/Site Editor surface only when the user is an admin.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Github,
  HelpCircle,
  ChevronRight,
  Sun,
  Moon,
  Globe,
  Wand2,
  ShieldCheck,
  LogOut,
} from "lucide-react";
import { toast } from "sonner";
import { userMe, API } from "@/lib/api";
import { clearToken } from "@/lib/auth";
import { useTheme } from "@/components/theme/ThemeProvider";

export default function WorkspaceAccount() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [github, setGithub] = useState({ configured: false, linked: false, username: null });
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    userMe().then(({ data }) => {
      setUser(data);
      // Pull GitHub linked-state from auth_methods (server-side persistence)
      const linked = data?.auth_methods?.github || data?.linked_providers?.github;
      setGithub((g) => ({
        ...g,
        linked: !!linked,
        username: linked?.login || linked?.username || null,
      }));
    }).catch(() => {});
    // Pull OAuth provider configuration status (whether keys exist server-side)
    fetch(`${API}/oauth/status`).then((r) => r.json()).then((s) => {
      setGithub((g) => ({ ...g, configured: !!s?.github?.configured }));
    }).catch(() => {});
  }, []);

  const isAdmin = !!user?.is_admin || user?.role === "admin" || user?.email === "admin";
  const initials = (user?.name || user?.email || "NXT").slice(0, 1).toUpperCase();

  const handleConnectGithub = async () => {
    // Server-configured OAuth → straight to authorize. Otherwise, calm note.
    if (!github.configured) {
      toast.message("GitHub sign-in not yet configured", {
        description: "An admin needs to set OAUTH_GITHUB_CLIENT_ID / SECRET in the backend.",
      });
      return;
    }
    if (github.linked) {
      // Already linked — open the user's GitHub profile in a new tab as a
      // quick affordance, since we don't have a disconnect endpoint yet.
      if (github.username) window.open(`https://github.com/${github.username}`, "_blank");
      else toast.success("GitHub is already linked.");
      return;
    }
    window.location.href = `${API}/oauth/github/start?return=/workspace/account`;
  };

  return (
    <div className="px-5 sm:px-6 pt-8 sm:pt-12 pb-16 max-w-[680px] mx-auto" data-testid="workspace-account">
      {/* Identity */}
      <div className="flex flex-col items-center text-center mb-8">
        <div
          className="h-20 w-20 rounded-full flex items-center justify-center text-[28px] font-semibold mb-3"
          style={{
            background: "var(--nxt-avatar-bg)",
            border: "1px solid var(--nxt-accent-border)",
            color: "var(--nxt-fg)",
          }}
          data-testid="account-avatar"
        >
          {initials}
        </div>
        <div className="text-[18px] font-semibold tracking-tight" style={{ color: "var(--nxt-fg)" }}>
          {user?.name || "NXT1 Workspace"}
        </div>
        <div className="text-[12.5px] mt-0.5" style={{ color: "var(--nxt-fg-faint)" }}>
          {user?.email || "—"}
        </div>
      </div>

      <SectionLabel>Appearance</SectionLabel>
      <RowGroup>
        <Row
          icon={theme === "light" ? Sun : Moon}
          title={`Theme · ${theme === "light" ? "Light" : "Dark"}`}
          subtitle="Switch between matte graphite and warm light"
          onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          chevron
          testId="account-theme"
        />
      </RowGroup>

      <SectionLabel>Connections</SectionLabel>
      <RowGroup>
        <Row
          icon={Github}
          title={
            github.linked
              ? `GitHub · @${github.username || "connected"}`
              : github.configured
                ? "Connect GitHub"
                : "GitHub (not configured)"
          }
          subtitle={
            github.linked
              ? "Linked — tap to open your profile"
              : github.configured
                ? "Link your GitHub account in one tap"
                : "Awaiting OAuth credentials on the server"
          }
          onClick={handleConnectGithub}
          chevron
          state={github.linked ? "connected" : github.configured ? "ready" : "idle"}
          testId="account-github"
        />
        <Row
          icon={Globe}
          title="Domains"
          subtitle="Connect custom domains"
          onClick={() => navigate("/workspace/domains")}
          chevron
          testId="account-domains"
        />
      </RowGroup>

      {isAdmin && (
        <>
          <SectionLabel>Admin</SectionLabel>
          <RowGroup>
            <Row
              icon={ShieldCheck}
              title="Admin panel"
              subtitle="User access, integrations, deployments"
              onClick={() => navigate("/admin")}
              chevron
              testId="account-admin"
            />
            <Row
              icon={Wand2}
              title="Site Editor"
              subtitle="Edit public-site content"
              onClick={() => navigate("/admin/site-editor")}
              chevron
              testId="account-site-editor"
            />
          </RowGroup>
        </>
      )}

      <SectionLabel>Support</SectionLabel>
      <RowGroup>
        <Row
          icon={HelpCircle}
          title="Help & Support"
          onClick={() => navigate("/contact")}
          chevron
          testId="account-help"
        />
      </RowGroup>

      <div className="h-6" aria-hidden />

      <button
        type="button"
        onClick={() => { clearToken(); navigate("/"); }}
        className="w-full inline-flex items-center justify-center gap-2 h-11 rounded-2xl text-[13.5px] transition"
        style={{
          background: "var(--nxt-surface-soft)",
          border: "1px solid var(--nxt-border-soft)",
          color: "var(--nxt-fg-dim)",
        }}
        data-testid="account-signout"
      >
        <LogOut size={14} /> Sign out
      </button>

      <div
        className="mt-12 mono text-[9px] tracking-[0.32em] uppercase text-center"
        style={{ color: "var(--nxt-fg-faint)" }}
      >
        DISCOVER · DEVELOP · DELIVER
      </div>
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div
      className="mono text-[10px] tracking-[0.24em] uppercase mt-6 mb-2 px-1"
      style={{ color: "var(--nxt-fg-faint)" }}
    >
      {children}
    </div>
  );
}

function RowGroup({ children }) {
  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{
        background: "var(--nxt-surface-soft)",
        border: "1px solid var(--nxt-border-soft)",
      }}
    >
      {children}
    </div>
  );
}

function Row({ icon: Icon, title, subtitle, onClick, right, chevron, state, testId }) {
  const Cmp = onClick ? "button" : "div";
  const dotColor =
    state === "connected" ? "#5EEAD4" :
    state === "ready"     ? "rgba(255,255,255,0.5)" :
    "transparent";
  return (
    <Cmp
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className="w-full text-left flex items-center gap-3.5 px-4 py-3.5 transition"
      style={{ borderBottom: "1px solid var(--nxt-border-soft)" }}
      data-testid={testId}
    >
      <span
        className="relative h-9 w-9 shrink-0 rounded-xl flex items-center justify-center"
        style={{
          background: "var(--nxt-chip-bg)",
          border: "1px solid var(--nxt-border-soft)",
        }}
      >
        <Icon size={14.5} style={{ color: "var(--nxt-fg-dim)" }} />
        {state && state !== "idle" && (
          <span
            className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full"
            style={{
              background: dotColor,
              boxShadow: "0 0 0 2px var(--nxt-surface-soft)",
            }}
            aria-hidden
          />
        )}
      </span>
      <span className="flex-1 min-w-0">
        <span className="block text-[14px] font-medium truncate" style={{ color: "var(--nxt-fg)" }}>
          {title}
        </span>
        {subtitle && (
          <span className="block text-[12.5px] truncate mt-0.5" style={{ color: "var(--nxt-fg-faint)" }}>
            {subtitle}
          </span>
        )}
      </span>
      {right}
      {chevron && <ChevronRight size={14} style={{ color: "var(--nxt-fg-faint)" }} />}
    </Cmp>
  );
}
