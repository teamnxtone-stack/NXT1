/**
 * NXT1 — Dashboard (Phase 16 Command Center)
 *
 * Complete from-scratch rewrite.
 *
 * Layout (no "dashboard" feel):
 *
 *   ┌────┬───────────────────────────────────────────────────────┐
 *   │ R  │   AI WORKSPACE · NXT1                                 │
 *   │ a  │                                                       │
 *   │ i  │           ╭──────────────────────────────╮            │
 *   │ l  │           │  Describe what to build…     │            │
 *   │    │           │                              │            │
 *   │    │           │  [modes]   [provider][Build] │            │
 *   │    │           ╰──────────────────────────────╯            │
 *   │    │                                                       │
 *   │    │   // recent · N projects                              │
 *   │    │   ┌───┐  ┌───┐  ┌───┐                                  │
 *   │    │   │   │  │   │  │   │   (quiet, no hard borders)      │
 *   │    │   └───┘  └───┘  └───┘                                  │
 *   └────┴───────────────────────────────────────────────────────┘
 *
 * Removed entirely (per direction):
 *   • metric tiles, status counters, "stats" dashboards
 *   • boxy headers, bordered import card, admin banner-tile
 *   • center-aligned dashboard chrome
 *
 * Added:
 *   • floating left rail (icon-only, no chrome)
 *   • center prompt cockpit as the operational hero
 *   • quiet project grid with subtle graphite hover glow
 *   • contextual right "peek panel" for import / settings / profile
 *   • carbon graphite material system (no pure black anywhere)
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  listProjects,
  createProject,
  deleteProject,
  importGithub,
  importZipUrl,
  userMe,
} from "@/lib/api";
import { getToken, clearToken } from "@/lib/auth";
import {
  Home as HomeIcon,
  Upload,
  Settings as SettingsIcon,
  LogOut,
  ShieldCheck,
  Sparkles,
  Layers,
  Globe,
  Smartphone,
  Puzzle,
  Github,
  FileArchive,
  Loader2,
  ArrowRight,
  Trash2,
  X,
  Plus,
  CornerDownLeft,
} from "lucide-react";
import Brand from "@/components/Brand";
import GradientBackdrop from "@/components/GradientBackdrop";
import ModelPickerCockpit from "@/components/premium/ModelPickerCockpit";
import SettingsSheet from "@/components/dashboard/SettingsSheet";

const BUILDER_MODES = [
  { key: "fullstack", label: "Full Stack", icon: Layers,     brief: "Build a full-stack app with frontend, backend API, and database." },
  { key: "website",   label: "Website",   icon: Globe,       brief: "Build a polished website / SPA with responsive design." },
  { key: "mobile",    label: "Mobile",    icon: Smartphone,  brief: "Build a mobile app (Expo / React Native) with native feel." },
  { key: "extension", label: "Extension", icon: Puzzle,      brief: "Build a browser extension (Chrome manifest v3)." },
];

const PEEK = { NONE: null, IMPORT: "import", SETTINGS: "settings" };

export default function DashboardPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [projects, setProjects] = useState([]);
  const [loading, setLoading]   = useState(true);

  // Hero prompt state
  const [draft, setDraft] = useState("");
  const [mode, setMode]   = useState("fullstack");
  const [provider, setProvider] = useState("anthropic");
  const [busy, setBusy] = useState(false);
  const taRef = useRef(null);

  // Identity
  const [me, setMe] = useState(null);

  // Peek panel
  const [peek, setPeek] = useState(PEEK.NONE);

  // Import state
  const [importMode, setImportMode] = useState("zip");
  const [importBusy, setImportBusy] = useState(false);
  const [importName, setImportName] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const zipInputRef = useRef(null);

  // ──────────────────────────────────────────────────────────────
  // Bootstrap
  // ──────────────────────────────────────────────────────────────
  useEffect(() => {
    userMe().then(({ data }) => setMe(data)).catch(() => {});
  }, []);

  const refresh = async () => {
    setLoading(true);
    try {
      const { data } = await listProjects();
      setProjects(data);
    } catch {
      toast.error("Failed to load projects");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { refresh(); }, []);

  // Restore prompt from landing handoff
  useEffect(() => {
    const fromQuery = searchParams.get("prompt") || "";
    let saved = "";
    try { saved = window.localStorage.getItem("nxt1_draft_prompt") || ""; }
    catch { /* ignore */ }
    const restored = fromQuery || saved;
    if (restored) {
      setDraft(restored);
      toast.success("Welcome back — your prompt was restored.");
      try { window.localStorage.removeItem("nxt1_draft_prompt"); } catch { /* ignore */ }
      if (fromQuery) {
        searchParams.delete("prompt");
        setSearchParams(searchParams, { replace: true });
      }
    }
    // Auto-focus the prompt — the workspace is prompt-first.
    setTimeout(() => taRef.current?.focus(), 100);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keyboard shortcut: ⌘/Ctrl + I to open import peek
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "i") {
        e.preventDefault();
        setPeek(PEEK.IMPORT);
      }
      if (e.key === "Escape") setPeek(PEEK.NONE);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ──────────────────────────────────────────────────────────────
  // Actions
  // ──────────────────────────────────────────────────────────────
  const persistDraft = (val) => {
    setDraft(val);
    try { window.localStorage.setItem("nxt1_draft_prompt", val); } catch { /* ignore */ }
  };

  const handleBuild = async () => {
    const v = (draft || "").trim();
    if (!v || busy) {
      taRef.current?.focus();
      return;
    }
    setBusy(true);
    try {
      const m = BUILDER_MODES.find((x) => x.key === mode);
      const brief = m ? `${m.brief} App brief: ${v}` : v;
      // Use first 80 chars of prompt as project name
      const projectName = v.slice(0, 80).replace(/\s+/g, " ").trim();
      const { data } = await createProject(projectName, brief);
      // Auto-start durable workflow alongside the chat stream.
      try {
        const api = await import("@/lib/api");
        api.startWorkflow(data.id, v, "internal").catch(() => {});
      } catch { /* ignore */ }
      try { window.localStorage.removeItem("nxt1_draft_prompt"); } catch { /* ignore */ }
      navigate(`/builder/${data.id}?prompt=${encodeURIComponent(v)}&mode=${mode}&provider=${provider}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start your build");
      setBusy(false);
    }
  };

  const handleDelete = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm("Delete this project? This cannot be undone.")) return;
    try {
      await deleteProject(id);
      toast.success("Project deleted");
      refresh();
    } catch {
      toast.error("Delete failed");
    }
  };

  const logout = () => {
    clearToken();
    navigate("/", { replace: true });
  };

  // Import flow
  const handleZipUpload = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      toast.error("Please upload a .zip file");
      return;
    }
    setImportBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const url = `${importZipUrl}${importName ? `?project_name=${encodeURIComponent(importName)}` : ""}`;
      const resp = await fetch(url, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: fd,
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || "Import failed");
      toast.success(`Imported ${data.files_count} files`);
      setPeek(PEEK.NONE);
      navigate(`/builder/${data.id}`);
    } catch (e) {
      toast.error(e.message || "Import failed");
    } finally {
      setImportBusy(false);
    }
  };

  const handleGithubImport = async (e) => {
    e.preventDefault();
    if (!repoUrl.trim()) return;
    setImportBusy(true);
    try {
      const { data } = await importGithub(repoUrl.trim(), branch.trim() || null, importName.trim());
      toast.success(`Imported ${data.files_count} files`);
      setPeek(PEEK.NONE);
      navigate(`/builder/${data.id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message || "Import failed");
    } finally {
      setImportBusy(false);
    }
  };

  // Derived
  const isAdmin = me?.role === "admin";
  const projectCount = projects.length;
  const projectLabel = useMemo(
    () => (projectCount === 0 ? "no projects yet" : `${projectCount} ${projectCount === 1 ? "project" : "projects"}`),
    [projectCount],
  );

  // ──────────────────────────────────────────────────────────────
  // Render
  // ──────────────────────────────────────────────────────────────
  return (
    <div
      className="relative min-h-screen w-full overflow-x-hidden text-white"
      style={{ background: "var(--surface-0)" }}
      data-testid="dashboard-page"
    >
      <GradientBackdrop variant="workspace" intensity="soft" />

      {/* ============================================================
          TOP HORIZONTAL NAV — Workspace · Deployments · Site Editor · Admin · Account
          Clean, premium, ChatGPT-logged-in-home feel. No floating rail.
         ============================================================ */}
      <header
        className="sticky top-0 z-30 nxt-os-in"
        style={{
          background: "linear-gradient(180deg, rgba(43,43,49,0.78) 0%, rgba(43,43,49,0.55) 100%)",
          backdropFilter: "blur(20px) saturate(140%)",
          WebkitBackdropFilter: "blur(20px) saturate(140%)",
          borderBottom: "1px solid var(--hairline)",
        }}
        data-testid="workspace-topnav"
      >
        <div className="mx-auto max-w-[1100px] px-4 sm:px-6 h-14 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 sm:gap-5 min-w-0">
            <button
              onClick={() => navigate("/")}
              className="shrink-0"
              aria-label="NXT1 home"
              title="NXT1"
              data-testid="topnav-logo"
            >
              <Brand size="md" gradient />
            </button>
            <nav className="hidden md:flex items-center gap-0.5 ml-2">
              <button className="os-pill" data-active="true" data-testid="topnav-workspace">
                Workspace
              </button>
              <button
                onClick={() => {
                  // Open most-recent project's deployment surface
                  if (projects.length > 0) {
                    const recent = [...projects].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))[0];
                    navigate(`/builder/${recent.id}?tab=deploy`);
                  } else {
                    toast.info("Start a build to see deployments");
                  }
                }}
                className="os-pill"
                data-testid="topnav-deployments"
              >
                Deployments
              </button>
              {isAdmin && (
                <button
                  onClick={() => navigate("/admin/site-editor")}
                  className="os-pill"
                  data-testid="topnav-site-editor"
                >
                  Site Editor
                </button>
              )}
              {isAdmin && (
                <button
                  onClick={() => navigate("/admin")}
                  className="os-pill"
                  data-testid="topnav-admin"
                >
                  Admin
                </button>
              )}
            </nav>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => setPeek(PEEK.IMPORT)}
              className="os-pill hidden sm:inline-flex"
              data-testid="topnav-import"
              title="Import project  ⌘I"
            >
              <Upload size={11} strokeWidth={2} /> Import
            </button>
            <button
              onClick={() => setPeek(PEEK.SETTINGS)}
              className="rail-btn"
              aria-label="Account"
              title="Account"
              data-testid="topnav-account"
            >
              <SettingsIcon size={14} strokeWidth={1.8} />
            </button>
            <button
              onClick={logout}
              className="rail-btn"
              aria-label="Sign out"
              title="Sign out"
              data-testid="topnav-logout"
            >
              <LogOut size={14} strokeWidth={1.8} />
            </button>
            <div
              className="ml-1 h-8 w-8 rounded-full flex items-center justify-center text-[11px] font-bold tracking-tight"
              style={{
                background: "linear-gradient(135deg, var(--surface-3) 0%, var(--surface-1) 100%)",
                color: "rgba(255,255,255,0.85)",
                boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.07)",
                fontFamily: "'Cabinet Grotesk', sans-serif",
              }}
              title={me?.email || "Signed in"}
              data-testid="topnav-avatar"
            >
              {(me?.email || "?").charAt(0).toUpperCase()}
            </div>
          </div>
        </div>
        {/* Mobile sub-nav row */}
        <nav className="md:hidden flex items-center gap-0.5 px-4 pb-2 overflow-x-auto no-scrollbar">
          <button className="os-pill shrink-0" data-active="true">Workspace</button>
          <button
            onClick={() => {
              if (projects.length > 0) {
                const recent = [...projects].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))[0];
                navigate(`/builder/${recent.id}?tab=deploy`);
              }
            }}
            className="os-pill shrink-0"
          >
            Deployments
          </button>
          {isAdmin && (
            <button onClick={() => navigate("/admin/site-editor")} className="os-pill shrink-0">Site Editor</button>
          )}
          {isAdmin && (
            <button onClick={() => navigate("/admin")} className="os-pill shrink-0">Admin</button>
          )}
        </nav>
      </header>

      {/* ============================================================
          MAIN COLUMN — prompt-first command center
         ============================================================ */}
      <main className="relative z-10 px-4 sm:px-6 pb-24 pt-10 sm:pt-12">
        <div className="mx-auto max-w-[920px]">

          {/* Overline + identity line */}
          <div className="flex items-center justify-between mb-5 sm:mb-7 nxt-os-in nxt-os-in-1">
            <span className="nxt-overline" data-testid="workspace-overline">
              AI WORKSPACE
              {me?.email && (
                <span className="text-white/30 ml-2 normal-case tracking-normal text-[11px]">
                  · {me.email}
                </span>
              )}
            </span>
            <span className="mono text-[10.5px] tracking-[0.22em] uppercase text-white/30 hidden sm:inline">
              {projectLabel}
            </span>
          </div>

          {/* Hero headline — quiet, single line */}
          <h1
            className="text-[36px] sm:text-[44px] lg:text-[52px] leading-[1.04] tracking-[-0.025em] font-medium mb-7 sm:mb-10 nxt-os-in nxt-os-in-2"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
            data-testid="workspace-hero"
          >
            <span className="text-white">What are we building </span>
            <span
              style={{
                background: "linear-gradient(180deg, #E8E8EE 0%, #8A8A93 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              today?
            </span>
          </h1>

          {/* ─────────────── Prompt cockpit (operational hero) ─────────────── */}
          <div
            className="relative group nxt-os-in nxt-os-in-3"
            data-testid="workspace-prompt-cockpit"
          >
            {/* Ambient glow behind input — alive on focus */}
            <div
              aria-hidden
              className="absolute -inset-x-6 -inset-y-5 rounded-[36px] blur-3xl opacity-40 group-focus-within:opacity-80 transition-opacity duration-500 pointer-events-none nxt-ambient-drift"
              style={{
                background:
                  "radial-gradient(60% 60% at 50% 100%, rgba(94,234,212,0.16) 0%, rgba(94,234,212,0) 70%), radial-gradient(60% 60% at 50% 0%, rgba(99,102,241,0.10) 0%, rgba(99,102,241,0) 70%)",
              }}
            />

            <div
              className="relative rounded-[24px] glass-1 transition-all duration-300 hover:border-white/15 focus-within:border-white/20"
              style={{ boxShadow: "var(--elev-2)" }}
            >
              <textarea
                ref={taRef}
                rows={3}
                value={draft}
                onChange={(e) => persistDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    handleBuild();
                  }
                }}
                placeholder="Describe what you want to build…"
                className="w-full bg-transparent outline-none resize-none text-[15px] sm:text-[16px] leading-[1.55] tracking-[-0.005em] px-5 sm:px-6 pt-5 pb-3 placeholder:text-white/30 text-white"
                disabled={busy}
                data-testid="workspace-prompt-input"
                style={{ fontSize: "16px" }}
              />

              {/* Build-type cards — always-visible 4-up row, no hidden scroll */}
              <div className="px-3 sm:px-4 pt-1 pb-2">
                <div
                  className="grid grid-cols-4 gap-1.5 sm:gap-2"
                  role="tablist"
                  aria-label="Build type"
                >
                  {BUILDER_MODES.map((m) => {
                    const Icon = m.icon;
                    const active = mode === m.key;
                    return (
                      <button
                        key={m.key}
                        type="button"
                        onClick={() => setMode(m.key)}
                        data-testid={`workspace-mode-${m.key}`}
                        role="tab"
                        aria-selected={active}
                        className="relative flex flex-col items-center justify-center gap-1.5 px-1 py-2.5 rounded-2xl transition-all duration-200"
                        style={
                          active
                            ? {
                                background: "linear-gradient(180deg, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.04) 100%)",
                                boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.10), 0 8px 24px -10px rgba(255,255,255,0.18)",
                                color: "#fff",
                              }
                            : {
                                background: "transparent",
                                boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.04)",
                                color: "rgba(255,255,255,0.5)",
                              }
                        }
                      >
                        <Icon size={15} strokeWidth={1.7} className={active ? "text-white" : ""} />
                        <span className="text-[11px] sm:text-[12px] font-medium tracking-tight whitespace-nowrap">
                          {m.label}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Action row — provider picker + Build CTA */}
              <div className="flex items-center justify-between gap-2 px-3 sm:px-4 pb-3 pt-1">
                <div className="flex-1 min-w-0">
                  <ModelPickerCockpit
                    value={provider}
                    onChange={setProvider}
                    providers={{ emergent: true, anthropic: true }}
                    compact
                  />
                </div>
                <button
                  type="button"
                  onClick={handleBuild}
                  disabled={!draft.trim() || busy}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-[13px] font-semibold tracking-tight bg-white text-[#1F1F23] hover:bg-white/95 transition-all duration-200 shadow-[0_8px_28px_-10px_rgba(255,255,255,0.55)] hover:shadow-[0_14px_42px_-10px_rgba(255,255,255,0.75)] hover:-translate-y-0.5 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:shadow-none shrink-0"
                  data-testid="workspace-build-button"
                >
                  {busy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                  {busy ? "Starting…" : "Build"}
                </button>
              </div>
            </div>

            {/* Helper line — quiet shortcuts */}
            <div className="mt-4 flex items-center justify-center gap-5 mono text-[10px] tracking-[0.22em] uppercase text-white/30">
              <span className="inline-flex items-center gap-1.5">
                <CornerDownLeft size={11} /> ⌘ + ↵ to build
              </span>
              <span className="opacity-50">·</span>
              <span className="inline-flex items-center gap-1.5">
                <Upload size={11} /> ⌘ + I to import
              </span>
            </div>
          </div>

          {/* ─────────────── Recent projects (quiet grid) ─────────────── */}
          <div className="mt-16 sm:mt-20 nxt-os-in nxt-os-in-4">
            <div className="flex items-center gap-4 mb-5">
              <span className="nxt-overline">RECENT</span>
              <span className="h-px flex-1 bg-white/5" />
              <span className="mono text-[10px] tracking-[0.22em] uppercase text-white/30">
                {projectLabel}
              </span>
            </div>

            {loading ? (
              <ProjectGridSkeleton />
            ) : projects.length === 0 ? (
              <EmptyState onImport={() => setPeek(PEEK.IMPORT)} onFocus={() => taRef.current?.focus()} />
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
                {projects.map((p) => (
                  <ProjectCard
                    key={p.id}
                    project={p}
                    onOpen={() => navigate(`/builder/${p.id}`)}
                    onDelete={(e) => handleDelete(p.id, e)}
                  />
                ))}
              </div>
            )}
          </div>

        </div>
      </main>

      {/* ============================================================
          PEEK PANEL — right contextual sheet (import / settings)
         ============================================================ */}
      {peek === PEEK.IMPORT && (
        <PeekPanel onClose={() => !importBusy && setPeek(PEEK.NONE)} title="Import a project" subtitle="Bring an existing repo or zip into the workspace">
          <ImportPanelBody
            mode={importMode}
            setMode={setImportMode}
            busy={importBusy}
            importName={importName}
            setImportName={setImportName}
            repoUrl={repoUrl}
            setRepoUrl={setRepoUrl}
            branch={branch}
            setBranch={setBranch}
            zipInputRef={zipInputRef}
            onZipChoose={() => zipInputRef.current?.click()}
            onZipChange={(e) => handleZipUpload(e.target.files?.[0])}
            onGithubSubmit={handleGithubImport}
          />
        </PeekPanel>
      )}

      {/* Settings remains its own existing component for parity */}
      <SettingsSheet
        open={peek === PEEK.SETTINGS}
        onClose={() => setPeek(PEEK.NONE)}
      />

      {/* Scrim when peek is open (graphite, never pure black) */}
      {peek === PEEK.IMPORT && (
        <div
          className="fixed inset-0 z-50 scrim-soft cursor-pointer"
          onClick={() => !importBusy && setPeek(PEEK.NONE)}
          data-testid="peek-scrim"
        />
      )}
    </div>
  );
}

/* ============================================================================
   Subcomponents
   ============================================================================ */

function ProjectCard({ project: p, onOpen, onDelete }) {
  return (
    <div
      onClick={onOpen}
      className="glow-hover relative rounded-2xl p-5 min-h-[140px] flex flex-col justify-between cursor-pointer group"
      style={{
        background: "linear-gradient(180deg, var(--surface-2) 0%, var(--surface-1) 100%)",
        boxShadow: "var(--elev-1)",
      }}
      data-testid={`project-card-${p.id}`}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          <div
            className="h-9 w-9 rounded-xl flex items-center justify-center text-[14px] font-bold shrink-0"
            style={{
              background: p.deployed
                ? "linear-gradient(135deg, #5EEAD4 0%, #6366F1 100%)"
                : "linear-gradient(135deg, var(--surface-4) 0%, var(--surface-2) 100%)",
              color: p.deployed ? "#1F1F23" : "rgba(255,255,255,0.7)",
              fontFamily: "'Cabinet Grotesk', sans-serif",
              boxShadow: p.deployed
                ? "0 8px 24px -10px rgba(94,234,212,0.5)"
                : "inset 0 0 0 1px rgba(255,255,255,0.06)",
            }}
            data-testid={`project-avatar-${p.id}`}
          >
            {(p.name || "?").charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div
              className="text-[15px] font-semibold tracking-tight leading-tight truncate"
              style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
            >
              {p.name}
            </div>
            {p.description && (
              <div className="text-white/40 text-[12px] mt-0.5 line-clamp-1 leading-snug">
                {p.description}
              </div>
            )}
          </div>
        </div>
        <button
          onClick={onDelete}
          className="opacity-0 group-hover:opacity-100 transition text-white/40 hover:text-red-300 p-1 -mr-1 shrink-0"
          data-testid={`project-delete-${p.id}`}
          aria-label="Delete project"
        >
          <Trash2 size={13} />
        </button>
      </div>
      <div className="flex items-center justify-between text-[10.5px] mono uppercase tracking-[0.18em] text-white/35">
        <span>
          {new Date(p.updated_at).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
          })}
        </span>
        <span className="flex items-center gap-1.5">
          {p.deployed ? (
            <>
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 nxt-pulse" />
              <span className="text-emerald-300/90">LIVE</span>
            </>
          ) : (
            <>
              <span className="h-1.5 w-1.5 rounded-full bg-white/20" />
              <span>DRAFT</span>
            </>
          )}
        </span>
      </div>
    </div>
  );
}

function ProjectGridSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="rounded-2xl p-5 min-h-[140px] animate-pulse"
          style={{ background: "var(--surface-1)" }}
        >
          <div className="h-3 w-20 bg-white/8 rounded mb-4" />
          <div className="h-5 w-3/4 bg-white/8 rounded" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({ onImport, onFocus }) {
  return (
    <div
      className="rounded-2xl p-10 sm:p-12 flex flex-col items-center justify-center text-center nxt-os-in"
      style={{
        background:
          "radial-gradient(80% 80% at 50% 0%, rgba(94,234,212,0.06) 0%, rgba(94,234,212,0) 60%), var(--surface-1)",
        boxShadow: "inset 0 0 0 1px var(--hairline)",
      }}
      data-testid="dashboard-empty-state"
    >
      <div className="h-12 w-12 rounded-2xl flex items-center justify-center mb-4"
        style={{
          background: "linear-gradient(135deg, var(--surface-3) 0%, var(--surface-1) 100%)",
          boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.06)",
        }}
      >
        <Sparkles size={18} className="text-[#5EEAD4]" />
      </div>
      <h3
        className="text-[18px] font-semibold tracking-tight mb-1.5"
        style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
      >
        Your workspace is quiet.
      </h3>
      <p className="text-[13px] text-white/45 max-w-sm leading-relaxed mb-5">
        Describe an app above to start your first build, or bring an existing repo in.
      </p>
      <div className="flex items-center gap-2">
        <button
          onClick={onFocus}
          className="os-pill"
          data-active="true"
          data-testid="empty-focus-prompt"
        >
          <Sparkles size={12} /> Start with a prompt
        </button>
        <button
          onClick={onImport}
          className="os-pill"
          data-testid="empty-import"
        >
          <Upload size={12} /> Import a project
        </button>
      </div>
    </div>
  );
}

function PeekPanel({ children, onClose, title, subtitle }) {
  return (
    <aside
      className="peek-panel"
      data-open="true"
      data-testid="peek-panel"
      role="dialog"
    >
      <div className="h-full flex flex-col">
        <div className="px-6 pt-5 pb-4 border-b border-white/5 flex items-start justify-between gap-3">
          <div>
            <h2
              className="text-[18px] font-semibold tracking-tight"
              style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
            >
              {title}
            </h2>
            {subtitle && (
              <p className="text-[12px] text-white/45 mt-0.5">{subtitle}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rail-btn"
            aria-label="Close"
            data-testid="peek-close"
          >
            <X size={15} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </div>
    </aside>
  );
}

function ImportPanelBody({
  mode, setMode, busy, importName, setImportName,
  repoUrl, setRepoUrl, branch, setBranch,
  zipInputRef, onZipChoose, onZipChange, onGithubSubmit,
}) {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-1.5 p-1 rounded-xl"
        style={{ background: "var(--surface-1)", boxShadow: "inset 0 0 0 1px var(--hairline)" }}
      >
        <button
          type="button"
          onClick={() => setMode("zip")}
          data-active={mode === "zip"}
          className="os-pill justify-center"
          data-testid="import-mode-zip"
        >
          <FileArchive size={13} /> ZIP upload
        </button>
        <button
          type="button"
          onClick={() => setMode("github")}
          data-active={mode === "github"}
          className="os-pill justify-center"
          data-testid="import-mode-github"
        >
          <Github size={13} /> GitHub URL
        </button>
      </div>

      <div>
        <label className="nxt-overline block mb-1.5">Project name (optional)</label>
        <input
          value={importName}
          onChange={(e) => setImportName(e.target.value)}
          placeholder="My imported project"
          className="nxt-input"
          data-testid="import-name-input"
        />
      </div>

      {mode === "zip" ? (
        <>
          <input
            ref={zipInputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={onZipChange}
            data-testid="import-zip-input"
          />
          <button
            onClick={onZipChoose}
            disabled={busy}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-[13px] font-semibold bg-white text-[#1F1F23] hover:bg-white/95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="import-zip-button"
          >
            {busy ? (
              <><Loader2 size={14} className="animate-spin" /> Importing…</>
            ) : (
              <><Upload size={14} /> Choose .zip file</>
            )}
          </button>
          <p className="text-[12px] text-white/40 leading-relaxed">
            We'll skip <span className="mono text-white/55">node_modules</span>, <span className="mono text-white/55">.git</span>, build dirs and binary files. Max 30 MB. NXT1 will detect frameworks, routes, env vars, and dependencies automatically.
          </p>
        </>
      ) : (
        <form onSubmit={onGithubSubmit} className="space-y-3">
          <div>
            <label className="nxt-overline block mb-1.5">GitHub URL</label>
            <input
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              className="nxt-input mono"
              data-testid="import-github-url"
            />
          </div>
          <div>
            <label className="nxt-overline block mb-1.5">Branch (optional)</label>
            <input
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="main"
              className="nxt-input mono"
              data-testid="import-github-branch"
            />
          </div>
          <button
            type="submit"
            disabled={busy || !repoUrl.trim()}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-[13px] font-semibold bg-white text-[#1F1F23] hover:bg-white/95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="import-github-submit"
          >
            {busy ? (
              <><Loader2 size={14} className="animate-spin" /> Cloning…</>
            ) : (
              <><Github size={14} /> Import from GitHub</>
            )}
          </button>
          <p className="text-[12px] text-white/40 leading-relaxed">
            Public repos only. We shallow-clone (depth 1) and skip build dirs.
          </p>
        </form>
      )}
    </div>
  );
}
