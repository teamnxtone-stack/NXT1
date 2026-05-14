"""Provider Registry + Routing engine.

The registry is the single entry point for ai_service / routes / agents to
resolve a provider. It handles:
  - reading env vars to determine availability
  - building a failover chain based on ProviderSpec metadata
  - tier-based routing for "auto" mode
  - explicit user/project selection in "manual" mode
  - tracking last-error timestamps per provider id

Routing decision flow (see `route`):
  1. routing_mode == "manual" AND explicit_provider available
     → return that provider (+ model)
  2. routing_mode == "auto":
     - pick by tier + task hints
     - else default by task
     - else first-available in priority order
  3. Build failover chain from spec.failover_targets filtered by availability.

Failover is handled by the caller via `try_chain(intent)` which yields
providers one at a time so generation can be retried under the same prompt.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, Iterator, List, Optional

from .adapters import ALL_ADAPTERS
from .base import (
    BaseProvider,
    LatencyTier,
    ProviderError,
    ProviderSpec,
    ProviderUnavailable,
    RouteIntent,
)

logger = logging.getLogger("nxt1.providers.registry")


# ─── Env-var aliases ────────────────────────────────────────────────────────
# Some providers ship multiple commonly-used env var names. We accept all of
# them and copy the alias into the canonical name at import time so the rest
# of the registry only has to check one variable per provider.
# Primary (canonical) → list of accepted aliases.
ENV_ALIASES = {
    "GEMINI_API_KEY":     ["GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY"],
    "XAI_API_KEY":        ["GROK_API_KEY", "XAI_GROK_API_KEY"],
    "ANTHROPIC_API_KEY":  ["CLAUDE_API_KEY"],
    "OPENAI_API_KEY":     [],
    "DEEPSEEK_API_KEY":   [],
    "OPENROUTER_API_KEY": [],
    "GROQ_API_KEY":       [],
    "EMERGENT_LLM_KEY":   ["EMERGENT_LLM_API_KEY"],
}


def _hydrate_env_aliases():
    """Copy alias env vars onto the canonical name once at startup so the
    rest of the registry can do a simple `os.environ.get(canonical)` check.
    This keeps the export-to-GitHub path simple: only the canonical names
    are documented; aliases are accepted for convenience."""
    for canonical, aliases in ENV_ALIASES.items():
        if os.environ.get(canonical):
            continue
        for alias in aliases:
            val = os.environ.get(alias)
            if val:
                os.environ[canonical] = val
                logger.info(f"env alias: copied {alias} → {canonical}")
                break


_hydrate_env_aliases()


# Phase B.9 (2026-05-13) — Auto-set preferred provider on boot when the user
# has configured exactly one real provider key. Skipping if AI_PROVIDER is
# already set (user override), or if the only available provider is
# `emergent` (the managed fallback — we want it usable but not "preferred").
#
# When the user later deploys to their own infra and drops in only their
# GEMINI_API_KEY (or XAI_API_KEY / ANTHROPIC_API_KEY / etc.), NXT1 will pick
# that provider automatically without requiring AI_PROVIDER to be set.
def _auto_set_preferred_provider() -> None:
    if os.environ.get("AI_PROVIDER"):
        return  # explicit user override wins
    env_to_provider = {
        "OPENAI_API_KEY":     "openai",
        "ANTHROPIC_API_KEY":  "anthropic",
        "GEMINI_API_KEY":     "gemini",
        "XAI_API_KEY":        "xai",
        "GROQ_API_KEY":       "groq",
        "DEEPSEEK_API_KEY":   "deepseek",
        "OPENROUTER_API_KEY": "openrouter",
    }
    available = [pid for env, pid in env_to_provider.items() if os.environ.get(env)]
    pref_order = ["anthropic", "openai", "xai", "gemini", "openrouter", "groq", "deepseek"]
    pick: Optional[str] = next((p for p in pref_order if p in available), None)
    if pick:
        os.environ["AI_PROVIDER"] = pick
        logger.info(f"AI_PROVIDER auto-set to {pick!r} (first available real provider key on boot)")
    else:
        logger.info("AI_PROVIDER not auto-set: no first-party provider keys configured")


_auto_set_preferred_provider()


# Priority order when auto-routing with no other signal. Tuned for code
# generation as the primary task in NXT1. xAI/Grok now first-class.
DEFAULT_PRIORITY = ["anthropic", "openai", "xai", "gemini", "emergent", "openrouter", "groq", "deepseek"]

# Task → preferred provider id list. First available wins.
TASK_PRIORITY: Dict[str, List[str]] = {
    "code-generation": ["anthropic", "openai", "xai", "emergent", "openrouter", "deepseek"],
    "architecture":    ["anthropic", "openai", "xai", "emergent", "openrouter"],
    "debug":           ["anthropic", "openai", "xai", "emergent", "deepseek"],
    "refactor":        ["anthropic", "openai", "xai", "emergent", "deepseek"],
    "orchestration":   ["openai", "anthropic", "xai", "emergent", "openrouter"],
    "product-plan":    ["openai", "anthropic", "xai", "emergent"],
    "route-page":      ["openai", "anthropic", "emergent"],
    "scaffold":        ["openai", "anthropic", "emergent"],
    "agent-router":    ["openai", "anthropic", "xai", "emergent", "groq"],
    "narration":       ["groq", "gemini", "openai", "anthropic", "emergent"],
    "inference":       ["groq", "gemini", "openai", "emergent"],
    "devops":          ["openai", "anthropic", "xai", "emergent"],
}

# Tier → preferred provider id list. Used when intent.tier is set.
TIER_PRIORITY: Dict[LatencyTier, List[str]] = {
    LatencyTier.FAST:      ["groq", "gemini", "openai", "emergent"],
    LatencyTier.BALANCED:  ["anthropic", "openai", "xai", "gemini", "emergent", "openrouter"],
    LatencyTier.REASONING: ["anthropic", "xai", "deepseek", "openai", "emergent"],
}


class ProviderRegistry:
    def __init__(self):
        # adapter_class.spec.id → adapter class
        self._adapters_by_id = {cls.spec.id: cls for cls in ALL_ADAPTERS}
        # Last error timestamps (set by failover loop) so we deprioritise
        # recently-failed providers within a short window.
        self._error_at: Dict[str, float] = {}

    # ----- spec/availability surface -----
    def list_specs(self) -> List[ProviderSpec]:
        return [cls.spec for cls in ALL_ADAPTERS]

    def available(self) -> List[str]:
        out = []
        for cls in ALL_ADAPTERS:
            if self._has_env(cls.spec.requires_env):
                out.append(cls.spec.id)
        return out

    def _has_env(self, keys: List[str]) -> bool:
        return all(bool((os.environ.get(k) or "").strip()) for k in keys)

    def health_status(self) -> dict:
        avail = set(self.available())
        items = []
        for spec in self.list_specs():
            items.append({
                **spec.to_dict(),
                "available": spec.id in avail,
                "last_error_at": self._error_at.get(spec.id),
            })
        return {"providers": items, "available": list(avail)}

    def mark_error(self, provider_id: str) -> None:
        self._error_at[provider_id] = time.time()

    # ----- resolution -----
    def get(self, provider_id: str, model: Optional[str] = None) -> BaseProvider:
        cls = self._adapters_by_id.get(provider_id)
        if not cls:
            raise ProviderUnavailable(f"Unknown provider '{provider_id}'")
        # Pull env key. requires_env[0] is the primary key for all current adapters.
        env_key = cls.spec.requires_env[0] if cls.spec.requires_env else ""
        api_key = (os.environ.get(env_key) or "").strip()
        if not api_key:
            raise ProviderUnavailable(f"Provider '{provider_id}' not configured ({env_key} missing)")
        return cls(api_key=api_key, model=model)

    def _first_available(self, ids: List[str]) -> Optional[str]:
        avail = set(self.available())
        for pid in ids:
            if pid in avail:
                return pid
        return None

    # ----- routing -----
    def resolve(self, intent: RouteIntent) -> BaseProvider:
        """Resolve a SINGLE provider for this intent. Does NOT do failover — use
        try_chain() for that. This returns the highest-priority available
        provider, raising ProviderUnavailable if nothing is configured.
        """
        pid = self._pick(intent)
        if not pid:
            raise ProviderUnavailable(
                "No AI provider is configured. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, "
                "GEMINI_API_KEY, GROQ_API_KEY, DEEPSEEK_API_KEY, OPENROUTER_API_KEY, "
                "or EMERGENT_LLM_KEY."
            )
        return self.get(pid, intent.explicit_model)

    def _pick(self, intent: RouteIntent) -> Optional[str]:
        # 1. Manual override
        if intent.routing_mode == "manual" and intent.explicit_provider:
            avail = set(self.available())
            if intent.explicit_provider in avail:
                return intent.explicit_provider
            # Manual but not configured — fall through to auto with the
            # explicit provider as the *first* preference.
            ranked = [intent.explicit_provider] + DEFAULT_PRIORITY
            return self._first_available(ranked)

        # 2. Auto: tier-first
        if intent.tier:
            tier_pref = TIER_PRIORITY.get(intent.tier, [])
            pid = self._first_available(tier_pref)
            if pid:
                return pid

        # 3. Auto: task-first
        if intent.task:
            task_pref = TASK_PRIORITY.get(intent.task, [])
            pid = self._first_available(task_pref)
            if pid:
                return pid

        # 4. Explicit-as-hint (auto with hint)
        if intent.explicit_provider:
            ranked = [intent.explicit_provider] + DEFAULT_PRIORITY
            return self._first_available(ranked)

        # 5. Plain default priority
        return self._first_available(DEFAULT_PRIORITY)

    def try_chain(self, intent: RouteIntent) -> Iterator[BaseProvider]:
        """Yield providers in failover order for this intent.

        Caller is expected to wrap each provider call in try/except and
        invoke `registry.mark_error(pid)` on ProviderError before moving to
        the next one.
        """
        # Build chain: primary + spec.failover_targets + DEFAULT_PRIORITY tail.
        seen = set()
        primary_pid = self._pick(intent)
        chain: List[str] = []
        if primary_pid:
            chain.append(primary_pid)
        if primary_pid and primary_pid in self._adapters_by_id:
            for t in self._adapters_by_id[primary_pid].spec.failover_targets:
                if t not in chain:
                    chain.append(t)
        for t in DEFAULT_PRIORITY:
            if t not in chain:
                chain.append(t)
        # Filter to available
        avail = set(self.available())
        for pid in chain:
            if pid in seen or pid not in avail:
                continue
            seen.add(pid)
            try:
                yield self.get(pid, intent.explicit_model if pid == primary_pid else None)
            except ProviderError as e:
                logger.warning(f"registry.try_chain: skip {pid} ({e})")
                self.mark_error(pid)
                continue


# Singleton
registry = ProviderRegistry()


def route(intent: RouteIntent) -> BaseProvider:
    """Top-level convenience: resolve a single provider for an intent.
    Equivalent to `registry.resolve(intent)`.
    """
    return registry.resolve(intent)
