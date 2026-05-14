/**
 * NXT1 — Social Content Studio
 *
 * Two-panel layout (desktop) / stacked (mobile):
 *   • LEFT: Chat-style brief input + profile config + live progress
 *   • RIGHT: Native post calendar/grid (drafts → approve → schedule → posted)
 *
 * Generation runs on a detached backend asyncio task — closing the browser
 * does NOT stop it. The page reconnects to any in-flight job_id stored in
 * localStorage and resumes progress display.
 */
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Sparkles, Send, Image as ImageIcon, Calendar as CalIcon,
  RefreshCw, Trash2, Check, Upload, ChevronDown, ChevronUp,
  Instagram, Linkedin, Twitter, Globe, Loader2, X,
  Rocket, Clock as ClockIcon,
} from "lucide-react";
import {
  socialGetProfile, socialSaveProfile, socialUploadLogo,
  socialGenerate, socialListPosts, socialUpdatePost,
  socialDeletePost, socialRegeneratePost, socialListJobs,
  socialPublishNow, socialSchedulePost,
  mediaUrl,
} from "@/lib/api";
import useJobProgress, { rememberJob, recallJob, forgetJob } from "@/hooks/useJobProgress";
import ConnectionsAndAutopilot from "@/components/social/ConnectionsAndAutopilot";

const TONES = ["professional", "founder", "casual", "personal"];
const ALL_PLATFORMS = [
  { id: "instagram", label: "Instagram", icon: Instagram },
  { id: "linkedin",  label: "LinkedIn",  icon: Linkedin  },
  { id: "twitter",   label: "X",         icon: Twitter   },
];

const CHIPS = [
  "Generate a week of LinkedIn posts about AI productivity, professional tone",
  "Today's Instagram post about my product launch",
  "Twitter thread about my founder journey",
  "Personal brand content for the week, casual",
];

export default function SocialPage() {
  const [profile, setProfile] = useState(null);
  const [profileOpen, setProfileOpen] = useState(false);

  const [brief, setBrief] = useState("");
  const [tone, setTone] = useState("professional");
  const [platforms, setPlatforms] = useState(["instagram", "linkedin", "twitter"]);
  const [duration, setDuration] = useState("this week");

  const [jobId, setJobId] = useState(() => recallJob("social"));
  const [posts, setPosts] = useState([]);
  const [filterPlatform, setFilterPlatform] = useState("all");
  const [loadingPosts, setLoadingPosts] = useState(false);

  // ─── load profile + posts on mount ─────────────────────────────────────
  useEffect(() => {
    socialGetProfile().then(({ data }) => {
      setProfile(data);
      if (data?.tone) setTone(data.tone);
      if (data?.platforms?.length) setPlatforms(data.platforms);
    }).catch(() => {});
    refreshPosts();
    // eslint-disable-next-line
  }, []);

  const refreshPosts = useCallback(async () => {
    setLoadingPosts(true);
    try {
      const params = filterPlatform === "all" ? {} : { platform: filterPlatform };
      const { data } = await socialListPosts(params);
      setPosts(data.items || []);
    } finally {
      setLoadingPosts(false);
    }
  }, [filterPlatform]);

  useEffect(() => { refreshPosts(); }, [filterPlatform, refreshPosts]);

  // ─── job progress (persistent) ─────────────────────────────────────────
  const { job } = useJobProgress(jobId, {
    onDone: () => {
      forgetJob("social");
      refreshPosts();
      // keep the job summary visible for ~10s then clear
      setTimeout(() => setJobId(""), 10000);
    },
  });

  // On mount, also fetch the latest in-flight job in case localStorage was cleared
  useEffect(() => {
    if (jobId) return;
    socialListJobs(5).then(({ data }) => {
      const live = (data.items || []).find((j) => ["queued", "running"].includes(j.status));
      if (live) {
        setJobId(live.id);
        rememberJob("social", live.id);
      }
    }).catch(() => {});
    // eslint-disable-next-line
  }, []);

  const onGenerate = async () => {
    if (!brief.trim()) return;
    try {
      const { data } = await socialGenerate({
        brief,
        tone,
        platforms,
        duration,
        about: profile?.about || "",
        niche: profile?.niche || "",
      });
      setJobId(data.job_id);
      rememberJob("social", data.job_id);
      setBrief("");
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed to start generation");
    }
  };

  const onSaveProfile = async (patch) => {
    const next = { ...(profile || {}), ...patch };
    setProfile(next);
    await socialSaveProfile({
      tone: next.tone || "professional",
      platforms: next.platforms || ["instagram", "linkedin", "twitter"],
      niche: next.niche || "",
      about: next.about || "",
    });
  };

  const onLogoUpload = async (file) => {
    try {
      const { data } = await socialUploadLogo(file);
      setProfile((p) => ({ ...(p || {}), logo_url: data.logo_url, logo_path: data.logo_path }));
    } catch (e) {
      alert("Logo upload failed");
    }
  };

  const onRegenerate = async (postId) => {
    setPosts((prev) => prev.map((p) => p.id === postId ? { ...p, _regenerating: true } : p));
    try {
      const { data } = await socialRegeneratePost(postId);
      setPosts((prev) => prev.map((p) => p.id === postId ? data : p));
    } catch (e) {
      alert("Regenerate failed");
    } finally {
      setPosts((prev) => prev.map((p) => p.id === postId ? { ...p, _regenerating: false } : p));
    }
  };

  const onApprove = async (postId) => {
    const { data } = await socialUpdatePost(postId, { status: "approved" });
    setPosts((prev) => prev.map((p) => p.id === postId ? data : p));
  };

  const onPublishNow = async (postId) => {
    if (!confirm("Publish this post to the live platform now?")) return;
    setPosts((prev) => prev.map((p) => p.id === postId ? { ...p, _publishing: true } : p));
    try {
      await socialPublishNow(postId);
      const { data } = await socialListPosts(
        filterPlatform === "all" ? {} : { platform: filterPlatform }
      );
      setPosts(data.items || []);
    } catch (e) {
      alert(e?.response?.data?.detail || "Publish failed");
      setPosts((prev) => prev.map((p) => p.id === postId ? { ...p, _publishing: false } : p));
    }
  };

  const onSchedule = async (postId) => {
    const when = prompt(
      "When to publish? (ISO timestamp, e.g. 2026-05-20T14:00:00Z)",
      new Date(Date.now() + 3600 * 1000).toISOString()
    );
    if (!when) return;
    try {
      await socialSchedulePost(postId, when);
      const { data } = await socialListPosts(
        filterPlatform === "all" ? {} : { platform: filterPlatform }
      );
      setPosts(data.items || []);
    } catch (e) {
      alert(e?.response?.data?.detail || "Schedule failed");
    }
  };

  const onDelete = async (postId) => {
    if (!confirm("Delete this post?")) return;
    await socialDeletePost(postId);
    setPosts((prev) => prev.filter((p) => p.id !== postId));
  };

  const togglePlatform = (id) => {
    setPlatforms((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
    );
  };

  return (
    <div
      className="flex flex-col lg:flex-row h-full min-h-0 w-full"
      data-testid="social-page"
      style={{ background: "var(--nxt-bg)", color: "var(--nxt-fg)" }}
    >
      {/* LEFT — Chat + Profile + Progress */}
      <aside
        className="w-full lg:w-[40%] lg:max-w-[520px] shrink-0 flex flex-col min-h-0 border-r"
        style={{ borderColor: "var(--nxt-border)" }}
      >
        <div className="px-5 pt-6 pb-3">
          <div className="flex items-center gap-2 mb-1">
            <Sparkles size={16} style={{ color: "var(--nxt-accent)" }} />
            <span className="mono text-[10px] tracking-[0.28em] uppercase"
                  style={{ color: "var(--nxt-text-3)" }}>
              Social · Content Agent
            </span>
          </div>
          <h1 className="text-[22px] sm:text-[26px] font-medium tracking-tight"
              style={{ color: "var(--nxt-fg)" }}>
            What should we publish?
          </h1>
        </div>

        {/* Chat input */}
        <div className="px-5">
          <div
            className="rounded-2xl p-3 flex flex-col gap-2"
            style={{
              background: "var(--nxt-surface-2)",
              border: "1px solid var(--nxt-border-strong)",
            }}
          >
            <textarea
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              placeholder="Tell me what content to create..."
              rows={3}
              data-testid="social-brief-input"
              className="w-full bg-transparent outline-none resize-none text-[14.5px] leading-relaxed placeholder:opacity-60"
              style={{ color: "var(--nxt-fg)" }}
            />
            <div className="flex items-center justify-between gap-2 pt-2"
                 style={{ borderTop: "1px solid var(--nxt-border)" }}>
              <div className="flex items-center gap-1.5 flex-wrap">
                {ALL_PLATFORMS.map(({ id, icon: Icon }) => {
                  const active = platforms.includes(id);
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => togglePlatform(id)}
                      data-testid={`social-toggle-${id}`}
                      className="h-8 w-8 rounded-full inline-flex items-center justify-center transition"
                      style={{
                        background: active ? "var(--nxt-accent)" : "var(--nxt-surface-3)",
                        color: active ? "#0F1117" : "var(--nxt-fg-dim)",
                        border: "1px solid var(--nxt-border-strong)",
                      }}
                      title={id}
                    >
                      <Icon size={14} />
                    </button>
                  );
                })}
                <select
                  value={duration}
                  onChange={(e) => setDuration(e.target.value)}
                  data-testid="social-duration"
                  className="h-8 px-2 rounded-full text-[12px] outline-none"
                  style={{
                    background: "var(--nxt-surface-3)",
                    color: "var(--nxt-fg-dim)",
                    border: "1px solid var(--nxt-border-strong)",
                  }}
                >
                  <option value="today">Today</option>
                  <option value="this week">This week</option>
                  <option value="daily for 14">14 days</option>
                  <option value="daily for 30">30 days</option>
                </select>
                <select
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  data-testid="social-tone"
                  className="h-8 px-2 rounded-full text-[12px] outline-none capitalize"
                  style={{
                    background: "var(--nxt-surface-3)",
                    color: "var(--nxt-fg-dim)",
                    border: "1px solid var(--nxt-border-strong)",
                  }}
                >
                  {TONES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <button
                type="button"
                onClick={onGenerate}
                disabled={!brief.trim() || (job && ["queued", "running"].includes(job.status))}
                data-testid="social-generate-btn"
                className="h-9 px-4 rounded-full inline-flex items-center gap-1.5 text-[13px] font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  background: "var(--nxt-accent)",
                  color: "#0F1117",
                }}
              >
                {job && ["queued", "running"].includes(job.status)
                  ? <Loader2 size={14} className="animate-spin" />
                  : <Send size={13} />}
                Generate
              </button>
            </div>
          </div>

          {/* Quick chips */}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {CHIPS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setBrief(c)}
                data-testid={`social-chip-${c.slice(0, 10)}`}
                className="text-[11.5px] px-3 py-1.5 rounded-full transition hover:opacity-90"
                style={{
                  background: "var(--nxt-surface)",
                  color: "var(--nxt-fg-dim)",
                  border: "1px solid var(--nxt-border)",
                }}
              >
                {c.length > 48 ? c.slice(0, 48) + "…" : c}
              </button>
            ))}
          </div>
        </div>

        {/* Progress */}
        <AnimatePresence>
          {job && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="mx-5 mt-4 rounded-xl p-3.5"
              style={{
                background: "var(--nxt-surface)",
                border: "1px solid var(--nxt-border)",
              }}
              data-testid="social-progress"
            >
              <div className="flex items-center justify-between text-[12px] mb-2"
                   style={{ color: "var(--nxt-text-2)" }}>
                <span className="inline-flex items-center gap-1.5">
                  {["queued", "running"].includes(job.status) ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : job.status === "completed" ? (
                    <Check size={12} style={{ color: "var(--nxt-success)" }} />
                  ) : (
                    <X size={12} style={{ color: "var(--nxt-error)" }} />
                  )}
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
              <div className="mt-3 space-y-1 max-h-32 overflow-y-auto">
                {(job.logs || []).slice(-6).map((l, i) => (
                  <div key={i} className="text-[11.5px] flex gap-2"
                       style={{ color: "var(--nxt-text-3)" }}>
                    <span className="opacity-50 shrink-0">{l.level}</span>
                    <span className="truncate" style={{ color: "var(--nxt-text-2)" }}>{l.msg}</span>
                  </div>
                ))}
              </div>
              <p className="text-[10.5px] mt-3 leading-relaxed"
                 style={{ color: "var(--nxt-text-3)" }}>
                Running on the server — safe to close this tab. Come back any time.
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Profile config */}
        <div className="px-5 pt-4 pb-6">
          <button
            type="button"
            onClick={() => setProfileOpen((o) => !o)}
            data-testid="social-profile-toggle"
            className="w-full flex items-center justify-between text-[12.5px] py-2"
            style={{ color: "var(--nxt-text-2)" }}
          >
            <span className="mono tracking-[0.18em] uppercase text-[10.5px]">
              Brand · Identity
            </span>
            {profileOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          <AnimatePresence>
            {profileOpen && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="space-y-3 pt-2">
                  <Field label="Niche / Industry">
                    <input
                      type="text"
                      value={profile?.niche || ""}
                      onChange={(e) => setProfile((p) => ({ ...(p || {}), niche: e.target.value }))}
                      onBlur={() => onSaveProfile({})}
                      placeholder="AI startup founder"
                      data-testid="social-niche-input"
                      className="w-full bg-transparent outline-none text-[13px] py-2 px-3 rounded-lg"
                      style={{
                        background: "var(--nxt-surface)",
                        border: "1px solid var(--nxt-border)",
                        color: "var(--nxt-fg)",
                      }}
                    />
                  </Field>
                  <Field label="About me">
                    <textarea
                      rows={2}
                      value={profile?.about || ""}
                      onChange={(e) => setProfile((p) => ({ ...(p || {}), about: e.target.value }))}
                      onBlur={() => onSaveProfile({})}
                      placeholder="Short bio — used to personalize content."
                      data-testid="social-about-input"
                      className="w-full bg-transparent outline-none text-[13px] py-2 px-3 rounded-lg resize-none"
                      style={{
                        background: "var(--nxt-surface)",
                        border: "1px solid var(--nxt-border)",
                        color: "var(--nxt-fg)",
                      }}
                    />
                  </Field>
                  <Field label="Logo / brand asset (PNG)">
                    <div className="flex items-center gap-2">
                      <label
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] cursor-pointer transition"
                        style={{
                          background: "var(--nxt-surface)",
                          border: "1px solid var(--nxt-border)",
                          color: "var(--nxt-fg-dim)",
                        }}
                      >
                        <Upload size={12} /> Upload
                        <input
                          type="file"
                          accept="image/png,image/jpeg,image/webp"
                          className="hidden"
                          data-testid="social-logo-upload"
                          onChange={(e) => e.target.files?.[0] && onLogoUpload(e.target.files[0])}
                        />
                      </label>
                      {profile?.logo_url && (
                        <img
                          src={mediaUrl(profile.logo_url)}
                          alt="logo"
                          className="h-8 w-8 rounded object-contain"
                          style={{ background: "var(--nxt-surface-3)" }}
                        />
                      )}
                    </div>
                  </Field>

                  <div className="pt-2">
                    <ConnectionsAndAutopilot />
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </aside>

      {/* RIGHT — Post calendar */}
      <section className="flex-1 min-h-0 flex flex-col">
        <div
          className="shrink-0 px-5 sm:px-7 py-4 flex items-center justify-between gap-3 flex-wrap"
          style={{ borderBottom: "1px solid var(--nxt-border)" }}
        >
          <div className="flex items-center gap-2">
            <CalIcon size={15} style={{ color: "var(--nxt-fg-dim)" }} />
            <h2 className="text-[15px] font-medium" style={{ color: "var(--nxt-fg)" }}>
              Content Calendar
            </h2>
            <span className="text-[11.5px] mono opacity-60">{posts.length} posts</span>
          </div>
          <div className="flex items-center gap-1">
            {[
              { id: "all", icon: Globe },
              ...ALL_PLATFORMS,
            ].map(({ id, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setFilterPlatform(id)}
                data-testid={`social-filter-${id}`}
                className="h-8 w-8 rounded-full inline-flex items-center justify-center transition"
                style={{
                  background: filterPlatform === id ? "var(--nxt-accent)" : "transparent",
                  color: filterPlatform === id ? "#0F1117" : "var(--nxt-fg-dim)",
                  border: "1px solid var(--nxt-border)",
                }}
              >
                <Icon size={13} />
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto p-5 sm:p-7">
          {posts.length === 0 && !loadingPosts && (
            <div className="text-center py-20" style={{ color: "var(--nxt-text-3)" }}>
              <ImageIcon size={28} className="mx-auto mb-3 opacity-40" />
              <p className="text-[13px]">No posts yet. Tell the agent what to create on the left.</p>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {posts.map((p) => (
              <PostCard
                key={p.id}
                post={p}
                onRegenerate={() => onRegenerate(p.id)}
                onApprove={() => onApprove(p.id)}
                onDelete={() => onDelete(p.id)}
                onPublish={() => onPublishNow(p.id)}
                onSchedule={() => onSchedule(p.id)}
              />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-[11px] mb-1 mono tracking-[0.16em] uppercase"
            style={{ color: "var(--nxt-text-3)" }}>
        {label}
      </span>
      {children}
    </label>
  );
}

function PostCard({ post, onRegenerate, onApprove, onDelete, onPublish, onSchedule }) {
  const platformMeta = ALL_PLATFORMS.find((p) => p.id === post.platform) || ALL_PLATFORMS[1];
  const Icon = platformMeta.icon;
  const isApproved = post.status === "approved" || post.status === "scheduled" || post.status === "posted";
  const isPosted = post.status === "posted";

  return (
    <article
      className="rounded-2xl overflow-hidden flex flex-col"
      style={{
        background: "var(--nxt-surface)",
        border: "1px solid var(--nxt-border)",
      }}
      data-testid={`post-card-${post.id}`}
    >
      <div className="relative aspect-square w-full overflow-hidden"
           style={{ background: "var(--nxt-panel)" }}>
        {post.image_url && (
          <img
            src={mediaUrl(post.image_url)}
            alt={post.topic || "post"}
            className="absolute inset-0 w-full h-full object-cover"
            loading="lazy"
          />
        )}
        {(post._regenerating || post._publishing) && (
          <div className="absolute inset-0 grid place-items-center"
               style={{ background: "rgba(0,0,0,0.6)" }}>
            <Loader2 size={24} className="animate-spin"
                     style={{ color: "var(--nxt-accent)" }} />
          </div>
        )}
        <span
          className="absolute top-2 left-2 inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] mono uppercase tracking-wider backdrop-blur"
          style={{
            background: "rgba(0,0,0,0.55)",
            color: "var(--nxt-fg)",
          }}
        >
          <Icon size={10} /> Day {post.day || 1}
        </span>
        {isApproved && (
          <span
            className="absolute top-2 right-2 inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] mono uppercase tracking-wider"
            style={{
              background: isPosted ? "var(--nxt-success)" : "var(--nxt-accent)",
              color: "#0F1117",
            }}
          >
            <Check size={10} /> {post.status}
          </span>
        )}
      </div>
      <div className="p-3 flex-1 flex flex-col gap-2">
        <p className="text-[12.5px] leading-relaxed line-clamp-5"
           style={{ color: "var(--nxt-fg)" }}>
          {post.caption}
        </p>
        {(post.hashtags || []).length > 0 && (
          <p className="text-[11px] leading-snug" style={{ color: "var(--nxt-accent)" }}>
            {(post.hashtags || []).map((h) => `#${h}`).join(" ")}
          </p>
        )}
        {post.last_publish_error && (
          <p className="text-[10.5px] leading-snug"
             style={{ color: "var(--nxt-error)" }}>
            {post.last_publish_error}
          </p>
        )}
        {isPosted && post.platform_url && (
          <a
            href={post.platform_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10.5px] underline"
            style={{ color: "var(--nxt-accent)" }}
          >
            View live post ↗
          </a>
        )}
      </div>
      <div
        className="grid grid-cols-5 gap-1 px-2 py-2"
        style={{ borderTop: "1px solid var(--nxt-border)" }}
      >
        <IconBtn
          icon={RefreshCw}
          label="Regenerate"
          onClick={onRegenerate}
          disabled={post._regenerating || isPosted}
          testid={`post-regen-${post.id}`}
          color="var(--nxt-fg-dim)"
        />
        <IconBtn
          icon={Check}
          label="Approve"
          onClick={onApprove}
          disabled={isApproved}
          testid={`post-approve-${post.id}`}
          color="var(--nxt-success)"
        />
        <IconBtn
          icon={ClockIcon}
          label="Schedule"
          onClick={onSchedule}
          disabled={isPosted}
          testid={`post-schedule-${post.id}`}
          color="var(--nxt-info)"
        />
        <IconBtn
          icon={Rocket}
          label="Post now"
          onClick={onPublish}
          disabled={post._publishing || isPosted}
          testid={`post-publish-${post.id}`}
          color="var(--nxt-accent)"
        />
        <IconBtn
          icon={Trash2}
          label="Delete"
          onClick={onDelete}
          testid={`post-delete-${post.id}`}
          color="var(--nxt-error)"
        />
      </div>
    </article>
  );
}

function IconBtn({ icon: Icon, label, onClick, disabled, testid, color }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      data-testid={testid}
      title={label}
      aria-label={label}
      className="flex flex-col items-center justify-center gap-0.5 py-1.5 rounded-md transition hover:opacity-90 disabled:opacity-30 disabled:cursor-not-allowed min-h-[44px]"
      style={{ color }}
    >
      <Icon size={13} />
      <span className="text-[9.5px] leading-none">{label}</span>
    </button>
  );
}
