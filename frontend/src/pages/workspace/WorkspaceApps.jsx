/**
 * NXT1 — Workspace Apps (Drafts / Live segments)
 *
 * Two clean segments. No search clutter. No recency clutter. Just clarity.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { listProjects, deployUrl } from "@/lib/api";

export default function WorkspaceApps() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [segment, setSegment] = useState("drafts");

  useEffect(() => {
    listProjects().then(({ data }) => setProjects(data || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const drafts = useMemo(() => projects.filter((p) => !p.deployed), [projects]);
  const live = useMemo(() => projects.filter((p) => p.deployed || p.deploy_slug), [projects]);
  const items = segment === "drafts" ? drafts : live;

  return (
    <div className="px-5 sm:px-6 pt-12 sm:pt-16 max-w-[680px] mx-auto" data-testid="workspace-apps">
      {/* Segmented header */}
      <div
        className="flex p-1 rounded-2xl mb-8"
        style={{ background: "var(--nxt-surface-soft)", border: "1px solid var(--nxt-border-soft)" }}
        role="tablist"
      >
        <SegmentButton
          label={`Drafts${drafts.length ? `  ${drafts.length}` : ""}`}
          active={segment === "drafts"}
          onClick={() => setSegment("drafts")}
          testId="segment-drafts"
        />
        <SegmentButton
          label={`Live Apps${live.length ? `  ${live.length}` : ""}`}
          active={segment === "live"}
          onClick={() => setSegment("live")}
          testId="segment-live"
        />
      </div>

      {loading ? (
        <div className="text-[13px]" style={{ color: "var(--nxt-fg-faint)" }}>Loading…</div>
      ) : items.length === 0 ? (
        <EmptyState segment={segment} onCTA={() => navigate("/workspace")} />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((p) => (
            <AppRow
              key={p.id}
              project={p}
              isLive={segment === "live"}
              onOpen={() => navigate(`/builder/${p.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SegmentButton({ label, active, onClick, testId }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="relative flex-1 py-2.5 text-[13.5px] font-medium tracking-tight rounded-xl transition"
      style={{
        color: active ? "var(--nxt-fg)" : "var(--nxt-fg-dim)",
      }}
      role="tab"
      aria-selected={active}
      data-testid={testId}
    >
      {active && (
        <motion.span
          layoutId="apps-segment-bg"
          className="absolute inset-0 rounded-xl"
          transition={{ type: "spring", stiffness: 380, damping: 32 }}
          style={{
            background: "var(--nxt-surface)",
            border: "1px solid var(--nxt-border)",
            boxShadow: "var(--nxt-shadow-sm)",
          }}
          aria-hidden
        />
      )}
      <span className="relative">{label}</span>
    </button>
  );
}

function AppRow({ project, isLive, onOpen }) {
  return (
    <motion.button
      whileTap={{ scale: 0.985 }}
      type="button"
      onClick={onOpen}
      className="w-full min-w-0 flex items-center gap-3 px-3.5 py-3 rounded-2xl text-left transition"
      style={{
        background: "var(--nxt-surface-soft)",
        border: "1px solid var(--nxt-border-soft)",
      }}
      data-testid={`app-card-${project.id}`}
    >
      <span
        className="h-9 w-9 shrink-0 rounded-xl flex items-center justify-center text-[12px] mono font-semibold"
        style={{ background: "var(--nxt-chip-bg)", color: "var(--nxt-fg-dim)" }}
      >
        {(project.name || "N").slice(0, 1).toUpperCase()}
      </span>
      <span className="flex-1 min-w-0">
        <span
          className="block text-[14px] font-medium truncate"
          style={{ color: "var(--nxt-fg)" }}
        >
          {project.name || "Untitled"}
        </span>
        <span
          className="flex items-center gap-1.5 text-[11.5px] mt-0.5 truncate"
          style={{ color: "var(--nxt-fg-faint)" }}
        >
          {isLive && (
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" aria-hidden />
          )}
          {project.framework || project.template_kind || (isLive ? "Live" : "Draft")}
        </span>
      </span>
    </motion.button>
  );
}

function EmptyState({ segment, onCTA }) {
  return (
    <div
      className="rounded-2xl py-10 px-6 text-center"
      style={{ background: "var(--nxt-surface-soft)", border: "1px solid var(--nxt-border-soft)" }}
    >
      <div className="text-[15px] font-medium mb-1" style={{ color: "var(--nxt-fg)" }}>
        {segment === "live" ? "No live apps yet" : "No drafts yet"}
      </div>
      <div className="text-[12.5px] mb-5" style={{ color: "var(--nxt-fg-faint)" }}>
        {segment === "live"
          ? "Deploy a build to make it publicly accessible."
          : "Tell NXT1 what to build and your draft will show up here."}
      </div>
      <button
        type="button"
        onClick={onCTA}
        className="inline-flex items-center gap-1.5 h-10 px-4 rounded-xl text-[13px] font-semibold"
        style={{ background: "var(--nxt-accent)", color: "var(--nxt-bg)" }}
      >
        Start a build
      </button>
    </div>
  );
}
