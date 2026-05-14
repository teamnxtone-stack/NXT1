/**
 * NXT1 — Workspace module placeholders (trimmed).
 *
 * Only Drafts/Deployments/Editor/Domains/Providers/Settings views are kept
 * here for deep-linked routes from Account. The shell does NOT expose them
 * in navigation; users reach them via Account drilldowns.
 */
import { FileEdit, Rocket, Globe, Cpu, Settings as Cog, Wand2 } from "lucide-react";
import { useState } from "react";
import WorkspaceModulePlaceholder from "./WorkspaceModulePlaceholder";
import HostingPicker from "@/components/workspace/HostingPicker";
import HostingOS from "@/components/workspace/HostingOS";
import ModelVariantPicker from "@/components/workspace/ModelVariantPicker";
import SystemDiagnosticsPanel from "@/components/workspace/SystemDiagnosticsPanel";

export function WorkspaceDrafts() {
  return (
    <WorkspaceModulePlaceholder
      testId="workspace-drafts"
      title="Drafts"
      subtitle="Work in progress."
      icon={FileEdit}
      rationale="Your unsaved builds and resumable jobs surface here."
      primary={{ label: "Open Apps", to: "/workspace/apps" }}
    />
  );
}

export function WorkspaceDeployments() {
  return (
    <WorkspaceModulePlaceholder
      testId="workspace-deployments"
      title="Deployments"
      subtitle="All deploys."
      icon={Rocket}
      rationale="Open a project to deploy or roll back."
      primary={{ label: "Live Apps", to: "/workspace/apps" }}
    />
  );
}

export function WorkspaceDomains() {
  return (
    <div className="max-w-[1080px] mx-auto px-5 sm:px-6 py-8 sm:py-12" data-testid="workspace-domains">
      <div className="mb-7 sm:mb-9">
        <div
          className="mono text-[10px] tracking-[0.30em] uppercase mb-2"
          style={{ color: "var(--nxt-fg-faint)" }}
        >
          Hosting · Domains
        </div>
        <h1
          className="text-[28px] sm:text-[34px] font-semibold tracking-tight leading-tight mb-2"
          style={{ color: "var(--nxt-fg)" }}
        >
          Where will it live?
        </h1>
        <p
          className="text-[14px] max-w-[640px] leading-relaxed"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          Pick a hosting provider. NXT1 ships to the major platforms — Vercel, Netlify,
          Railway, Cloudflare — plus your own server via SSH. Providers without
          credentials wired show a friendly "Connect" hint.
        </p>
      </div>
      <HostingPicker />
      <div className="mt-8">
        <HostingOS />
      </div>
    </div>
  );
}

export function WorkspaceProviders() {
  const [selected, setSelected] = useState(() => {
    try {
      const raw = window.localStorage.getItem("nxt1_default_model");
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  });
  const handleChange = (v) => {
    setSelected(v);
    try { window.localStorage.setItem("nxt1_default_model", JSON.stringify(v)); } catch { /* ignore */ }
  };
  return (
    <div
      className="max-w-[1080px] mx-auto px-5 sm:px-6 py-8 sm:py-12"
      data-testid="workspace-providers"
    >
      <div className="mb-7 sm:mb-9">
        <div
          className="mono text-[10px] tracking-[0.30em] uppercase mb-2"
          style={{ color: "var(--nxt-fg-faint)" }}
        >
          Providers · Models
        </div>
        <h1
          className="text-[28px] sm:text-[34px] font-semibold tracking-tight leading-tight mb-2"
          style={{ color: "var(--nxt-fg)" }}
        >
          Pick your default model.
        </h1>
        <p
          className="text-[14px] max-w-[640px] leading-relaxed"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          NXT1 routes across Claude, GPT, Gemini, Groq, DeepSeek, and OpenRouter. Choose a
          default — or let NXT1 auto-route by task and tier. Per-project overrides land next.
        </p>
      </div>
      <ModelVariantPicker value={selected} onChange={handleChange} />
    </div>
  );
}

export function WorkspaceSettings() {
  return (
    <div
      className="max-w-[1080px] mx-auto px-5 sm:px-6 py-8 sm:py-12"
      data-testid="workspace-settings"
    >
      <div className="mb-7 sm:mb-9">
        <div
          className="mono text-[10px] tracking-[0.30em] uppercase mb-2"
          style={{ color: "var(--nxt-fg-faint)" }}
        >
          Settings · System
        </div>
        <h1
          className="text-[28px] sm:text-[34px] font-semibold tracking-tight leading-tight mb-2"
          style={{ color: "var(--nxt-fg)" }}
        >
          System diagnostics.
        </h1>
        <p
          className="text-[14px] max-w-[640px] leading-relaxed"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          See exactly what's wired and what's not — AI provider keys, OAuth credentials,
          hosting tokens, and core services. Build for portability so you can detach to your
          own infrastructure with zero hardcoded credentials.
        </p>
      </div>
      <SystemDiagnosticsPanel />
    </div>
  );
}

export function WorkspaceEditor() {
  return (
    <WorkspaceModulePlaceholder
      testId="workspace-editor"
      title="Site Editor"
      subtitle="Visual editing for your live apps."
      icon={Wand2}
      rationale="Inline visual editing lands in a follow-up pass. Use the Builder chat for edits today."
      primary={{ label: "Open Apps", to: "/workspace/apps" }}
    />
  );
}
