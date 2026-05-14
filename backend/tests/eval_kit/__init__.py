"""NXT1 eval kit — programmatic builder-quality measurement.

Modelled on chef's `test-kitchen/` but Python/pytest-native and pluggable.

Use cases
=========
  • Regression tracking: run the same fixture tasks across model/prompt
    changes; compare scores.
  • Compare protocols: same fixture run with `?protocol=tag` vs
    `?protocol=json` to validate which wins on tokens & quality.
  • Pre-deploy gate: keep the eval green before flipping defaults.

Layout
======
  fixtures/          → JSON task specs (input, expected criteria)
  runner.py          → exposes `run_fixture()` — invokes the builder pipeline
  scorer.py          → scoring rubrics (structural, validation, keyword)
  __init__.py        → public surface

NOT included today (deferred)
=============================
  • LLM-graded scorer
  • Multi-turn fixtures (one user message → one AI response only for now)
  • Headless preview boot
  • CI integration (run-on-PR)
"""
from .runner import Fixture, FixtureResult, run_fixture, load_fixtures
from .scorer import Scorer, ScoreCard

__all__ = ["Fixture", "FixtureResult", "run_fixture", "load_fixtures",
            "Scorer", "ScoreCard"]
