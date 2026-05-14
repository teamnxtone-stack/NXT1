/**
 * AdminWorkspace — Jacob's unified control panel. One page, left sidebar,
 * everything for running NXT1 in one place: overview / site editor / brand &
 * theme / users / keys / deploys / history. Admin-only.
 *
 * Replaces the old `/admin/site-editor` standalone page; that route still
 * works but the dashboard tile now points here.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  Code2,
  ExternalLink,
  Globe2,
  Github,
  History as HistoryIcon,
  Key,
  LayoutDashboard,
  Palette,
  ScrollText,
  Sparkles,
  Users,
} from "lucide-react";
import Brand from "@/components/Brand";
import { adminGithubStatus, adminOverview } from "@/lib/api";
import SiteEditorBody from "@/components/admin/SiteEditorBody";
import BrandThemePanel from "@/components/admin/BrandThemePanel";
import EditableKeysPanel from "@/components/admin/EditableKeysPanel";
import AdminDomainsPanel from "@/components/admin/AdminDomainsPanel";
import AuditPanel from "@/components/admin/AuditPanel";
import UsersPanel from "@/components/dashboard/UsersPanel";
import GithubStatusBanner from "@/components/admin/GithubStatusBanner";

const NAV = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "site-editor", label: "AI Site Editor", icon: Sparkles, accent: true },
  { id: "brand", label: "Brand & Theme", icon: Palette },
  { id: "users", label: "Users", icon: Users },
  { id: "keys", label: "Keys & Secrets", icon: Key },
  { id: "domains", label: "NXT1 Domains", icon: Globe2 },
  { id: "audit", label: "Audit Log", icon: ScrollText },
  { id: "history", label: "Edit History", icon: HistoryIcon },
];

export default function AdminWorkspace() {
  const [params, setParams] = useSearchParams();
  const section = params.get("s") || "overview";
  const [overview, setOverview] = useState(null);
  const [gh, setGh] = useState(null);

  useEffect(() => {
    adminOverview().then(({ data }) => setOverview(data)).catch(() => {});
    adminGithubStatus().then(({ data }) => setGh(data)).catch(() => {});
  }, []);

  const setSection = (id) => {
    const next = new URLSearchParams(params);
    next.set("s", id);
    setParams(next, { replace: true });
  };

  return (
    <div
      className="min-h-[100dvh] w-full surface-recessed text-white flex flex-col"
      data-testid="admin-workspace"
      style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}
    >
      {/* Top bar */}
      <header className="h-12 shrink-0 flex items-center justify-between px-4 sm:px-5 border-b border-white/10 bg-[#1F1F23]">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            to="/workspace"
            className="h-8 w-8 flex items-center justify-center rounded-full text-zinc-300 hover:text-white hover:bg-white/5 transition shrink-0"
            data-testid="admin-back"
            aria-label="Back to dashboard"
          >
            <ArrowLeft size={14} />
          </Link>
          <Brand size="sm" gradient />
          <span className="text-zinc-700">/</span>
          <span className="mono text-[10.5px] tracking-[0.32em] uppercase text-zinc-300 truncate">
            workspace
          </span>
        </div>
        <div className="flex items-center gap-2">
          {overview?.users?.pending > 0 && (
            <button
              onClick={() => setSection("users")}
              className="inline-flex items-center gap-1.5 px-2 sm:px-2.5 py-1 rounded-full border border-amber-400/30 bg-amber-500/[0.08] text-amber-200 text-[9.5px] sm:text-[10.5px] mono uppercase tracking-wider hover:border-amber-400/50 transition"
              data-testid="admin-pending-users-pill"
            >
              {overview.users.pending} pending
            </button>
          )}
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10.5px] mono uppercase tracking-wider border ${
              gh?.ready
                ? "border-emerald-400/30 bg-emerald-500/[0.07] text-emerald-200"
                : "border-zinc-600/40 bg-zinc-700/10 text-zinc-400"
            }`}
            data-testid="admin-gh-pill"
          >
            <Github size={10} />
            {gh?.ready ? gh.login : gh?.configured ? "token issue" : "no token"}
          </span>
        </div>
      </header>

      <div className="flex-1 min-h-0 grid lg:grid-cols-[220px_minmax(0,1fr)]">
        {/* Sidebar */}
        <nav className="border-b lg:border-b-0 lg:border-r border-white/8 bg-[#1F1F23] p-2 lg:p-3 flex lg:flex-col gap-0.5 overflow-x-auto">
          {NAV.map((it) => {
            const Icon = it.icon;
            const active = section === it.id;
            return (
              <button
                key={it.id}
                onClick={() => setSection(it.id)}
                className={`group inline-flex items-center gap-2.5 px-3 py-2 rounded-lg text-[12.5px] transition shrink-0 ${
                  active
                    ? it.accent
                      ? "bg-emerald-500/10 border border-emerald-400/30 text-emerald-100"
                      : "bg-white/[0.06] border border-white/15 text-white"
                    : "border border-transparent text-zinc-400 hover:text-white hover:bg-white/[0.03]"
                }`}
                data-testid={`admin-nav-${it.id}`}
              >
                <Icon size={13} className={active && it.accent ? "text-emerald-300" : ""} />
                <span className="font-medium">{it.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Content */}
        <main className="min-h-0 overflow-y-auto">
          {section === "overview" && <OverviewTab overview={overview} gh={gh} onJump={setSection} />}
          {section === "site-editor" && <SiteEditorBody />}
          {section === "brand" && <BrandThemePanel />}
          {section === "users" && (
            <div className="max-w-3xl">
              <UsersPanel />
            </div>
          )}
          {section === "keys" && <EditableKeysPanel gh={gh} />}
          {section === "domains" && <AdminDomainsPanel />}
          {section === "audit" && <AuditPanel />}
          {section === "history" && (
            <div className="p-4 sm:p-6">
              <SectionTitle eyebrow="Edit history" title="Site Editor + Brand changes" />
              <SiteEditorBody historyOnly />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function SectionTitle({ eyebrow, title, children }) {
  return (
    <div className="mb-5">
      <div className="mono text-[10px] tracking-[0.32em] uppercase text-zinc-500 mb-1.5">
        // {eyebrow}
      </div>
      <h1
        className="text-2xl sm:text-3xl font-black tracking-tighter text-white"
        style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
      >
        {title}
      </h1>
      {children}
    </div>
  );
}

function OverviewTab({ overview, gh, onJump }) {
  const tiles = useMemo(() => {
    if (!overview) return [];
    return [
      {
        label: "Users",
        value: overview.users?.total ?? 0,
        sub: overview.users?.pending
          ? `${overview.users.pending} awaiting access`
          : "all approved",
        icon: Users,
        onClick: () => onJump("users"),
        accent: overview.users?.pending > 0 ? "amber" : "emerald",
      },
      {
        label: "Site edits",
        value: overview.site_edits?.total ?? 0,
        sub: overview.site_edits?.last
          ? `Last: ${overview.site_edits.last.summary?.slice(0, 36)}…`
          : "No edits yet",
        icon: Sparkles,
        onClick: () => onJump("history"),
        accent: "emerald",
      },
      {
        label: "Projects",
        value: overview.projects?.total ?? 0,
        sub: "User-built apps",
        icon: Code2,
        accent: "zinc",
      },
      {
        label: "Origin",
        value: (overview.deploy_origin || "").replace(/^https?:\/\//, ""),
        sub: "Public preview origin",
        icon: Globe2,
        accent: "zinc",
        small: true,
      },
    ];
  }, [overview, onJump]);

  return (
    <div className="p-4 sm:p-6 max-w-5xl">
      <SectionTitle eyebrow="overview" title="Workspace status" />
      <GithubStatusBanner gh={gh} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 mt-4">
        {tiles.map((t) => (
          <button
            key={t.label}
            onClick={t.onClick}
            disabled={!t.onClick}
            className="rounded-2xl border border-white/8 bg-[#1F1F23] p-4 text-left hover:border-white/20 transition disabled:hover:border-white/8"
          >
            <div className="flex items-center gap-2 mb-2">
              <t.icon
                size={12}
                className={
                  t.accent === "amber"
                    ? "text-amber-300"
                    : t.accent === "emerald"
                      ? "text-emerald-300"
                      : "text-zinc-500"
                }
              />
              <span className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500">
                {t.label}
              </span>
            </div>
            <div
              className={`text-white tracking-tight font-black ${
                t.small ? "text-[15px] truncate" : "text-2xl"
              }`}
              style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
            >
              {t.value}
            </div>
            <div className="text-[11px] text-zinc-500 mt-1 truncate">{t.sub}</div>
          </button>
        ))}
      </div>

      {/* Provider chips */}
      <div className="mt-6">
        <div className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500 mb-2">
          Connected providers
        </div>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(overview?.providers || {}).map(([key, ok]) => (
            <span
              key={key}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] mono uppercase tracking-wider ${
                ok
                  ? "border-emerald-400/25 bg-emerald-500/[0.06] text-emerald-200"
                  : "border-white/8 bg-white/[0.02] text-zinc-600"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-400" : "bg-zinc-700"}`} />
              {key}
            </span>
          ))}
        </div>
      </div>

      {/* Quick actions */}
      <div className="mt-6 grid sm:grid-cols-2 gap-2.5">
        <button
          onClick={() => onJump("site-editor")}
          className="group flex items-center gap-3 px-4 py-4 rounded-2xl border border-emerald-400/25 bg-gradient-to-br from-[#0d1614] to-[#1F1F23] hover:border-emerald-400/50 transition text-left"
          data-testid="admin-quick-site-editor"
        >
          <span className="h-10 w-10 rounded-xl bg-emerald-500/15 border border-emerald-400/30 flex items-center justify-center shrink-0">
            <Sparkles size={15} className="text-emerald-300" />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] text-emerald-100 font-semibold">AI Site Editor</div>
            <div className="text-[11.5px] text-zinc-400 mt-0.5 truncate">
              Edit NXT1 by chat → diff → push → deploy.
            </div>
          </div>
          <ExternalLink size={13} className="text-emerald-300/70 group-hover:text-emerald-300" />
        </button>
        <button
          onClick={() => onJump("brand")}
          className="group flex items-center gap-3 px-4 py-4 rounded-2xl border border-white/10 surface-1 hover:border-white/25 transition text-left"
          data-testid="admin-quick-brand"
        >
          <span className="h-10 w-10 rounded-xl bg-white/[0.04] border border-white/10 flex items-center justify-center shrink-0">
            <Palette size={15} className="text-fuchsia-300" />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] text-white font-semibold">Brand & Theme</div>
            <div className="text-[11.5px] text-zinc-500 mt-0.5 truncate">
              Colors, fonts, hero copy, footer — saved + deployed.
            </div>
          </div>
          <ExternalLink size={13} className="text-zinc-500 group-hover:text-white" />
        </button>
      </div>
    </div>
  );
}

// (Legacy KeysTab removed — replaced by EditableKeysPanel.)
