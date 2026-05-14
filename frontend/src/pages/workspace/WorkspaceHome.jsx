/**
 * NXT1 — Workspace Home (Claude/ChatGPT/Blink-style anchored composer)
 *
 * Hero greeting + suggestions occupy the top of the canvas; the composer
 * sits anchored along the bottom with safe-area padding (Claude/ChatGPT
 * feel). Suggestions adapt to the selected mode (Full Stack / Website /
 * Mobile / Extension). No metrics, no sidebars, no recents.
 */
import { useEffect, useMemo, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";
import {
  Sparkles,
  Layers,
  Smartphone,
  Puzzle,
  Globe,
  ArrowUp,
  Loader2,
  UploadCloud,
  Github,
  LayoutTemplate,
} from "lucide-react";
import { createProject, userMe, startWorkflow } from "@/lib/api";
import api, { importZipUrl, listScaffolds } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { friendlyError } from "@/lib/errors";

// Curated starter prompts for each scaffold — feeds the build immediately so
// users don't sit on an empty template; the foundation loads + chat fires.
const TEMPLATE_STARTER_PROMPTS = {
  "react-vite":              "A modern React + Vite single-page web app with a clean hero, feature grid, and footer.",
  "nextjs-tailwind":         "A Next.js 15 SaaS app with a landing page, dashboard route, and Tailwind-styled components.",
  "fullstack-fastapi-react": "A full-stack FastAPI + React app with a backend health endpoint and a frontend that calls it.",
  "fastapi-backend":         "A FastAPI backend service with auth, a sample CRUD resource, and /api/health.",
  "express-backend":         "An Express.js backend with JSON middleware, /api/health, and a sample CRUD route.",
  "expo-rn":                 "An Expo React Native mobile app with a tab bar and three starter screens.",
  "browser-extension":       "A Chrome Manifest V3 extension with a polished popup UI and persistent storage.",
  "ai-chat-streaming":       "An AI chat app with streaming responses, model picker, and message history.",
  "dashboard":               "A premium admin dashboard with KPI cards, a chart, and a recent-activity table.",
  "portfolio":               "A premium developer portfolio with hero, projects grid, about, and contact section.",
  "landing":                 "A premium SaaS landing page with hero, feature grid, pricing, and waitlist form.",
  "db-app":                  "A web app backed by a database with CRUD over a sample resource and a polished UI.",
};

const MODES = [
  { id: "fullstack", label: "Full Stack", icon: Layers     },
  { id: "website",   label: "Website",    icon: Globe      },
  { id: "mobile",    label: "Mobile",     icon: Smartphone },
  { id: "extension", label: "Extension",  icon: Puzzle     },
];

// Adaptive suggestion library — chips below the composer change with mode.
const SUGGESTIONS = {
  fullstack: [
    { label: "SaaS dashboard",    prompt: "Build a SaaS dashboard with auth, billing, and an admin panel." },
    { label: "AI platform",       prompt: "Build an AI platform with prompt history, model picker, and team sharing." },
    { label: "Admin system",      prompt: "Build an internal admin system with role-based access and audit logs." },
  ],
  website: [
    { label: "Portfolio",         prompt: "Design a premium developer portfolio with hero, projects, and contact form." },
    { label: "Marketing launch",  prompt: "Build a marketing launch page with waitlist signup and feature grid." },
    { label: "Docs site",         prompt: "Build a modern documentation site with sidebar nav and code samples." },
  ],
  mobile: [
    { label: "Fitness app",       prompt: "Build a mobile fitness app with workout tracking and progress charts." },
    { label: "AI chat app",       prompt: "Build a mobile AI chat companion with streaming responses." },
    { label: "Social app",        prompt: "Build a mobile social app with feed, profiles, and messaging." },
  ],
  extension: [
    { label: "Productivity",      prompt: "Build a Chrome productivity extension to summarise any open tab." },
    { label: "AI sidebar",        prompt: "Build a Chrome AI sidebar that answers questions about the current page." },
    { label: "Tab manager",       prompt: "Build a Chrome tab manager with groups, search, and snooze." },
  ],
};

const CYCLE_PROMPTS = {
  fullstack: [
    "A SaaS dashboard with billing…",
    "An AI platform with prompt history…",
    "An admin system with role-based access…",
  ],
  website: [
    "A premium portfolio with hero, projects, and contact…",
    "A marketing launch page with a waitlist…",
    "A documentation site with sidebar nav and code samples…",
  ],
  mobile: [
    "A fitness tracker with workouts and charts…",
    "A mobile AI chat companion…",
    "A social app with feed and messaging…",
  ],
  extension: [
    "A Chrome extension that summarises any tab…",
    "An AI sidebar for the current page…",
    "A tab manager with groups and snooze…",
  ],
};

export default function WorkspaceHome() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState("fullstack");
  const [submitting, setSubmitting] = useState(false);
  const [phIdx, setPhIdx] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [importing, setImporting] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importTab, setImportTab] = useState("zip"); // zip | github
  const [repoUrl, setRepoUrl] = useState("");
  // Templates gallery state
  const [showTemplates, setShowTemplates] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  // ZIP upload progress (0-100, null = idle)
  const [uploadProgress, setUploadProgress] = useState(null);
  const taRef = useRef(null);
  const fileInputRef = useRef(null);

  // Load template catalogue lazily on first open of the sheet
  useEffect(() => {
    if (!showTemplates || templates.length > 0) return;
    setTemplatesLoading(true);
    listScaffolds()
      .then(({ data }) => setTemplates(data.scaffolds || []))
      .catch(() => setTemplates([]))
      .finally(() => setTemplatesLoading(false));
  }, [showTemplates, templates.length]);

  // Start a brand-new build from a chosen template — fast-path:
  // creates the project, then jumps to the Builder with the starter prompt
  // pre-filled so generation begins immediately on landing.
  const handleStartFromTemplate = async (tpl) => {
    if (submitting) return;
    setSubmitting(true);
    setShowTemplates(false);
    try {
      const starter = TEMPLATE_STARTER_PROMPTS[tpl.id] || `Build a ${tpl.label}.`;
      const { data } = await createProject({
        name: tpl.label,
        prompt: starter,
        mode,
        scaffold_id: tpl.id,           // hint for the inferencer / generation pipeline
        framework: tpl.framework,
      });
      // Auto-start the durable workflow alongside the chat stream.
      startWorkflow(data.id, starter, "internal").catch(() => {});
      navigate(`/builder/${data.id}?prompt=${encodeURIComponent(starter)}&mode=${mode}&scaffold=${tpl.id}`);
    } catch (e) {
      const fe = friendlyError(e?.response?.data?.detail || "Couldn't start that template.");
      toast.error(fe.title, { description: fe.hint });
    } finally {
      setSubmitting(false);
    }
  };

  const handleZipFile = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      toast.error("Please drop a .zip archive");
      return;
    }
    setImporting(true);
    setUploadProgress(0);
    try {
      // Use XHR so we can wire real upload progress — fetch() doesn't
      // expose `upload.onprogress`. Falls through to the same backend
      // endpoint as the regular import flow.
      const data = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const fd = new FormData();
        fd.append("file", file);
        const url = `${importZipUrl}?project_name=${encodeURIComponent(file.name.replace(/\.zip$/i, ""))}`;
        xhr.open("POST", url);
        xhr.setRequestHeader("Authorization", `Bearer ${getToken()}`);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            // Cap visual at 92% while the backend is still indexing — we
            // ease the rest of the way once the response lands.
            setUploadProgress(Math.min(92, pct));
          }
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              setUploadProgress(100);
              resolve(JSON.parse(xhr.responseText));
            } catch (err) { reject(err); }
          } else {
            reject(new Error(xhr.responseText || `HTTP ${xhr.status}`));
          }
        };
        xhr.onerror = () => reject(new Error("Network error during upload"));
        xhr.send(fd);
      });
      toast.success(`Imported ${data.files_count} files`, {
        description: `Detected ${data.framework || "auto-framework"} · opening ${data.name}…`,
      });
      navigate(`/builder/${data.id}`);
    } catch (e) {
      const fe = friendlyError(e?.message || "ZIP import failed");
      toast.error(fe.title, { description: fe.hint });
    } finally {
      setImporting(false);
      setUploadProgress(null);
      setShowImport(false);
    }
  };

  const handleGithubImport = async () => {
    const url = repoUrl.trim();
    if (!url) return;
    setImporting(true);
    try {
      const { data } = await api.post("/projects/import/github", { repo_url: url });
      toast.success(`Imported ${data.files_count} files`, {
        description: `Opening ${data.name}…`,
      });
      navigate(`/builder/${data.id}`);
    } catch (e) {
      const fe = friendlyError(e?.response?.data?.detail || e?.message || "GitHub import failed");
      toast.error(fe.title, { description: fe.hint });
    } finally {
      setImporting(false);
      setShowImport(false);
    }
  };

  useEffect(() => {
    try {
      const draft = window.localStorage.getItem("nxt1_draft_prompt");
      if (draft) {
        setPrompt(draft);
        window.localStorage.removeItem("nxt1_draft_prompt");
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    userMe().then(({ data }) => setUser(data)).catch(() => {});
  }, []);

  // Cycle placeholder every 4.2s — pauses when user has typed something.
  useEffect(() => {
    if (prompt) return;
    const t = setInterval(() => setPhIdx((i) => i + 1), 4200);
    return () => clearInterval(t);
  }, [prompt]);

  const cycle = CYCLE_PROMPTS[mode] || CYCLE_PROMPTS.fullstack;
  const placeholder = cycle[phIdx % cycle.length];
  const suggestions = SUGGESTIONS[mode] || SUGGESTIONS.fullstack;

  const handleSubmit = async () => {
    const trimmed = prompt.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    try {
      const { data } = await createProject({
        name: trimmed.slice(0, 60),
        prompt: trimmed,
        mode,
      });
      // Auto-start the durable build pipeline so the planner/architect/coder
      // workflow lights up alongside the chat stream — visible inside
      // Builder → Tools → Build pipeline.
      startWorkflow(data.id, trimmed, "internal").catch(() => {});
      navigate(`/builder/${data.id}?prompt=${encodeURIComponent(trimmed)}&mode=${mode}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't start your build.");
    } finally {
      setSubmitting(false);
    }
  };

  const greeting = useMemo(() => {
    const name = (user?.name || user?.email || "").split("@")[0] || "";
    const hour = new Date().getHours();
    const part = hour < 6 ? "Late" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
    return name ? `${part}, ${name.split(".")[0]}.` : `${part}.`;
  }, [user]);

  return (
    <div
      className="relative h-full w-full flex flex-col"
      data-testid="workspace-home"
      onDragEnter={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragOver={(e) => { e.preventDefault(); }}
      onDragLeave={(e) => {
        // Only clear when leaving the container entirely (not entering a child)
        if (e.currentTarget === e.target) setDragOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const f = e.dataTransfer?.files?.[0];
        if (f) handleZipFile(f);
      }}
    >
      {/* Drag-drop overlay — fullscreen, only visible while user is dragging a zip */}
      <AnimatePresence>
        {(dragOver || importing) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="absolute inset-0 z-50 flex items-center justify-center p-8 pointer-events-none"
            style={{
              background: "var(--scrim)",
              backdropFilter: "blur(8px)",
            }}
            data-testid="workspace-drop-overlay"
          >
            <div
              className="rounded-3xl px-8 py-10 text-center max-w-[420px] w-full"
              style={{
                background: "var(--nxt-surface)",
                border: "2px dashed var(--nxt-accent-border)",
                boxShadow: "var(--nxt-shadow-lg)",
              }}
            >
              <span
                className="h-12 w-12 mx-auto rounded-full flex items-center justify-center mb-4"
                style={{
                  background: "var(--nxt-accent-bg)",
                  border: "1px solid var(--nxt-accent-border)",
                }}
              >
                {importing
                  ? <Loader2 size={20} className="animate-spin" style={{ color: "var(--nxt-accent)" }} />
                  : <UploadCloud size={20} style={{ color: "var(--nxt-accent)" }} />
                }
              </span>
              <h3
                className="text-[16px] font-semibold tracking-tight mb-1"
                style={{ color: "var(--nxt-fg)" }}
              >
                {importing ? "Importing your project…" : "Drop a .zip to import"}
              </h3>
              <p className="text-[13px]" style={{ color: "var(--nxt-fg-dim)" }}>
                {importing
                  ? "Reading files, detecting the framework, building the workspace."
                  : "NXT1 will detect the framework and scaffold the workspace automatically."}
              </p>
              {/* Real upload progress bar — only visible while a transfer is active */}
              {importing && uploadProgress !== null && (
                <div className="mt-4">
                  <div
                    className="h-1.5 w-full rounded-full overflow-hidden"
                    style={{ background: "var(--nxt-chip-bg)" }}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-200"
                      style={{
                        width: `${uploadProgress}%`,
                        background: "var(--nxt-accent)",
                      }}
                    />
                  </div>
                  <div
                    className="mt-2 mono text-[10.5px] tracking-[0.2em] uppercase text-center"
                    style={{ color: "var(--nxt-fg-faint)" }}
                  >
                    {uploadProgress < 100 ? `${uploadProgress}% uploaded` : "indexing files…"}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Import sheet (zip upload + github URL) — opens via the "Import" pill */}
      <AnimatePresence>
        {showImport && !dragOver && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="absolute inset-0 z-40 flex items-center justify-center p-6"
            style={{
              background: "var(--scrim)",
              backdropFilter: "blur(8px)",
            }}
            onClick={() => !importing && setShowImport(false)}
            data-testid="workspace-import-sheet"
          >
            <div
              onClick={(e) => e.stopPropagation()}
              className="rounded-2xl p-5 sm:p-6 w-full max-w-[460px]"
              style={{
                background: "var(--nxt-surface)",
                border: "1px solid var(--nxt-border)",
                boxShadow: "var(--nxt-shadow-lg)",
              }}
            >
              <div className="flex items-center gap-2 mb-1">
                <span
                  className="mono text-[10px] tracking-[0.22em] uppercase"
                  style={{ color: "var(--nxt-fg-faint)" }}
                >
                  // import existing project
                </span>
              </div>
              <h3
                className="text-[20px] font-semibold tracking-tight mb-1"
                style={{ color: "var(--nxt-fg)", fontFamily: "'Cabinet Grotesk', sans-serif" }}
              >
                Bring your code in.
              </h3>
              <p className="text-[13px] mb-4" style={{ color: "var(--nxt-fg-dim)" }}>
                Upload a .zip or paste a public GitHub URL — NXT1 detects the framework and gets you previewing.
              </p>
              <div
                className="inline-flex p-0.5 rounded-full mb-4"
                style={{
                  background: "var(--nxt-chip-bg)",
                  border: "1px solid var(--nxt-border-soft)",
                }}
              >
                {["zip", "github"].map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setImportTab(t)}
                    className="px-3 py-1.5 rounded-full text-[12px] font-medium transition"
                    style={{
                      background: importTab === t ? "var(--nxt-surface)" : "transparent",
                      color: importTab === t ? "var(--nxt-fg)" : "var(--nxt-fg-faint)",
                      boxShadow: importTab === t ? "var(--nxt-shadow-sm)" : "none",
                    }}
                    data-testid={`workspace-import-tab-${t}`}
                  >
                    {t === "zip" ? "Upload ZIP" : "GitHub URL"}
                  </button>
                ))}
              </div>

              {importTab === "zip" ? (
                <div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".zip"
                    className="hidden"
                    onChange={(e) => handleZipFile(e.target.files?.[0])}
                    data-testid="workspace-import-zip-input"
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={importing}
                    className="w-full inline-flex items-center justify-center gap-2 h-12 rounded-2xl text-[14px] font-medium transition disabled:opacity-60"
                    style={{
                      background: "var(--nxt-accent)",
                      color: "var(--nxt-bg)",
                    }}
                    data-testid="workspace-import-zip-button"
                  >
                    {importing
                      ? <Loader2 size={14} className="animate-spin" />
                      : <UploadCloud size={14} strokeWidth={2.4} />
                    }
                    {importing ? "Importing…" : "Choose .zip file"}
                  </button>
                  <p
                    className="text-[11.5px] mt-3 text-center"
                    style={{ color: "var(--nxt-fg-faint)" }}
                  >
                    or drag-and-drop anywhere on this page.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 px-3 h-12 rounded-2xl"
                    style={{
                      background: "var(--nxt-surface-soft)",
                      border: "1px solid var(--nxt-border)",
                    }}
                  >
                    <Github size={14} style={{ color: "var(--nxt-fg-faint)" }} />
                    <input
                      type="url"
                      value={repoUrl}
                      onChange={(e) => setRepoUrl(e.target.value)}
                      placeholder="https://github.com/owner/repo"
                      className="flex-1 bg-transparent outline-none text-[14px]"
                      style={{ color: "var(--nxt-fg)" }}
                      data-testid="workspace-import-github-url"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleGithubImport}
                    disabled={importing || !repoUrl.trim()}
                    className="w-full inline-flex items-center justify-center gap-2 h-12 rounded-2xl text-[14px] font-medium transition disabled:opacity-60"
                    style={{
                      background: "var(--nxt-accent)",
                      color: "var(--nxt-bg)",
                    }}
                    data-testid="workspace-import-github-button"
                  >
                    {importing
                      ? <Loader2 size={14} className="animate-spin" />
                      : <Github size={14} strokeWidth={2.4} />
                    }
                    {importing ? "Cloning…" : "Import from GitHub"}
                  </button>
                </div>
              )}

              <button
                type="button"
                onClick={() => !importing && setShowImport(false)}
                disabled={importing}
                className="block mx-auto mt-4 text-[12px] transition"
                style={{ color: "var(--nxt-fg-faint)" }}
              >
                Cancel
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Templates gallery sheet — 12 pre-cached production scaffolds.
          Tap a card to instantly spin up a new project with that foundation
          pre-loaded and a curated starter prompt already in the chat queue. */}
      <AnimatePresence>
        {showTemplates && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="absolute inset-0 z-40 flex items-center justify-center p-4 sm:p-6"
            style={{
              background: "var(--scrim)",
              backdropFilter: "blur(8px)",
            }}
            onClick={() => !submitting && setShowTemplates(false)}
            data-testid="workspace-templates-sheet"
          >
            <div
              onClick={(e) => e.stopPropagation()}
              className="rounded-2xl w-full max-w-[860px] max-h-[90vh] flex flex-col"
              style={{
                background: "var(--nxt-surface)",
                border: "1px solid var(--nxt-border)",
                boxShadow: "var(--nxt-shadow-lg)",
              }}
            >
              <div
                className="px-5 sm:px-6 pt-5 pb-4 border-b"
                style={{ borderColor: "var(--hairline)" }}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="mono text-[10px] tracking-[0.22em] uppercase"
                    style={{ color: "var(--nxt-fg-faint)" }}
                  >
                    // template gallery
                  </span>
                </div>
                <h3
                  className="text-[22px] sm:text-[24px] font-semibold tracking-tight"
                  style={{ color: "var(--nxt-fg)", fontFamily: "'Cabinet Grotesk', sans-serif" }}
                >
                  Pick a foundation. Ship today.
                </h3>
                <p className="text-[13px] mt-1" style={{ color: "var(--nxt-fg-dim)" }}>
                  Every template is production-ready and pre-cached — your build starts in milliseconds.
                </p>
              </div>

              <div className="flex-1 overflow-y-auto p-4 sm:p-5">
                {templatesLoading && (
                  <div className="flex items-center justify-center py-12" style={{ color: "var(--nxt-fg-faint)" }}>
                    <Loader2 size={16} className="animate-spin mr-2" />
                    <span className="text-[13px]">Loading templates…</span>
                  </div>
                )}
                {!templatesLoading && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {templates.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => handleStartFromTemplate(t)}
                        disabled={submitting}
                        className="group text-left rounded-xl p-4 transition disabled:opacity-60"
                        style={{
                          background: "var(--nxt-surface-soft)",
                          border: "1px solid var(--nxt-border-soft)",
                        }}
                        data-testid={`template-card-${t.id}`}
                      >
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <span
                            className="h-8 w-8 rounded-lg flex items-center justify-center shrink-0"
                            style={{
                              background: "var(--nxt-accent-bg)",
                              border: "1px solid var(--nxt-accent-border)",
                            }}
                          >
                            <LayoutTemplate size={14} style={{ color: "var(--nxt-accent)" }} />
                          </span>
                          {(t.capabilities || []).slice(0, 1).map((c) => (
                            <span
                              key={c}
                              className="mono text-[9px] tracking-[0.22em] uppercase px-1.5 py-0.5 rounded-full"
                              style={{
                                background: "var(--nxt-chip-bg)",
                                color: "var(--nxt-fg-faint)",
                                border: "1px solid var(--nxt-border-soft)",
                              }}
                            >
                              {c}
                            </span>
                          ))}
                        </div>
                        <div
                          className="text-[14.5px] font-semibold tracking-tight mb-0.5"
                          style={{ color: "var(--nxt-fg)" }}
                        >
                          {t.label}
                        </div>
                        <div
                          className="text-[11.5px] mono mb-2"
                          style={{ color: "var(--nxt-fg-faint)" }}
                        >
                          {t.framework}
                        </div>
                        <div
                          className="text-[12px] leading-relaxed line-clamp-2"
                          style={{ color: "var(--nxt-fg-dim)" }}
                        >
                          {t.notes || `Production-grade ${t.framework} starter.`}
                        </div>
                        <div
                          className="mt-3 inline-flex items-center gap-1 text-[11px] mono tracking-wide opacity-0 group-hover:opacity-100 transition"
                          style={{ color: "var(--nxt-accent)" }}
                        >
                          Start build →
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div
                className="px-5 sm:px-6 py-3 border-t flex items-center justify-between"
                style={{ borderColor: "var(--hairline)" }}
              >
                <span
                  className="mono text-[10.5px] tracking-[0.22em] uppercase"
                  style={{ color: "var(--nxt-fg-faint)" }}
                >
                  {templates.length} templates · pre-cached
                </span>
                <button
                  type="button"
                  onClick={() => !submitting && setShowTemplates(false)}
                  className="text-[12.5px] transition"
                  style={{ color: "var(--nxt-fg-dim)" }}
                >
                  Close
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Hero zone — vertically centered in the empty area above composer */}
      <div className="flex-1 min-h-0 flex flex-col items-center justify-center px-5 sm:px-6 py-6">
        <div className="max-w-[680px] w-full text-center">
          <div
            className="mono text-[10px] tracking-[0.28em] uppercase mb-3"
            style={{ color: "var(--nxt-fg-faint)" }}
            data-testid="home-greeting-overline"
          >
            {greeting}
          </div>
          <motion.h1
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45 }}
            className="text-[32px] sm:text-[44px] font-semibold tracking-tight leading-[1.05] mb-3"
            style={{ color: "var(--nxt-fg)" }}
            data-testid="home-hero"
          >
            What will you build today?
          </motion.h1>
          <p
            className="text-[13.5px] sm:text-[14.5px] leading-relaxed max-w-[520px] mx-auto"
            style={{ color: "var(--nxt-fg-dim)" }}
          >
            Pick a build type and describe it — NXT1 will scaffold, generate, preview and ship it.
          </p>
          <div className="mt-5 flex items-center justify-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => setShowImport(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] transition"
              style={{
                background: "transparent",
                border: "1px dashed var(--nxt-border)",
                color: "var(--nxt-fg-dim)",
              }}
              data-testid="workspace-import-trigger"
            >
              <UploadCloud size={11} strokeWidth={2.2} />
              Import existing project
              <span className="opacity-50">·</span>
              <span className="opacity-80">ZIP or GitHub</span>
            </button>
            {/* Template gallery is intentionally hidden from end users — the
                12 scaffolds are selected internally by NXT1's inference layer
                based on the prompt + chosen mode. The visible "Start from a
                template" pill was removed per user direction. */}
          </div>
        </div>
      </div>

      {/* Bottom-anchored composer zone — Claude/ChatGPT feel.
          `mt-auto` pushes this to the bottom of the flex column regardless
          of the surrounding scroll container's height behaviour. */}
      <div
        className="mt-auto shrink-0 px-3 sm:px-4 pt-3"
        style={{
          background: "linear-gradient(180deg, transparent 0%, var(--nxt-bg) 30%)",
          paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 14px)",
        }}
        data-testid="home-composer-zone"
      >
        <div className="mx-auto max-w-[760px]">
          {/* Mode pills row */}
          <div
            className="grid grid-cols-4 gap-1.5 sm:gap-2 mb-2.5"
            role="tablist"
            aria-label="Build type"
            data-testid="home-mode-row"
          >
            {MODES.map((m) => {
              const Icon = m.icon;
              const active = mode === m.id;
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setMode(m.id)}
                  role="tab"
                  aria-selected={active}
                  className="relative inline-flex items-center justify-center gap-2 h-10 rounded-full text-[12.5px] font-medium tracking-tight transition-all"
                  style={active
                    ? {
                        background: "var(--nxt-accent-bg)",
                        border: "1px solid var(--nxt-accent-border)",
                        color: "var(--nxt-fg)",
                        boxShadow: "inset 0 0 0 1px var(--nxt-accent-border)",
                      }
                    : {
                        background: "var(--nxt-chip-bg)",
                        border: "1px solid var(--nxt-chip-border)",
                        color: "var(--nxt-fg-dim)",
                      }}
                  data-testid={`home-mode-${m.id}`}
                >
                  <Icon size={13} style={{ color: active ? "var(--nxt-accent)" : "currentColor" }} />
                  <span>{m.label}</span>
                </button>
              );
            })}
          </div>

          {/* Adaptive suggestion chips — change with mode */}
          <div
            className="flex flex-wrap gap-1.5 mb-2.5"
            data-testid="home-suggestion-chips"
          >
            {suggestions.map((s) => (
              <button
                key={s.label}
                type="button"
                onClick={() => {
                  setPrompt(s.prompt);
                  setTimeout(() => taRef.current?.focus(), 30);
                }}
                className="inline-flex items-center gap-1.5 px-3 h-8 rounded-full text-[11.5px] transition"
                style={{
                  background: "var(--nxt-surface-soft)",
                  border: "1px solid var(--nxt-border-soft)",
                  color: "var(--nxt-fg-dim)",
                }}
                data-testid={`home-suggest-${s.label.toLowerCase().replace(/\s+/g, "-")}`}
              >
                <Sparkles size={10} style={{ color: "var(--nxt-accent)" }} />
                {s.label}
              </button>
            ))}
          </div>

          {/* Composer card */}
          <div
            className="rounded-3xl"
            style={{
              background: "var(--nxt-surface)",
              border: "1px solid var(--nxt-border)",
              boxShadow: "var(--nxt-shadow-lg)",
            }}
            data-testid="home-prompt-composer"
          >
            <textarea
              ref={taRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") handleSubmit();
              }}
              placeholder={placeholder}
              className="w-full bg-transparent text-[16px] p-4 sm:p-5 outline-none resize-none placeholder:opacity-60"
              style={{ color: "var(--nxt-fg)", lineHeight: 1.5 }}
              rows={2}
              data-testid="home-prompt-input"
            />
            <div className="px-3 pb-3 pt-1 flex items-center justify-between gap-2">
              <span
                className="mono text-[10px] tracking-[0.24em] uppercase"
                style={{ color: "var(--nxt-fg-faint)" }}
              >
                ⌘ + ↵ to build
              </span>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!prompt.trim() || submitting}
                className="inline-flex items-center justify-center h-10 w-10 rounded-full transition shrink-0"
                style={{
                  background: prompt.trim() ? "var(--nxt-accent)" : "var(--nxt-chip-bg)",
                  color: prompt.trim() ? "var(--nxt-bg)" : "var(--nxt-fg-faint)",
                  boxShadow: prompt.trim() ? "0 10px 22px -8px rgba(94,234,212,0.40)" : "none",
                }}
                aria-label="Build"
                data-testid="home-prompt-submit"
              >
                {submitting ? <Loader2 size={15} className="animate-spin" /> : <ArrowUp size={16} strokeWidth={2.4} />}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
