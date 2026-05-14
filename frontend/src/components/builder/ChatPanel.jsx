import { useEffect, useMemo, useRef, useState } from "react";
import {
  Send,
  Loader2,
  User,
  RefreshCw,
  Paperclip,
  Eye,
  Rocket,
  Sparkles,
  Github,
  CheckCircle2,
  ExternalLink,
  Share2,
  Activity,
  Cpu,
  X,
} from "lucide-react";
import { toast } from "sonner";
import api, { getMessages, chatStreamUrl, uploadAsset } from "@/lib/api";
import { friendlyError } from "@/lib/errors";
import ModelPickerCockpit from "@/components/premium/ModelPickerCockpit";
import ActivityStream from "@/components/premium/ActivityStream";
import { createStreamReducer } from "@/components/premium/streamReducer";
import ComposerActions from "@/components/premium/ComposerActions";
import ProtocolModeChip from "@/components/builder/ProtocolModeChip";
import BuildTimeline from "@/components/builder/BuildTimeline";
import ResumeWorkflowChip from "@/components/builder/ResumeWorkflowChip";
import { fileActivity } from "@/lib/fileActivity";
import {
  liveSyncAppend,
  liveSyncCommit,
  liveSyncRemove,
  liveSyncReset,
} from "@/lib/webcontainer/liveSync";

const SUGGESTIONS = [
  "A calm focus timer with ambient backdrops",
  "A pricing page that converts",
  "A portfolio that feels alive",
];

const FOLLOWUPS = [
  "Make it feel more premium",
  "Tighten the spacing",
  "Add a contact section",
  "Mobile-first pass",
];

export default function ChatPanel({ projectId, initialPrompt = "", onFilesUpdated, onAutoDeploy, onPreviewClick, onDeployClick, onDeployNow, onSaveToGithub, onSharePreview }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [streamSize, setStreamSize] = useState(0);
  const [activeProvider, setActiveProvider] = useState("anthropic");
  const [uploading, setUploading] = useState(false);
  const [lastBuildAt, setLastBuildAt] = useState(0);
  const [lastSummary, setLastSummary] = useState(null); // {explanation, files, receipts}
  const [savingToGithub, setSavingToGithub] = useState(false);
  const [deployingNow, setDeployingNow] = useState(false);
  const [sharingPreview, setSharingPreview] = useState(false);
  const [narration, setNarration] = useState([]); // live narration lines during stream
  const [currentPhase, setCurrentPhase] = useState(null); // structured phase label
  const [inference, setInference] = useState(null); // inferred foundation
  const [scaffoldFiles, setScaffoldFiles] = useState([]); // scaffold files being loaded
  const [activitySteps, setActivitySteps] = useState([]); // ActivityStream steps
  const streamReducerRef = useRef(createStreamReducer());
  const [activeJobs, setActiveJobs] = useState([]); // resumable jobs banner
  const [currentJobId, setCurrentJobId] = useState(null);
  const [providers, setProviders] = useState({ emergent: true }); // ai providers map for cockpit
  // Protocol selector: "auto" (server decides) | "tag" (cheap surgical edits) | "json"
  // (legacy full rewrites). Persisted per-project to local storage so a power
  // user's choice survives reloads without polluting the UI by default.
  const [protocolMode, setProtocolMode] = useState(() => {
    try {
      return localStorage.getItem(`nxt1-proto:${projectId}`) || "auto";
    } catch { return "auto"; }
  });
  const persistProtocol = (v) => {
    setProtocolMode(v);
    try { localStorage.setItem(`nxt1-proto:${projectId}`, v); } catch { /* ignore */ }
  };
  const fileInputRef = useRef(null);
  const scrollRef = useRef(null);
  const abortRef = useRef(null);

  const refresh = async () => {
    try {
      const { data } = await getMessages(projectId);
      // Rehydrate inline tool receipts + last-build summary so the Preview /
      // Share / Deploy / Save action row survives a reload.
      const hydrated = (data || []).map((m) =>
        m.role !== "user" && Array.isArray(m.tool_receipts) && m.tool_receipts.length > 0
          ? { ...m, _receipts: m.tool_receipts }
          : m,
      );
      setMessages(hydrated);
      // Find the most recent successful assistant message — show the post-build
      // action row even if no tool_receipts exist (e.g. non-streaming builds,
      // legacy messages, or builds restored from a job). Any assistant message
      // whose status isn't explicitly "failed" or "interrupted" counts as a
      // successful build worth re-surfacing actions for.
      const lastAssistant = [...hydrated].reverse().find(
        (m) => m.role !== "user"
          && m.status !== "failed"
          && m.status !== "interrupted"
          && (m.build_summary || m.tool_receipts || m.explanation || m.content),
      );
      if (lastAssistant) {
        const bs = lastAssistant.build_summary || {};
        const receiptsCount = (lastAssistant.tool_receipts || []).length;
        setLastSummary({
          explanation: lastAssistant.content || lastAssistant.explanation || "",
          receipts: lastAssistant.tool_receipts || [],
          fileCount:
            (bs.created || 0) + (bs.edited || 0) || receiptsCount || 0,
        });
        setLastBuildAt(Date.parse(lastAssistant.created_at) || Date.now());
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (projectId) {
      refresh();
      refreshActiveJobs();
    }
    // Fetch provider connection map once on mount so the cockpit can show
    // accurate green/idle status dots.
    api.get(`/system/providers`)
      .then(({ data }) => setProviders({ ...(data?.ai || {}), emergent: true }))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // Auto-build on landing → builder transition. When the user typed a prompt
  // on the landing page, the URL carries it as `?prompt=...`; we fire it as
  // the first chat turn as soon as the empty project finishes hydrating, so
  // the builder shows generation in-flight instead of an empty "Tell NXT1"
  // screen the user has to re-type into. Guarded by a per-project session
  // marker (set in BuilderPage) so a hard refresh doesn't re-trigger.
  const autoFiredRef = useRef(false);
  useEffect(() => {
    if (!projectId || !initialPrompt) return;
    if (autoFiredRef.current) return;
    if (loading) return;                  // wait until first refresh() done
    if (streaming) return;                // never compete with a live stream
    if (messages.length > 0) return;      // user has past turns → don't replay
    autoFiredRef.current = true;
    setInput(initialPrompt);
    // Submit on the next tick so the optimistic message uses the input we
    // just set.
    setTimeout(() => {
      submit(null, initialPrompt);
    }, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, initialPrompt, loading, streaming, messages.length]);

  const refreshActiveJobs = async () => {
    try {
      const { data } = await api.get(`/projects/${projectId}/jobs/active`);
      setActiveJobs(data.items || []);
    } catch {
      /* ignore — banner just doesn't show */
    }
  };

  // Light polling while a job is running so the banner updates without
  // requiring a full ChatPanel re-mount.
  useEffect(() => {
    if (activeJobs.length === 0) return;
    const t = setInterval(refreshActiveJobs, 3000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJobs.length, projectId]);

  const cancelJob = async (jobId) => {
    try {
      await api.post(`/jobs/${jobId}/cancel`);
      toast.success("Job cancelled");
      await refreshActiveJobs();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Cancel failed");
    }
  };

  // Allow other panels to inject a prompt directly into the chat (e.g. from
  // the ProductAgent suggestions in OverviewPanel).
  useEffect(() => {
    const onInject = (ev) => {
      const text = ev?.detail?.text;
      if (!text) return;
      submit({ preventDefault() {} }, text);
    };
    window.addEventListener("nxt1:sendChat", onInject);
    return () => window.removeEventListener("nxt1:sendChat", onInject);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProvider, streaming, projectId]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, streaming, streamSize]);

  const submit = async (e, prefill) => {
    e?.preventDefault?.();
    const msg = (prefill ?? input).trim();
    if (!msg || streaming) return;
    setInput("");
    setStreaming(true);
    setStreamSize(0);
    setStoppedByUser(false);
    setInference(null);
    setScaffoldFiles([]);
    // Reset the activity stream for a new build
    streamReducerRef.current.reset();
    setActivitySteps([]);

    const optimistic = {
      id: `tmp-${Date.now()}`,
      role: "user",
      content: msg,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, optimistic]);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const resp = await fetch(chatStreamUrl(projectId, protocolMode), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, provider: activeProvider }),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        // Pull the body if we can but NEVER surface raw HTML / JSON dumps.
        let raw = "";
        try { raw = await resp.text(); } catch { /* ignore */ }
        const err = new Error(raw || `HTTP ${resp.status}`);
        err._friendly = friendlyError(raw || `HTTP ${resp.status}`);
        throw err;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let lastSize = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const json = line.slice(5).trim();
          if (!json) continue;
          let ev;
          try { ev = JSON.parse(json); } catch { continue; }

          // Feed the ActivityStream reducer with every event we see.
          // It curates raw events into a small, human-readable orchestration feed.
          streamReducerRef.current.push(ev);
          setActivitySteps(streamReducerRef.current.snapshot());

          if (ev.type === "user_message") {
            // already optimistic; replace with server one to get id
            setMessages((m) => [...m.filter((x) => x.id !== optimistic.id), ev.message]);
          } else if (ev.type === "job") {
            setCurrentJobId(ev.job_id);
            refreshActiveJobs();
          } else if (ev.type === "start") {
            setReceipts([]);
            setNarration([]);
            setCurrentPhase("Starting…");
            fileActivity.reset();
            liveSyncReset();
          } else if (ev.type === "phase") {
            setCurrentPhase(ev.label);
            // The backend may attach inference payload to the phase event when
            // it's the "Inferring foundation" / "Foundation loaded" phase.
            if (ev.inference) {
              setInference(ev.inference);
            }
          } else if (ev.type === "narration") {
            // Live first-person prose from the narrator agent
            setNarration((n) => [
              ...n,
              { id: `n-${Date.now()}-${n.length}`, line: ev.line },
            ]);
          } else if (ev.type === "chunk") {
            lastSize = ev.size;
            setStreamSize(ev.size);
          } else if (ev.type === "tag_chunk") {
            // Tag-mode: a file is being written live. Mark it active in the
            // file-activity bus so the explorer can show a writing pulse.
            if (ev.path) fileActivity.writing(ev.path);
            // Stream-time WebContainer live-sync: accumulate the delta so
            // we can flush a single fs.writeFile at tag close (no-op when
            // no WC is booted).
            if (ev.path && ev.delta) liveSyncAppend(ev.path, ev.delta);
          } else if (ev.type === "tool") {
            // File-mutation receipts always feed the activity bus so the
            // explorer can flash a tan "recent" dot, even if we choose not
            // to render them inline elsewhere.
            if (ev.path && (
              ev.action === "created" || ev.action === "edited" ||
              ev.action === "deleted" || ev.action === "renamed" ||
              ev.action === "deps-applied"
            )) {
              fileActivity.done(ev.path);
            }
            // Stream-time WebContainer live-sync: flush / mirror.
            if (ev.path) {
              if (ev.action === "created" || ev.action === "edited") {
                // Fire-and-forget; the commit is async but we don't want
                // to block the event loop here.
                liveSyncCommit(ev.path);
              } else if (ev.action === "deleted") {
                liveSyncRemove(ev.path);
              } else if (ev.action === "renamed" && ev.from) {
                liveSyncRemove(ev.from);
                liveSyncCommit(ev.path);
              }
            }
            if (ev.action === "scaffold") {
              // Scaffold receipts feed the OrchestrationOverlay, not the
              // standard "files I touched" list.
              setScaffoldFiles((s) => [...s, ev.path]);
            } else {
              // Inline tool-receipt bubble: viewed/edited/created/deleted <path>
              setReceipts((r) => [
                ...r,
                { id: `${ev.action}-${ev.path}-${Date.now()}-${r.length}`, ...ev },
              ]);
            }
          } else if (ev.type === "info") {
            toast.info(ev.message);
          } else if (ev.type === "assistant_message") {
            setMessages((m) => [...m, { ...ev.message, _receipts: pendingReceiptsRef.current }]);
            pendingReceiptsRef.current = [];
            setReceipts([]);
          } else if (ev.type === "done") {
            // Snapshot the receipts for the upcoming assistant_message
            pendingReceiptsRef.current = receiptsRef.current.slice();
            onFilesUpdated?.(ev.files);
            setLastBuildAt(Date.now());
            setLastSummary({
              explanation: ev.explanation || "",
              receipts: receiptsRef.current.slice(),
              fileCount: (ev.files || []).length,
            });
            toast.success("Build ready — preview is live");
            // Finalize the activity stream with "Ready to preview"
            streamReducerRef.current.complete("Ready to preview");
            setActivitySteps(streamReducerRef.current.snapshot());
          } else if (ev.type === "auto_deploy") {
            if (ev.error) toast.error(`Auto-deploy: ${ev.error}`);
            else toast.success("Auto-deployed");
            onAutoDeploy?.(ev.deployment);
          } else if (ev.type === "error") {
            const fe = friendlyError(ev.message);
            toast.error(fe.title, { description: fe.hint });
            setMessages((m) => [...m, {
              id: `err-${Date.now()}`,
              role: "assistant",
              _error: fe,
              content: fe.title,
              created_at: new Date().toISOString(),
            }]);
          } else if (ev.type === "end") {
            // closed
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        const fe = err._friendly || friendlyError(err);
        toast.error(fe.title, { description: fe.hint });
        setMessages((m) => [...m, {
          id: `err-${Date.now()}`,
          role: "assistant",
          _error: fe,
          content: fe.title,
          created_at: new Date().toISOString(),
        }]);
      }
    } finally {
      setStreaming(false);
      setCurrentPhase(null);
      setCurrentJobId(null);
      abortRef.current = null;
      refreshActiveJobs();
    }
  };

  const [stoppedByUser, setStoppedByUser] = useState(false);
  const [receipts, setReceipts] = useState([]); // live tool receipts during stream
  const receiptsRef = useRef([]);
  const pendingReceiptsRef = useRef([]);
  useEffect(() => {
    receiptsRef.current = receipts;
  }, [receipts]);

  const cancel = async () => {
    abortRef.current?.abort();
    setStreaming(false);
    setCurrentPhase(null);
    setStoppedByUser(true);
    // ALSO tell the backend to halt the build mid-stream (Phase 11.2).
    // The ai_service generator polls db.jobs.status every 0.5s and bails on
    // status=cancelled, then _persist_build_state writes a cancelled message.
    if (currentJobId) {
      try {
        await api.post(`/projects/${projectId}/jobs/${currentJobId}/cancel`);
        toast("Build cancelled — server has stopped the agent.");
      } catch (e) {
        toast(`Agent stopped locally — server cancel failed: ${e?.response?.data?.detail || e.message}`);
      } finally {
        setCurrentJobId(null);
        refreshActiveJobs();
      }
    } else {
      toast("Agent stopped — type 'continue' or hit Continue to resume.");
    }
  };

  const handleUploadFiles = async (fileList) => {
    if (!fileList || fileList.length === 0) return;
    setUploading(true);
    const uploaded = [];
    try {
      for (const f of Array.from(fileList).slice(0, 6)) {
        try {
          const { data } = await uploadAsset(projectId, f);
          uploaded.push(data);
        } catch (err) {
          toast.error(`${f.name}: ${err?.response?.data?.detail || "upload failed"}`);
        }
      }
      if (uploaded.length > 0) {
        const refs = uploaded.map((a) => `assets/${a.filename}`).join(", ");
        setInput((curr) =>
          curr
            ? `${curr}\n\nAttached: ${refs}`
            : `I just uploaded: ${refs}\n\nUse them in the build.`,
        );
        toast.success(
          `Uploaded ${uploaded.length} file${uploaded.length === 1 ? "" : "s"}`,
        );
        window.dispatchEvent(new CustomEvent("nxt1:filesChanged"));
      }
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="flex flex-col h-full surface-recessed" data-testid="chat-panel">
      <div className="h-10 shrink-0 flex items-center px-4 border-b border-white/5">
        <span className="nxt-overline">// ai builder</span>
        <span className="ml-auto nxt-overline flex items-center gap-2 max-w-[60%] truncate">
          <span className={`h-1.5 w-1.5 rounded-full ${streaming ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`} />
          {streaming
            ? (currentPhase || "WORKING…").toUpperCase()
            : "READY"}
        </span>
      </div>

      {/* Resumable jobs banner — surfaces background work that's still
          running so a user who left/refreshed can see what NXT1 is doing. */}
      {activeJobs.length > 0 && !streaming && (
        <div className="shrink-0 px-3 py-2 border-b border-amber-400/20 bg-amber-500/[0.04]" data-testid="active-jobs-banner">
          {activeJobs.map((j) => (
            <div key={j.id} className="flex items-center gap-2 flex-wrap">
              <Activity size={11} className="text-amber-300 animate-pulse" />
              <span className="nxt-overline text-amber-200">
                {j.kind.toUpperCase()} · {(j.phase || "running").toUpperCase()}
              </span>
              {j.progress > 0 && (
                <span className="text-[10.5px] mono text-amber-300/60">
                  {Math.round((j.progress || 0) * 100)}%
                </span>
              )}
              <button
                onClick={() => cancelJob(j.id)}
                className="ml-auto text-amber-300/60 hover:text-amber-100 text-[10.5px] mono uppercase tracking-wider px-2 py-0.5 rounded-full border border-amber-400/20 hover:border-amber-400/40 transition flex items-center gap-1"
                data-testid={`cancel-job-${j.id}`}
              >
                <X size={9} /> Cancel
              </button>
            </div>
          ))}
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-5">
        {loading ? (
          <div className="text-zinc-500 text-sm mono">loading session…</div>
        ) : (messages.length === 0 && (initialPrompt || autoFiredRef.current)) ? (
          /* The user came from landing with a prompt — show a calm
             "starting your build" state instead of the welcome screen.
             The auto-fire effect above will inject the first message any
             frame now. */
          <div className="space-y-5 nxt-fade-up">
            <div>
              <div className="flex items-center gap-2 mb-3">
                <span className="nxt-overline">// session_001</span>
                <span className="h-px flex-1 bg-white/5" />
                <span className="mono text-[10px] tracking-[0.30em] uppercase text-white/25">
                  ORCHESTRATING
                </span>
              </div>
              <h2
                className="text-[24px] sm:text-[28px] font-semibold tracking-tight leading-[1.1]"
                style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
                data-testid="autobuild-headline"
              >
                <span className="text-white">Starting your build </span>
                <span
                  style={{
                    background: "linear-gradient(180deg, #C8B98C 0%, #8C8163 100%)",
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                    backgroundClip: "text",
                  }}
                >
                  from your prompt.
                </span>
              </h2>
              <p className="text-white/45 mt-2 text-[13px] leading-relaxed max-w-md italic">
                “{initialPrompt}”
              </p>
            </div>
            <div className="inline-flex items-center gap-2 text-[12px] text-white/55">
              <span className="h-1.5 w-1.5 rounded-full bg-[#C8B98C] animate-pulse" aria-hidden />
              Selecting scaffold and queuing the first turn…
            </div>
          </div>
        ) : messages.length === 0 ? (
          // Empty state intentionally rendered as nothing (2026-05-13).
          // The composer at the bottom of the panel is enough — users
          // arriving without a prompt should NOT see a "Tell NXT1 what
          // to build" pseudo-cover screen. They go straight to the empty
          // chat area and the input.
          <div className="h-full" data-testid="chat-empty" />
        ) : (
          messages.map((m) => {
            // Retroactively sanitize historical raw error dumps that were
            // saved into the chat log BEFORE the friendly-error layer
            // existed. Any old `⚠ Generation failed: ... LiteLLM ...` will
            // be transparently re-rendered as a calm card.
            const looksLikeOldError =
              !m._error &&
              m.role === "assistant" &&
              typeof m.content === "string" &&
              /^⚠|LiteLLM|BadGateway|Generation failed|Streaming failed|traceback|OpenAIException/i.test(m.content);
            const effectiveError = m._error || (looksLikeOldError ? friendlyError(m.content) : null);
            return (
            <div key={m.id} className="nxt-fade-up">
              <div className="flex items-center gap-2 mb-1.5">
                {m.role === "user" ? (
                  <>
                    <User size={12} className="text-zinc-500" />
                    <span className="nxt-overline">you</span>
                  </>
                ) : (
                  <>
                    <Cpu size={12} className="text-emerald-400" />
                    <span className="nxt-overline text-emerald-400/80">nxt1.ai</span>
                  </>
                )}
                <span className="nxt-overline text-zinc-700">
                  {new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
              </div>
              {effectiveError ? (
                <FriendlyErrorCard
                  error={effectiveError}
                  onRetry={(e) => submit(e, "Retry the last instruction.")}
                  onSwitchModel={() => {
                    // Best-effort: focus the model cockpit trigger
                    const trigger = document.querySelector('[data-testid="model-cockpit-trigger"]');
                    if (trigger) trigger.click();
                  }}
                />
              ) : (
                <div
                  className={`text-[14px] leading-relaxed whitespace-pre-wrap pl-4 border-l ${
                    m.role === "user" ? "border-white/10 text-white" : "border-emerald-400/30 text-zinc-200"
                  }`}
                >
                  {m.content}
                </div>
              )}
              {/* Tool receipts attached to a completed assistant turn */}
              {m.role !== "user" && m._receipts && m._receipts.length > 0 && (
                <ToolReceiptsList receipts={m._receipts} className="ml-4 mt-2" />
              )}
              {/* "What I did" brief — short summary card after the agent finishes */}
              {m.role !== "user" && m._receipts && m._receipts.length > 0 && (
                <AgentBrief receipts={m._receipts} className="ml-4 mt-2" />
              )}
              {/* Cinematic build timeline + validation summary (Phase B.1.3).
                  Calm by default — one mono line; tap reveals the per-phase
                  vertical strip with millisecond durations. */}
              {m.role !== "user" && Array.isArray(m.timeline) && m.timeline.length > 0 && (
                <div className="ml-4 mt-1">
                  <BuildTimeline
                    timeline={m.timeline}
                    validation={m.validation}
                    protocolUsed={m.protocol_used}
                  />
                </div>
              )}
            </div>
            );
          })
        )}
        {streaming && (
          <div className="nxt-fade-up" data-testid="agent-timeline">
            {/* Cinematic vertical orchestration feed — newest near bottom,
                older steps drift upward with fade + blur. */}
            <ActivityStream steps={activitySteps} />
            {/* Tool receipts (files touched) appear quietly under the stream */}
            {receipts.length > 0 && (
              <div className="pt-2.5 pl-1">
                <ToolReceiptsList receipts={receipts} className="opacity-80" />
              </div>
            )}
          </div>
        )}

        {/* Post-stop: Continue chip — appears when the user hit stop and the agent halted */}
        {stoppedByUser && !streaming && (
          <div className="nxt-fade-up pt-2" data-testid="chat-continue-chip">
            <button
              type="button"
              onClick={(e) => {
                setStoppedByUser(false);
                submit(e, "Continue from where you left off.");
              }}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white text-black text-sm font-semibold hover:bg-zinc-100 transition"
              data-testid="chat-continue-button"
            >
              ▶ Continue
            </button>
            <span className="ml-2 text-[12px] text-zinc-500">
              Pick up where the agent stopped
            </span>
          </div>
        )}

        {/* Post-build summary card — ONLY appears when there are real
            generated files/receipts (i.e. something actually to preview/share).
            Hide gracefully when the session is empty so the chat feels calm. */}
        {!streaming &&
          lastBuildAt > 0 &&
          lastSummary &&
          messages.length > 0 &&
          (lastSummary.fileCount > 0 || (lastSummary.receipts || []).length > 0) && (
          <div className="nxt-slide-up pt-2" data-testid="chat-post-build-actions">
            <BuildSummaryCard
              summary={lastSummary}
              deploying={deployingNow}
              sharing={sharingPreview}
              onDeployNow={async () => {
                if (!onDeployNow) {
                  onDeployClick?.();
                  return;
                }
                setDeployingNow(true);
                try {
                  await onDeployNow();
                } finally {
                  setDeployingNow(false);
                }
              }}
              onPreviewClick={() => onPreviewClick?.()}
              onSharePreview={async () => {
                if (!onSharePreview) return;
                setSharingPreview(true);
                try {
                  await onSharePreview();
                } finally {
                  setSharingPreview(false);
                }
              }}
              onPickProvider={() => onDeployClick?.()}
            />
            <div className="flex flex-wrap gap-1.5 mt-3">
              {FOLLOWUPS.map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={(e) => submit(e, f)}
                  className="text-[11px] mono uppercase tracking-wide text-zinc-400 px-2.5 py-1 border border-white/10 hover:border-white/30 hover:text-white rounded-sm transition-colors"
                  data-testid={`chat-followup-${f.replace(/\s+/g, "-").toLowerCase()}`}
                >
                  <Sparkles size={10} className="inline mr-1.5 -mt-0.5" />
                  {f}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <form onSubmit={submit} className="shrink-0 px-3 sm:px-4 pt-3 pb-3 sm:pb-4 surface-0 nxt-safe-bottom nxt-mobile-composer">
        <ResumeWorkflowChip projectId={projectId} />
        <div
          className="flex items-end gap-1.5 rounded-3xl border border-white/10 surface-1 px-2 py-2 shadow-[0_8px_32px_-12px_rgba(0,0,0,0.55)] focus-within:border-white/22 focus-within:shadow-[0_12px_48px_-12px_rgba(94,234,212,0.16)] transition-all"
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,.pdf,.csv,.json,.txt,.md,.zip"
            className="hidden"
            onChange={(e) => handleUploadFiles(e.target.files)}
            data-testid="chat-file-input"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || streaming}
            className="h-10 w-10 sm:h-9 sm:w-9 rounded-full flex items-center justify-center bg-white/5 border border-white/10 text-zinc-300 hover:bg-white/10 hover:text-white transition disabled:opacity-50 shrink-0"
            title="Upload files"
            data-testid="chat-upload-button"
          >
            {uploading ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Paperclip size={15} />
            )}
          </button>
          {/* Expandable actions: Save to GitHub / Deploy / Preview / Export.
              Hidden until tapped, never permanently above the chat.
              Note: Export = ZIP download. Share preview is intentionally
              NOT exposed here — it only surfaces in the post-build summary
              card after a successful generation. */}
          <ComposerActions
            projectId={projectId}
            liveUrl={null}
            deployState="idle"
            previewReady={lastBuildAt > 0}
            onPreview={() => onPreviewClick?.()}
            onDeploy={() => onDeployClick?.()}
            onDownload={() => {
              // Trigger a ZIP download of the project files. The dedicated
              // download endpoint streams a clean archive — no share link.
              window.location.href = `${api.defaults.baseURL || ""}/projects/${projectId}/download`;
            }}
            activeProvider={activeProvider}
            providers={providers}
            onProviderChange={(v) => setActiveProvider(v)}
          />
          <textarea
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              const t = e.target;
              t.style.height = "0";
              t.style.height = `${Math.min(t.scrollHeight, 160)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(e);
              }
            }}
            rows={1}
            placeholder={streaming ? "Add another instruction…" : "Message NXT1…"}
            className="flex-1 bg-transparent border-0 outline-none text-[15px] sm:text-[15px] resize-none px-2 py-2 placeholder:text-zinc-500 max-h-40 min-h-[2.4rem] leading-snug"
            disabled={false}
            data-testid="chat-input-textarea"
            style={{ overflowY: "auto", fontSize: "16px" }}
          />
          {streaming ? (
            <button
              type="button"
              onClick={cancel}
              className="h-10 w-10 sm:h-9 sm:w-9 rounded-full flex items-center justify-center bg-white text-black hover:bg-zinc-100 transition shrink-0"
              data-testid="chat-cancel-button"
              aria-label="Stop agent"
              title="Stop"
            >
              {/* Filled stop square — matches reference UI */}
              <span className="block h-3 w-3 rounded-[2px] bg-[#1F1F23]" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="h-10 w-10 sm:h-9 sm:w-9 rounded-full flex items-center justify-center bg-white text-[#1F1F23] hover:bg-zinc-100 disabled:bg-white/10 disabled:text-white/30 transition shrink-0"
              data-testid="chat-send-button"
              aria-label="Send"
            >
              <Send size={15} strokeWidth={2.4} />
            </button>
          )}
        </div>
        {/* Composer footer removed (2026-05-13): the AUTO/protocol pill and
            the separate model tile both lived here. Model selection now
            lives inside the ⋯ menu (ComposerActions → ModelRow) and
            protocol mode stays on "auto" — the smartest default. */}
      </form>
    </div>
  );
}

/* ---------------- Inline tool-receipt rendering ---------------- */

const ACTION_META = {
  viewed: { color: "text-zinc-400", verb: "Viewed" },
  edited: { color: "text-amber-300", verb: "Edited" },
  created: { color: "text-emerald-300", verb: "Created" },
  deleted: { color: "text-rose-300", verb: "Deleted" },
};

function ToolReceiptsList({ receipts, className = "" }) {
  return (
    <div
      className={`space-y-1 ${className}`}
      data-testid="tool-receipts"
    >
      {receipts.map((r) => {
        const meta = ACTION_META[r.action] || ACTION_META.viewed;
        return (
          <div
            key={r.id || `${r.action}-${r.path}`}
            className="flex items-center gap-2 text-[12.5px] mono"
            data-testid={`tool-receipt-${r.action}`}
          >
            <span className={meta.color}>›</span>
            <span className="text-zinc-500">{meta.verb}</span>
            <span className="text-zinc-200 truncate">{r.path}</span>
            <span className="text-emerald-400 ml-auto shrink-0">✓</span>
          </div>
        );
      })}
    </div>
  );
}

function AgentBrief({ receipts, className = "" }) {
  const counts = receipts.reduce(
    (acc, r) => {
      acc[r.action] = (acc[r.action] || 0) + 1;
      return acc;
    },
    { created: 0, edited: 0, viewed: 0, deleted: 0 }
  );
  const bits = [];
  if (counts.created) bits.push(`created ${counts.created} file${counts.created > 1 ? "s" : ""}`);
  if (counts.edited) bits.push(`edited ${counts.edited} file${counts.edited > 1 ? "s" : ""}`);
  if (counts.viewed) bits.push(`reviewed ${counts.viewed} file${counts.viewed > 1 ? "s" : ""}`);
  if (counts.deleted) bits.push(`removed ${counts.deleted} file${counts.deleted > 1 ? "s" : ""}`);
  if (bits.length === 0) return null;
  const summary = bits.join(" · ");
  return (
    <div
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-emerald-400/25 bg-emerald-500/[0.07] text-[12px] text-emerald-200 ${className}`}
      data-testid="agent-brief"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
      Done — {summary}.
    </div>
  );
}

/**
 * BuildSummaryCard — the polished post-build "what just happened" card with a
 * primary "Deploy Now" CTA. Auto-Vercel by default; "Pick provider" opens the
 * full Deploy sheet for users who want CF Pages or internal preview.
 */
function BuildSummaryCard({ summary, deploying, sharing, onDeployNow, onPreviewClick, onSharePreview, onPickProvider }) {
  const counts = (summary?.receipts || []).reduce(
    (acc, r) => {
      acc[r.action] = (acc[r.action] || 0) + 1;
      return acc;
    },
    { created: 0, edited: 0, viewed: 0, deleted: 0 }
  );
  const stats = [];
  if (counts.created) stats.push({ label: "created", value: counts.created });
  if (counts.edited) stats.push({ label: "edited", value: counts.edited });
  if (counts.viewed) stats.push({ label: "reviewed", value: counts.viewed });
  if (counts.deleted) stats.push({ label: "removed", value: counts.deleted });
  if (stats.length === 0 && summary?.fileCount) {
    stats.push({ label: "files", value: summary.fileCount });
  }
  // Best-effort sentence break of the explanation into bullets
  const bullets = (summary?.explanation || "")
    .split(/[\.\n]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 4)
    .slice(0, 3);

  return (
    <div
      className="rounded-2xl border border-emerald-400/25 bg-gradient-to-br from-[#0d1614] via-[#1F1F23] to-[#1F1F23] p-4 sm:p-5"
      data-testid="build-summary-card"
    >
      <div className="flex items-center gap-2 mb-2.5">
        <span className="h-7 w-7 rounded-full bg-emerald-500/15 border border-emerald-400/30 flex items-center justify-center">
          <CheckCircle2 size={14} className="text-emerald-300" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-semibold text-emerald-200 tracking-tight">
            Build ready
          </div>
          <div className="text-[11px] mono uppercase tracking-wider text-emerald-400/70">
            preview is live · deploy when you’re ready
          </div>
        </div>
      </div>
      {bullets.length > 0 && (
        <ul className="space-y-1 mb-3">
          {bullets.map((b, i) => (
            <li key={i} className="text-[13px] text-zinc-200 leading-relaxed flex gap-2">
              <span className="text-emerald-400 shrink-0">›</span>
              <span>{b.endsWith(".") ? b : `${b}.`}</span>
            </li>
          ))}
        </ul>
      )}
      {stats.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3.5">
          {stats.map((s) => (
            <span
              key={s.label}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-white/10 bg-white/[0.03] text-[11px] mono text-zinc-300"
            >
              <span className="text-emerald-300 font-semibold">{s.value}</span>
              <span className="text-zinc-500">{s.label}</span>
            </span>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onDeployNow}
          disabled={deploying}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-emerald-400 text-black text-sm font-semibold shadow hover:bg-emerald-300 transition disabled:opacity-60 disabled:cursor-not-allowed"
          data-testid="chat-deploy-now-button"
        >
          {deploying ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Rocket size={14} strokeWidth={2.5} />
          )}
          {deploying ? "Deploying…" : "Deploy Now"}
        </button>
        {onSharePreview && (
          <button
            type="button"
            onClick={onSharePreview}
            disabled={sharing}
            className="group inline-flex items-center gap-1.5 px-3 py-2.5 rounded-full text-[12.5px] transition disabled:opacity-60"
            style={{
              background: "transparent",
              color: "var(--nxt-fg-faint)",
              border: "1px dashed var(--nxt-border-soft)",
            }}
            data-testid="chat-share-preview-button"
            title="Generate a shareable read-only preview link"
          >
            {sharing ? (
              <Loader2 size={11} className="animate-spin" />
            ) : (
              <Share2 size={11} strokeWidth={2.2} />
            )}
            <span className="tracking-tight">
              {sharing ? "Generating link…" : "Share read-only link"}
            </span>
          </button>
        )}
        <button
          type="button"
          onClick={onPreviewClick}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-transparent border border-white/15 text-zinc-200 text-sm hover:border-white/30 hover:text-white transition"
          data-testid="chat-preview-button"
        >
          <Eye size={14} strokeWidth={2.5} />
          Preview
        </button>
        <button
          type="button"
          onClick={onPickProvider}
          className="inline-flex items-center gap-2 px-3 py-2.5 rounded-full bg-transparent border border-white/15 text-zinc-300 text-sm hover:border-white/30 hover:text-white transition"
          data-testid="chat-deploy-pick-button"
        >
          <ExternalLink size={13} />
          Pick provider · domain
        </button>
      </div>
    </div>
  );
}

/**
 * NarrationStream — renders the live first-person narration as scrolling lines
 * with a typing cursor on the most recent line until the next line arrives.
 */
function NarrationStream({ lines }) {
  const isLast = (i) => i === lines.length - 1;
  return (
    <div className="space-y-1.5" data-testid="agent-narration">
      {lines.map((n, i) => (
        <div
          key={n.id}
          className="flex items-start gap-2 text-[14px] leading-relaxed text-zinc-200"
        >
          <span className="text-emerald-400 shrink-0 mt-0.5">›</span>
          <span className={isLast(i) ? "nxt-cursor" : ""}>{n.line}</span>
        </div>
      ))}
    </div>
  );
}



/**
 * FriendlyErrorCard — replaces raw LiteLLM/budget/traceback dumps with a
 * calm, polite retry card. Never renders the underlying provider trace.
 */
function FriendlyErrorCard({ error, onRetry, onSwitchModel }) {
  const showSwitch =
    error.category === "budget" ||
    error.category === "rate_limit" ||
    error.category === "auth" ||
    error.category === "provider";
  return (
    <div
      className="ml-4 rounded-2xl px-4 py-3.5 flex items-start gap-3"
      style={{
        background: "var(--nxt-surface-soft)",
        border: "1px solid var(--nxt-border)",
        boxShadow: "var(--nxt-shadow-sm, 0 2px 12px -4px rgba(0,0,0,0.4))",
      }}
      data-testid="chat-friendly-error"
    >
      <span
        className="h-7 w-7 rounded-full flex items-center justify-center shrink-0 mt-0.5"
        style={{
          background: "rgba(245, 158, 11, 0.14)",
          border: "1px solid rgba(245, 158, 11, 0.36)",
        }}
      >
        <Activity size={13} style={{ color: "#F59E0B" }} />
      </span>
      <div className="flex-1 min-w-0">
        <div
          className="text-[13.5px] font-semibold tracking-tight"
          style={{ color: "var(--nxt-fg)" }}
        >
          {error.title}
        </div>
        <div
          className="text-[12.5px] leading-relaxed mt-0.5"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          {error.hint}
        </div>
        <div className="flex items-center gap-2 mt-2.5">
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] font-medium transition"
            style={{
              background: "var(--nxt-accent)",
              color: "var(--nxt-bg)",
            }}
            data-testid="chat-friendly-error-retry"
          >
            <RefreshCw size={11} strokeWidth={2.4} />
            Retry
          </button>
          {showSwitch && (
            <button
              type="button"
              onClick={onSwitchModel}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] transition"
              style={{
                background: "transparent",
                border: "1px solid var(--nxt-border)",
                color: "var(--nxt-fg-dim)",
              }}
              data-testid="chat-friendly-error-switch"
            >
              Switch model
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
