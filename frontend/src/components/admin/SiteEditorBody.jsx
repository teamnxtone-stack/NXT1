/**
 * SiteEditorBody — body of the site editor (reused by AdminWorkspace).
 * Identical behavior to the standalone /admin/site-editor page but no top
 * chrome (chrome lives in AdminWorkspace's shell).
 *
 * Pass `historyOnly` to render only the history list — useful for the
 * dedicated History tab.
 */
import { useEffect, useRef, useState } from "react";
import {
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
import {
  siteEditorApply,
  siteEditorHistory,
  siteEditorListFiles,
  siteEditorPropose,
  siteEditorRollback,
} from "@/lib/api";

const SUGGESTIONS = [
  "Tighten the landing copy and shorten the hero paragraph by half.",
  "Add a 'Pricing' section to the landing page with 3 tiers.",
  "Move the admin Workspace link out of the footer entirely.",
  "Make the public footer 2-column on mobile.",
];

export default function SiteEditorBody({ historyOnly = false }) {
  const [files, setFiles] = useState([]);
  const [history, setHistory] = useState([]);
  const [prompt, setPrompt] = useState("");
  const [proposing, setProposing] = useState(false);
  const [proposal, setProposal] = useState(null);
  const [applying, setApplying] = useState(false);
  const [scope, setScope] = useState([]);
  const promptRef = useRef(null);

  useEffect(() => {
    if (!historyOnly) {
      siteEditorListFiles().then(({ data }) => setFiles(data.items || [])).catch(() => {});
    }
    refreshHistory();
  }, [historyOnly]);

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

  if (historyOnly) {
    return <HistoryList items={history} onRollback={rollback} />;
  }

  return (
    <div className="grid lg:grid-cols-[minmax(0,1fr)_320px] min-h-full">
      <main className="px-4 sm:px-6 py-6">
        <div className="max-w-3xl">
          <div className="mono text-[10px] tracking-[0.32em] uppercase text-zinc-500 mb-1.5">
            // ai site editor
          </div>
          <h1
            className="text-2xl sm:text-3xl font-black tracking-tighter mb-2"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
          >
            What do you want to change?
          </h1>
          <p className="text-zinc-400 text-[13px] mb-5 leading-relaxed">
            Plain English. NXT1 inspects the code, proposes a diff, you approve,
            it pushes to GitHub, Vercel auto-deploys. Every change is reversible.
          </p>

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

          {!proposal && !proposing && (
            <div className="mt-3 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => {
                    setPrompt(s);
                    promptRef.current?.focus();
                  }}
                  className="text-[11.5px] mono text-zinc-400 px-2.5 py-1.5 border border-white/10 hover:border-white/30 hover:text-white rounded-full transition-colors"
                  data-testid={`site-editor-suggestion-${i}`}
                >
                  <Sparkles size={10} className="inline mr-1.5 -mt-0.5" />
                  {s}
                </button>
              ))}
            </div>
          )}

          {proposal && (
            <ProposalCard
              proposal={proposal}
              applying={applying}
              onApply={apply}
              onDiscard={() => setProposal(null)}
            />
          )}

          <div className="mt-8">
            <div className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500 mb-2 flex items-center gap-1.5">
              <History size={10} />
              Recent edits
            </div>
            <HistoryList items={history.slice(0, 6)} onRollback={rollback} compact />
          </div>
        </div>
      </main>

      <aside className="hidden lg:block border-l border-white/8 bg-[#1F1F23] overflow-y-auto">
        <FilesRail files={files} scope={scope} onToggle={togglePath} />
      </aside>
    </div>
  );
}

function ProposalCard({ proposal, applying, onApply, onDiscard }) {
  return (
    <div
      className="mt-5 rounded-2xl border border-emerald-400/25 bg-gradient-to-br from-[#0d1614] via-[#1F1F23] to-[#1F1F23] p-5"
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
      <div className="flex flex-wrap gap-2">
        <button
          onClick={onApply}
          disabled={applying}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-emerald-400 text-black text-sm font-semibold shadow hover:bg-emerald-300 transition disabled:opacity-60"
          data-testid="site-editor-apply"
        >
          {applying ? <Loader2 size={13} className="animate-spin" /> : <GitBranch size={13} strokeWidth={2.5} />}
          {applying ? "Pushing to GitHub…" : "Apply + push"}
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
    <div className="p-3.5">
      <div className="flex items-center gap-2 mb-2.5">
        <Code2 size={12} className="text-zinc-500" />
        <span className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500">
          Whitelisted files
        </span>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3 leading-relaxed">
        Tap to scope a proposal to specific files. AI may only read &amp; write
        these paths.
      </p>
      <div className="space-y-1">
        {files.map((f) => {
          const sel = scope.includes(f.path);
          return (
            <button
              key={f.path}
              onClick={() => onToggle(f.path)}
              className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md border transition text-left ${
                sel
                  ? "border-emerald-400/40 bg-emerald-500/[0.07] text-emerald-100"
                  : "border-white/5 bg-white/[0.02] text-zinc-300 hover:border-white/15"
              }`}
              data-testid={`site-editor-file-${f.path}`}
            >
              <span
                className={`h-3.5 w-3.5 rounded-sm border flex items-center justify-center shrink-0 ${
                  sel ? "bg-emerald-400 border-emerald-300" : "border-white/15"
                }`}
              >
                {sel && <Check size={9} className="text-black" />}
              </span>
              <FileText size={10} className="text-zinc-500 shrink-0" />
              <span className="text-[11px] mono truncate">{f.path}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function HistoryList({ items, onRollback, compact = false }) {
  if (!items || items.length === 0) {
    return (
      <div className="text-[12px] text-zinc-500 py-6 text-center border border-dashed border-white/10 rounded-lg">
        No edits yet.
      </div>
    );
  }
  return (
    <div className={compact ? "space-y-1.5" : "space-y-2"}>
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
              <div className="text-[12.5px] text-white truncate">{it.summary || it.prompt}</div>
              <div className="text-[10px] mono uppercase tracking-wider text-zinc-500 mt-1">
                {it.status} · {(it.files || []).length} files · {fmtTime(it.created_at)}
                {it.source === "brand_theme" && " · brand"}
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
  );
}

function fmtTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return "";
  }
}
