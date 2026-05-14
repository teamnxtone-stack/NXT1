/**
 * NXT1 — Builder app header (Phase 8 minimal).
 *
 * Identity only. Operational controls live near the composer now, behind
 * a compact expandable ComposerActions button. The floating PreviewBar
 * (separate component) animates in only when a preview is ready.
 */
import { useNavigate } from "react-router-dom";
import { ArrowLeft, SlidersHorizontal } from "lucide-react";
import Brand from "@/components/Brand";
import NotificationCenter from "@/components/NotificationCenter";

export default function AppHeader({ project, onOpenTools }) {
  const navigate = useNavigate();
  return (
    <header
      className="h-12 shrink-0 nxt-glass border-b flex items-center justify-between px-2 sm:px-4 gap-2"
      style={{ borderColor: "var(--nxt-border-soft)" }}
      data-testid="builder-header"
    >
      <div className="flex items-center gap-2 sm:gap-3 min-w-0">
        <button
          onClick={() => navigate("/workspace")}
          className="p-1 transition shrink-0"
          style={{ color: "var(--nxt-fg-dim)" }}
          data-testid="back-to-dashboard"
          aria-label="Back to workspace"
        >
          <ArrowLeft size={16} />
        </button>
        <Brand size="md" gradient />
        <div className="hidden sm:block h-4 w-px" style={{ background: "var(--nxt-border)" }} />
        <div className="min-w-0 hidden sm:flex items-center gap-2">
          <span
            className="text-[10px] mono tracking-[0.22em] uppercase"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            project
          </span>
          <span
            className="text-sm font-medium truncate max-w-[160px] md:max-w-[260px]"
            style={{ color: "var(--nxt-fg)" }}
            data-testid="builder-project-name"
          >
            {project?.name || "—"}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <NotificationCenter />
        <button
          onClick={onOpenTools}
          className="inline-flex items-center gap-1.5 h-9 px-2.5 sm:px-3 rounded-xl text-[12.5px] transition"
          style={{
            background: "transparent",
            border: "1px solid var(--nxt-border-soft)",
            color: "var(--nxt-fg-dim)",
          }}
          data-testid="open-tools-button"
          title="Advanced tools"
        >
          <SlidersHorizontal size={13} />
          <span className="hidden md:inline">Tools</span>
        </button>
      </div>
    </header>
  );
}
