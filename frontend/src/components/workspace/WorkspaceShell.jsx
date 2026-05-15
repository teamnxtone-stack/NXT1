/**
 * NXT1 — Workspace Shell (Hamburger-only).
 *
 * The workspace IS the chat. No bottom tabs. No giant rail. No metrics.
 * One hamburger button in the top-left opens a clean drawer with the
 * THREE primary surfaces — Home, Apps, Account — plus Admin for operators.
 *
 * Simplified Feb 2026: "Apps" vs "Live Apps" was redundant and confusing;
 * Settings is now folded into Account drilldowns (a single canonical
 * configuration surface). Reference feel: Claude / ChatGPT / Blink.new.
 */
import { useEffect, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import NotificationCenter from "@/components/NotificationCenter";
import {
  Menu,
  X,
  Home as HomeIcon,
  FileEdit,
  User,
  ShieldCheck,
  Wand2,
  LogOut,
  ChevronRight,
  Sun,
  Moon,
  Sparkles as SparklesIcon,
  Bot,
  Megaphone,
  Film,
  Brain,
  MessageSquare,
} from "lucide-react";
import Brand from "@/components/Brand";
import { clearToken } from "@/lib/auth";
import { userMe } from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";

export default function WorkspaceShell() {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="h-[100dvh] w-full flex flex-col"
      style={{
        background: "var(--nxt-bg)",
        color: "var(--nxt-fg)",
        fontFamily: "'IBM Plex Sans', sans-serif",
      }}
      data-testid="workspace-shell"
    >
      <MinimalTopBar onMenu={() => setOpen(true)} />
      <main className="flex-1 min-h-0 overflow-y-auto flex flex-col" data-testid="workspace-main">
        <Outlet />
      </main>
      <AnimatePresence>
        {open && <HamburgerDrawer onClose={() => setOpen(false)} />}
      </AnimatePresence>
    </div>
  );
}

function MinimalTopBar({ onMenu }) {
  return (
    <header
      className="shrink-0 h-12 flex items-center justify-between px-3 sm:px-5"
      style={{ background: "transparent" }}
      data-testid="workspace-topbar"
    >
      <button
        type="button"
        onClick={onMenu}
        className="inline-flex items-center justify-center h-10 w-10 rounded-full transition"
        style={{
          background: "var(--nxt-chip-bg)",
          border: "1px solid var(--nxt-border-soft)",
          color: "var(--nxt-fg-dim)",
        }}
        aria-label="Open menu"
        data-testid="workspace-menu-trigger"
      >
        <Menu size={16} />
      </button>
      <Brand size="sm" gradient />
      <NotificationCenter />
    </header>
  );
}

function HamburgerDrawer({ onClose }) {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const { theme, toggle } = useTheme();

  useEffect(() => {
    userMe().then(({ data }) => setUser(data)).catch(() => {});
    function onKey(e) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const isAdmin = !!user?.is_admin || user?.role === "admin" || user?.email === "admin";
  const initials = (user?.name || user?.email || "NXT").slice(0, 1).toUpperCase();

  const go = (path) => { onClose(); navigate(path); };

  const primary = [
    { id: "home",     label: "Home",     icon: HomeIcon,     onClick: () => go("/") },
    { id: "apps",     label: "Apps",     icon: FileEdit,     onClick: () => go("/workspace/apps") },
    { id: "social",   label: "Social",   icon: Megaphone,    onClick: () => go("/workspace/social") },
    { id: "studio",   label: "Studio",   icon: Film,         onClick: () => go("/workspace/studio") },
    { id: "memory",   label: "Memory",   icon: Brain,        onClick: () => go("/workspace/memory") },
    { id: "leads",    label: "Leads",    icon: MessageSquare, onClick: () => go("/workspace/leads") },
    { id: "agents",   label: "Agents",   icon: SparklesIcon, onClick: () => go("/workspace/agents") },
    { id: "agentos",  label: "AgentOS",  icon: Bot,          onClick: () => go("/agentos") },
    { id: "account",  label: "Account",  icon: User,         onClick: () => go("/workspace/account") },
  ];
  const adminItems = isAdmin ? [
    { id: "admin",       label: "Admin Panel", icon: ShieldCheck, onClick: () => go("/admin") },
    { id: "site-editor", label: "Site Editor", icon: Wand2,       onClick: () => go("/admin/site-editor") },
  ] : [];

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.18 }}
        className="fixed inset-0 z-50"
        style={{ background: "rgba(0, 0, 0, 0.42)", backdropFilter: "blur(4px)" }}
        onClick={onClose}
        aria-hidden
      />
      <motion.aside
        initial={{ x: "-100%" }}
        animate={{ x: 0 }}
        exit={{ x: "-100%" }}
        transition={{ type: "spring", stiffness: 360, damping: 32 }}
        className="fixed top-0 bottom-0 left-0 z-50 w-[88vw] max-w-[320px] flex flex-col"
        style={{
          background: "var(--nxt-bg)",
          borderRight: "1px solid var(--nxt-border)",
          paddingTop: "env(safe-area-inset-top, 0px)",
          paddingBottom: "env(safe-area-inset-bottom, 0px)",
        }}
        role="dialog"
        aria-label="Workspace menu"
        data-testid="workspace-drawer"
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-2">
          <Brand size="md" gradient />
          <button
            type="button"
            onClick={onClose}
            className="h-9 w-9 inline-flex items-center justify-center rounded-full transition"
            style={{ color: "var(--nxt-fg-dim)" }}
            aria-label="Close menu"
            data-testid="workspace-drawer-close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Identity */}
        <button
          type="button"
          onClick={() => go("/workspace/account")}
          className="mx-3 mt-2 mb-3 flex items-center gap-3 p-3 rounded-2xl text-left transition"
          style={{
            background: "var(--nxt-surface-soft)",
            border: "1px solid var(--nxt-border-soft)",
          }}
          data-testid="drawer-identity"
        >
          <span
            className="h-10 w-10 shrink-0 rounded-full flex items-center justify-center text-[15px] font-semibold"
            style={{
              background: "var(--nxt-avatar-bg)",
              border: "1px solid var(--nxt-accent-border)",
            }}
          >
            {initials}
          </span>
          <span className="flex-1 min-w-0">
            <span className="block text-[14px] font-medium truncate" style={{ color: "var(--nxt-fg)" }}>
              {user?.name || "NXT1 Workspace"}
            </span>
            <span className="block text-[12px] truncate mt-0.5" style={{ color: "var(--nxt-fg-faint)" }}>
              {user?.email || "—"}
            </span>
          </span>
          <ChevronRight size={14} style={{ color: "var(--nxt-fg-faint)" }} />
        </button>

        <nav className="flex-1 overflow-y-auto px-3 pb-3 space-y-0.5">
          {primary.map((m) => <DrawerItem key={m.id} {...m} />)}
          {adminItems.length > 0 && (
            <>
              <SectionLabel>Admin</SectionLabel>
              {adminItems.map((m) => <DrawerItem key={m.id} {...m} />)}
            </>
          )}
          <SectionLabel>Appearance</SectionLabel>
          <DrawerItem
            id="theme"
            label={`Theme · ${theme === "light" ? "Light" : "Dark"}`}
            icon={theme === "light" ? Sun : Moon}
            onClick={toggle}
          />
        </nav>

        <div className="px-3 pb-4">
          <button
            type="button"
            onClick={() => { clearToken(); onClose(); navigate("/"); }}
            className="w-full inline-flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-[13.5px] transition"
            style={{
              background: "var(--nxt-surface-soft)",
              border: "1px solid var(--nxt-border-soft)",
              color: "var(--nxt-fg-dim)",
            }}
            data-testid="drawer-signout"
          >
            <LogOut size={14} /> Sign out
          </button>
          <div
            className="mt-3 mono text-[9px] tracking-[0.32em] uppercase text-center"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            DISCOVER · DEVELOP · DELIVER
          </div>
        </div>
      </motion.aside>
    </>
  );
}

function DrawerItem({ id, label, icon: Icon, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition text-left"
      style={{ color: "var(--nxt-fg-dim)" }}
      data-testid={`drawer-${id}`}
    >
      <Icon size={15.5} strokeWidth={1.8} />
      <span className="flex-1 text-[14px] tracking-tight" style={{ color: "var(--nxt-fg)" }}>
        {label}
      </span>
      <ChevronRight size={13} style={{ color: "var(--nxt-fg-faint)" }} />
    </button>
  );
}

function SectionLabel({ children }) {
  return (
    <div
      className="mono text-[9.5px] tracking-[0.24em] uppercase mt-4 mb-1.5 px-3"
      style={{ color: "var(--nxt-fg-faint)" }}
    >
      {children}
    </div>
  );
}
