/**
 * NXT1 — Landing (Phase 15 rebuild)
 *
 * Complete rewrite. No more incremental patches.
 *
 * Composition (top → bottom, single viewport):
 *   1. Minimal header — wordmark left, "Sign in" right
 *   2. Tiny overline tag
 *   3. Hero — 2 lines of cinematic display type
 *   4. One subtitle line (max)
 *   5. Centered prompt cockpit — input + mode pills + model trigger + Build pill
 *   6. Tiny footer
 *
 * Removed entirely (per direction):
 *   - capability cards / feature strip
 *   - giant marketing paragraph
 *   - duplicate Discover · Develop · Deliver triple-tag
 *   - "AI software platform · private build · v0.6" technical clutter
 *   - any bordered cards / boxes / bottom CTAs
 *
 * Background: subtle graphite gradient (variant="cinema" in backdrop).
 * Aesthetic: ChatGPT / Blink / Arc — quiet, premium, prompt-first.
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import PublicFooter from "@/components/PublicFooter";
import { ArrowRight, Sparkles, Layers, Globe, Smartphone, Puzzle } from "lucide-react";
import Brand from "@/components/Brand";
import GradientBackdrop from "@/components/GradientBackdrop";
import ModelPickerCockpit from "@/components/premium/ModelPickerCockpit";
import LandingShowcase from "@/components/landing/LandingShowcase";
import HomepageDemos from "@/components/landing/HomepageDemos";
import PromptToDeployFlow from "@/components/landing/PromptToDeployFlow";
import ThemeSwitcher from "@/components/theme/ThemeSwitcher";
import { useTheme } from "@/components/theme/ThemeProvider";
import { isAuthenticated } from "@/lib/auth";

const MODES = [
  { key: "fullstack", label: "Full Stack", icon: Layers     },
  { key: "website",   label: "Website",    icon: Globe      },
  { key: "mobile",    label: "Mobile",     icon: Smartphone },
  { key: "extension", label: "Extension",  icon: Puzzle     },
];

// Adaptive suggestion chips — change with selected mode.
const MODE_SUGGESTIONS = {
  fullstack: [
    { label: "SaaS dashboard",   prompt: "Build a SaaS dashboard with authentication, billing, and an admin panel." },
    { label: "AI platform",      prompt: "Build an AI platform with prompt history, a model picker, and team sharing." },
    { label: "Admin system",     prompt: "Build an internal admin system with role-based access and audit logs." },
  ],
  website: [
    { label: "Portfolio",        prompt: "Design a premium developer portfolio with hero, projects, and contact form." },
    { label: "Marketing launch", prompt: "Build a marketing launch page with waitlist signup and feature grid." },
    { label: "Docs site",        prompt: "Build a modern documentation site with sidebar nav and code samples." },
  ],
  mobile: [
    { label: "Fitness app",      prompt: "Build a mobile fitness app with workout tracking and progress charts." },
    { label: "AI chat app",      prompt: "Build a mobile AI chat companion with streaming responses." },
    { label: "Social app",       prompt: "Build a mobile social app with feed, profiles, and messaging." },
  ],
  extension: [
    { label: "Productivity",     prompt: "Build a Chrome productivity extension that summarises any open tab." },
    { label: "AI sidebar",       prompt: "Build a Chrome AI sidebar that answers questions about the current page." },
    { label: "Tab manager",      prompt: "Build a Chrome tab manager with groups, search, and snooze." },
  ],
};

// Rotating intelligent prompt examples — typed in/out with a soft cursor.
const PLACEHOLDER_CYCLE = [
  "Build a modern SaaS dashboard with billing…",
  "Create an AI mobile app for journaling…",
  "Design a portfolio with smooth animations…",
  "Ship a realtime collaborative todo app…",
  "Spin up a marketing site for a launch…",
  "Build an internal admin for a small team…",
];

function useTypedPlaceholder(cycle, { isPaused }) {
  const [text, setText] = useState("");
  const stateRef = useRef({ i: 0, phase: "typing", cursor: 0 });

  useEffect(() => {
    if (isPaused) return;
    let mounted = true;
    const tick = () => {
      if (!mounted) return;
      const s = stateRef.current;
      const target = cycle[s.i % cycle.length];
      if (s.phase === "typing") {
        if (s.cursor < target.length) {
          s.cursor += 1;
          setText(target.slice(0, s.cursor));
          const delay = 28 + Math.random() * 30;
          timer = setTimeout(tick, delay);
        } else {
          s.phase = "hold";
          timer = setTimeout(tick, 1700);
        }
      } else if (s.phase === "hold") {
        s.phase = "erasing";
        timer = setTimeout(tick, 20);
      } else if (s.phase === "erasing") {
        if (s.cursor > 0) {
          s.cursor -= 1;
          setText(target.slice(0, s.cursor));
          timer = setTimeout(tick, 14);
        } else {
          s.i += 1;
          s.phase = "typing";
          timer = setTimeout(tick, 220);
        }
      }
    };
    let timer = setTimeout(tick, 600);
    return () => { mounted = false; clearTimeout(timer); };
  }, [cycle, isPaused]);

  return text;
}

export default function LandingPage() {
  const navigate = useNavigate();
  const { theme } = useTheme();
  const isLight = theme === "light";
  const [authed, setAuthed] = useState(false);
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState("fullstack");
  const [provider, setProvider] = useState("anthropic");
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef(null);
  // Rotating placeholder pauses only when the user has typed something
  const placeholder = useTypedPlaceholder(PLACEHOLDER_CYCLE, {
    isPaused: !!draft,
  });

  useEffect(() => {
    setAuthed(isAuthenticated());
    try {
      const saved = window.localStorage.getItem("nxt1_draft_prompt") || "";
      if (saved) setDraft(saved);
    } catch { /* ignore */ }
    // Auto-focus the prompt on landing — the whole experience revolves around it.
    setTimeout(() => textareaRef.current?.focus(), 80);
  }, []);

  const onDraftChange = (val) => {
    setDraft(val);
    try { window.localStorage.setItem("nxt1_draft_prompt", val); }
    catch { /* ignore */ }
  };

  const onBuild = () => {
    const v = (draft || "").trim();
    if (!v) {
      textareaRef.current?.focus();
      return;
    }
    try { window.localStorage.setItem("nxt1_draft_prompt", v); }
    catch { /* ignore */ }
    const target = authed ? "/workspace" : "/signup";
    navigate(
      `${target}?prompt=${encodeURIComponent(v)}&mode=${mode}&return=/dashboard`,
    );
  };

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden"
      style={{
        fontFamily: "'Inter', sans-serif",
        color: "var(--nxt-fg)",
      }}
      data-testid="landing-page"
    >
      <GradientBackdrop variant="cinema" intensity="soft" />

      {/* Header — minimal: section anchors + Sign in + Create account */}
      <header className="relative z-20 px-5 sm:px-10 pt-5 sm:pt-6 flex items-center justify-between">
        <Brand size="md" gradient />
        {/* Section anchors — desktop only. Click jumps to the matching
            block; each section has a scroll-mt offset so the header
            doesn't overlap. */}
        <nav className="hidden md:flex items-center gap-1" data-testid="landing-section-nav">
          {[
            { id: "flow",      label: "How it works" },
            { id: "features",  label: "Demos" },
            { id: "ship",      label: "What you ship" },
            { id: "agents",    label: "Agents" },
            { id: "showcase",  label: "Models" },
          ].map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className="text-[12.5px] tracking-tight px-3 py-2 rounded-full transition-colors hover:opacity-100"
              style={{ color: "var(--nxt-fg-dim)" }}
              data-testid={`landing-nav-${s.id}`}
            >
              {s.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-1.5 sm:gap-2">
          <ThemeSwitcher />
          {authed ? (
            <button
              onClick={() => navigate("/workspace")}
              className="text-[13px] tracking-tight font-medium px-3 py-2 rounded-full transition-colors"
              style={{ color: "var(--nxt-fg)" }}
              data-testid="nav-dashboard-button"
            >
              Open workspace
              <ArrowRight size={13} className="inline ml-1" />
            </button>
          ) : (
            <>
              <button
                onClick={() => navigate("/signin")}
                className="text-[13px] tracking-tight px-3 py-2 transition-colors hover:opacity-100"
                style={{ color: "var(--nxt-fg-dim)" }}
                data-testid="nav-signin-button"
              >
                Sign in
              </button>
              <button
                onClick={() => navigate("/signup")}
                className="text-[13px] tracking-tight font-medium px-3.5 py-2 rounded-full transition-all"
                style={
                  isLight
                    ? {
                        background: "#1F1F23",
                        color: "#FAFAFA",
                        border: "1px solid rgba(26,26,31,0.18)",
                        boxShadow: "0 6px 16px -8px rgba(31,31,35,0.35)",
                      }
                    : {
                        background: "linear-gradient(180deg, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.04) 100%)",
                        border: "1px solid rgba(255,255,255,0.10)",
                        color: "#FAFAFA",
                      }
                }
                data-testid="nav-signup-button"
              >
                Request access
              </button>
            </>
          )}
        </div>
      </header>

      {/* Hero — centered, prompt-first */}
      <main className="relative z-10 mx-auto max-w-[920px] px-5 sm:px-6 pt-[8vh] sm:pt-[10vh] pb-20">

        {/* Invitation overline removed (2026-05-13 user request) —
            framing now sits in the Jwood signature row below the headline
            and the request-access CTA in the top nav. */}

        {/* Hero headline — quiet, cinematic, repositioned for founders */}
        <h1
          className="text-[44px] sm:text-[64px] lg:text-[80px] leading-[0.96] tracking-[-0.035em] font-medium text-center mb-4 sm:mb-5"
          style={{ fontFamily: "'Cabinet Grotesk', sans-serif" }}
        >
          <span
            className="block"
            style={{ color: "var(--nxt-fg)" }}
          >
            Build software.
          </span>
          <span
            className="block"
            style={{
              background: isLight
                ? "linear-gradient(180deg, #1A1A1F 0%, #6A6259 100%)"
                : "linear-gradient(180deg, #E8E8EE 0%, #8A8A93 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            Host it. Ship it.
          </span>
        </h1>

        {/* DISCOVER · DEVELOP · DELIVER — branded supporting tagline under headline */}
        <div className="flex items-center justify-center mb-3" data-testid="brand-triplet">
          <span
            className="mono text-[11px] sm:text-[12px] tracking-[0.42em] uppercase font-semibold bg-clip-text text-transparent"
            style={{
              backgroundImage: isLight
                ? "linear-gradient(110deg, #0E8C73 0%, #B58320 50%, #C25A1F 100%)"
                : "linear-gradient(110deg, #5EEAD4 0%, #F0D28A 50%, #FF8A3D 100%)",
            }}
          >
            DISCOVER · DEVELOP · DELIVER
          </span>
        </div>

        <p
          className="text-center text-[14px] sm:text-[15px] max-w-[600px] mx-auto mb-5 sm:mb-6 leading-relaxed"
          style={{ color: "var(--nxt-fg-dim)" }}
        >
          An AI-native platform for founders, builders, and serious teams shipping MVPs,
          internal tools, dashboards, and full-stack software. Create, host, and deploy
          from one place.
        </p>

        {/* Jwood Technologies signature — replaces the limited-access pill.
            Sits as a quiet co-sign under the subtitle. */}
        <div className="flex items-center justify-center mb-10" data-testid="landing-jwood-signature">
          <span
            className="inline-flex items-center gap-2.5 mono text-[10.5px] sm:text-[11px] tracking-[0.32em] uppercase"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            <span
              className="h-px w-6 sm:w-10"
              style={{ background: "var(--nxt-border-soft)" }}
            />
            A product of <span style={{ color: "var(--nxt-fg-dim)", fontWeight: 600, letterSpacing: "0.18em" }}>Jwood Technologies</span>
            <span
              className="h-px w-6 sm:w-10"
              style={{ background: "var(--nxt-border-soft)" }}
            />
          </span>
        </div>

        {/* Prompt cockpit — the most important surface on the entire site.
            Intentionally stays as a dark graphite "device island" in BOTH
            modes — it visually reads as the actual builder workspace. */}
        <div
          className="mx-auto max-w-[760px] relative group"
          data-testid="landing-prompt-cockpit"
        >
          {/* Soft ambient glow behind the input — feels alive on hover/focus */}
          <div
            aria-hidden
            className="absolute -inset-x-8 -inset-y-6 rounded-[40px] blur-3xl opacity-50 group-focus-within:opacity-90 transition-opacity duration-500 pointer-events-none"
            style={{
              background: isLight
                ? "radial-gradient(60% 60% at 50% 100%, rgba(20,130,110,0.18) 0%, rgba(20,130,110,0) 70%), radial-gradient(60% 60% at 50% 0%, rgba(99,102,241,0.10) 0%, rgba(99,102,241,0) 70%)"
                : "radial-gradient(60% 60% at 50% 100%, rgba(94,234,212,0.18) 0%, rgba(94,234,212,0) 70%), radial-gradient(60% 60% at 50% 0%, rgba(99,102,241,0.10) 0%, rgba(99,102,241,0) 70%)",
            }}
          />

          <div
            className="relative rounded-[28px] transition-all duration-300"
            style={{
              // Always a solid matte graphite island — never bleeds into cream
              background: "linear-gradient(180deg, #303038 0%, #1F1F23 100%)",
              border: isLight
                ? "1px solid rgba(26,26,31,0.10)"
                : "1px solid rgba(255,255,255,0.10)",
              boxShadow: isLight
                ? "0 28px 60px -22px rgba(40,30,15,0.30), 0 8px 22px -10px rgba(40,30,15,0.18), inset 0 1px 0 rgba(255,255,255,0.04)"
                : "0 28px 60px -22px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.04)",
            }}
          >
            <textarea
              ref={textareaRef}
              rows={3}
              value={draft}
              onChange={(e) => onDraftChange(e.target.value)}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  onBuild();
                }
              }}
              placeholder={placeholder ? `${placeholder}` : "Describe what you want to build…"}
              className="w-full bg-transparent outline-none resize-none text-[16px] sm:text-[17px] leading-[1.55] tracking-[-0.005em] px-6 pt-5 pb-3 placeholder:text-white/35 text-white"
              data-testid="landing-prompt-input"
              style={{ fontSize: "16px" }}
            />

              {/* Build-type cards — always-visible 4-up row, no hidden scroll */}
              <div className="px-3 sm:px-4 pt-1 pb-2">
                <div
                  className="grid grid-cols-4 gap-1.5 sm:gap-2"
                  role="tablist"
                  aria-label="Build type"
                >
                  {MODES.map((m) => {
                    const Icon = m.icon || Sparkles;
                    const active = mode === m.key;
                    return (
                      <button
                        key={m.key}
                        type="button"
                        onClick={() => setMode(m.key)}
                        data-testid={`landing-mode-${m.key}`}
                        role="tab"
                        aria-selected={active}
                        className="relative flex flex-col items-center justify-center gap-1.5 px-1 py-2.5 rounded-2xl transition-all duration-200"
                        style={
                          active
                            ? {
                                background: "linear-gradient(180deg, rgba(94,234,212,0.16) 0%, rgba(94,234,212,0.04) 100%)",
                                boxShadow: "inset 0 0 0 1px rgba(94,234,212,0.32), 0 8px 24px -10px rgba(94,234,212,0.28)",
                                color: "#FFFFFF",
                              }
                            : {
                                background: "rgba(255,255,255,0.025)",
                                boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.06)",
                                color: "rgba(255,255,255,0.70)",
                              }
                        }
                      >
                        <Icon
                          size={15}
                          strokeWidth={1.7}
                          style={{ color: active ? "#5EEAD4" : "rgba(255,255,255,0.70)" }}
                        />
                        <span className="text-[11px] sm:text-[12px] font-medium tracking-tight whitespace-nowrap">
                          {m.label}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Action row — provider + Build CTA */}
              <div className="flex items-center justify-between gap-2 px-3 sm:px-4 pb-3 pt-1">
                <div className="flex-1 min-w-0">
                  <ModelPickerCockpit
                    value={provider}
                    onChange={setProvider}
                    providers={{ emergent: true, anthropic: true }}
                    compact
                  />
                </div>                <button
                  type="button"
                  onClick={onBuild}
                  disabled={!draft.trim()}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-[13px] font-semibold tracking-tight bg-white text-[#1F1F23] hover:bg-white/95 transition-all duration-200 shadow-[0_8px_28px_-10px_rgba(255,255,255,0.55)] hover:shadow-[0_14px_42px_-10px_rgba(255,255,255,0.75)] hover:-translate-y-0.5 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:shadow-none shrink-0"
                  data-testid="landing-build-button"
                >
                  <Sparkles size={13} />
                  Build
                </button>
              </div>
          </div>

          {/* Single ultra-quiet hint line under input */}
          <p
            className="mt-4 text-center mono text-[10px] tracking-[0.24em] uppercase"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            ⌘ + ↵ to build
          </p>

          {/* Adaptive suggestion chips — change with selected mode */}
          <div
            className="mt-5 flex flex-wrap items-center justify-center gap-1.5"
            data-testid="landing-suggestion-chips"
          >
            {(MODE_SUGGESTIONS[mode] || []).map((s) => (
              <button
                key={s.label}
                type="button"
                onClick={() => {
                  onDraftChange(s.prompt);
                  setTimeout(() => textareaRef.current?.focus(), 30);
                }}
                className="inline-flex items-center gap-1.5 px-3 h-8 rounded-full text-[11.5px] transition"
                style={{
                  background: "var(--nxt-chip-bg)",
                  border: "1px solid var(--nxt-chip-border)",
                  color: "var(--nxt-fg-dim)",
                }}
                data-testid={`landing-suggest-${s.label.toLowerCase().replace(/\s+/g, "-")}`}
              >
                <Sparkles size={10} style={{ color: "var(--nxt-accent)" }} />
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </main>

      {/* The NXT1 loop — animated 4-stage flow demo (Prompt → App → Preview → Deploy) */}
      <div id="flow" className="scroll-mt-20">
        <PromptToDeployFlow />
      </div>

      {/* Premium feature sections — Base44 / Roark inspired storytelling */}
      <div id="features" className="scroll-mt-20">
        <HomepageDemos />
      </div>

      {/* Capability strip — what NXT1 helps you ship */}
      <section
        id="ship"
        className="scroll-mt-20 relative mx-auto max-w-[1080px] px-5 sm:px-6 py-16 sm:py-20"
        data-testid="landing-capability-strip"
      >
        <div className="text-center mb-10">
          <span
            className="mono text-[10.5px] sm:text-[11px] tracking-[0.42em] uppercase font-medium"
            style={{ color: "var(--nxt-fg-faint)" }}
          >
            WHAT YOU CAN SHIP
          </span>
          <h2
            className="mt-4 text-[26px] sm:text-[34px] lg:text-[40px] leading-[1.05] tracking-[-0.025em] font-medium"
            style={{ fontFamily: "'Cabinet Grotesk', sans-serif", color: "var(--nxt-fg)" }}
          >
            Built for builders, founders, and serious teams.
          </h2>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
          {[
            "MVPs",
            "Full-stack apps",
            "Marketing sites",
            "Dashboards",
            "Internal tools",
            "Mobile apps",
            "AI workflows",
            "Custom software",
          ].map((label) => (
            <div
              key={label}
              className="rounded-xl px-4 py-4 sm:py-5"
              style={{
                background: "var(--nxt-surface-soft)",
                border: "1px solid var(--nxt-border-soft)",
              }}
            >
              <span
                className="block text-[13px] sm:text-[14px] font-medium tracking-tight"
                style={{ color: "var(--nxt-fg)" }}
              >
                {label}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Agents library teaser — workspace-only catalog of 191 agents + 52 skills */}
      <section
        id="agents"
        className="scroll-mt-20 relative mx-auto max-w-[1080px] px-5 sm:px-6 py-16 sm:py-20"
        data-testid="landing-agents-teaser"
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12 items-center">
          <div>
            <span
              className="mono text-[10.5px] sm:text-[11px] tracking-[0.42em] uppercase font-medium"
              style={{ color: "var(--nxt-fg-faint)" }}
            >
              AGENTS LIBRARY
            </span>
            <h2
              className="mt-4 text-[28px] sm:text-[38px] lg:text-[44px] leading-[1.05] tracking-[-0.025em] font-medium"
              style={{ fontFamily: "'Cabinet Grotesk', sans-serif", color: "var(--nxt-fg)" }}
            >
              <span style={{ color: "var(--nxt-fg)" }}>Pick an agent.</span>{" "}
              <span
                style={{
                  background: isLight
                    ? "linear-gradient(180deg, #1A1A1F 0%, #6A6259 100%)"
                    : "linear-gradient(180deg, #E8E8EE 0%, #8A8A93 100%)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  backgroundClip: "text",
                }}
              >
                Tell it what to do.
              </span>
            </h2>
            <p
              className="mt-4 text-[14px] sm:text-[15px] leading-relaxed max-w-[480px]"
              style={{ color: "var(--nxt-fg-dim)" }}
            >
              191 specialised AI agents (backend architects, security auditors,
              test automators, DevOps responders) plus 52 personal-assistant
              skills (GitHub, Notion, iMessage, Apple Notes, Whisper). All
              browsable from a single workspace surface — connect your own
              keys and they answer through whichever provider you choose.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => navigate(authed ? "/workspace/agents" : "/signin?return=/workspace/agents")}
                className="inline-flex items-center gap-2 h-11 px-5 rounded-full text-[13.5px] font-semibold tracking-tight transition-all hover:-translate-y-0.5"
                style={{
                  background: isLight ? "#1F1F23" : "#FFFFFF",
                  color: isLight ? "#FAFAFA" : "#1F1F23",
                  boxShadow: isLight
                    ? "0 10px 28px -10px rgba(31,31,35,0.30)"
                    : "0 10px 28px -10px rgba(255,255,255,0.40)",
                }}
                data-testid="landing-agents-cta"
              >
                Open agents library
                <ArrowRight size={13} />
              </button>
              <span
                className="inline-flex items-center mono text-[11px] tracking-[0.22em] uppercase"
                style={{ color: "var(--nxt-fg-faint)" }}
              >
                Workspace · Auth required
              </span>
            </div>
          </div>

          {/* Right column — a cluster of agent chips you can recognise at a glance */}
          <div className="grid grid-cols-2 gap-2.5 sm:gap-3">
            {[
              { name: "backend-architect",      hint: "Service design" },
              { name: "security-auditor",       hint: "OWASP review" },
              { name: "frontend-developer",     hint: "UI components" },
              { name: "test-automator",         hint: "Coverage + CI" },
              { name: "devops-troubleshooter",  hint: "Incident triage" },
              { name: "code-reviewer",          hint: "Refactor" },
              { name: "github",                 hint: "Personal skill" },
              { name: "notion",                 hint: "Personal skill" },
            ].map((a) => (
              <div
                key={a.name}
                className="rounded-xl px-3 py-3"
                style={{
                  background: "var(--nxt-surface-soft)",
                  border: "1px solid var(--nxt-border-soft)",
                }}
              >
                <div
                  className="font-mono text-[12px] truncate"
                  style={{ color: "var(--nxt-fg)" }}
                >
                  {a.name}
                </div>
                <div
                  className="text-[10.5px] mt-0.5 opacity-70"
                  style={{ color: "var(--nxt-fg-dim)" }}
                >
                  {a.hint}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div id="showcase" className="scroll-mt-20">
        <LandingShowcase />
      </div>


      {/* Quiet footer — Brand · routes · Made in the USA */}
      <PublicFooter />
    </div>
  );
}
