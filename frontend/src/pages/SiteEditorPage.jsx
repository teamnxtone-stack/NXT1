/**
 * SiteEditorPage — admin-only AI-powered editor for the NXT1 site itself.
 *
 * Type a natural language prompt → AI proposes file edits → review the diff
 * summary → Apply commits to disk and pushes to GitHub. Vercel auto-deploys
 * on the GitHub commit. Full history with one-click rollback.
 *
 * Whitelist-only: backend exposes a curated set of safe paths
 * (frontend/src/pages/*.jsx, components/Brand.jsx, etc) — the AI cannot
 * touch routing, env, or backend infrastructure.
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Code2,
  ExternalLink,
  FileText,
  GitBranch,
  History,
  Loader2,
  RotateCcw,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { toast } from "sonner";
import Brand from "@/components/Brand";
import {
  siteEditorApply,
  siteEditorHistory,
  siteEditorListFiles,
  siteEditorPropose,
  siteEditorRollback,
} from "@/lib/api";

const SUGGESTIONS = [
  "Make the hero gradient more emerald-forward.",
  "Add a 'Pricing' link in the public nav that scrolls to a new pricing section.",
  "Tighten the landing copy and shorten the hero paragraph by half.",
  "Switch the public footer to a 2-column layout on mobile.",
];

export default function SiteEditorPage() {
  const [files, setFiles] = useState([]);
  const [history, setHistory] = useState([]);
  const [prompt, setPrompt] = useState("");
  const [proposing, setProposing] = useState(false);
  const [proposal, setProposal] = useState(null); // {edit_id, summary, explanation, files:[{path,content}]}
  const [applying, setApplying] = useState(false);
  const [scope, setScope] = useState([]); // selected paths; empty = all
  const [showHistory, setShowHistory] = useState(false);
  const promptRef = useRef(null);

  useEffect(() => {
    siteEditorListFiles().then(({ data }) => setFiles(data.items || [])).catch(() => {});
    refreshHistory();
  }, []);

  const refreshHistory = () =>
    siteEditorHistory().then(({ data }) => setHistory(data.items || [])).catch(() => {});

  const togglePath = (p) =>
    setScope((s) => (s.includes(p) ? s.filter((x) => x !== p) : [...s, p]));

  const propose = async (text = prompt) => {
    if (!text.trim()) {
      toast.error("Type a prompt first.");
      return;
    }
    setProposal(null);
    setProposing(true);
    try {
      const { data } = await siteEditorPropose(text, scope.length ? scope : null);
      setProposal(data);
      toast.success("Edit proposed — review and apply when ready.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't generate proposal");
    } finally {
      setProposing(false);
    }
  };

  const apply = async () => {
    if (!proposal) return;
    setApplying(true);
    try {
      const { data } = await siteEditorApply(proposal.edit_id, { push_to_github: true });
      const ghErr = data?.github?.error;
      if (ghErr) {
        toast.warning("Applied locally — GitHub push failed", { description: ghErr });
      } else if (data?.github?.repo_url) {
        toast.success("Applied + pushed to GitHub. Vercel will auto-deploy.", {
          description: data.github.repo_url,
          action: {
            label: "Open repo",
            onClick: () => window.open(data.github.repo_url, "_blank"),
          },
        });
      } else {
        toast.success("Applied to disk.");
      }
      setProposal(null);
      setPrompt("");
      refreshHistory();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Apply failed");
    } finally {
      setApplying(false);
    }
  };

  const rollback = async (id) => {
    try {
      await siteEditorRollback(id);
      toast.success("Rolled back to that snapshot.");
      refreshHistory();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Rollback failed");
    }
  };

  return (
    <div
      className="min-h-[100dvh] w-full surface-recessed text-white flex flex-col"
      data-testid="site-editor-page"
      style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}
    >
      {/* Header */}
      <header className="h-14 shrink-0 flex items-center justify-between px-4 sm:px-6 border-b border-white/10 bg-[#1F1F23]">
        <div className="flex items-center gap-3">
          <Link
            to="/workspace"
            className="h-9 w-9 flex items-center justify-center rounded-full text-zinc-300 hover:text-white hover:bg-white/5 transition"
            data-testid="site-editor-back"
            aria-label="Back to dashboard"
          >
            <ArrowLeft size={15} />
          </Link>
          <Brand size="sm" gradient />
          <span className="text-zinc-600">/</span>
          <span className="mono text-[11px] tracking-[0.28em] uppercase text-emerald-300 flex items-center gap-1.5">
            <Sparkles size={11} />
            site editor
          </span>
        </div>
        <button
          onClick={() => setShowHistory((v) => !v)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] mono uppercase tracking-wider border border-white/15 text-zinc-200 hover:border-white/30 hover:text-white transition"
          data-testid="site-editor-history-toggle"
        >
          <History size={11} />
          History ({history.length})
        </button>
      </header>

      {/* Body */}
      <div className="flex-1 min-h-0 grid lg:grid-cols-[minmax(0,1fr)_360px]">
        {/* Main column */}
        <main className="min-h-0 overflow-y-auto px-4 sm:px-8 py-8">
          <div className="max-w-3xl mx-auto">
            <div className="mono text-[10px] tracking-[0.32em] uppercase text-zinc-500 mb-2">
              // Edit the site with natural language
            </div>
            <h1
              className="text-3xl sm:text-4xl font-black tracking-tighter mb-2"
              style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
            >
              What do you want to change?
            </h1>
            <p className="text-zinc-400 text-[14px] mb-7 leading-relaxed">
              Describe a tweak in plain English. NXT1 will edit the site
              source, push to GitHub, and Vercel will auto-deploy. Every
              change is reversible from history.
            </p>

            {/* Prompt input */}
            <div className="rounded-2xl border border-white/10 surface-1 p-1">
              <textarea
                ref={promptRef}
                rows={3}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    propose();
                  }
                }}
                placeholder="e.g. Add a Pricing section after the hero with 3 tiers. Make the CTA copy more direct."
                className="w-full bg-transparent border-0 outline-none resize-none px-4 py-3 text-[14px] text-white placeholder:text-zinc-600"
                data-testid="site-editor-prompt"
              />
              <div className="flex items-center justify-between px-3 py-2 border-t border-white/5">
                <div className="text-[11px] mono uppercase tracking-wider text-zinc-500">
                  {scope.length === 0
                    ? `${files.length} files in scope`
                    : `${scope.length} of ${files.length} files in scope`}
                </div>
                <button
                  type="button"
                  onClick={() => propose()}
                  disabled={proposing || !prompt.trim()}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-400 text-black text-sm font-semibold hover:bg-emerald-300 transition disabled:opacity-60 disabled:cursor-not-allowed"
                  data-testid="site-editor-propose"
                >
                  {proposing ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Send size={13} strokeWidth={2.5} />
                  )}
                  {proposing ? "Thinking…" : "Propose changes"}
                </button>
              </div>
            </div>

            {/* Suggestions */}
            {!proposal && !proposing && (
              <div className="mt-4 flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => {
                      setPrompt(s);
                      promptRef.current?.focus();
                    }}
                    className="text-[12px] mono text-zinc-400 px-3 py-1.5 border border-white/10 hover:border-white/30 hover:text-white rounded-full transition-colors"
                    data-testid={`site-editor-suggestion-${SUGGESTIONS.indexOf(s)}`}
                  >
                    <Sparkles size={10} className="inline mr-1.5 -mt-0.5" />
                    {s}
                  </button>
                ))}
              </div>
            )}

            {/* Proposal */}
            {proposal && (
              <ProposalCard
                proposal={proposal}
                applying={applying}
                onApply={apply}
                onDiscard={() => setProposal(null)}
              />
            )}
          </div>
        </main>

        {/* Side rail */}
        <aside className="hidden lg:block border-l border-white/8 bg-[#1F1F23] overflow-y-auto">
          {showHistory ? (
            <HistoryRail
              items={history}
              onClose={() => setShowHistory(false)}
              onRollback={rollback}
            />
          ) : (
            <FilesRail files={files} scope={scope} onToggle={togglePath} />
          )}
        </aside>
      </div>

      {/* Mobile history overlay */}
      {showHistory && (
        <div className="lg:hidden fixed inset-0 z-40 bg-graphite-scrim-strong backdrop-blur-sm">
          <div className="absolute inset-0 bg-[#1F1F23] overflow-y-auto">
            <HistoryRail items={history} onClose={() => setShowHistory(false)} onRollback={rollback} />
          </div>
        </div>
      )}
    </div>
  );
}

function ProposalCard({ proposal, applying, onApply, onDiscard }) {
  return (
    <div
      className="mt-6 rounded-2xl border border-emerald-400/25 bg-gradient-to-br from-[#0d1614] via-[#1F1F23] to-[#1F1F23] p-5"
      data-testid="site-editor-proposal"
    >
      <div className="flex items-start gap-3 mb-4">
        <span className="h-9 w-9 rounded-full bg-emerald-500/15 border border-emerald-400/30 flex items-center justify-center shrink-0">
          <Sparkles size={14} className="text-emerald-300" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] mono uppercase tracking-[0.28em] text-emerald-400 mb-1">
            Proposed change · {proposal.files?.length || 0} files
          </div>
          <div className="text-[15px] font-semibold text-emerald-100 mb-1.5">
            {proposal.summary}
          </div>
          {proposal.explanation && (
            <p className="text-[13px] text-zinc-300 leading-relaxed">
              {proposal.explanation}
            </p>
          )}
        </div>
      </div>

      {/* File list */}
      <div className="space-y-1.5 mb-4">
        {(proposal.files || []).map((f) => (
          <div
            key={f.path}
            className="flex items-center gap-2 text-[12px] mono text-zinc-300 bg-graphite-scrim-soft border border-white/5 rounded-lg px-3 py-2"
          >
            <FileText size={12} className="text-emerald-300/80 shrink-0" />
            <span className="truncate">{f.path}</span>
            <span className="ml-auto text-zinc-500">{(f.content || "").length.toLocaleString()} chars</span>
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={onApply}
          disabled={applying}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-emerald-400 text-black text-sm font-semibold shadow hover:bg-emerald-300 transition disabled:opacity-60"
          data-testid="site-editor-apply"
        >
          {applying ? <Loader2 size={13} className="animate-spin" /> : <GitBranch size={13} strokeWidth={2.5} />}
          {applying ? "Pushing to GitHub…" : "Apply + push to GitHub"}
        </button>
        <button
          onClick={onDiscard}
          disabled={applying}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-transparent border border-white/15 text-zinc-200 text-sm hover:border-white/30 hover:text-white transition disabled:opacity-60"
          data-testid="site-editor-discard"
        >
          <X size={13} />
          Discard
        </button>
      </div>
    </div>
  );
}

function FilesRail({ files, scope, onToggle }) {
  return (
    <div className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <Code2 size={13} className="text-zinc-500" />
        <span className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500">
          Whitelisted files
        </span>
      </div>
      <p className="text-[12px] text-zinc-500 mb-4 leading-relaxed">
        These are the only files the AI may read or edit. Tap to scope a
        proposal to specific files only.
      </p>
      <div className="space-y-1.5">
        {files.map((f) => {
          const sel = scope.includes(f.path);
          return (
            <button
              key={f.path}
              onClick={() => onToggle(f.path)}
              className={`group w-full flex items-center gap-2 px-2.5 py-2 rounded-md border transition text-left ${
                sel
                  ? "border-emerald-400/40 bg-emerald-500/[0.07] text-emerald-100"
                  : "border-white/5 bg-white/[0.02] text-zinc-300 hover:border-white/15"
              }`}
              data-testid={`site-editor-file-${f.path}`}
            >
              <span
                className={`h-4 w-4 rounded-sm border flex items-center justify-center shrink-0 ${
                  sel ? "bg-emerald-400 border-emerald-300" : "border-white/15"
                }`}
              >
                {sel && <Check size={10} className="text-black" />}
              </span>
              <FileText size={11} className="text-zinc-500 shrink-0" />
              <span className="text-[11.5px] mono truncate">{f.path}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function HistoryRail({ items, onClose, onRollback }) {
  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <History size={13} className="text-zinc-500" />
          <span className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500">
            Edit history
          </span>
        </div>
        <button
          onClick={onClose}
          className="h-7 w-7 flex items-center justify-center rounded-full text-zinc-500 hover:text-white hover:bg-white/5 transition"
          aria-label="Close history"
        >
          <X size={13} />
        </button>
      </div>
      {items.length === 0 ? (
        <div className="text-[12px] text-zinc-500 py-6 text-center border border-dashed border-white/10 rounded-lg">
          No edits yet.
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((it) => (
            <div
              key={it.edit_id}
              className="rounded-xl border border-white/8 surface-1 p-3"
              data-testid={`site-editor-history-${it.edit_id}`}
            >
              <div className="flex items-start gap-2">
                <span
                  className={`h-2 w-2 rounded-full mt-1.5 shrink-0 ${
                    it.status === "applied"
                      ? "bg-emerald-400"
                      : it.status === "rolled_back"
                        ? "bg-amber-400"
                        : "bg-zinc-500"
                  }`}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-[12px] text-white truncate">{it.summary || it.prompt}</div>
                  <div className="text-[10px] mono uppercase tracking-wider text-zinc-500 mt-1">
                    {it.status} · {(it.files || []).length} files · {fmtTime(it.created_at)}
                  </div>
                  {it.github?.repo_url && (
                    <a
                      href={it.github.repo_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 inline-flex items-center gap-1 text-[11px] text-emerald-300 hover:underline"
                    >
                      <ExternalLink size={10} />
                      {it.github.owner}/{it.github.name}
                    </a>
                  )}
                </div>
                {it.status === "applied" && (
                  <button
                    onClick={() => onRollback(it.edit_id)}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] mono uppercase tracking-wider border border-white/10 text-zinc-400 hover:border-white/30 hover:text-white transition"
                    data-testid={`site-editor-rollback-${it.edit_id}`}
                  >
                    <RotateCcw size={10} />
                    Roll back
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function fmtTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return "";
  }
}
