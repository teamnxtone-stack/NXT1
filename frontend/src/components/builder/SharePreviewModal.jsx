/**
 * SharePreviewModal — slim modal that surfaces the shareable preview link with
 * copy, open-in-new-tab, public/private toggle and password protection.
 */
import { useEffect, useState } from "react";
import { Copy, ExternalLink, Lock, Sparkles, Unlock, X } from "lucide-react";
import { toast } from "sonner";
import { createPreview } from "@/lib/api";

export default function SharePreviewModal({ open, onClose, projectId, preview, onUpdated, onRegenerate, regenerating }) {
  const [copied, setCopied] = useState(false);
  const [pwInput, setPwInput] = useState("");
  const [showPwField, setShowPwField] = useState(false);
  const [savingPw, setSavingPw] = useState(false);
  const [togglingPublic, setTogglingPublic] = useState(false);

  useEffect(() => {
    if (!open) {
      setCopied(false);
      setPwInput("");
      setShowPwField(false);
    }
  }, [open]);

  if (!open || !preview?.url) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(preview.url);
      setCopied(true);
      toast.success("Preview link copied");
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error("Couldn't copy — long-press to copy manually");
    }
  };

  const togglePublic = async () => {
    if (!projectId) return;
    setTogglingPublic(true);
    try {
      const { data } = await createPreview(projectId, { public: preview.public === false });
      onUpdated?.(data);
      toast.success(data.public === false ? "Preview is now private" : "Preview is now public");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't update preview");
    } finally {
      setTogglingPublic(false);
    }
  };

  const setPassword = async () => {
    if (!projectId || pwInput.length < 4) {
      toast.error("Password must be at least 4 characters");
      return;
    }
    setSavingPw(true);
    try {
      const { data } = await createPreview(projectId, { password: pwInput });
      onUpdated?.(data);
      setPwInput("");
      setShowPwField(false);
      toast.success("Preview locked with password");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't set password");
    } finally {
      setSavingPw(false);
    }
  };

  const removePassword = async () => {
    if (!projectId) return;
    setSavingPw(true);
    try {
      const { data } = await createPreview(projectId, { password: "" });
      onUpdated?.(data);
      toast.success("Password removed");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't remove password");
    } finally {
      setSavingPw(false);
    }
  };

  const updated = preview.updated_at ? new Date(preview.updated_at) : null;
  const builds = preview.build_count || 1;

  return (
    <div
      className="fixed inset-0 z-[80] bg-graphite-scrim backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4 nxt-fade-up"
      data-testid="share-preview-modal"
      onClick={onClose}
    >
      <div
        className="w-full sm:w-[480px] bg-[#1F1F23] border border-white/10 rounded-t-3xl sm:rounded-2xl shadow-[0_30px_80px_-20px_rgba(0,0,0,0.8)] overflow-hidden nxt-safe-bottom"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/8">
          <div>
            <div className="text-[10px] mono uppercase tracking-[0.32em] text-emerald-300 flex items-center gap-1.5">
              <Sparkles size={10} />
              shareable preview
            </div>
            <div className="text-[16px] font-semibold text-white mt-1">
              Send this to anyone for review
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-8 w-8 rounded-full flex items-center justify-center text-zinc-400 hover:text-white hover:bg-white/5 transition"
            data-testid="share-preview-close"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 max-h-[75vh] overflow-y-auto">
          {/* The URL */}
          <div>
            <div className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500 mb-2">
              Preview URL
            </div>
            <div className="flex items-stretch gap-2">
              <input
                value={preview.url}
                readOnly
                className="flex-1 min-w-0 px-3 py-2.5 rounded-lg bg-graphite-scrim-soft border border-white/10 text-[13px] mono text-zinc-200 focus:outline-none focus:border-white/30 truncate"
                data-testid="share-preview-url-input"
              />
              <button
                type="button"
                onClick={copy}
                className={`px-3.5 py-2.5 rounded-lg border text-[12px] mono uppercase tracking-wider transition shrink-0 ${
                  copied
                    ? "bg-emerald-400/15 border-emerald-400/40 text-emerald-200"
                    : "bg-white text-black border-white hover:bg-zinc-100"
                }`}
                data-testid="share-preview-copy-button"
              >
                <span className="inline-flex items-center gap-1.5">
                  <Copy size={12} />
                  {copied ? "copied" : "copy"}
                </span>
              </button>
            </div>
          </div>

          {/* Stats */}
          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-white/10 bg-white/[0.03] text-[11px] mono text-zinc-300">
              <span className="text-emerald-300 font-semibold">{builds}</span>
              <span className="text-zinc-500">{builds === 1 ? "build" : "builds"}</span>
            </span>
            {updated && (
              <span
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-white/10 bg-white/[0.03] text-[11px] mono text-zinc-300"
                title={updated.toISOString()}
              >
                <span className="text-zinc-500">updated</span>
                <span className="text-zinc-200">{relativeTime(updated)}</span>
              </span>
            )}
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] mono ${
              preview.public === false
                ? "border-amber-400/25 bg-amber-500/[0.07] text-amber-200"
                : "border-emerald-400/25 bg-emerald-500/[0.07] text-emerald-200"
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${preview.public === false ? "bg-amber-400" : "bg-emerald-400"}`} />
              {preview.public === false ? "private" : "public"}
            </span>
            {preview.password_protected && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-fuchsia-400/30 bg-fuchsia-500/[0.07] text-fuchsia-200 text-[11px] mono">
                <Lock size={10} />
                password
              </span>
            )}
          </div>

          {/* Primary actions */}
          <div className="flex flex-wrap gap-2 pt-1">
            <a
              href={preview.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-emerald-400 text-black text-sm font-semibold hover:bg-emerald-300 transition"
              data-testid="share-preview-open-button"
            >
              <ExternalLink size={13} />
              Open preview
            </a>
            <button
              type="button"
              onClick={onRegenerate}
              disabled={regenerating}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-transparent border border-white/15 text-zinc-200 text-sm hover:border-white/30 hover:text-white transition disabled:opacity-60"
              data-testid="share-preview-refresh-button"
            >
              {regenerating ? "Refreshing…" : "Refresh build"}
            </button>
          </div>

          {/* Privacy controls */}
          <div className="pt-3 mt-2 border-t border-white/5 space-y-3">
            <div className="mono text-[10px] tracking-[0.28em] uppercase text-zinc-500">
              Privacy
            </div>

            {/* Public/Private */}
            <div className="flex items-center gap-3 px-3.5 py-3 rounded-xl border border-white/10 surface-1">
              <span className="h-9 w-9 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center shrink-0">
                {preview.public === false ? (
                  <Lock size={14} className="text-amber-300" />
                ) : (
                  <Unlock size={14} className="text-emerald-300" />
                )}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-[13px] text-white">
                  {preview.public === false ? "Private preview" : "Public preview"}
                </div>
                <div className="text-[11px] text-zinc-500 mt-0.5 leading-snug">
                  {preview.public === false
                    ? "Anyone with the link sees a 'private preview' page."
                    : "Anyone with the link can view this preview."}
                </div>
              </div>
              <button
                type="button"
                onClick={togglePublic}
                disabled={togglingPublic}
                className={`relative h-6 w-11 rounded-full border transition shrink-0 ${
                  preview.public !== false
                    ? "bg-emerald-400/90 border-emerald-300"
                    : "bg-white/5 border-white/15"
                }`}
                data-testid="share-preview-public-toggle"
                aria-pressed={preview.public !== false}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-[#1F1F23] shadow transition-all ${
                    preview.public !== false ? "left-[22px]" : "left-0.5"
                  }`}
                />
              </button>
            </div>

            {/* Password */}
            <div className="px-3.5 py-3 rounded-xl border border-white/10 surface-1">
              <div className="flex items-center gap-3">
                <span className="h-9 w-9 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center shrink-0">
                  <Lock size={14} className={preview.password_protected ? "text-fuchsia-300" : "text-zinc-400"} />
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] text-white">
                    {preview.password_protected ? "Password protected" : "Password protect"}
                  </div>
                  <div className="text-[11px] text-zinc-500 mt-0.5 leading-snug">
                    {preview.password_protected
                      ? "Anyone with the link must enter the password to view."
                      : "Lock this preview behind a password reviewers must enter."}
                  </div>
                </div>
                {preview.password_protected ? (
                  <button
                    type="button"
                    onClick={removePassword}
                    disabled={savingPw}
                    className="px-2.5 py-1.5 rounded-md text-[11px] mono uppercase tracking-wider border border-white/15 text-zinc-300 hover:border-white/30 hover:text-white transition shrink-0"
                    data-testid="share-preview-remove-password"
                  >
                    Remove
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => setShowPwField((v) => !v)}
                    className="px-2.5 py-1.5 rounded-md text-[11px] mono uppercase tracking-wider border border-white/15 text-zinc-300 hover:border-white/30 hover:text-white transition shrink-0"
                    data-testid="share-preview-set-password-toggle"
                  >
                    {showPwField ? "Cancel" : "Set"}
                  </button>
                )}
              </div>
              {showPwField && !preview.password_protected && (
                <form
                  onSubmit={(e) => { e.preventDefault(); setPassword(); }}
                  className="flex items-stretch gap-2 mt-3"
                >
                  <input
                    type="text"
                    value={pwInput}
                    onChange={(e) => setPwInput(e.target.value)}
                    placeholder="Choose a password (min 4 chars)"
                    minLength={4}
                    autoFocus
                    className="flex-1 px-3 py-2.5 rounded-lg bg-graphite-scrim-soft border border-white/10 text-[13px] text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-fuchsia-400/40"
                    data-testid="share-preview-password-input"
                  />
                  <button
                    type="submit"
                    disabled={savingPw || pwInput.length < 4}
                    className="px-3.5 py-2.5 rounded-lg bg-fuchsia-400 text-black text-[12px] mono uppercase tracking-wider font-semibold hover:bg-fuchsia-300 transition disabled:opacity-60 shrink-0"
                    data-testid="share-preview-save-password"
                  >
                    {savingPw ? "Saving…" : "Lock"}
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function relativeTime(d) {
  const ms = Date.now() - d.getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.floor(h / 24);
  return `${days}d ago`;
}
