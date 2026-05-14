import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  createDeployment,
  createPreview,
  deployUrl,
  downloadZipUrl,
  getPreview,
  getProject,
  getProviders,
  listAssets,
  listDeployments,
  saveToGithub,
  scaffoldBackend,
} from "@/lib/api";
import AppHeader from "@/components/builder/AppHeader";
import ChatPanel from "@/components/builder/ChatPanel";
import PreviewPanel from "@/components/builder/PreviewPanel";
import DeploymentPanel from "@/components/builder/DeploymentPanel";
import DeployAndDomainSheet from "@/components/builder/DeployAndDomainSheet";
import SheetOverlay from "@/components/builder/SheetOverlay";
import SharePreviewModal from "@/components/builder/SharePreviewModal";
import ToolsDrawer from "@/components/builder/ToolsDrawer";
import BuilderBootSequence from "@/components/builder/BuilderBootSequence";
import BoltDiyOverlay from "@/components/builder/BoltDiyOverlay";
import { friendlyError } from "@/lib/errors";

/**
 * Chat-first BuilderPage (Phase 10 redesign).
 * - Chat is full-screen and always visible.
 * - Floating actions: Preview, Deploy, Tools (mobile-first; pinned on desktop too).
 * - Preview / Deploy / Tools each open as overlay sheets — no permanent tabs.
 * - All advanced systems (Files, Runtime, Env, DB, Domains, History, Overview)
 *   live inside the single ToolsDrawer.
 */
export default function BuilderPage() {
  const { projectId } = useParams();
  // The landing flow navigates here as `/builder/:id?prompt=<encoded>` so the
  // user never has to re-type their idea — closes "from a sentence to a
  // running app" with zero friction. We only honour it ONCE per project,
  // and stash a per-project consumed marker in sessionStorage so a hard
  // refresh doesn't re-trigger the build.
  const [searchParams] = useSearchParams();
  const initialPrompt = useMemo(() => {
    const fromUrl = (searchParams.get("prompt") || "").trim();
    if (!fromUrl) return "";
    try {
      const key = `nxt1-init-prompt-consumed:${projectId}`;
      if (sessionStorage.getItem(key)) return "";
      sessionStorage.setItem(key, "1");
    } catch { /* ignore */ }
    return fromUrl;
  }, [searchParams, projectId]);
  const [project, setProject] = useState(null);
  const [files, setFiles] = useState([]);
  const [assets, setAssets] = useState([]);
  const [activeFile, setActiveFile] = useState("index.html");

  // Overlay state
  const [previewOpen, setPreviewOpen] = useState(false);
  const [deployOpen, setDeployOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [toolsInitial, setToolsInitial] = useState(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [previewMeta, setPreviewMeta] = useState(null);
  const [refreshingPreview, setRefreshingPreview] = useState(false);

  const [activeProvider, setActiveProvider] = useState(null);
  const [autoDeployment, setAutoDeployment] = useState(null);

  const refreshProject = useCallback(async () => {
    try {
      const { data } = await getProject(projectId);
      setProject(data);
      setFiles(data.files || []);
    } catch {
      toast.error("Failed to load project");
    }
  }, [projectId]);

  const refreshAssets = useCallback(async () => {
    try {
      const { data } = await listAssets(projectId);
      setAssets(data);
    } catch {
      // ignore
    }
  }, [projectId]);

  useEffect(() => {
    refreshProject();
    refreshAssets();
    getPreview(projectId)
      .then(({ data }) => {
        if (data && data.slug) setPreviewMeta(data);
      })
      .catch(() => {});
    // Rehydrate the latest deployment so the Deploy panel + autoDeployment
    // indicator survive a refresh / leave-and-return. We surface the most
    // recent in-progress build (status=building) OR — if none — the last
    // completed deploy so the "live URL" pill stays visible.
    listDeployments(projectId)
      .then(({ data }) => {
        const items = data?.items || data || [];
        const inProgress = items.find(
          (d) => d.status === "building" || d.status === "queued" || d.status === "initializing",
        );
        const latest = inProgress || items[items.length - 1] || null;
        if (latest) setAutoDeployment(latest);
      })
      .catch(() => {});
    getProviders()
      .then(({ data }) => {
        const ai = data.ai || {};
        if (ai.anthropic) setActiveProvider("anthropic");
        else if (ai.openai) setActiveProvider("openai");
        else if (ai.emergent) setActiveProvider("emergent");
      })
      .catch(() => {});
    const onFC = () => refreshProject();
    window.addEventListener("nxt1:filesChanged", onFC);
    return () => window.removeEventListener("nxt1:filesChanged", onFC);
  }, [refreshProject, refreshAssets, projectId]);

  const onFilesUpdated = (newFiles) => {
    setFiles(newFiles);
    setProject((p) => (p ? { ...p, files: newFiles } : p));
    // Auto-pop the preview the first time the AI ships a build, so users see
    // the result without needing to tap anything. Only on desktop — mobile
    // users should tap the floating Preview to keep the chat in view.
    if (window.matchMedia("(min-width: 1024px)").matches && !previewOpen) {
      setPreviewOpen(true);
    }
  };

  const onFileSaved = (path, content) => {
    setFiles((curr) => curr.map((f) => (f.path === path ? { ...f, content } : f)));
  };

  const onAutoDeploy = (deployment) => {
    if (!deployment) return;
    setAutoDeployment(deployment);
    setProject((p) =>
      p && deployment.status === "deployed"
        ? { ...p, deployed: true, deploy_slug: deployment.public_url?.split("/").pop() }
        : p
    );
    refreshProject();
  };

  const onDownload = () => {
    window.location.href = downloadZipUrl(projectId);
  };

  const liveUrl =
    project?.deployed && project?.deploy_slug ? deployUrl(project.deploy_slug) : null;

  const hasBackend = (files || []).some((f) => f.path.startsWith("backend/"));

  const handleScaffold = async (kind) => {
    try {
      await scaffoldBackend(projectId, kind, true);
      toast.success(`Generated ${kind} starter`);
      await refreshProject();
      try {
        const { refreshAnalysis } = await import("@/lib/api");
        await refreshAnalysis(projectId);
      } catch {
        /* ignore */
      }
      window.dispatchEvent(new CustomEvent("nxt1:filesChanged"));
    } catch (e) {
      const fe = friendlyError(e?.response?.data?.detail || "Scaffold failed");
      toast.error(fe.title, { description: fe.hint });
    }
  };

  const sendChat = (text) => {
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent("nxt1:sendChat", { detail: { text } }));
    }, 60);
  };

  const openTools = (initial = null) => {
    setToolsInitial(initial);
    setToolsOpen(true);
  };

  return (
    <div
      className="h-[100dvh] flex flex-col overflow-hidden surface-0 relative"
      data-testid="builder-page"
    >
      {/* Cinematic boot sequence — streams live progress while the project
          loads instead of a stagnant empty screen. Self-dismisses on ready. */}
      <BuilderBootSequence project={project} files={files} />

      {/* bolt.diy — when sidecar is reachable, takes over the entire builder
          (the new primary build/edit UI). When not, renders a small banner
          and the legacy NXT1 builder stays usable. */}
      <BoltDiyOverlay />

      <AppHeader
        project={project}
        onOpenTools={() => openTools(null)}
      />

      {/* Main area — chat is full-screen on mobile, chat + sticky preview on lg+ */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12">
        {/* Chat — primary surface */}
        <section
          className="col-span-1 lg:col-span-7 min-h-0 relative flex flex-col"
          data-testid="builder-chat-section"
        >
          <div className="flex-1 min-h-0">
            <ChatPanel
              projectId={projectId}
              initialPrompt={initialPrompt}
              onFilesUpdated={onFilesUpdated}
              onAutoDeploy={onAutoDeploy}
              onPreviewClick={() => setPreviewOpen(true)}
              onDeployClick={() => setDeployOpen(true)}
              onDeployNow={async () => {
                // Auto-pick Vercel (per user choice) and open the deploy
                // sheet so they can watch the build logs stream in.
                try {
                  const { data: dep } = await createDeployment(projectId, "vercel");
                  setAutoDeployment(dep);
                  setDeployOpen(true);
                  toast.success("Deploying to Vercel — streaming logs in Deploy panel");
                } catch (e) {
                  const fe = friendlyError(e?.response?.data?.detail || e?.message || "Deploy failed");
                  toast.error(fe.title, { description: fe.hint });
                  setDeployOpen(true); // open sheet so user can pick another provider
                }
              }}
              onSaveToGithub={async () => {
                try {
                  const { data } = await saveToGithub(projectId, {
                    repo_name: project?.name,
                    private: true,
                  });
                  toast.success(
                    `Pushed ${data.file_count} files to ${data.owner}/${data.name}`,
                    {
                      description: data.repo_url,
                      action: {
                        label: "Open",
                        onClick: () => window.open(data.repo_url, "_blank"),
                      },
                    }
                  );
                  refreshProject();
                } catch (e) {
                  const fe = friendlyError(e?.response?.data?.detail || e?.message || "GitHub save failed");
                  toast.error(fe.title, { description: fe.hint });
                }
              }}
              onSharePreview={async () => {
                try {
                  const { data } = await createPreview(projectId, {});
                  setPreviewMeta(data);
                  setShareOpen(true);
                  // Best-effort silent clipboard copy on first open
                  try {
                    await navigator.clipboard.writeText(data.url);
                  } catch {
                    /* ignore */
                  }
                } catch (e) {
                  const fe = friendlyError(e?.response?.data?.detail || e?.message || "Couldn't generate preview link");
                  toast.error(fe.title, { description: fe.hint });
                }
              }}
              onConnectDomain={() => setDeployOpen(true)}
              deployedUrl={autoDeployment?.status === "deployed" ? (autoDeployment.public_url || autoDeployment.url) : null}
            />
          </div>

          {/* Mobile preview is now reachable via the composer ⋯ menu
              (ComposerActions). The previous floating "Preview" oval was
              noisy + competed visually with the bottom-anchored composer. */}
        </section>

        {/* Persistent preview on desktop only */}
        <aside
          className="hidden lg:flex lg:col-span-5 border-l border-white/5 min-h-0"
          data-testid="builder-desktop-preview"
        >
          <div className="flex-1 min-h-0 min-w-0">
            <PreviewPanel
              files={files}
              activeFile={activeFile}
              projectId={projectId}
              onFileSaved={onFileSaved}
            />
          </div>
        </aside>
      </div>

      {/* Mobile / on-demand preview overlay */}
      <SheetOverlay
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        title="Preview"
        size="full"
        side="bottom"
        testId="preview-sheet"
      >
        <PreviewPanel
          files={files}
          activeFile={activeFile}
          projectId={projectId}
          onFileSaved={onFileSaved}
        />
      </SheetOverlay>

      {/* Deploy + Domain unified flow — opens from Share/Preview/Deploy */}
      <DeployAndDomainSheet
        open={deployOpen}
        projectId={projectId}
        onClose={() => setDeployOpen(false)}
        onDeployed={() => {
          refreshProject();
          setDeployOpen(false);
        }}
      />
      {/* Legacy DeploymentPanel still lives in ToolsDrawer for power users */}

      {/* Tools drawer — every advanced system lives here */}
      <ToolsDrawer
        open={toolsOpen}
        onClose={() => setToolsOpen(false)}
        initialTool={toolsInitial}
        projectId={projectId}
        project={project}
        files={files}
        activeFile={activeFile}
        setActiveFile={setActiveFile}
        hasBackend={hasBackend}
        onScaffoldBackend={handleScaffold}
        onFilesChanged={refreshProject}
        refreshProject={refreshProject}
        refreshAssets={refreshAssets}
        onSendChat={sendChat}
        activeProvider={activeProvider}
        autoDeployment={autoDeployment}
        setAutoDeployment={setAutoDeployment}
      />

      {/* Share preview modal — branded shareable URL with copy + refresh */}
      <SharePreviewModal
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        projectId={projectId}
        preview={previewMeta}
        regenerating={refreshingPreview}
        onUpdated={(data) => setPreviewMeta(data)}
        onRegenerate={async () => {
          setRefreshingPreview(true);
          try {
            const { data } = await createPreview(projectId, {});
            setPreviewMeta(data);
            toast.success("Preview link refreshed");
          } catch (e) {
            const fe = friendlyError(e?.response?.data?.detail || e?.message || "Refresh failed");
            toast.error(fe.title, { description: fe.hint });
          } finally {
            setRefreshingPreview(false);
          }
        }}
      />
    </div>
  );
}
