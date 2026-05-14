/**
 * NXT1 — Publish Bar
 *
 * One cohesive operational bar that unifies Save-to-GitHub · Deploy · Preview.
 * Designed to feel like a single flow rather than three random buttons:
 *
 *   [ ○ GitHub:  not-connected | connected (repo → branch) | saved 2m ago ]
 *   [ ○ Deploy:  idle | running | live ]
 *   [ ○ Preview: ready ]
 *
 * Connected states use a tiny dot indicator and a soft glow. Mobile-first:
 * collapses into a compact bottom-anchored bar with the same affordances.
 *
 * The bar is intentionally STATEFUL but stateless about underlying APIs —
 * the parent passes `github`, `deploy`, `previewReady` props.
 */
import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Github, Rocket, Eye, ExternalLink, Loader2, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

export function PublishBar({
  projectId,
  github,            // { repo_url, repo_name, branch, last_saved_at, source_name } | null
  deploy,            // { state: "idle"|"running"|"live", url?, last_deployed_at? }
  previewReady,      // bool
  onPreviewClick,
  onDeployClick,
  onGithubSaved,     // callback after successful github save
  compact = false,
}) {
  return (
    <div
      className="flex items-center gap-1.5 rounded-2xl"
      style={{
        background: "linear-gradient(180deg, rgba(48,48,56,0.55) 0%, rgba(36,36,40,0.55) 100%)",
        border: "1px solid rgba(255,255,255,0.07)",
        padding: 4,
        backdropFilter: "blur(14px) saturate(140%)",
        WebkitBackdropFilter: "blur(14px) saturate(140%)",
      }}
      data-testid="publish-bar"
    >
      <GithubAction
        projectId={projectId}
        github={github}
        compact={compact}
        onSaved={onGithubSaved}
      />
      <Divider />
      <DeployAction deploy={deploy} compact={compact} onClick={onDeployClick} />
      <Divider />
      <PreviewAction ready={previewReady} compact={compact} onClick={onPreviewClick} />
    </div>
  );
}

function Divider() {
  return <span aria-hidden className="h-5 w-px bg-white/8 shrink-0" />;
}

function Pill({ state, children, onClick, testId, title }) {
  // State → dot color
  const dotColor =
    state === "connected" || state === "live" || state === "ready"
      ? "rgba(94,234,212,0.95)"
      : state === "running"
      ? "rgba(255,204,102,0.95)"
      : "rgba(255,255,255,0.22)";
  const dotGlow =
    state === "connected" || state === "live" || state === "ready"
      ? "0 0 0 3px rgba(94,234,212,0.10)"
      : state === "running"
      ? "0 0 0 3px rgba(255,204,102,0.10)"
      : "none";
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      data-testid={testId}
      data-state={state}
      className="group inline-flex items-center gap-2 h-9 px-3 rounded-xl text-[12.5px] text-white/85 hover:text-white transition"
      style={{ background: "transparent" }}
    >
      <span
        className="relative h-1.5 w-1.5 rounded-full shrink-0"
        style={{ background: dotColor, boxShadow: dotGlow }}
        aria-hidden
      >
        {state === "running" && (
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{ background: dotColor, opacity: 0.4 }}
            animate={{ scale: [1, 2.4, 1], opacity: [0.4, 0, 0.4] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
          />
        )}
      </span>
      {children}
    </button>
  );
}

/* ---------- GitHub action ---------- */
function GithubAction({ projectId, github, compact, onSaved }) {
  const [busy, setBusy] = useState(false);
  const connected = Boolean(github?.repo_url || github?.source_name);
  const repoName = github?.repo_name || github?.source_name || "";
  const branch = github?.branch || "main";
  const state = busy ? "running" : connected ? "connected" : "idle";

  async function save() {
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/integrations/projects/${projectId}/github/save`, {});
      onSaved?.(data);
      toast.success("Saved to GitHub", {
        description: `${data?.repo_name || "repo"} · ${data?.branch || "main"}`,
      });
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      if (status === 401 || /token/i.test(detail || "")) {
        toast.message("Connect GitHub to enable Save", {
          description: "Add a GitHub token in Tools → Integrations.",
        });
      } else {
        toast.error(detail || "Couldn't save to GitHub.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Pill
      state={state}
      onClick={save}
      testId="publish-github"
      title={connected ? `Save to ${repoName} (${branch})` : "Save this build to your GitHub"}
    >
      {busy ? (
        <Loader2 size={13} className="animate-spin" />
      ) : (
        <Github size={13} />
      )}
      {!compact && (
        <span className="truncate max-w-[120px]">
          {busy ? "Saving…" : connected ? repoName || "GitHub" : "Save to GitHub"}
        </span>
      )}
    </Pill>
  );
}

/* ---------- Deploy action ---------- */
function DeployAction({ deploy, compact, onClick }) {
  const state =
    deploy?.state === "running"
      ? "running"
      : deploy?.url
      ? "live"
      : "idle";
  const label =
    state === "running" ? "Deploying…" : state === "live" ? "Live" : "Deploy";
  return (
    <Pill state={state} onClick={onClick} testId="publish-deploy" title="Deploy this build">
      {state === "running" ? (
        <Loader2 size={13} className="animate-spin" />
      ) : state === "live" && deploy?.url ? (
        <a
          href={deploy.url}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-1 text-emerald-300"
        >
          <Rocket size={13} />
          {!compact && <span>Live</span>}
          <ExternalLink size={10} />
        </a>
      ) : (
        <Rocket size={13} />
      )}
      {state !== "live" && !compact && <span>{label}</span>}
    </Pill>
  );
}

/* ---------- Preview action ---------- */
function PreviewAction({ ready, compact, onClick }) {
  const state = ready ? "ready" : "idle";
  return (
    <Pill state={state} onClick={onClick} testId="publish-preview" title="Open preview">
      <Eye size={13} />
      {!compact && <span>Preview</span>}
      {!compact && ready && <ChevronRight size={12} className="opacity-50" />}
    </Pill>
  );
}

export default PublishBar;
