"""NXT1 — Task-typed Provider Routing (Phase 11 W4 — Track 7).

Layered on top of `services.providers.registry` to map *task types* to the
best provider+model variant for the job. Today the registry's RouteIntent
only knows about latency tier (fast/balanced/reasoning). This module adds
a semantic dimension:

    task_type   →   tier preference   +   provider preference   +   model variant hint

So when the orchestrator dispatches a planner task it picks the strongest
reasoning model; a builder task picks a coding-tuned model; a UI-copy task
picks a fast/cheap model; etc.

The mapping is intentionally additive — when a task type isn't mapped, we
fall back to the existing `pick_provider(intent)` behaviour.

Public API:
    suggest_for_task(task_type)             -> dict { provider_id, model, tier, reason }
    available_for_task(task_type)           -> list[dict] of fallbacks in priority order

Task vocabulary (extend freely):
    architecture-plan     planner agent
    code-generation       builder agent — primary build path
    code-edit             builder agent — incremental edit
    build-repair          fix failing builds, dependency resolution
    debugging             runtime/lint error triage
    ui-copy               marketing copy / labels / placeholders
    ui-design             tailwind / shadcn surface generation
    deployment-error      analyse build/deploy logs
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .registry import registry as provider_registry, RouteIntent
from .base import ProviderError
from .catalog import list_provider_variants

logger = logging.getLogger("nxt1.providers.tasks")


# ----------------------------------------------------------------------
# Mapping table — easy to tune by hand or override per project later.
#
# Each entry shape:
#   tier:          preferred latency tier (fast | balanced | reasoning)
#   providers:     preferred provider order; first available wins
#   model_pref:    list of (provider_id, model_id_substring) hints that
#                  bias model variant selection. First match wins.
#   reason:        short human-readable rationale surfaced to the UI/CLI
# ----------------------------------------------------------------------
TASK_ROUTING: Dict[str, Dict] = {
    "architecture-plan": {
        "tier":      "reasoning",
        "providers": ["anthropic", "openai", "deepseek", "emergent"],
        "model_pref": [
            ("anthropic", "opus"),         # Claude Opus 4.1 — deep planning
            ("deepseek",  "reasoner"),     # R1-style reasoning
            ("openai",    "o4-mini"),
        ],
        "reason": "Reasoning-tuned models plan multi-step architectures best.",
    },
    "code-generation": {
        "tier":      "balanced",
        "providers": ["anthropic", "openai", "deepseek", "emergent"],
        "model_pref": [
            ("anthropic", "sonnet"),       # Claude Sonnet 4.5 — strongest coder
            ("deepseek",  "chat"),         # coding-tuned, low cost
            ("openai",    "gpt-4.1"),
        ],
        "reason": "Code-strong models with balanced latency for primary builds.",
    },
    "code-edit": {
        "tier":      "balanced",
        "providers": ["anthropic", "openai", "deepseek", "emergent"],
        "model_pref": [
            ("anthropic", "sonnet"),
            ("deepseek",  "chat"),
            ("openai",    "gpt-4.1"),
        ],
        "reason": "Same tier as generation — incremental edits stay on the strong coder.",
    },
    "build-repair": {
        "tier":      "reasoning",
        "providers": ["anthropic", "openai", "deepseek", "emergent"],
        "model_pref": [
            ("anthropic", "opus"),
            ("deepseek",  "reasoner"),
            ("openai",    "o4-mini"),
        ],
        "reason": "Reasoning models triage build/dep errors more reliably.",
    },
    "debugging": {
        "tier":      "reasoning",
        "providers": ["anthropic", "deepseek", "openai", "emergent"],
        "model_pref": [
            ("anthropic", "opus"),
            ("deepseek",  "reasoner"),
            ("openai",    "o4-mini"),
        ],
        "reason": "Reasoning over stack traces + repo context.",
    },
    "ui-copy": {
        "tier":      "fast",
        "providers": ["groq", "anthropic", "gemini", "openai", "emergent"],
        "model_pref": [
            ("anthropic", "haiku"),        # Claude Haiku — fast + on-brand
            ("groq",      "llama"),
            ("gemini",    "flash"),
            ("openai",    "gpt-4o-mini"),
        ],
        "reason": "Short marketing copy benefits from fast/cheap models.",
    },
    "ui-design": {
        "tier":      "balanced",
        "providers": ["anthropic", "openai", "emergent"],
        "model_pref": [
            ("anthropic", "sonnet"),
            ("openai",    "gpt-4.1"),
        ],
        "reason": "Balanced models produce the best Tailwind/Shadcn surfaces.",
    },
    "deployment-error": {
        "tier":      "reasoning",
        "providers": ["anthropic", "deepseek", "openai", "emergent"],
        "model_pref": [
            ("anthropic", "opus"),
            ("deepseek",  "reasoner"),
            ("openai",    "o4-mini"),
        ],
        "reason": "Deploy/log triage benefits from reasoning models.",
    },
}


def _first_model_for(provider_id: str, hints: List) -> Optional[str]:
    """Pick the first variant whose id contains one of the hint substrings
    matching the given provider. Falls back to provider's default model
    when no hint matches.
    """
    variants = list_provider_variants(provider_id)
    if not variants:
        return None
    # honour hints (provider_id, substring)
    for hp, sub in hints:
        if hp != provider_id:
            continue
        for v in variants:
            if sub in v.get("id", ""):
                return v["id"]
    # honour the recommended flag
    rec = next((v["id"] for v in variants if v.get("recommended")), None)
    return rec or variants[0]["id"]


def _family_for_model(model: Optional[str]) -> Optional[str]:
    """Derive the underlying provider family from a model id, so the UI can
    show 'anthropic / claude-sonnet-4.5 (via emergent)' instead of just
    'emergent'. The Emergent universal-key is a *transport* — the actual
    model still belongs to anthropic / openai / gemini / xai / etc.
    """
    if not model:
        return None
    m = model.lower()
    if "claude" in m or "haiku" in m or "sonnet" in m or "opus" in m:
        return "anthropic"
    if m.startswith("gpt") or "o4" in m or "o3" in m or m.startswith("text-") or m.startswith("dall-e"):
        return "openai"
    if "gemini" in m or m.startswith("imagen") or "gemma" in m:
        return "gemini"
    if "grok" in m:
        return "xai"
    if "llama" in m or "mixtral" in m:
        return "groq"
    if "deepseek" in m:
        return "deepseek"
    return None


def suggest_for_task(task_type: str) -> Dict:
    """Return a routing suggestion {provider_id, model, tier, reason}
    for a task type. Falls back gracefully to whatever provider is
    available when the mapping has no match.
    """
    mapping = TASK_ROUTING.get(task_type)
    available = set(provider_registry.available())

    def _resolve_any(tier: str) -> Optional[str]:
        try:
            p = provider_registry.resolve(RouteIntent(task=task_type, tier=tier))
            # BaseProvider exposes its spec at .spec or its id at .id directly.
            return getattr(p, "id", None) or getattr(getattr(p, "spec", None), "id", None)
        except ProviderError:
            return None

    if not mapping:
        pid = _resolve_any("balanced")
        if not pid:
            return {"provider_id": None, "model": None, "tier": "balanced",
                    "model_family": None, "transport": None,
                    "reason": "No providers available."}
        model = _first_model_for(pid, [])
        family = _family_for_model(model) or pid
        return {
            "provider_id": family,
            "transport":   pid,
            "model":       model,
            "model_family": family,
            "tier":        "balanced",
            "reason":      "Default balanced routing.",
        }

    for pid in mapping["providers"]:
        if pid not in available:
            continue
        model = _first_model_for(pid, mapping.get("model_pref", []))
        family = _family_for_model(model) or pid
        return {
            "provider_id": family,
            "transport":   pid,
            "model":       model,
            "model_family": family,
            "tier":        mapping["tier"],
            "reason":      mapping["reason"],
        }

    pid = _resolve_any(mapping["tier"])
    model = _first_model_for(pid, mapping.get("model_pref", [])) if pid else None
    family = _family_for_model(model) or pid
    return {
        "provider_id": family,
        "transport":   pid,
        "model":       model,
        "model_family": family,
        "tier":        mapping["tier"],
        "reason":      f"Fallback: preferred providers unavailable. ({mapping['reason']})",
    }


def available_for_task(task_type: str) -> List[Dict]:
    """Return ALL providers a task could fall back to (in priority order)."""
    mapping = TASK_ROUTING.get(task_type) or {}
    specs   = {s.id: s for s in provider_registry.list_specs()}
    available = set(provider_registry.available())
    providers = mapping.get("providers") or list(specs.keys())
    out = []
    for pid in providers:
        spec = specs.get(pid)
        if not spec:
            continue
        out.append({
            "provider_id": pid,
            "available":   pid in available,
            "model":       _first_model_for(pid, mapping.get("model_pref", [])),
            "tier":        mapping.get("tier") or (spec.tier.value if hasattr(spec, "tier") else None),
        })
    return out


def task_routing_table() -> Dict[str, Dict]:
    """Return the full task routing table — useful for /api/ai/task-routing."""
    return {k: dict(v) for k, v in TASK_ROUTING.items()}
