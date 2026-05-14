"""chat_intent.py — Classify whether the user's chat message is a
build/edit request that should drive the file-generation pipeline OR a
plain Q&A question that should get a conversational answer (no code
regen, no scaffold mutation).

The classifier is intentionally pattern-based first (zero LLM cost,
zero latency) and only falls through to the AI when the patterns are
ambiguous. We err strongly on the side of "build" — false-negatives on
the build path are far worse than false-positives on the Q&A path.

Public API:
    classify_intent(message: str) -> Literal["build", "qa"]
    NXT1_HELP_PROMPT  — the system prompt used for Q&A replies; includes
                        an accurate snapshot of NXT1's UI / feature map
                        so answers are grounded in reality.
"""
from __future__ import annotations
import re
from typing import Literal

# Imperative verbs that indicate a build/edit/create intent. If any of
# these appears as a leading word, the message is "build" regardless of
# trailing question marks ("Can you add a contact form?" → build).
_BUILD_VERBS = {
    "add", "build", "create", "make", "generate", "remove", "delete",
    "change", "update", "modify", "fix", "rewrite", "rebuild", "redesign",
    "refactor", "rename", "move", "split", "merge", "implement", "wire",
    "hook", "include", "swap", "replace", "convert", "extract", "inline",
    "ship", "scaffold", "stub", "import", "install", "configure", "set",
    "deploy", "publish", "push", "save", "commit", "polish", "tighten",
    "tweak", "shrink", "expand", "extend", "use", "show", "hide",
    "darken", "lighten", "style", "format", "lay", "design", "draft",
    "give", "put", "drop", "lay",
}
# Question-leading words → Q&A by default (unless overridden by a build verb).
_QA_LEADERS = {
    "how", "what", "why", "when", "where", "who", "which", "can", "do",
    "does", "is", "are", "should", "could", "would", "will", "explain",
    "describe", "tell", "help", "summarize", "summarise", "list",
    "compare", "define",
}
# Phrases that almost always mean Q&A even mid-sentence.
_QA_PATTERNS = [
    re.compile(r"\bhow do i\b", re.I),
    re.compile(r"\bhow can i\b", re.I),
    re.compile(r"\bhow does\b", re.I),
    re.compile(r"\bwhat is\b", re.I),
    re.compile(r"\bwhat's\b", re.I),
    re.compile(r"\bwhat are\b", re.I),
    re.compile(r"\bwhat does\b", re.I),
    re.compile(r"\btell me (?:about|how|what|why)\b", re.I),
    re.compile(r"\bexplain (?:to me|how|what|why|the)\b", re.I),
    re.compile(r"\bcan you tell\b", re.I),
    re.compile(r"\bdo i need\b", re.I),
    re.compile(r"\bwhere (?:do|is|can|are)\b", re.I),
    re.compile(r"\bwhy (?:does|is|did|am|are)\b", re.I),
]


def classify_intent(message: str) -> Literal["build", "qa"]:
    """Best-effort intent split. Defaults to 'build' when ambiguous.

    Rules (in order):
      1. Strong Q&A patterns (regex) → 'qa'
      2. Leading word is a build verb → 'build'
      3. Leading word is a question word AND message ends with '?'
         AND no build verb appears in the first 6 words → 'qa'
      4. Default → 'build'
    """
    msg = (message or "").strip()
    if len(msg) < 3:
        return "build"

    # 1. Strong Q&A patterns
    for pat in _QA_PATTERNS:
        if pat.search(msg):
            return "qa"

    # Tokenise leading words (lowercase, strip punctuation)
    tokens = re.findall(r"[A-Za-z']+", msg.lower())
    if not tokens:
        return "build"

    head = tokens[0]
    early = set(tokens[:6])

    # 2. Leading build verb
    if head in _BUILD_VERBS:
        return "build"

    # 3. Question leader + '?' + no build verb in first 6 words
    if head in _QA_LEADERS and msg.rstrip().endswith("?") and not (early & _BUILD_VERBS):
        return "qa"

    # 4. Default: assume build
    return "build"


# Grounded help prompt — the AI uses this when answering Q&A so it
# tells the user about real NXT1 features (Tools drawer → Domains,
# composer ⋯ menu → Deploy, etc.) instead of hallucinating.
NXT1_HELP_PROMPT = """You are NXT1 — the AI agent inside the NXT1 builder. The user is
asking a question (not requesting a build/edit). Respond conversationally,
warmly, briefly. Do NOT emit code, JSON, scaffold tags, or file blobs.

Ground every answer in real NXT1 UI:
- **Connect a custom domain**: open the Tools drawer (top-right `Tools`
  button or `⋯` in the composer on mobile) → tap **Domains** → type
  your hostname (e.g. `app.mybrand.com`) → press Add. If NXT1 manages
  the zone (Cloudflare token configured), the CNAME is created
  automatically and SSL provisions in 1–2 minutes. Otherwise you'll
  see the exact DNS records to paste at your registrar.
- **Deploy live**: composer toolbar → **Deploy now** (auto-picks Vercel)
  or **Pick provider** for Cloudflare Pages.
- **Public share link**: build summary card → **Share preview** (or the
  composer `⋯` → Share). Creates a `nxtone.tech/p/<slug>` URL.
- **Save to GitHub**: composer paperclip row → GitHub icon. Pushes the
  full project in one commit. First push asks for a fine-grained PAT
  with Contents + Administration write.
- **See files / history / env vars / databases**: all in Tools drawer.
- **AgentOS** (personal agent suite): top-left hamburger → AgentOS.
- **Switch model**: composer `⋯` → Model picker.
- **Stop / continue a build**: white circle stop in composer; ▶ Continue
  pill appears after stop.

Answer in 1–4 short sentences. If the user follow-up is "do it for me",
the NEXT message can become a build request — that's fine. For now,
just explain. No headings, no bullet lists unless absolutely needed.
"""
