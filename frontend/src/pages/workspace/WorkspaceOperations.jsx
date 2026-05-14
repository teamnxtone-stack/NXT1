/**
 * NXT1 — Workspace Operations
 *
 * A single canonical "operations & infrastructure" page tying together
 * the four new tracks: Premium UI Gallery, Durable Workflows, Hosting OS
 * (Caddy + Cloudflare), and the Sandboxed Self-Heal runner.
 *
 * This is the home for the build/deploy infrastructure surfaces that
 * Phase 11 → 12 introduced.
 */
import { useState } from "react";
// UIBlockGallery hidden — the 17-block registry is backend-only now.
// import UIBlockGallery from "@/components/workspace/UIBlockGallery";
import WorkflowsPanel from "@/components/workspace/WorkflowsPanel";
import HostingOS from "@/components/workspace/HostingOS";
import SelfHealPanel from "@/components/workspace/SelfHealPanel";
import { useSearchParams } from "react-router-dom";
import { Workflow, Cloud, Wrench } from "lucide-react";

const TABS = [
  { id: "workflows", label: "Workflows",         icon: Workflow },
  { id: "hosting",   label: "Hosting · Domains", icon: Cloud   },
  { id: "heal",      label: "Self-Heal",         icon: Wrench   },
];

export default function WorkspaceOperations() {
  const [params, setParams] = useSearchParams();
  const initial = TABS.find((t) => t.id === params.get("tab"))?.id || "workflows";
  const [tab, setTab] = useState(initial);
  const setTabAndUrl = (id) => {
    setTab(id);
    setParams((p) => { p.set("tab", id); return p; });
  };
  const projectId = params.get("project_id") || params.get("pid") || "";

  return (
    <div
      className="max-w-[1120px] mx-auto px-5 sm:px-6 py-8 sm:py-12"
      data-testid="workspace-operations"
    >
      <div className="mb-7 sm:mb-9">
        <div
          className="mono text-[10px] tracking-[0.30em] uppercase mb-2"
          style={{ color: "var(--nxt-fg-faint)" }}
        >
          Build · Hosting · Self-Heal
        </div>
        <h1
          className="text-[28px] sm:text-[34px] font-semibold tracking-tight leading-tight mb-2"
          style={{ color: "var(--nxt-fg)" }}
        >
          Operations.
        </h1>
        <p
          className="text-[14px] max-w-[640px] leading-relaxed"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          Premium UI generation, durable agent workflows, BYO Cloudflare + Caddy
          for custom domains with auto-SSL, and a sandboxed self-healing build
          loop. Everything portable, everything self-hostable.
        </p>
      </div>

      {/* Tab bar */}
      <div
        className="flex flex-wrap gap-1.5 mb-6 p-1 rounded-full w-fit"
        style={{
          background: "var(--nxt-surface)",
          border: "1px solid var(--nxt-border)",
        }}
        data-testid="ops-tabs"
      >
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTabAndUrl(id)}
            data-testid={`ops-tab-${id}`}
            className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-full transition"
            style={{
              background: tab === id ? "var(--nxt-fg)" : "transparent",
              color: tab === id ? "var(--nxt-bg)" : "var(--nxt-fg-dim)",
            }}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "workflows" && <WorkflowsPanel />}
      {tab === "hosting"   && <HostingOS />}
      {tab === "heal"      && (
        projectId
          ? <SelfHealPanel projectId={projectId} />
          : <SelfHealHelper />
      )}
    </div>
  );
}

function SelfHealHelper() {
  return (
    <div
      className="rounded-xl p-6 text-center border"
      style={{ borderColor: "var(--nxt-border)", background: "var(--nxt-surface)" }}
      data-testid="heal-helper"
    >
      <Wrench className="w-6 h-6 mx-auto mb-3 opacity-50"
              style={{ color: "var(--nxt-fg-dim)" }} />
      <div className="text-[13px] mb-1" style={{ color: "var(--nxt-fg)" }}>
        Self-heal runs per project.
      </div>
      <div className="text-[12px] max-w-[420px] mx-auto"
           style={{ color: "var(--nxt-fg-dim)" }}>
        Open the Builder for any app, then click the wrench icon — or pass{" "}
        <code className="mono">?tab=heal&project_id=&lt;id&gt;</code> in the URL.
      </div>
    </div>
  );
}
