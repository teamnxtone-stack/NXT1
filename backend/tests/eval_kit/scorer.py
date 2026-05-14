"""Eval-kit scorer — graded rubric for a `FixtureResult`.

Score components (0.0–1.0 each, weighted):
  • completion (0.20)        — did we get a non-error result?
  • validation (0.20)        — static validation passes?
  • paths_present (0.15)     — expected files actually present in output
  • paths_created (0.15)     — expected new files actually created
  • keywords_in_any (0.15)   — every required keyword found in some file
  • max_files_changed (0.05) — didn't go nuts touching unrelated files
  • explanation_present (0.05) — assistant emitted an explanation
  • notes_or_clean (0.05)    — either useful notes OR no warnings

Aggregate score = weighted average. Pass threshold defaults to 0.7.

Scorers compose. A future LLM-graded scorer can be plugged via `Scorer.add`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

from .runner import FixtureResult


@dataclass
class ScoreCard:
    fixture_id: str
    components: Dict[str, float] = field(default_factory=dict)
    weights: Dict[str, float] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)

    @property
    def aggregate(self) -> float:
        if not self.components:
            return 0.0
        total_w = sum(self.weights.get(k, 1.0) for k in self.components)
        if total_w <= 0:
            return 0.0
        s = sum(self.components[k] * self.weights.get(k, 1.0)
                for k in self.components)
        return round(s / total_w, 4)

    def passed(self, threshold: float = 0.7) -> bool:
        return self.aggregate >= threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "aggregate": self.aggregate,
            "passed": self.passed(),
            "components": dict(self.components),
            "weights": dict(self.weights),
            "issues": list(self.issues),
        }


WEIGHTS_DEFAULT: Dict[str, float] = {
    "completion": 0.20,
    "validation": 0.20,
    "paths_present": 0.15,
    "paths_created": 0.15,
    "keywords_in_any": 0.15,
    "max_files_changed": 0.05,
    "explanation_present": 0.05,
    "notes_or_clean": 0.05,
}


ScoreFunc = Callable[[FixtureResult], Tuple[float, List[str]]]


class Scorer:
    def __init__(self, weights: Dict[str, float] | None = None):
        self.weights = dict(weights or WEIGHTS_DEFAULT)
        self._extra: List[Tuple[str, ScoreFunc, float]] = []

    def add(self, name: str, fn: ScoreFunc, weight: float = 0.1) -> None:
        """Add a custom score component."""
        self._extra.append((name, fn, weight))
        self.weights[name] = weight

    def score(self, result: FixtureResult, expected: Dict[str, Any]) -> ScoreCard:
        card = ScoreCard(fixture_id=result.fixture_id, weights=dict(self.weights))

        # completion
        if result.success:
            card.components["completion"] = 1.0
        else:
            card.components["completion"] = 0.0
            card.issues.append(f"completion: failed ({result.error or 'no done event'})")

        # validation
        v = result.validation or {}
        if v.get("error_count", 0) == 0:
            card.components["validation"] = 1.0
        else:
            card.components["validation"] = 0.0
            card.issues.append(
                f"validation: {v['error_count']} static error(s) — "
                f"{[i['message'] for i in v.get('issues', [])[:3]]}"
            )

        # path checks
        paths_present = expected.get("paths_present") or []
        if paths_present:
            file_paths = {f["path"] for f in result.files}
            hit = sum(1 for p in paths_present if p in file_paths)
            card.components["paths_present"] = hit / len(paths_present)
            if hit < len(paths_present):
                missing = [p for p in paths_present if p not in file_paths]
                card.issues.append(f"paths_present: missing {missing}")
        else:
            card.components["paths_present"] = 1.0

        paths_created = expected.get("paths_created") or []
        if paths_created:
            changed = set(result.paths_changed)
            hit = sum(1 for p in paths_created if p in changed)
            card.components["paths_created"] = hit / len(paths_created)
            if hit < len(paths_created):
                missing = [p for p in paths_created if p not in changed]
                card.issues.append(f"paths_created: missing {missing}")
        else:
            card.components["paths_created"] = 1.0

        keywords = expected.get("keywords_in_any") or []
        if keywords:
            blob = " ".join(f.get("content", "") for f in result.files)
            hit = sum(1 for k in keywords if k.lower() in blob.lower())
            card.components["keywords_in_any"] = hit / len(keywords)
            if hit < len(keywords):
                missing = [k for k in keywords if k.lower() not in blob.lower()]
                card.issues.append(f"keywords_in_any: missing {missing}")
        else:
            card.components["keywords_in_any"] = 1.0

        max_files = expected.get("max_files_changed")
        if max_files is not None:
            n = len(result.paths_changed)
            if n <= max_files:
                card.components["max_files_changed"] = 1.0
            else:
                # Linear penalty above the limit, floor at 0
                card.components["max_files_changed"] = max(0.0,
                    1.0 - (n - max_files) / max_files)
                card.issues.append(f"max_files_changed: changed {n} > {max_files}")
        else:
            card.components["max_files_changed"] = 1.0

        card.components["explanation_present"] = 1.0 if (result.explanation or "").strip() else 0.0
        # notes_or_clean: pass if there's a meaningful notes string OR no warns
        warn_count = v.get("warn_count", 0)
        card.components["notes_or_clean"] = 1.0 if ((result.notes or "").strip() or warn_count == 0) else 0.0

        # Extra scorers
        for name, fn, _w in self._extra:
            try:
                val, msgs = fn(result)
                card.components[name] = max(0.0, min(1.0, float(val)))
                card.issues.extend(msgs or [])
            except Exception as e:
                card.components[name] = 0.0
                card.issues.append(f"{name}: scorer raised {e}")
        return card


__all__ = ["Scorer", "ScoreCard", "WEIGHTS_DEFAULT"]
