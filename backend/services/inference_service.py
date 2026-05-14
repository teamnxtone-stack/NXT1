"""NXT1 Intelligent Project Inference — prompt → framework/template.

Given a natural-language prompt, infer what the user is trying to build and
recommend a scaffold pack. The goal is for the user to feel “NXT1 understands
what I’m trying to build” before the AI even starts editing.

The inference pipeline is intentionally cheap and deterministic:
  1. heuristic classifier (keyword + signal matching)
  2. (optional) AI-assisted classifier when heuristic confidence is low

Nothing here blocks the build path — if inference fails or is uncertain,
the builder falls back to the existing default scaffold.

Public API:
    infer_project_kind(prompt, existing_signals=None) -> InferenceResult

This service is consumed by routes/chat.py at the start of a build, and the
result is persisted to projects.analysis.inference for audit and UI display.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional

logger = logging.getLogger("nxt1.inference")


# ---------- Result type ----------
@dataclass
class InferenceResult:
    kind: str                          # "web-static" | "react-vite" | "nextjs-tailwind" | "expo-rn" | "browser-extension" | "ai-chat-streaming"
    framework: str                     # human label e.g. "Next.js + Tailwind"
    rationale: str                     # short explanation shown to the user
    confidence: float                  # 0.0 … 1.0
    required_capabilities: List[str] = field(default_factory=list)
    suggested_provider_tier: str = "balanced"   # latency tier hint for the build
    signals_matched: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------- Heuristic classifier ----------
# Each rule lists trigger phrases/keywords. First-match-with-highest-weight wins.
# Weight is roughly "how confident" — used to compute final confidence score.
_RULES = [
    # ---- mobile / native ----
    {
        "kind": "expo-rn",
        "framework": "Expo + React Native",
        "rationale": "Native mobile app foundation with Expo's hot reload and OTA updates.",
        "capabilities": ["mobile", "native-runtime"],
        "tier": "balanced",
        "weight": 0.94,
        "keywords": [
            r"\bexpo\b", r"\breact native\b", r"\brn\b",
            r"\bmobile app\b", r"\bios app\b", r"\bandroid app\b",
            r"\bnative app\b", r"\biphone app\b",
            # 2026-05-13: catch mobile-* product nouns (e.g. "mobile habit
            # tracker") without firing on "mobile-friendly website".
            r"\bmobile\s+(?:tracker|app|game|application|utility|wallet|workout|fitness|habit|journal|chat|messenger|reminder|todo|player|recorder|scanner|reader)\b",
            r"\b(?:habit|workout|fitness|step|sleep|water|meditation)\s+tracker\b",
        ],
    },
    # ---- browser extension ----
    {
        "kind": "browser-extension",
        "framework": "Chrome / Firefox extension (MV3)",
        "rationale": "Manifest V3 browser extension scaffold with content + background scripts.",
        "capabilities": ["extension", "content-script", "background-worker"],
        "tier": "balanced",
        "weight": 0.95,
        "keywords": [
            r"\bchrome extension\b", r"\bbrowser extension\b",
            r"\bfirefox add-?on\b", r"\bmv3\b", r"\bmanifest v3\b",
            # 2026-05-13: catch "chrome <noun> extension" forms
            # ("chrome translator extension", "chrome sidebar extension", etc.)
            r"\bchrome\s+\w+\s+extension\b",
            r"\bfirefox\s+\w+\s+extension\b",
            r"\bbrowser\s+\w+\s+extension\b",
            # Standalone "extension" with explicit browser context elsewhere
            r"\b(?:chrome|firefox|edge|safari)\b.{0,40}\bextension\b",
        ],
    },
    # ---- AI chat / streaming app ----
    {
        "kind": "ai-chat-streaming",
        "framework": "AI chat (streaming) + Tailwind",
        "rationale": "Streaming-ready foundation for chat-style AI apps with SSE/WebSocket hooks.",
        "capabilities": ["sse", "chat-stream", "llm-proxy"],
        "tier": "fast",
        "weight": 0.9,
        "keywords": [
            r"\bai chat\b", r"\bchatbot\b", r"\bchat app\b",
            r"\bllm app\b", r"\bstreaming chat\b", r"\bgpt clone\b",
            r"\bclaude clone\b", r"\bagent ui\b", r"\bcopilot ui\b",
        ],
    },
    # ---- Next.js (SaaS / dashboard / marketing) ----
    {
        "kind": "nextjs-tailwind",
        "framework": "Next.js 14 + Tailwind",
        "rationale": "App-router Next.js with Tailwind — best for SaaS, dashboards, and marketing sites.",
        "capabilities": ["ssr", "api-routes", "tailwind"],
        "tier": "balanced",
        "weight": 0.88,
        "keywords": [
            r"\bnext\.?js\b", r"\bnextjs\b",
            r"\bsaas\b", r"\bdashboard\b", r"\badmin panel\b",
            r"\blanding page\b", r"\bmarketing site\b",
            r"\bsubscription\b", r"\bstripe\b",
            r"\bauthentication app\b",
        ],
    },
    # ---- React + Vite (single-page apps) ----
    {
        "kind": "react-vite",
        "framework": "React + Vite + Tailwind",
        "rationale": "Fast Vite-powered React SPA — ideal for tools, dashboards, and interactive apps.",
        "capabilities": ["spa", "vite", "tailwind"],
        "tier": "balanced",
        "weight": 0.82,
        "keywords": [
            r"\bvite\b", r"\breact app\b", r"\bspa\b", r"\bsingle page\b",
            r"\bcomponent library\b", r"\bdesign system\b",
            r"\bkanban\b", r"\btodo app\b", r"\btask manager\b",
            r"\bnotes app\b", r"\bcrm\b", r"\bpipeline\b",
        ],
    },
    # ---- Tauri (Rust + web-frontend desktop apps) ----
    {
        "kind": "tauri-desktop",
        "framework": "Tauri 2 + React + Rust",
        "rationale": "Cross-platform desktop app with Tauri's Rust core + a React webview UI.",
        "capabilities": ["desktop", "native-runtime", "rust"],
        "tier": "balanced",
        "weight": 0.92,
        "keywords": [
            r"\btauri\b", r"\brust desktop\b", r"\bwry\b",
            r"\bdesktop app\b", r"\belectron alternative\b",
            r"\bmac app\b", r"\bwindows app\b", r"\blinux app\b",
            r"\bnative desktop\b",
        ],
    },
    # ---- Turborepo (monorepo orchestration) ----
    {
        "kind": "turborepo-monorepo",
        "framework": "Turborepo + pnpm workspaces",
        "rationale": "Monorepo orchestration with shared packages, build caching, and parallel pipelines.",
        "capabilities": ["monorepo", "turbo", "pnpm-workspaces", "shared-packages"],
        "tier": "balanced",
        "weight": 0.91,
        "keywords": [
            r"\bturborepo\b", r"\bturbo repo\b", r"\bturbo monorepo\b",
            r"\bmonorepo\b", r"\bnx monorepo\b",
            r"\bpnpm workspaces\b", r"\bworkspaces?\b.*\bpackages?\b",
            r"\bapps and packages\b", r"\bshared (ui|components|libraries)\b",
        ],
    },
]

# Generic fallback when nothing matches: simple static site (current default).
_FALLBACK = {
    "kind": "web-static",
    "framework": "Multi-page HTML + CSS",
    "rationale": "Static HTML/CSS/JS foundation — great starting point for portfolios and simple sites.",
    "capabilities": [],
    "tier": "balanced",
    "weight": 0.5,
}


def infer_project_kind(prompt: str, existing_signals: Optional[dict] = None) -> InferenceResult:
    """Heuristic prompt classifier. Returns an InferenceResult with confidence.

    `existing_signals` can be passed by callers that have additional context
    (e.g. for imported projects: detected framework, file tree). When present,
    they bias the classifier and bump confidence.
    """
    text = (prompt or "").lower()
    if not text:
        return _result_from(_FALLBACK, matched=["empty-prompt"], confidence=0.4)

    # Existing-project bias: if we already know the framework, lock to it.
    if existing_signals:
        fw = (existing_signals.get("framework") or "").lower()
        if fw in {"nextjs", "next"}:
            return _result_from(_rule_by_kind("nextjs-tailwind"), matched=["existing:nextjs"], confidence=0.97)
        if fw in {"vite", "react-vite"}:
            return _result_from(_rule_by_kind("react-vite"), matched=["existing:vite"], confidence=0.97)
        if fw in {"expo", "react-native"}:
            return _result_from(_rule_by_kind("expo-rn"), matched=["existing:expo"], confidence=0.97)
        if fw in {"tauri"}:
            return _result_from(_rule_by_kind("tauri-desktop"), matched=["existing:tauri"], confidence=0.97)
        if fw in {"turborepo", "turbo"}:
            return _result_from(_rule_by_kind("turborepo-monorepo"), matched=["existing:turborepo"], confidence=0.97)

        # File-tree signals (when import provides a partial repo).
        tree = set(existing_signals.get("files") or [])
        if tree:
            if any(p.startswith("src-tauri/") or p == "src-tauri/tauri.conf.json" for p in tree):
                return _result_from(_rule_by_kind("tauri-desktop"), matched=["files:src-tauri"], confidence=0.96)
            if "turbo.json" in tree or "pnpm-workspace.yaml" in tree:
                return _result_from(_rule_by_kind("turborepo-monorepo"), matched=["files:turbo.json"], confidence=0.96)
            if "app.json" in tree and any(p.startswith("app/") or p.startswith("(tabs)/") for p in tree):
                return _result_from(_rule_by_kind("expo-rn"), matched=["files:expo-router"], confidence=0.95)

    # Score each rule by # of matching keywords (case-insensitive, word boundary).
    best = None
    best_score = 0
    best_matched: List[str] = []
    for rule in _RULES:
        matched = []
        for pat in rule["keywords"]:
            if re.search(pat, text):
                matched.append(pat)
        if not matched:
            continue
        score = len(matched) * rule["weight"]
        if score > best_score:
            best, best_score, best_matched = rule, score, matched

    if not best:
        return _result_from(_FALLBACK, matched=["no-match"], confidence=0.55)

    # Confidence: scale by # of matches but cap at the rule's base weight + 0.05 bonus.
    confidence = min(0.98, best["weight"] + 0.02 * (len(best_matched) - 1))
    return _result_from(best, matched=best_matched, confidence=confidence)


def _rule_by_kind(kind: str) -> dict:
    for r in _RULES:
        if r["kind"] == kind:
            return r
    return _FALLBACK


def _result_from(rule: dict, matched: List[str], confidence: float) -> InferenceResult:
    return InferenceResult(
        kind=rule["kind"],
        framework=rule["framework"],
        rationale=rule["rationale"],
        confidence=round(confidence, 3),
        required_capabilities=list(rule.get("capabilities", [])),
        suggested_provider_tier=rule.get("tier", "balanced"),
        signals_matched=matched[:6],
    )
