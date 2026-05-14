"""LLM-graded scorer for the NXT1 eval kit.

Adds a "taste" dimension to the structural rubric in scorer.py. Uses the
fastest available provider (via `get_provider_for_task("inference")`) to
grade three orthogonal dimensions, each on a 1–5 integer scale:

  • visual_taste          — Does the output look like a polished, modern,
                            production-grade product (typography, spacing,
                            palette, micro-interactions)?
  • code_quality          — Idiomatic, well-structured, no obvious smells?
  • instruction_adherence — Did it follow the user's instructions precisely
                            without scope creep or unrelated rewrites?

Output is normalized to [0..1] per dimension before being plugged into the
existing weighted aggregate so the LLM score sits alongside the structural
score, not on top of it.

Failures are non-fatal: a network error or parse failure returns 0.0 with
an informative `issues[]` entry, so the rest of the rubric still produces
a meaningful aggregate.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import List, Tuple

from services.ai_service import get_provider_for_task

from .runner import FixtureResult
from .scorer import ScoreFunc

logger = logging.getLogger("nxt1.evalkit.llm_scorer")


GRADER_SYSTEM_PROMPT = """You are a strict, calibrated grader of AI-generated
web projects. You receive:

  • the user's original prompt
  • the AI's explanation of what it changed
  • a representative sample of the files it produced

Grade ALL three dimensions on a 1–5 integer scale (1 = poor, 5 = excellent):

  visual_taste          — Is the design polished, modern, production-grade?
                          Typography, spacing, palette, micro-interactions,
                          responsive details. Penalise generic / "AI-slop"
                          looks (purple gradients on white, default Arial,
                          centered everything, no hierarchy).
  code_quality          — Is the code idiomatic, well-structured, free of
                          obvious smells (unused vars, dead code, broken
                          imports, magic strings, console.logs)?
  instruction_adherence — Did it follow the user's request precisely without
                          scope creep, unrelated rewrites, or missing
                          requirements?

Respond with STRICT JSON only — no prose, no markdown:

{
  "visual_taste":          { "score": 1-5, "reason": "<1 short sentence>" },
  "code_quality":          { "score": 1-5, "reason": "<1 short sentence>" },
  "instruction_adherence": { "score": 1-5, "reason": "<1 short sentence>" }
}
"""


def _sample_files(files, max_files: int = 6, per_file_chars: int = 3500) -> str:
    """Pick representative files for grading. Prefer index.html / App.jsx /
    main CSS / page-level components."""
    if not files:
        return "(no files)"
    priority = ("index.html", "src/App.jsx", "src/App.tsx", "src/main.jsx",
                 "src/index.js", "styles/main.css", "src/styles.css",
                 "tailwind.config.js", "package.json")
    by_path = {f["path"]: f for f in files}
    chosen = [by_path[p] for p in priority if p in by_path]
    # Fill the rest with whatever else looks visual (.jsx/.tsx/.html/.css)
    for f in files:
        if len(chosen) >= max_files:
            break
        p = f["path"]
        if p in {c["path"] for c in chosen}:
            continue
        if p.endswith((".jsx", ".tsx", ".html", ".css", ".js")):
            chosen.append(f)
    blob_parts = []
    for f in chosen[:max_files]:
        content = (f.get("content") or "")[:per_file_chars]
        if len(f.get("content") or "") > per_file_chars:
            content += "\n/* …truncated… */"
        blob_parts.append(f"=== {f['path']} ===\n{content}")
    return "\n\n".join(blob_parts)


_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> dict:
    s = (text or "").strip()
    # Strip markdown fences
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        pass
    m = _JSON_OBJ_RE.search(s)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


async def grade_result(result: FixtureResult, user_message: str) -> dict:
    """Run a single grading pass. Returns the parsed grader JSON, or `{}` on
    failure (caller treats as zero across the board).
    """
    try:
        provider = get_provider_for_task("inference")
    except Exception as e:
        logger.warning(f"llm-scorer: no provider available ({e})")
        return {}

    user_prompt = (
        f"USER PROMPT:\n{user_message[:600]}\n\n"
        f"AI EXPLANATION:\n{(result.explanation or '')[:600]}\n\n"
        f"FILES (sampled):\n{_sample_files(result.files)}\n\n"
        "Respond with the grading JSON now."
    )
    session_id = f"eval-grade-{uuid.uuid4().hex[:8]}"
    try:
        raw = await provider.generate(GRADER_SYSTEM_PROMPT, user_prompt, session_id)
    except Exception as e:
        logger.warning(f"llm-scorer: provider call failed ({e})")
        return {}
    parsed = _extract_json(raw)
    return parsed if isinstance(parsed, dict) else {}


def _component(parsed: dict, key: str) -> Tuple[float, List[str]]:
    if not parsed:
        return 0.0, [f"llm:{key}: grader unavailable"]
    block = parsed.get(key) or {}
    raw = block.get("score")
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return 0.0, [f"llm:{key}: invalid score {raw!r}"]
    if score < 1 or score > 5:
        return 0.0, [f"llm:{key}: score {score} out of range"]
    normalised = (score - 1) / 4.0   # 1→0.0 … 5→1.0
    msgs: List[str] = []
    reason = (block.get("reason") or "").strip()
    if score <= 3 and reason:
        msgs.append(f"llm:{key} ({score}/5): {reason}")
    return normalised, msgs


def attach_llm_grader(scorer, user_message: str,
                        weights: dict | None = None) -> None:
    """Plug LLM-graded components into an existing `Scorer` instance.

    Default weights are conservative (0.10 each) so the structural rubric
    still dominates and one bad LLM grade can't fail an otherwise correct
    output. Caller can override `weights`.
    """
    import asyncio
    w = weights or {
        "llm:visual_taste": 0.10,
        "llm:code_quality": 0.10,
        "llm:instruction_adherence": 0.10,
    }
    # We cache the single grader call across the three components.
    cache: dict = {"parsed": None, "done": False}

    def _ensure_graded(result: FixtureResult) -> dict:
        if cache["done"]:
            return cache["parsed"] or {}
        loop = asyncio.new_event_loop()
        try:
            cache["parsed"] = loop.run_until_complete(grade_result(result, user_message))
        finally:
            cache["done"] = True
            loop.close()
        return cache["parsed"] or {}

    def _make_scorer(dim: str) -> ScoreFunc:
        def _fn(result):
            parsed = _ensure_graded(result)
            return _component(parsed, dim)
        return _fn

    for full_name, weight in w.items():
        dim = full_name.split(":", 1)[1] if ":" in full_name else full_name
        scorer.add(full_name, _make_scorer(dim), weight=weight)


__all__ = ["attach_llm_grader", "grade_result", "GRADER_SYSTEM_PROMPT"]
