/**
 * ToolsDrawer — single drawer that surfaces all "advanced" panels (Overview,
 * Files, Runtime, Env, Database, Domains, History, Deploy) so they no longer
 * need permanent tab real-estate in the chat-first builder. Power users open
 * this when they need it; everyone else lives in chat.
 *
 * Two modes:
 *   - "menu" (default) — vertical list of system categories. Picking one swaps
 *     the body to the actual panel.
 *   - "panel:<key>" — full panel rendered with a back button.
 */
import { useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Code2,
  Database,
  FolderTree,
  GitCommit,
  Globe,
  Home,
  Key,
  Rocket,
  Server,
  Sparkles,
  Workflow,
  Wrench,
  Layers,
} from "lucide-react";
import SheetOverlay from "./SheetOverlay";
import OverviewPanel from "./OverviewPanel";
import FileExplorer from "./FileExplorer";
import VersionHistory from "./VersionHistory";
import RuntimePanel from "./RuntimePanel";
import EnvVarsPanel from "./EnvVarsPanel";
import DatabasePanel from "./DatabasePanel";
import DomainsPanel from "./DomainsPanel";
import MigrationPanel from "./MigrationPanel";
import CommitHistory from "./CommitHistory";
import DeploymentPanel from "./DeploymentPanel";
import WorkflowsPanel from "@/components/workspace/WorkflowsPanel";
import SelfHealPanel from "@/components/workspace/SelfHealPanel";
import UIBlockGallery from "@/components/workspace/UIBlockGallery";
import { useDevMode } from "@/lib/devMode";

// Items that are only revealed when Developer Mode is ON.
const DEV_ONLY = new Set(["runtime", "env", "files", "history"]);

const ITEMS = [
  {
    key: "overview",
    label: "Overview",
    blurb: "ProductAgent • launch readiness",
    icon: Home,
    color: "text-emerald-300",
  },
  {
    key: "workflow",
    label: "Build pipeline",
    blurb: "Planner → coder → tester → deploy",
    icon: Workflow,
    color: "text-cyan-300",
  },
  {
    key: "selfheal",
    label: "Self-heal",
    blurb: "Sandboxed bounded retry loop",
    icon: Wrench,
    color: "text-amber-300",
  },
  // "Premium UI blocks" tile intentionally hidden — the 17-block registry now
  // lives backend-only at /api/ui/registry and is auto-retrieved by the build
  // agent when a user describes what they want. The UI surface is no longer
  // exposed to end users (per product direction).
  // {
  //   key: "uiblocks",
  //   label: "Premium UI blocks",
  //   blurb: "Magic UI · Aceternity · Origin",
  //   icon: Layers,
  //   color: "text-violet-300",
  // },
  {
    key: "migration",
    label: "Migration",
    blurb: "Reconnect detected stack",
    icon: Sparkles,
    color: "text-emerald-300",
  },
  {
    key: "deploy",
    label: "Deploy",
    blurb: "Vercel · Cloudflare · internal",
    icon: Rocket,
    color: "text-amber-300",
  },
  {
    key: "domains",
    label: "Domains",
    blurb: "Custom domains · SSL",
    icon: Globe,
    color: "text-sky-300",
  },
  {
    key: "runtime",
    label: "Runtime",
    blurb: "Backend sandbox · logs",
    icon: Server,
    color: "text-violet-300",
  },
  {
    key: "env",
    label: "Env vars",
    blurb: "Secrets & configuration",
    icon: Key,
    color: "text-zinc-300",
  },
  {
    key: "db",
    label: "Database",
    blurb: "Connections · schema",
    icon: Database,
    color: "text-fuchsia-300",
  },
  {
    key: "history",
    label: "History",
    blurb: "Version timeline · restore",
    icon: GitCommit,
    color: "text-rose-300",
  },
  {
    key: "files",
    label: "Files & code",
    blurb: "Developer mode",
    icon: FolderTree,
    color: "text-zinc-400",
  },
];

export default function ToolsDrawer({
  open,
  onClose,
  initialTool = null,
  projectId,
  project,
  files,
  activeFile,
  setActiveFile,
  hasBackend,
  onScaffoldBackend,
  onFilesChanged,
  refreshProject,
  refreshAssets,
  onSendChat,
  activeProvider,
  autoDeployment,
  setAutoDeployment,
}) {
  const [active, setActive] = useState(initialTool); // null | item.key
  const [devMode, setDev] = useDevMode();
  const visibleItems = ITEMS.filter((it) => !DEV_ONLY.has(it.key) || devMode);
  const item = visibleItems.find((i) => i.key === active);

  const back = () => setActive(null);

  // Reset to menu when drawer is closed
  const handleClose = () => {
    onClose?.();
    setTimeout(() => setActive(initialTool), 200);
  };

  const accessory = active ? (
    <button
      onClick={back}
      className="text-[11px] mono uppercase tracking-wider text-zinc-400 hover:text-white inline-flex items-center gap-1 px-2 py-1"
      data-testid="tools-drawer-back"
    >
      <ChevronLeft size={12} /> Tools
    </button>
  ) : null;

  return (
    <SheetOverlay
      open={open}
      onClose={handleClose}
      title={item ? `Tools · ${item.label}` : "Tools"}
      size={item ? "lg" : "md"}
      testId="tools-drawer"
      rightAccessory={accessory}
    >
      {!item ? (
        <div
          className="h-full overflow-y-auto p-4 sm:p-5 lg:p-4"
          data-testid="tools-drawer-menu"
        >
          <div className="text-[13px] text-zinc-300 px-1 py-1 mb-3 leading-relaxed">
            Everything else NXT1 can do — chat stays the star, the rest lives
            here.
          </div>
          {/* Developer Mode pill */}
          <div
            className="flex items-center gap-3 px-4 py-3.5 mb-4 border border-white/10 surface-1 rounded-2xl"
            data-testid="dev-mode-toggle-row"
          >
            <span className="h-9 w-9 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center shrink-0">
              <Code2 size={15} className="text-zinc-300" />
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-[14px] text-white font-medium">Developer Mode</div>
              <div className="text-[12px] text-zinc-500 mt-0.5 leading-snug">
                {devMode
                  ? "Files, runtime, env, and version history are visible."
                  : "Chat-first — advanced developer panels are hidden."}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setDev(!devMode)}
              className={`relative h-7 w-12 rounded-full border transition shrink-0 ${
                devMode
                  ? "bg-emerald-400/90 border-emerald-300"
                  : "bg-white/5 border-white/15"
              }`}
              data-testid="dev-mode-toggle"
              aria-pressed={devMode}
              aria-label="Toggle developer mode"
            >
              <span
                className={`absolute top-0.5 h-6 w-6 rounded-full bg-[#1F1F23] shadow transition-all ${
                  devMode ? "left-[22px]" : "left-0.5"
                }`}
              />
            </button>
          </div>
          <div className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500 px-1 mb-2">
            Project tools
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {visibleItems.map((it) => {
              const Icon = it.icon;
              return (
                <button
                  key={it.key}
                  onClick={() => setActive(it.key)}
                  className="group flex items-center gap-3 px-4 py-4 border border-white/10 hover:border-white/30 surface-1 hover:bg-[#111] rounded-2xl transition text-left active:scale-[.98]"
                  data-testid={`tools-item-${it.key}`}
                >
                  <div className="h-10 w-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center shrink-0">
                    <Icon size={16} className={it.color} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[14px] font-medium text-white truncate">
                      {it.label}
                    </div>
                    <div className="text-[12px] text-zinc-500 truncate mt-0.5">
                      {it.blurb}
                    </div>
                  </div>
                  <ChevronRight
                    size={15}
                    className="text-zinc-600 group-hover:text-white transition shrink-0"
                  />
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="h-full overflow-hidden" data-testid={`tools-panel-${item.key}`}>
          {item.key === "overview" && (
            <OverviewPanel
              projectId={projectId}
              project={project}
              onGoTab={(tk) => setActive(tk)}
              onScaffoldBackend={onScaffoldBackend}
              onSendChat={(text) => {
                handleClose();
                onSendChat?.(text);
              }}
            />
          )}
          {item.key === "workflow" && (
            <div className="h-full overflow-y-auto p-4 sm:p-5">
              <WorkflowsPanel projectId={projectId} />
            </div>
          )}
          {item.key === "selfheal" && (
            <div className="h-full overflow-y-auto p-4 sm:p-5">
              <SelfHealPanel projectId={projectId} />
            </div>
          )}
          {item.key === "uiblocks" && (
            <div className="h-full overflow-y-auto p-4 sm:p-5">
              <UIBlockGallery />
            </div>
          )}
          {item.key === "deploy" && (
            <DeploymentPanel
              projectId={projectId}
              project={project}
              onProjectUpdated={refreshProject}
              activeProvider={activeProvider}
              autoDeployment={autoDeployment}
              setAutoDeployment={setAutoDeployment}
            />
          )}
          {item.key === "domains" && (
            <DomainsPanel projectId={projectId} project={project} />
          )}
          {item.key === "runtime" && (
            <RuntimePanel projectId={projectId} hasBackend={hasBackend} />
          )}
          {item.key === "env" && <EnvVarsPanel projectId={projectId} />}
          {item.key === "db" && <DatabasePanel projectId={projectId} />}
          {item.key === "migration" && (
            <MigrationPanel
              projectId={projectId}
              onOpenPanel={(key) => setActive(key)}
              onSaveToGithub={() => onSendChat?.("Save this project to GitHub")}
              onDeploy={(provider) => onSendChat?.(`Deploy this project to ${provider}`)}
            />
          )}
          {item.key === "history" && (
            <CommitHistory
              projectId={projectId}
              currentFiles={files}
              onRestored={refreshProject}
            />
          )}
          {item.key === "files" && (
            <div className="grid grid-rows-[1fr_minmax(0,40%)] h-full">
              <FileExplorer
                files={files}
                activeFile={activeFile}
                onSelect={setActiveFile}
                onFilesChanged={onFilesChanged}
                projectId={projectId}
              />
              <div className="border-t border-white/5 min-h-0 overflow-hidden">
                <VersionHistory
                  projectId={projectId}
                  currentFiles={files}
                  onRestored={refreshProject}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </SheetOverlay>
  );
}
