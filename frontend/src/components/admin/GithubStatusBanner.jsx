/**
 * GithubStatusBanner — admin-only banner that surfaces whether the configured
 * GITHUB_TOKEN can actually push. Distinguishes:
 *   - configured + ready + write_probe=ok  -> green
 *   - configured + ready + write_probe!=ok -> amber w/ scope upgrade hint
 *   - configured + !ready                  -> red
 *   - !configured                          -> neutral
 */
import { AlertTriangle, CheckCircle2, ExternalLink, Github, KeyRound } from "lucide-react";

export default function GithubStatusBanner({ gh }) {
  if (!gh) {
    return (
      <div className="rounded-xl border border-white/10 surface-1 px-4 py-3 mb-4 text-[12px] text-zinc-500" data-testid="github-status-banner-loading">
        Checking GitHub token…
      </div>
    );
  }

  if (!gh.configured) {
    return (
      <div
        className="rounded-xl border border-white/10 surface-1 px-4 py-3 mb-4 flex items-start gap-3"
        data-testid="github-status-banner-missing"
      >
        <span className="h-7 w-7 rounded-lg bg-white/[0.04] border border-white/10 flex items-center justify-center shrink-0">
          <KeyRound size={13} className="text-zinc-400" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] text-white">No GITHUB_TOKEN configured</div>
          <div className="text-[12px] text-zinc-500 mt-0.5">
            Site Editor can still propose + apply edits to disk, but commits
            and Vercel auto-deploys are disabled until a fine-grained PAT is
            saved to <span className="mono text-zinc-300">/app/backend/.env</span>.
          </div>
        </div>
      </div>
    );
  }

  if (!gh.ready) {
    return (
      <div
        className="rounded-xl border border-red-400/30 bg-red-500/[0.07] px-4 py-3 mb-4 flex items-start gap-3"
        data-testid="github-status-banner-rejected"
      >
        <span className="h-7 w-7 rounded-lg bg-red-500/15 border border-red-400/30 flex items-center justify-center shrink-0">
          <AlertTriangle size={13} className="text-red-300" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] text-red-100">GitHub token is invalid</div>
          <div className="text-[12px] text-red-200/80 mt-0.5 leading-relaxed">
            {gh.summary}
          </div>
        </div>
      </div>
    );
  }

  // Ready but with the standard upgrade reminder (always show until first push succeeds)
  const probeOk = gh.write_probe === "ok";
  return (
    <div
      className={`rounded-xl border px-4 py-3 mb-4 flex items-start gap-3 ${
        probeOk
          ? "border-emerald-400/25 bg-emerald-500/[0.05]"
          : "border-amber-400/30 bg-amber-500/[0.07]"
      }`}
      data-testid={probeOk ? "github-status-banner-ready" : "github-status-banner-warn"}
    >
      <span
        className={`h-7 w-7 rounded-lg flex items-center justify-center shrink-0 border ${
          probeOk ? "bg-emerald-500/15 border-emerald-400/30" : "bg-amber-500/15 border-amber-400/30"
        }`}
      >
        {probeOk ? (
          <CheckCircle2 size={13} className="text-emerald-300" />
        ) : (
          <Github size={13} className="text-amber-300" />
        )}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-[13px] text-white flex items-center gap-2">
          GitHub: <span className="mono text-zinc-200">{gh.login}</span>
          {gh.avatar_url && (
            <img
              src={gh.avatar_url}
              alt=""
              className="h-4 w-4 rounded-full"
            />
          )}
        </div>
        <div className="text-[12px] text-zinc-400 mt-1 leading-relaxed">
          For Site Editor pushes, the fine-grained PAT must grant{" "}
          <span className="mono text-white">Contents: read &amp; write</span>,{" "}
          <span className="mono text-white">Administration: read &amp; write</span>, and{" "}
          <span className="mono text-white">Metadata: read</span> on the target repo.
        </div>
        <a
          href="https://github.com/settings/tokens?type=beta"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 mt-2 text-[11.5px] mono uppercase tracking-wider text-emerald-300 hover:underline"
        >
          Manage PAT scopes
          <ExternalLink size={10} />
        </a>
      </div>
    </div>
  );
}
