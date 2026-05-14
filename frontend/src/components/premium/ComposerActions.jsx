/**
 * NXT1 — ComposerActions
 *
 * A compact expandable button that lives near the chat composer. Tap it to
 * reveal a small sheet with Save to GitHub / Deploy / Preview / Export.
 *
 * Replaces the always-visible PublishBar in the builder header. The header
 * stays clean; operational actions are one tap away when you actually want
 * them. Mobile-first: 44px+ touch targets, safe-area aware, large pills.
 */
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { Github, Rocket, Eye, Download, MoreHorizontal, Loader2, ExternalLink, ChevronRight, Check } from "lucide-react";
import api from "@/lib/api";
import { ProviderLogo } from "./ProviderLogos";

// Provider metadata for the in-menu picker (mirrors ModelPickerCockpit's
// shape but trimmed for inline use — no sub-sheet, no kbd navigation).
const PROVIDER_META = {
  anthropic: { label: "Claude", sub: "Sonnet 4.5", tile: "#FAF9F5", invert: false },
  openai:    { label: "ChatGPT", sub: "GPT-4o class", tile: "#202021", invert: true },
  gemini:    { label: "Gemini", sub: "2.0 Pro", tile: "#FFFFFF", invert: false },
  xai:       { label: "Grok", sub: "Grok 4 · xAI", tile: "#0F0F10", invert: true },
  deepseek:  { label: "DeepSeek", sub: "R1 / V3", tile: "#FFFFFF", invert: false },
  emergent:  { label: "Auto", sub: "Smart routing", tile: "linear-gradient(135deg, #5EEAD4 0%, #0E7490 100%)", invert: false },
};
const PROVIDER_ORDER = ["anthropic", "openai", "gemini", "xai", "deepseek", "emergent"];

export default function ComposerActions({
  projectId,
  liveUrl,
  deployState = "idle",
  previewReady = false,
  onPreview,
  onDeploy,
  onDownload,
  // New (2026-05-13): the model picker now lives inside this menu instead of
  // as a separate composer-footer pill. Pass the same shape the cockpit used.
  activeProvider = "anthropic",
  providers = {},
  onProviderChange,
}) {
  const [open, setOpen] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const [github, setGithub] = useState(null);
  const [savingGh, setSavingGh] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    api
      .get(`/integrations/projects/${projectId}/github`)
      .then((r) => { if (!cancelled) setGithub(r.data || null); })
      .catch(() => { if (!cancelled) setGithub(null); });
    return () => { cancelled = true; };
  }, [projectId]);

  // Close on outside click / escape
  useEffect(() => {
    if (!open) return;
    function onDoc(e) {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target)) setOpen(false);
    }
    function onKey(e) { if (e.key === "Escape") setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const saveGithub = async () => {
    if (savingGh) return;
    setSavingGh(true);
    try {
      const { data } = await api.post(`/integrations/projects/${projectId}/github/save`, {});
      setGithub(data);
      toast.success("Saved to GitHub", { description: `${data?.repo_name || "repo"} · ${data?.branch || "main"}` });
      setOpen(false);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.message(detail || "Connect GitHub in Tools → Integrations to enable Save.");
    } finally {
      setSavingGh(false);
    }
  };

  const ghConnected = Boolean(github?.repo_url || github?.source_name);
  const ghLabel = ghConnected ? (github?.repo_name || github?.source_name || "GitHub") : "Save to GitHub";

  return (
    <div className="relative" ref={wrapRef} data-testid="composer-actions">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center justify-center h-9 w-9 rounded-xl transition"
        style={{
          background: open ? "var(--nxt-chip-bg)" : "transparent",
          border: "1px solid var(--nxt-border-soft)",
          color: "var(--nxt-fg-dim)",
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        title="More actions"
        data-testid="composer-actions-trigger"
      >
        <MoreHorizontal size={15} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 380, damping: 30 }}
            className="absolute z-30 left-0 bottom-12 w-[min(280px,calc(100vw-32px))] rounded-2xl overflow-hidden"
            style={{
              background: "var(--nxt-surface)",
              border: "1px solid var(--nxt-border)",
              boxShadow: "var(--nxt-shadow-lg)",
              backdropFilter: "blur(18px) saturate(140%)",
            }}
            role="menu"
            data-testid="composer-actions-menu"
          >
            {/* Model picker — replaces the old footer pill (2026-05-13).
                Tapping the row reveals an inline submenu so the user
                stays inside the same surface. */}
            <ModelRow
              activeProvider={activeProvider}
              providers={providers}
              expanded={modelOpen}
              onToggle={() => setModelOpen((v) => !v)}
              onPick={(k) => {
                onProviderChange?.(k);
                setModelOpen(false);
                setOpen(false);
              }}
            />
            <ActionRow
              icon={savingGh ? Loader2 : Github}
              iconSpinning={savingGh}
              title={savingGh ? "Saving…" : ghLabel}
              subtitle={ghConnected ? `Branch · ${github?.branch || "main"}` : "Push the latest build"}
              state={ghConnected ? "connected" : "idle"}
              onClick={saveGithub}
              testId="composer-action-github"
            />
            <ActionRow
              icon={Rocket}
              title={deployState === "running" ? "Deploying…" : liveUrl ? "Open live" : "Deploy"}
              subtitle={liveUrl ? liveUrl.replace(/^https?:\/\//, "") : "Publish this build"}
              state={deployState === "running" ? "running" : liveUrl ? "connected" : "idle"}
              onClick={() => {
                if (liveUrl) window.open(liveUrl, "_blank");
                else onDeploy?.();
                setOpen(false);
              }}
              right={liveUrl ? <ExternalLink size={11} /> : null}
              testId="composer-action-deploy"
            />
            <ActionRow
              icon={Eye}
              title="Preview"
              subtitle={previewReady ? "Open the live preview" : "Generate something first"}
              state={previewReady ? "connected" : "idle"}
              disabled={!previewReady}
              onClick={() => { onPreview?.(); setOpen(false); }}
              testId="composer-action-preview"
            />
            <ActionRow
              icon={Download}
              title="Export ZIP"
              subtitle="Download the full project"
              onClick={() => { onDownload?.(); setOpen(false); }}
              testId="composer-action-export"
              last
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ActionRow({ icon: Icon, iconSpinning, title, subtitle, state, onClick, right, disabled, testId, last }) {
  const dotColor =
    state === "connected" ? "#5EEAD4" :
    state === "running"   ? "#FBBF24" :
    "transparent";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="w-full flex items-center gap-3 px-3 py-3 text-left transition disabled:opacity-50"
      style={{ borderBottom: last ? "none" : "1px solid var(--nxt-border-soft)" }}
      data-testid={testId}
      role="menuitem"
    >
      <span
        className="relative h-8 w-8 shrink-0 rounded-lg flex items-center justify-center"
        style={{
          background: "var(--nxt-chip-bg)",
          border: "1px solid var(--nxt-border-soft)",
        }}
      >
        <Icon size={13.5} className={iconSpinning ? "animate-spin" : ""} style={{ color: "var(--nxt-fg-dim)" }} />
        {state && state !== "idle" && (
          <span
            className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full"
            style={{ background: dotColor, boxShadow: `0 0 0 2px var(--nxt-surface)` }}
            aria-hidden
          />
        )}
      </span>
      <span className="flex-1 min-w-0">
        <span className="block text-[13.5px] font-medium truncate" style={{ color: "var(--nxt-fg)" }}>
          {title}
        </span>
        {subtitle && (
          <span className="block text-[11.5px] truncate mt-0.5" style={{ color: "var(--nxt-fg-faint)" }}>
            {subtitle}
          </span>
        )}
      </span>
      {right}
    </button>
  );
}

function ModelRow({ activeProvider, providers, expanded, onToggle, onPick }) {
  const active = PROVIDER_META[activeProvider] || PROVIDER_META.anthropic;
  const visible = PROVIDER_ORDER.filter((k) => k in PROVIDER_META);
  return (
    <div style={{ borderBottom: "1px solid var(--nxt-border-soft)" }}>
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-3 py-3 text-left transition"
        data-testid="composer-action-model"
        role="menuitem"
        aria-expanded={expanded}
      >
        <span
          className="relative h-8 w-8 shrink-0 rounded-lg flex items-center justify-center overflow-hidden"
          style={{
            background: active.tile,
            border: "1px solid var(--nxt-border-soft)",
          }}
        >
          <ProviderLogo provider={activeProvider} size={14} invert={active.invert} />
        </span>
        <span className="flex-1 min-w-0">
          <span
            className="block text-[11px] font-mono tracking-[0.18em] uppercase"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            Model
          </span>
          <span
            className="block text-[13.5px] font-medium truncate"
            style={{ color: "var(--nxt-fg)" }}
          >
            {active.label}
            <span className="ml-1.5 text-[12px]" style={{ color: "var(--nxt-fg-faint)" }}>
              {active.sub}
            </span>
          </span>
        </span>
        <ChevronRight
          size={13}
          className="transition-transform duration-200 shrink-0"
          style={{
            color: "var(--nxt-fg-faint)",
            transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
          }}
        />
      </button>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.ul
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
            style={{ background: "var(--nxt-chip-bg)" }}
          >
            {visible.map((k) => {
              const meta = PROVIDER_META[k];
              const isActive = k === activeProvider;
              const connected = !!providers[k] || k === "emergent" || k === "anthropic";
              return (
                <li key={k}>
                  <button
                    type="button"
                    onClick={() => onPick(k)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 text-left transition hover:bg-white/[0.03]"
                    data-testid={`composer-model-option-${k}`}
                    role="menuitemradio"
                    aria-checked={isActive}
                  >
                    <span
                      className="h-6 w-6 shrink-0 rounded-md flex items-center justify-center overflow-hidden"
                      style={{
                        background: meta.tile,
                        border: "1px solid var(--nxt-border-soft)",
                      }}
                    >
                      <ProviderLogo provider={k} size={11} invert={meta.invert} />
                    </span>
                    <span className="flex-1 min-w-0">
                      <span
                        className="block text-[12.5px] font-medium truncate"
                        style={{ color: connected ? "var(--nxt-fg)" : "var(--nxt-fg-faint)" }}
                      >
                        {meta.label}
                      </span>
                      <span className="block text-[10.5px] truncate" style={{ color: "var(--nxt-fg-faint)" }}>
                        {connected ? meta.sub : "Not configured"}
                      </span>
                    </span>
                    {isActive && (
                      <Check size={12} className="shrink-0" style={{ color: "#5EEAD4" }} />
                    )}
                  </button>
                </li>
              );
            })}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
