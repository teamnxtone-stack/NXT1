"""NXT1 — Model Variant Catalogue (Phase 11 W2-A).

This module enriches the bare `ProviderSpec.models` (a list of model IDs) with
UX-shaped metadata (label, tier, badge, context_window, note). The frontend
ModelVariantPicker reads from `GET /api/ai/models` to render fast/balanced/
reasoning groups under each provider so users can intentionally pick a
specialised model variant.

Why a separate module:
  * adapters.py is the *integration* surface (HTTP/SDK code).
  * registry.py is the *routing* surface (decision logic).
  * catalog.py here is the *UX* surface (labels, badges, descriptions).

All catalogues are static + additive. If a model ID is not enriched here,
it still appears via the bare ProviderSpec.models list — just without rich
metadata. So this stays *non-blocking* for the provider pipeline.

Non-negotiable: NO hardcoded API keys. Lookups always go through env vars.
"""
from __future__ import annotations

from typing import Dict, List, Optional


# Each entry shape (all fields optional except id+label+tier):
#   id:             provider's model ID (matches ProviderSpec.models entries)
#   label:          short display label ("Claude Sonnet 4.5")
#   tier:           "fast" | "balanced" | "reasoning" | "coding"
#   badge:          short pill text ("New", "Reasoning", "Fast", "Pro")
#   context:        context window in tokens (None = inherit from ProviderSpec)
#   note:           one-line description for tooltip / picker subtext
#   recommended:    when True, surface as recommended default in the picker
VARIANTS: Dict[str, List[Dict]] = {
    # ---------- OpenAI ----------
    "openai": [
        {"id": "gpt-4.1",     "label": "GPT-4.1",       "tier": "balanced", "badge": "Pro",       "context": 128_000, "note": "Strongest for orchestration and structured outputs.", "recommended": True},
        {"id": "gpt-4o",      "label": "GPT-4o",        "tier": "balanced", "badge": "Vision",    "context": 128_000, "note": "Multimodal flagship with strong reasoning."},
        {"id": "gpt-4o-mini", "label": "GPT-4o mini",   "tier": "fast",     "badge": "Fast",      "context": 128_000, "note": "Speed-optimised for short tasks and routing."},
        {"id": "o4-mini",     "label": "o4-mini",       "tier": "reasoning","badge": "Reasoning", "context": 128_000, "note": "Reasoning-tuned mini model for plan + debug."},
    ],
    # ---------- Anthropic ----------
    "anthropic": [
        {"id": "claude-sonnet-4-5-20250929", "label": "Claude Sonnet 4.5", "tier": "balanced",  "badge": "Pro",       "context": 200_000, "note": "Default flagship for code generation.", "recommended": True},
        {"id": "claude-opus-4-1-20250805",  "label": "Claude Opus 4.1",   "tier": "reasoning", "badge": "Reasoning", "context": 200_000, "note": "Reasoning-heavy work + long-context planning."},
        {"id": "claude-haiku-4-5-20250929", "label": "Claude Haiku 4.5",  "tier": "fast",      "badge": "Fast",      "context": 200_000, "note": "Fast + cheap for narration, routing, and chips."},
    ],
    # ---------- Gemini ----------
    "gemini": [
        {"id": "gemini-2.0-flash",                "label": "Gemini 2.0 Flash",          "tier": "fast",      "badge": "Fast",      "context": 1_048_576, "note": "Ultra-fast multimodal for inference + UX previews.", "recommended": True},
        {"id": "gemini-2.0-flash-thinking-exp",   "label": "Gemini 2.0 Flash Thinking", "tier": "reasoning", "badge": "Reasoning", "context": 1_048_576, "note": "Experimental thinking mode for planner tasks."},
        {"id": "gemini-1.5-pro",                  "label": "Gemini 1.5 Pro",            "tier": "balanced",  "badge": "Vision",    "context": 2_000_000, "note": "Massive context window + vision."},
    ],
    # ---------- Groq ----------
    "groq": [
        {"id": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B",  "tier": "fast", "badge": "Fast", "context": 128_000, "note": "Open weights, blazing-fast inference.", "recommended": True},
        {"id": "llama-3.1-70b-versatile", "label": "Llama 3.1 70B",  "tier": "fast", "badge": "Fast", "context": 128_000, "note": "Reliable Llama 3.1 baseline."},
        {"id": "mixtral-8x7b-32768",      "label": "Mixtral 8x7B",   "tier": "fast", "badge": "MoE",  "context": 32_768,  "note": "Mixture-of-experts at speed."},
    ],
    # ---------- DeepSeek ----------
    "deepseek": [
        {"id": "deepseek-chat",     "label": "DeepSeek Chat",     "tier": "balanced",  "badge": "Coding",    "context": 64_000, "note": "Strong coding model at low cost.", "recommended": True},
        {"id": "deepseek-reasoner", "label": "DeepSeek Reasoner", "tier": "reasoning", "badge": "Reasoning", "context": 64_000, "note": "R1-style chain-of-thought reasoning."},
    ],
    # ---------- xAI / Grok ----------
    "xai": [
        {"id": "grok-4-latest",    "label": "Grok 4",            "tier": "balanced",  "badge": "Pro",       "context": 256_000, "note": "xAI flagship, strong tool-use + reasoning.", "recommended": True},
        {"id": "grok-4-reasoning", "label": "Grok 4 Reasoning",  "tier": "reasoning", "badge": "Reasoning", "context": 256_000, "note": "Reasoning-tuned Grok for planning + debug."},
        {"id": "grok-4-mini",      "label": "Grok 4 mini",       "tier": "fast",      "badge": "Fast",      "context": 128_000, "note": "Speed-optimised for routing + narration."},
    ],
    # ---------- OpenRouter (passthrough) ----------
    "openrouter": [
        {"id": "anthropic/claude-3.5-sonnet", "label": "Claude 3.5 Sonnet (via OR)", "tier": "balanced",  "badge": "Pro",     "context": 200_000, "note": "Anthropic via OpenRouter for unified billing.", "recommended": True},
        {"id": "openai/gpt-4o",              "label": "GPT-4o (via OR)",            "tier": "balanced",  "badge": "Vision", "context": 128_000, "note": "OpenAI flagship via OpenRouter."},
        {"id": "meta-llama/llama-3.1-405b-instruct", "label": "Llama 3.1 405B (via OR)", "tier": "reasoning", "badge": "Reasoning", "context": 32_768, "note": "Open weights, largest tier."},
    ],
    # ---------- Emergent (dev fallback) ----------
    "emergent": [
        {"id": "claude-sonnet-4-5-20250929", "label": "Claude Sonnet 4.5 (managed)", "tier": "balanced",  "badge": "Managed",   "context": 200_000, "note": "NXT1-hosted dev key. Auto-disabled once your provider key is set.", "recommended": True},
        {"id": "gpt-4.1",                    "label": "GPT-4.1 (managed)",          "tier": "balanced",  "badge": "Managed",   "context": 128_000, "note": "Routed through the managed key."},
        {"id": "gemini-2.0-flash",           "label": "Gemini 2.0 Flash (managed)", "tier": "fast",      "badge": "Managed",   "context": 1_048_576, "note": "Routed through the managed key."},
    ],
}


def list_provider_variants(provider_id: str) -> List[Dict]:
    """Return rich variant metadata for a provider id. Empty list if unknown."""
    return [dict(v) for v in VARIANTS.get(provider_id, [])]


def get_variant(provider_id: str, model_id: str) -> Optional[Dict]:
    for v in VARIANTS.get(provider_id, []):
        if v["id"] == model_id:
            return dict(v)
    return None


def merge_into_spec(spec_dict: Dict) -> Dict:
    """Augment a serialised ProviderSpec dict with `model_variants`.

    Spec dicts come from ProviderSpec.to_dict(). This is the canonical way
    routes/ai_meta.py should enrich provider payloads for the UI.
    """
    pid = spec_dict.get("id", "")
    variants = list_provider_variants(pid)
    spec_dict["model_variants"] = variants
    # Surface the recommended default model (if any) so the UI can pre-select.
    rec = next((v["id"] for v in variants if v.get("recommended")), None)
    spec_dict["recommended_model"] = rec or spec_dict.get("default_model")
    return spec_dict
