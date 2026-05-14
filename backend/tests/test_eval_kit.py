"""Pytest harness for the NXT1 eval-kit.

Skips automatically if no LLM provider is configured (no key in env). This
lets the harness live in CI without requiring secrets — engineers run it
locally with a key set to grade real builder output.

Usage:
    cd /app/backend
    pytest tests/test_eval_kit.py -v
"""
from __future__ import annotations

import asyncio
import pytest

from tests.eval_kit import (
    Scorer,
    load_fixtures,
    run_fixture,
)
from tests.eval_kit.runner import has_provider_configured


def _all_fixtures():
    return load_fixtures()


def test_eval_kit_loads_fixtures():
    """Sanity: at least one fixture file is present and parses."""
    fixtures = _all_fixtures()
    assert fixtures, "Expected at least one fixture JSON in eval_kit/fixtures/"
    ids = {f.id for f in fixtures}
    # Original starter fixtures
    assert "blank-pricing-page" in ids
    assert "edit-hero-title" in ids
    # P1 expansion (2026-05-13)
    assert "crud-todos-page" in ids
    assert "dark-mode-toggle" in ids
    assert "env-var-wiring" in ids


def test_fixture_shapes_are_valid():
    """Each fixture should have the keys the scorer + runner need."""
    for fx in _all_fixtures():
        assert fx.id and isinstance(fx.id, str)
        assert fx.user_message and isinstance(fx.user_message, str)
        assert fx.protocol in {"tag", "json", "auto"}
        assert isinstance(fx.starting_files, list)
        assert isinstance(fx.expected, dict)
        # Every expected key the scorer cares about must be a known shape
        for k in fx.expected.keys():
            assert k in {
                "paths_present", "paths_created", "keywords_in_any",
                "no_validation_errors", "max_files_changed",
            }, f"{fx.id}: unknown expected key '{k}'"


def test_scorer_handles_empty_result():
    """The scorer should never crash on a degenerate result."""
    from tests.eval_kit.runner import FixtureResult

    res = FixtureResult(fixture_id="empty", protocol_used="json", success=False,
                         error="no provider configured")
    card = Scorer().score(res, expected={"keywords_in_any": ["x"]})
    assert 0.0 <= card.aggregate <= 1.0
    assert not card.passed()
    assert "completion" in card.components
    assert "validation" in card.components


@pytest.mark.skipif(not has_provider_configured(),
                    reason="No LLM provider configured — eval requires real key")
@pytest.mark.slow
@pytest.mark.parametrize("fixture", _all_fixtures(), ids=lambda f: f.id)
def test_fixture(fixture):
    """Run the builder pipeline against each fixture and score the result."""
    result = asyncio.get_event_loop().run_until_complete(run_fixture(fixture))
    card = Scorer().score(result, expected=fixture.expected)
    # Print summary to pytest output so engineers see scores even on pass
    print(f"\n=== {fixture.id} ({result.protocol_used}) "
          f"aggregate={card.aggregate} passed={card.passed()}")
    if card.issues:
        for issue in card.issues:
            print(f"  - {issue}")
    if not card.passed():
        pytest.fail(f"Fixture {fixture.id} scored {card.aggregate} (<0.7). "
                    f"Issues: {card.issues}")
