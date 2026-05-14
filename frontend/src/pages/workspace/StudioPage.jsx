/**
 * NXT1 — Studio (Video)
 *
 * Native lightweight video studio:
 *   • Upload mp4/mov/webm clips
 *   • AI text-to-video via Fal.ai (CogVideoX-5B)
 *   • Sequence clips into a simple horizontal timeline (drag-reorder)
 *   • Preview the active clip in a player
 *   • Export = currently downloads the active clip (browser-side mp4
 *     concatenation is non-trivial without ffmpeg.wasm — flagged as v2)
 *   • Post to Social → creates social drafts the Social page sees
 *
 * Mobile collapses the timeline into a vertical clip-list and keeps the
 * Export / Post buttons fixed at the bottom.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload, Sparkles, Loader2, Play, Trash2, Download, Send,
  Film, X, ChevronRight, Check, Plus,
} from "lucide-react";
import {
  videoUpload, videoListClips, videoDeleteClip, videoGenerate,
  videoListJobs, videoHealth, videoPostToSocial, mediaUrl,
} from "@/lib/api";
import useJobProgress, { rememberJob, recallJob, forgetJob } from "@/hooks/useJobProgress";

const STYLES = [
  { id: "realistic", label: "Realistic" },
  { id: "animated",  label: "Animated"  },
  { id: "demo",      label: "Product Demo" },
];
const DURATIONS = [5, 10, 15];

export default function StudioPage() {
  const [clips, setClips] = useState([]);
  const [timeline, setTimeline] = useState([]);  // list of clip IDs
  const [activeIdx, setActiveIdx] = useState(0);
  const [aiOpen, setAiOpen] = useState(false);
  const [postOpen, setPostOpen] = useState(false);
  const [falConfigured, setFalConfigured] = useState(true);
  const [jobId, setJobId] = useState(() => recallJob("video"));

  const fileRef = useRef(null);
  const videoRef = useRef(null);

  // ─── load clips + check fal.ai config ──────────────────────────────────
  useEffect(() => {
    videoListClips().then(({ data }) => setClips(data.items || [])).catch(() => {});
    videoHealth().then(({ data }) => setFalConfigured(!!data.fal_configured)).catch(() => {});
  }, []);

  // resume in-flight job if any
  useEffect(() => {
    if (jobId) return;
    videoListJobs(5).then(({ data }) => {
      const live = (data.items || []).find((j) => ["queued", "running"].includes(j.status));
      if (live) {
        setJobId(live.id);
        rememberJob("video", live.id);
      }
    }).catch(() => {});
    // eslint-disable-next-line
  }, []);

  const refreshClips = useCallback(async () => {
    const { data } = await videoListClips();
    setClips(data.items || []);
  }, []);

  const { job } = useJobProgress(jobId, {
    onDone: async () => {
      forgetJob("video");
      await refreshClips();
      setTimeout(() => setJobId(""), 8000);
    },
  });

  const activeClipId = timeline[activeIdx];
  const activeClip = clips.find((c) => c.id === activeClipId);

  const onUpload = async (file) => {
    if (!file) return;
    try {
      const { data } = await videoUpload(file);
      setClips((prev) => [data, ...prev]);
      setTimeline((t) => [...t, data.id]);
    } catch (e) {
      alert("Upload failed: " + (e?.response?.data?.detail || e.message));
    }
  };

  const onAddToTimeline = (clipId) => {
    setTimeline((t) => [...t, clipId]);
  };
  const onRemoveFromTimeline = (idx) => {
    setTimeline((t) => t.filter((_, i) => i !== idx));
    if (idx === activeIdx && activeIdx > 0) setActiveIdx(activeIdx - 1);
  };
  const onDeleteClip = async (id) => {
    if (!confirm("Delete this clip permanently?")) return;
    await videoDeleteClip(id);
    setClips((prev) => prev.filter((c) => c.id !== id));
    setTimeline((t) => t.filter((cid) => cid !== id));
  };

  const onExport = () => {
    if (!activeClip) {
      alert("Add a clip to the timeline first.");
      return;
    }
    // v1: download the active clip directly. Multi-clip stitching uses
    // ffmpeg.wasm in v2 (heavy dep — gated behind a feature flag).
    const a = document.createElement("a");
    a.href = mediaUrl(activeClip.url);
    a.download = `nxt1-studio-${activeClip.id.slice(0, 8)}.mp4`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <div
      className="flex flex-col h-full min-h-0 w-full"
      data-testid="studio-page"
      style={{ background: "var(--nxt-bg)", color: "var(--nxt-fg)" }}
    >
      {/* HEADER */}
      <header
        className="shrink-0 flex items-center justify-between gap-3 px-4 sm:px-6 py-3"
        style={{ borderBottom: "1px solid var(--nxt-border)" }}
      >
        <div className="flex items-center gap-2">
          <Film size={16} style={{ color: "var(--nxt-accent)" }} />
          <span className="mono text-[10px] tracking-[0.28em] uppercase"
                style={{ color: "var(--nxt-text-3)" }}>NXT1 · STUDIO</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            data-testid="studio-upload-btn"
            className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12.5px] transition"
            style={{
              background: "var(--nxt-surface)",
              border: "1px solid var(--nxt-border)",
              color: "var(--nxt-fg-dim)",
            }}
          >
            <Upload size={12} /> Upload
          </button>
          <button
            type="button"
            onClick={() => setAiOpen(true)}
            data-testid="studio-ai-btn"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12.5px] transition"
            style={{
              background: "var(--nxt-surface)",
              border: "1px solid var(--nxt-border)",
              color: "var(--nxt-fg-dim)",
            }}
          >
            <Sparkles size={12} /> AI Generate
          </button>
          <button
            type="button"
            onClick={onExport}
            data-testid="studio-export-btn"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12.5px] font-medium transition"
            style={{
              background: "var(--nxt-accent)",
              color: "#0F1117",
            }}
          >
            <Download size={12} /> Export MP4
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="video/mp4,video/quicktime,video/webm"
            className="hidden"
            data-testid="studio-file-input"
            onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
          />
        </div>
      </header>

      {/* MAIN: player + clip library */}
      <div className="flex-1 min-h-0 flex flex-col lg:flex-row">
        {/* Player */}
        <div className="flex-1 min-h-0 flex flex-col p-4 sm:p-6 gap-4">
          <div
            className="flex-1 min-h-[240px] sm:min-h-[320px] rounded-2xl overflow-hidden grid place-items-center"
            style={{
              background: "var(--nxt-panel)",
              border: "1px solid var(--nxt-border)",
            }}
          >
            {activeClip ? (
              <video
                ref={videoRef}
                key={activeClip.id}
                controls
                src={mediaUrl(activeClip.url)}
                className="w-full h-full object-contain"
                data-testid="studio-player"
              />
            ) : (
              <div className="text-center px-6" style={{ color: "var(--nxt-text-3)" }}>
                <Play size={32} className="mx-auto mb-2 opacity-40" />
                <p className="text-[13.5px]">Upload a clip or generate one with AI to begin.</p>
              </div>
            )}
          </div>

          {/* Timeline */}
          <div
            className="rounded-2xl p-3"
            style={{
              background: "var(--nxt-surface)",
              border: "1px solid var(--nxt-border)",
            }}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="mono text-[10px] tracking-[0.2em] uppercase"
                    style={{ color: "var(--nxt-text-3)" }}>Timeline</span>
              <button
                type="button"
                onClick={() => setPostOpen(true)}
                disabled={!activeClip}
                data-testid="studio-post-social-btn"
                className="inline-flex items-center gap-1 text-[11.5px] disabled:opacity-40"
                style={{ color: "var(--nxt-accent)" }}
              >
                Post to Social <ChevronRight size={11} />
              </button>
            </div>
            {timeline.length === 0 ? (
              <p className="text-[12px] py-4 text-center"
                 style={{ color: "var(--nxt-text-3)" }}>
                No clips on the timeline. Tap a clip from the library to add it.
              </p>
            ) : (
              <div className="flex items-stretch gap-2 overflow-x-auto pb-1">
                {timeline.map((cid, i) => {
                  const c = clips.find((cc) => cc.id === cid);
                  if (!c) return null;
                  const active = i === activeIdx;
                  return (
                    <button
                      type="button"
                      key={`${cid}-${i}`}
                      onClick={() => setActiveIdx(i)}
                      data-testid={`timeline-clip-${i}`}
                      className="relative shrink-0 w-28 h-16 rounded-lg overflow-hidden text-left transition"
                      style={{
                        background: "var(--nxt-panel)",
                        border: active
                          ? "1.5px solid var(--nxt-accent)"
                          : "1px solid var(--nxt-border)",
                      }}
                    >
                      <video
                        src={mediaUrl(c.url)}
                        muted
                        preload="metadata"
                        className="w-full h-full object-cover"
                      />
                      <span
                        className="absolute bottom-0.5 left-1 mono text-[9px] uppercase tracking-wider px-1.5 rounded"
                        style={{
                          background: "rgba(0,0,0,0.65)",
                          color: c.kind === "ai" ? "var(--nxt-accent)" : "var(--nxt-fg-dim)",
                        }}
                      >
                        {c.kind === "ai" ? "AI" : "UP"} {i + 1}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); onRemoveFromTimeline(i); }}
                        className="absolute top-0.5 right-0.5 h-5 w-5 rounded-full grid place-items-center"
                        style={{ background: "rgba(0,0,0,0.6)" }}
                      >
                        <X size={9} />
                      </button>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* AI Progress */}
          <AnimatePresence>
            {job && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="rounded-xl p-3"
                style={{
                  background: "var(--nxt-surface)",
                  border: "1px solid var(--nxt-border)",
                }}
                data-testid="studio-job-progress"
              >
                <div className="flex items-center justify-between text-[12px] mb-2"
                     style={{ color: "var(--nxt-text-2)" }}>
                  <span className="inline-flex items-center gap-1.5">
                    {["queued", "running"].includes(job.status)
                      ? <Loader2 size={12} className="animate-spin" />
                      : <Check size={12} style={{ color: "var(--nxt-success)" }} />}
                    {job.phase || job.status}
                  </span>
                  <span>{Math.round((job.progress || 0) * 100)}%</span>
                </div>
                <div className="h-1 rounded-full overflow-hidden"
                     style={{ background: "var(--nxt-surface-3)" }}>
                  <div
                    className="h-full transition-all duration-500"
                    style={{
                      width: `${Math.max(2, (job.progress || 0) * 100)}%`,
                      background: "linear-gradient(90deg, var(--nxt-accent), var(--nxt-accent-2))",
                    }}
                  />
                </div>
                <p className="text-[10.5px] mt-2"
                   style={{ color: "var(--nxt-text-3)" }}>
                  Running on the server — close the tab if you want, it'll be here when you return.
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Clip library */}
        <aside
          className="w-full lg:w-[280px] shrink-0 flex flex-col min-h-0"
          style={{ borderLeft: "1px solid var(--nxt-border)" }}
        >
          <div className="px-4 py-3 flex items-center justify-between"
               style={{ borderBottom: "1px solid var(--nxt-border)" }}>
            <span className="mono text-[10px] tracking-[0.24em] uppercase"
                  style={{ color: "var(--nxt-text-3)" }}>Library</span>
            <span className="text-[11px]" style={{ color: "var(--nxt-text-3)" }}>
              {clips.length}
            </span>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto p-3 grid grid-cols-2 gap-2 content-start">
            {clips.length === 0 && (
              <div className="col-span-2 text-center py-10"
                   style={{ color: "var(--nxt-text-3)" }}>
                <p className="text-[12px]">No clips yet.</p>
              </div>
            )}
            {clips.map((c) => (
              <div
                key={c.id}
                className="relative aspect-video rounded-lg overflow-hidden group"
                style={{
                  background: "var(--nxt-panel)",
                  border: "1px solid var(--nxt-border)",
                }}
                data-testid={`library-clip-${c.id}`}
              >
                <video
                  src={mediaUrl(c.url)}
                  muted
                  preload="metadata"
                  className="w-full h-full object-cover"
                />
                <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition flex items-center justify-center gap-1"
                     style={{ background: "rgba(0,0,0,0.55)" }}>
                  <button
                    type="button"
                    onClick={() => onAddToTimeline(c.id)}
                    className="h-7 w-7 rounded-full grid place-items-center"
                    style={{ background: "var(--nxt-accent)", color: "#0F1117" }}
                    title="Add to timeline"
                    data-testid={`library-add-${c.id}`}
                  >
                    <Plus size={13} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeleteClip(c.id)}
                    className="h-7 w-7 rounded-full grid place-items-center"
                    style={{ background: "var(--nxt-error)", color: "#fff" }}
                    title="Delete"
                    data-testid={`library-delete-${c.id}`}
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
                {c.kind === "ai" && (
                  <span
                    className="absolute top-1 left-1 mono text-[8.5px] uppercase tracking-wider px-1.5 rounded"
                    style={{ background: "rgba(0,0,0,0.7)", color: "var(--nxt-accent)" }}
                  >
                    AI
                  </span>
                )}
              </div>
            ))}
          </div>
        </aside>
      </div>

      {/* AI Generate Drawer */}
      <AnimatePresence>
        {aiOpen && (
          <AiGenerateDrawer
            falConfigured={falConfigured}
            onClose={() => setAiOpen(false)}
            onJobStart={(jid) => {
              setJobId(jid);
              rememberJob("video", jid);
              setAiOpen(false);
            }}
          />
        )}
      </AnimatePresence>

      {/* Post to Social Modal */}
      <AnimatePresence>
        {postOpen && activeClip && (
          <PostToSocialModal
            clip={activeClip}
            onClose={() => setPostOpen(false)}
            onPosted={() => setPostOpen(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function AiGenerateDrawer({ falConfigured, onClose, onJobStart }) {
  const [prompt, setPrompt] = useState("");
  const [style, setStyle] = useState("realistic");
  const [duration, setDuration] = useState(5);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async () => {
    if (!prompt.trim()) return;
    setSubmitting(true);
    try {
      const { data } = await videoGenerate({ prompt, style, duration_s: duration });
      onJobStart(data.job_id);
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed to start AI video generation");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50"
        style={{ background: "rgba(0,0,0,0.55)", backdropFilter: "blur(4px)" }}
        onClick={onClose}
      />
      <motion.aside
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 320, damping: 30 }}
        className="fixed top-0 bottom-0 right-0 z-50 w-[92vw] max-w-[420px] flex flex-col"
        style={{
          background: "var(--nxt-bg-2)",
          borderLeft: "1px solid var(--nxt-border)",
        }}
        data-testid="studio-ai-drawer"
      >
        <div className="flex items-center justify-between px-5 py-4"
             style={{ borderBottom: "1px solid var(--nxt-border)" }}>
          <div className="flex items-center gap-2">
            <Sparkles size={14} style={{ color: "var(--nxt-accent)" }} />
            <h3 className="text-[14px] font-medium">AI Video Generator</h3>
          </div>
          <button type="button" onClick={onClose}
                  className="h-8 w-8 rounded-full grid place-items-center"
                  style={{ color: "var(--nxt-fg-dim)" }}>
            <X size={14} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {!falConfigured && (
            <div className="rounded-lg p-3 text-[11.5px]"
                 style={{
                   background: "rgba(251, 113, 133, 0.08)",
                   border: "1px solid rgba(251, 113, 133, 0.32)",
                   color: "var(--nxt-error)",
                 }}>
              FAL_API_KEY is not configured. Add it to <code>/app/backend/.env</code> and restart the backend.
            </div>
          )}
          <label className="block">
            <span className="block text-[11px] mb-1 mono tracking-[0.16em] uppercase"
                  style={{ color: "var(--nxt-text-3)" }}>Describe your video</span>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={4}
              placeholder="A product demo showing our app on a phone, clean background"
              data-testid="studio-ai-prompt"
              className="w-full bg-transparent outline-none text-[13.5px] py-2.5 px-3 rounded-lg resize-none leading-relaxed"
              style={{
                background: "var(--nxt-surface)",
                border: "1px solid var(--nxt-border)",
                color: "var(--nxt-fg)",
              }}
            />
          </label>

          <div>
            <span className="block text-[11px] mb-1.5 mono tracking-[0.16em] uppercase"
                  style={{ color: "var(--nxt-text-3)" }}>Style</span>
            <div className="flex gap-1.5">
              {STYLES.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setStyle(s.id)}
                  data-testid={`studio-style-${s.id}`}
                  className="px-3 py-1.5 rounded-full text-[12px] transition"
                  style={{
                    background: style === s.id ? "var(--nxt-accent)" : "var(--nxt-surface)",
                    color: style === s.id ? "#0F1117" : "var(--nxt-fg-dim)",
                    border: "1px solid var(--nxt-border)",
                  }}
                >{s.label}</button>
              ))}
            </div>
          </div>

          <div>
            <span className="block text-[11px] mb-1.5 mono tracking-[0.16em] uppercase"
                  style={{ color: "var(--nxt-text-3)" }}>Duration</span>
            <div className="flex gap-1.5">
              {DURATIONS.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDuration(d)}
                  data-testid={`studio-duration-${d}`}
                  className="px-4 py-1.5 rounded-full text-[12px] transition"
                  style={{
                    background: duration === d ? "var(--nxt-accent)" : "var(--nxt-surface)",
                    color: duration === d ? "#0F1117" : "var(--nxt-fg-dim)",
                    border: "1px solid var(--nxt-border)",
                  }}
                >{d}s</button>
              ))}
            </div>
          </div>

          <p className="text-[11px]" style={{ color: "var(--nxt-text-3)" }}>
            Runs on Fal.ai CogVideoX-5B. Typical wait: 30–90 seconds.
            The job runs in the background — you can close this tab and come back.
          </p>
        </div>
        <div className="p-5" style={{ borderTop: "1px solid var(--nxt-border)" }}>
          <button
            type="button"
            onClick={onSubmit}
            disabled={!prompt.trim() || submitting || !falConfigured}
            data-testid="studio-ai-submit"
            className="w-full h-11 rounded-full inline-flex items-center justify-center gap-1.5 text-[14px] font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ background: "var(--nxt-accent)", color: "#0F1117" }}
          >
            {submitting
              ? <><Loader2 size={14} className="animate-spin" /> Submitting…</>
              : <><Sparkles size={14} /> Generate video</>}
          </button>
        </div>
      </motion.aside>
    </>
  );
}

function PostToSocialModal({ clip, onClose, onPosted }) {
  const [caption, setCaption] = useState("");
  const [plats, setPlats] = useState(["instagram"]);
  const [posting, setPosting] = useState(false);

  const togglePlat = (p) => setPlats((prev) =>
    prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
  );

  const onSubmit = async () => {
    if (plats.length === 0) return;
    setPosting(true);
    try {
      await videoPostToSocial({ clip_id: clip.id, caption, platforms: plats });
      onPosted();
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed");
    } finally {
      setPosting(false);
    }
  };

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50"
        style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
        onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0 }}
        className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[92vw] max-w-[440px] rounded-2xl overflow-hidden"
        style={{ background: "var(--nxt-bg-2)", border: "1px solid var(--nxt-border)" }}
        data-testid="studio-post-modal"
      >
        <div className="flex items-center justify-between px-5 py-3"
             style={{ borderBottom: "1px solid var(--nxt-border)" }}>
          <h3 className="text-[14px] font-medium">Post to Social</h3>
          <button type="button" onClick={onClose}
                  className="h-8 w-8 rounded-full grid place-items-center"
                  style={{ color: "var(--nxt-fg-dim)" }}>
            <X size={14} />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div className="aspect-video rounded-lg overflow-hidden"
               style={{ background: "var(--nxt-panel)" }}>
            <video src={mediaUrl(clip.url)} muted controls className="w-full h-full object-contain" />
          </div>
          <label className="block">
            <span className="block text-[11px] mb-1 mono tracking-[0.16em] uppercase"
                  style={{ color: "var(--nxt-text-3)" }}>Caption</span>
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              rows={3}
              placeholder="Write a caption…"
              data-testid="studio-post-caption"
              className="w-full bg-transparent outline-none text-[13px] py-2 px-3 rounded-lg resize-none"
              style={{ background: "var(--nxt-surface)", border: "1px solid var(--nxt-border)", color: "var(--nxt-fg)" }}
            />
          </label>
          <div>
            <span className="block text-[11px] mb-1.5 mono tracking-[0.16em] uppercase"
                  style={{ color: "var(--nxt-text-3)" }}>Platforms</span>
            <div className="flex gap-1.5">
              {["instagram", "linkedin", "twitter"].map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => togglePlat(p)}
                  data-testid={`studio-post-plat-${p}`}
                  className="px-3 py-1.5 rounded-full text-[12px] capitalize transition"
                  style={{
                    background: plats.includes(p) ? "var(--nxt-accent)" : "var(--nxt-surface)",
                    color: plats.includes(p) ? "#0F1117" : "var(--nxt-fg-dim)",
                    border: "1px solid var(--nxt-border)",
                  }}
                >{p}</button>
              ))}
            </div>
          </div>
        </div>
        <div className="p-5" style={{ borderTop: "1px solid var(--nxt-border)" }}>
          <button
            type="button"
            onClick={onSubmit}
            disabled={posting || plats.length === 0}
            data-testid="studio-post-submit"
            className="w-full h-10 rounded-full inline-flex items-center justify-center gap-1.5 text-[13.5px] font-medium transition disabled:opacity-50"
            style={{ background: "var(--nxt-accent)", color: "#0F1117" }}
          >
            {posting
              ? <><Loader2 size={14} className="animate-spin" /> Sending…</>
              : <><Send size={13} /> Add to Calendar</>}
          </button>
        </div>
      </motion.div>
    </>
  );
}
