/**
 * ResumeWorkflowChip — tiny one-tap "Approve & deploy" pill that surfaces
 * directly above the chat composer when there's a `waiting` workflow for
 * the current project. Lets users approve the deploy hand-off without
 * opening Tools → Build pipeline.
 *
 * Polls /api/workflows/list?project_id=...&status=waiting every 5s and
 * disappears when no waiting workflow exists.
 */
import { useEffect, useState, useCallback } from "react";
import { Rocket, X, Loader2, CheckCircle2 } from "lucide-react";
import { listWorkflows, resumeWorkflow } from "@/lib/api";
import { toast } from "sonner";

export default function ResumeWorkflowChip({ projectId, onResumed }) {
  const [waiting, setWaiting] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const refresh = useCallback(async () => {
    if (!projectId || dismissed) return;
    try {
      const { data } = await listWorkflows({
        project_id: projectId,
        status: "waiting",
        limit: 1,
      });
      const item = (data?.items || [])[0] || null;
      setWaiting(item);
    } catch {
      /* swallow — chip is non-critical */
    }
  }, [projectId, dismissed]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  // Reset dismissal whenever the project changes
  useEffect(() => { setDismissed(false); }, [projectId]);

  if (!waiting || dismissed) return null;

  const handleApprove = async () => {
    setBusy(true);
    try {
      await resumeWorkflow(waiting.workflow_id, true);
      toast.success("Workflow approved — deploy hand-off complete.");
      setWaiting(null);
      onResumed?.(waiting.workflow_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't resume workflow");
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = async () => {
    setBusy(true);
    try {
      await resumeWorkflow(waiting.workflow_id, false);
      toast.success("Deploy declined — workflow cancelled.");
      setWaiting(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't cancel workflow");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      data-testid="resume-workflow-chip"
      className="mx-3 sm:mx-4 mb-2 rounded-2xl px-3 py-2 flex items-center gap-2 text-[12px] backdrop-blur-md"
      style={{
        background: "linear-gradient(90deg, rgba(245,158,11,0.10), rgba(245,158,11,0.04))",
        border: "1px solid rgba(245,158,11,0.25)",
        color: "rgba(252,211,77,0.95)",
      }}
    >
      <Rocket className="w-3.5 h-3.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="mono uppercase tracking-[0.2em] text-[9px] opacity-70">
          Build pipeline · waiting
        </span>
        <div className="truncate text-[12px]" style={{ color: "rgba(255,255,255,0.85)" }}>
          Build healthy — approve to deploy.
        </div>
      </div>
      <button
        type="button"
        onClick={handleApprove}
        disabled={busy}
        data-testid="resume-chip-approve"
        className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium transition flex-shrink-0"
        style={{
          background: "rgba(16,185,129,0.18)",
          color: "#86efac",
          border: "1px solid rgba(16,185,129,0.4)",
          opacity: busy ? 0.5 : 1,
        }}
      >
        {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
        Approve & deploy
      </button>
      <button
        type="button"
        onClick={handleCancel}
        disabled={busy}
        data-testid="resume-chip-cancel"
        className="px-2 py-1 rounded-full text-[11px] flex-shrink-0"
        style={{
          color: "rgba(255,255,255,0.55)",
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        Decline
      </button>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        data-testid="resume-chip-dismiss"
        aria-label="Dismiss"
        className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 transition"
        style={{ color: "rgba(255,255,255,0.4)" }}
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}
