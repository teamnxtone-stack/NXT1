"""Tests for the provider registry's env-alias hydration + auto-preferred-on-boot.

Phase B.9 (2026-05-13) — when the user drops in only their GEMINI_API_KEY
(or XAI / Anthropic / etc.) on Render, NXT1 should pick that provider
automatically. AI_PROVIDER as an explicit override always wins.
"""
from __future__ import annotations

import importlib
import os

import pytest


def _reload_registry():
    """Force a fresh import of the registry so module-level boot logic runs
    against the current os.environ."""
    import services.providers.registry  # noqa: F401  (ensure first import)
    import sys
    mod_name = "services.providers.registry"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


@pytest.fixture(autouse=True)
def _restore_env():
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


def _purge_provider_keys():
    for k in (
        "AI_PROVIDER",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
        "XAI_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY", "GOOGLE_API_KEY", "GROK_API_KEY",
        "CLAUDE_API_KEY", "GOOGLE_GEMINI_API_KEY",
        "EMERGENT_LLM_KEY", "EMERGENT_LLM_API_KEY",
    ):
        os.environ.pop(k, None)


def test_no_keys_means_no_auto_preference():
    _purge_provider_keys()
    _reload_registry()
    assert "AI_PROVIDER" not in os.environ


def test_emergent_only_does_not_auto_set():
    """Emergent is the dev fallback — having ONLY it set should not
    cause AI_PROVIDER to flip to 'emergent'. Auto-routing already
    handles that case."""
    _purge_provider_keys()
    os.environ["EMERGENT_LLM_KEY"] = "xx"
    _reload_registry()
    assert os.environ.get("AI_PROVIDER") in (None, "")


def test_only_gemini_picks_gemini():
    _purge_provider_keys()
    os.environ["GEMINI_API_KEY"] = "g-test"
    _reload_registry()
    assert os.environ["AI_PROVIDER"] == "gemini"


def test_only_xai_picks_xai():
    _purge_provider_keys()
    os.environ["XAI_API_KEY"] = "x-test"
    _reload_registry()
    assert os.environ["AI_PROVIDER"] == "xai"


def test_only_anthropic_picks_anthropic():
    _purge_provider_keys()
    os.environ["ANTHROPIC_API_KEY"] = "a-test"
    _reload_registry()
    assert os.environ["AI_PROVIDER"] == "anthropic"


def test_multi_provider_prefers_anthropic_first():
    """Anthropic is the configured top-of-priority for code generation."""
    _purge_provider_keys()
    os.environ["DEEPSEEK_API_KEY"] = "d"
    os.environ["GEMINI_API_KEY"] = "g"
    os.environ["ANTHROPIC_API_KEY"] = "a"
    _reload_registry()
    assert os.environ["AI_PROVIDER"] == "anthropic"


def test_explicit_ai_provider_is_honoured():
    _purge_provider_keys()
    os.environ["AI_PROVIDER"] = "gemini"
    os.environ["ANTHROPIC_API_KEY"] = "a"
    _reload_registry()
    # User override must win even though anthropic outranks gemini.
    assert os.environ["AI_PROVIDER"] == "gemini"


def test_google_alias_hydrates_to_gemini():
    _purge_provider_keys()
    os.environ["GOOGLE_API_KEY"] = "g-alias"
    _reload_registry()
    assert os.environ["GEMINI_API_KEY"] == "g-alias"
    # And auto-pref should pick gemini once the alias is hydrated.
    assert os.environ["AI_PROVIDER"] == "gemini"


def test_grok_alias_hydrates_to_xai():
    _purge_provider_keys()
    os.environ["GROK_API_KEY"] = "x-alias"
    _reload_registry()
    assert os.environ["XAI_API_KEY"] == "x-alias"
    assert os.environ["AI_PROVIDER"] == "xai"
