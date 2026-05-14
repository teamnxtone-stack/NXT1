"""Concrete provider adapters for NXT1.

Each adapter declares its ProviderSpec and implements generate/generate_stream.
Where possible we route through litellm so we get consistent streaming chunk
shape across vendors. Emergent universal key is also wrapped here for parity
with the rest of the registry.
"""
from __future__ import annotations

import logging
import os
from typing import AsyncIterator, Optional

import litellm

# `emergentintegrations` was a proprietary helper that bundled a managed key
# router. We removed it (Phase B.12 cleanup, 2026-05-13) because it's not on
# PyPI — `pip install emergentintegrations==0.1.0` fails on Render/Vercel
# during deploy. The Emergent adapter below now routes via litellm directly,
# using whichever vendor model is requested. The `EMERGENT_LLM_KEY` env var
# still works as a managed-key shortcut when set.

from .base import (
    BaseProvider,
    LatencyTier,
    ProviderAuthError,
    ProviderBadResponse,
    ProviderError,
    ProviderRateLimit,
    ProviderSpec,
    ProviderTimeout,
    ProviderUnavailable,
)

logger = logging.getLogger("nxt1.providers")


def _litellm_params(provider: str, model: str, api_key: str, system: str, user: str) -> dict:
    return {
        "model": f"{provider}/{model}",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "api_key": api_key,
    }


def _map_litellm_error(e: BaseException) -> ProviderError:
    """Convert a litellm/openai SDK exception into our taxonomy."""
    msg = str(e).lower()
    if "401" in msg or "unauthor" in msg or "invalid api key" in msg or "authentication" in msg:
        return ProviderAuthError(str(e))
    if "429" in msg or "rate limit" in msg or "overload" in msg or "quota" in msg:
        return ProviderRateLimit(str(e))
    if "timeout" in msg or "timed out" in msg:
        return ProviderTimeout(str(e))
    if "502" in msg or "503" in msg or "504" in msg or "bad gateway" in msg or "connection" in msg:
        return ProviderUnavailable(str(e))
    return ProviderUnavailable(str(e))


# ============================================================
# OpenAI
# ============================================================
class OpenAIProvider(BaseProvider):
    spec = ProviderSpec(
        id="openai",
        display_name="OpenAI",
        default_model="gpt-4.1",
        models=["gpt-4.1", "gpt-4o", "gpt-4o-mini", "o4-mini"],
        tier=LatencyTier.BALANCED,
        streaming=True,
        json_mode=True,
        supports_vision=True,
        supports_tools=True,
        context_window=128_000,
        requires_env=["OPENAI_API_KEY"],
        tags=["orchestration", "structured-output", "general"],
        failover_targets=["openrouter", "emergent", "anthropic"],
        cost_tier=0.7,
        reliability=0.95,
        note="Strong at structured output and orchestration tasks.",
    )

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        params = _litellm_params("openai", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 32000, "response_format": {"type": "json_object"}})
        try:
            resp = await litellm.acompletion(**params)
            return resp.choices[0].message.content or ""
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        params = _litellm_params("openai", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 32000, "response_format": {"type": "json_object"}, "stream": True})
        try:
            response = litellm.completion(**params)
            for chunk in response:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    yield delta
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)


# ============================================================
# Anthropic
# ============================================================
class AnthropicProvider(BaseProvider):
    spec = ProviderSpec(
        id="anthropic",
        display_name="Anthropic Claude",
        default_model="claude-sonnet-4-5-20250929",
        models=["claude-sonnet-4-5-20250929", "claude-opus-4-1-20250805", "claude-haiku-4-5-20251001"],
        tier=LatencyTier.BALANCED,
        streaming=True,
        json_mode=False,
        supports_vision=True,
        supports_tools=True,
        context_window=200_000,
        requires_env=["ANTHROPIC_API_KEY"],
        tags=["code", "refactor", "long-context", "engineering"],
        failover_targets=["openai", "openrouter", "emergent"],
        cost_tier=0.8,
        reliability=0.95,
        note="Best-in-class for engineering, refactors, and long-context code reasoning.",
    )

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        params = _litellm_params("anthropic", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 12000})
        try:
            resp = await litellm.acompletion(**params)
            return resp.choices[0].message.content or ""
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        params = _litellm_params("anthropic", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 12000, "stream": True})
        try:
            response = litellm.completion(**params)
            for chunk in response:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    yield delta
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)


# ============================================================
# Google Gemini
# ============================================================
class GeminiProvider(BaseProvider):
    spec = ProviderSpec(
        id="gemini",
        display_name="Google Gemini",
        default_model="gemini-2.0-flash",
        models=["gemini-2.0-flash", "gemini-2.0-flash-thinking-exp", "gemini-1.5-pro"],
        tier=LatencyTier.FAST,
        streaming=True,
        json_mode=True,
        supports_vision=True,
        supports_tools=True,
        context_window=1_000_000,
        requires_env=["GEMINI_API_KEY"],
        tags=["fast", "vision", "long-context", "multimodal"],
        failover_targets=["openai", "emergent", "openrouter"],
        cost_tier=0.4,
        reliability=0.9,
        note="Massive context window; strong multimodal. Great for analysis tasks.",
    )

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        params = _litellm_params("gemini", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 16000})
        try:
            resp = await litellm.acompletion(**params)
            return resp.choices[0].message.content or ""
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        params = _litellm_params("gemini", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 16000, "stream": True})
        try:
            response = litellm.completion(**params)
            for chunk in response:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    yield delta
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)


# ============================================================
# Groq (very fast)
# ============================================================
class GroqProvider(BaseProvider):
    spec = ProviderSpec(
        id="groq",
        display_name="Groq",
        default_model="llama-3.3-70b-versatile",
        models=["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "mixtral-8x7b-32768"],
        tier=LatencyTier.FAST,
        streaming=True,
        json_mode=True,
        supports_vision=False,
        supports_tools=True,
        context_window=128_000,
        requires_env=["GROQ_API_KEY"],
        tags=["fast", "narration", "routing"],
        failover_targets=["openai", "openrouter", "emergent"],
        cost_tier=0.2,
        reliability=0.85,
        note="Extremely fast inference. Ideal for narration / quick analyses.",
    )

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        params = _litellm_params("groq", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 8000, "response_format": {"type": "json_object"}})
        try:
            resp = litellm.completion(**params)
            return resp.choices[0].message.content or ""
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        params = _litellm_params("groq", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 8000, "response_format": {"type": "json_object"}, "stream": True})
        try:
            response = litellm.completion(**params)
            for chunk in response:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    yield delta
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)


# ============================================================
# DeepSeek (cost-efficient reasoning)
# ============================================================
class DeepSeekProvider(BaseProvider):
    spec = ProviderSpec(
        id="deepseek",
        display_name="DeepSeek",
        default_model="deepseek-chat",
        models=["deepseek-chat", "deepseek-reasoner"],
        tier=LatencyTier.REASONING,
        streaming=True,
        json_mode=True,
        supports_vision=False,
        supports_tools=False,
        context_window=64_000,
        requires_env=["DEEPSEEK_API_KEY"],
        tags=["reasoning", "cost-efficient", "code"],
        failover_targets=["openrouter", "anthropic", "openai"],
        cost_tier=0.15,
        reliability=0.85,
        note="Strong reasoning at low cost. Good fallback for budget-sensitive tasks.",
    )

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        # litellm routes DeepSeek via the `deepseek/` prefix.
        params = _litellm_params("deepseek", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 8000, "response_format": {"type": "json_object"}})
        try:
            resp = litellm.completion(**params)
            return resp.choices[0].message.content or ""
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        params = _litellm_params("deepseek", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 8000, "response_format": {"type": "json_object"}, "stream": True})
        try:
            response = litellm.completion(**params)
            for chunk in response:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    yield delta
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)


# ============================================================
# OpenRouter (aggregator)
# ============================================================
class OpenRouterProvider(BaseProvider):
    spec = ProviderSpec(
        id="openrouter",
        display_name="OpenRouter",
        default_model="anthropic/claude-3.5-sonnet",
        models=[
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "google/gemini-pro-1.5",
            "meta-llama/llama-3.1-405b-instruct",
            "deepseek/deepseek-chat",
        ],
        tier=LatencyTier.BALANCED,
        streaming=True,
        json_mode=False,
        supports_vision=True,
        supports_tools=True,
        context_window=200_000,
        requires_env=["OPENROUTER_API_KEY"],
        tags=["aggregator", "fallback"],
        failover_targets=["emergent", "openai", "anthropic"],
        cost_tier=0.55,
        reliability=0.85,
        note="Universal fallback aggregator. Routes to any model via single key.",
    )

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        params = _litellm_params("openrouter", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 16000})
        try:
            resp = litellm.completion(**params)
            return resp.choices[0].message.content or ""
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        params = _litellm_params("openrouter", self.model, self.api_key, system_prompt, user_prompt)
        params.update({"max_tokens": 16000, "stream": True})
        try:
            response = litellm.completion(**params)
            for chunk in response:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    yield delta
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)


# ============================================================
# xAI (Grok) — OpenAI-compatible Chat Completions API at api.x.ai/v1
# ============================================================
class XAIProvider(BaseProvider):
    spec = ProviderSpec(
        id="xai",
        display_name="xAI Grok",
        default_model="grok-4-latest",
        # As of late-2025 the public catalogue is grok-4 / grok-4-mini /
        # grok-4-reasoning. We include the marketing-tier alias too.
        models=[
            "grok-4-latest",
            "grok-4",
            "grok-4-reasoning",
            "grok-4-mini",
            "grok-4.20-reasoning",
            "grok-2-1212",
            "grok-beta",
        ],
        tier=LatencyTier.BALANCED,
        streaming=True,
        json_mode=True,
        supports_vision=True,
        supports_tools=True,
        context_window=256_000,
        requires_env=["XAI_API_KEY"],
        tags=["reasoning", "general", "tool-use"],
        failover_targets=["openai", "anthropic", "gemini", "openrouter", "emergent"],
        cost_tier=0.6,
        reliability=0.9,
        note="xAI Grok — large context, strong reasoning. Routed via the OpenAI-compatible api.x.ai/v1 endpoint.",
    )

    # xAI uses an OpenAI-compatible endpoint, so we ride the same litellm path
    # by prefixing the model with `xai/` (litellm provider-prefix) — litellm
    # then targets https://api.x.ai/v1 automatically.

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        params = _litellm_params("xai", self.model, self.api_key, system_prompt, user_prompt)
        params.update({
            "max_tokens": 16000,
            "response_format": {"type": "json_object"},
            "api_base": "https://api.x.ai/v1",
        })
        try:
            resp = litellm.completion(**params)
            return resp.choices[0].message.content or ""
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        params = _litellm_params("xai", self.model, self.api_key, system_prompt, user_prompt)
        params.update({
            "max_tokens": 16000,
            "response_format": {"type": "json_object"},
            "stream": True,
            "api_base": "https://api.x.ai/v1",
        })
        try:
            response = litellm.completion(**params)
            for chunk in response:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    yield delta
        except Exception as e:
            self.mark_error(e)
            raise _map_litellm_error(e)


# ============================================================
# Emergent universal key (universal fallback)
# ============================================================
class EmergentProvider(BaseProvider):
    spec = ProviderSpec(
        id="emergent",
        display_name="Emergent Universal",
        default_model="claude-sonnet-4-5-20250929",
        models=[
            "claude-sonnet-4-5-20250929",
            "claude-haiku-4-5-20251001",
            "gpt-4.1",
            "gpt-4o-mini",
        ],
        tier=LatencyTier.BALANCED,
        streaming=True,
        json_mode=False,
        supports_vision=True,
        supports_tools=False,
        context_window=200_000,
        requires_env=["EMERGENT_LLM_KEY"],
        tags=["fallback", "universal"],
        failover_targets=[],  # terminal fallback
        cost_tier=0.5,
        reliability=0.92,
        note="Universal key fallback. Used when no direct provider keys configured.",
    )

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        """Route via the Emergent universal-key proxy (OpenAI-compatible).

        The proxy at `/llm` accepts the universal key as an OpenAI key and
        forwards to the correct vendor based on the bare model name.
        """
        from services.ai_service import _acomplete
        target = (
            "openai" if (self.model.startswith("gpt") or self.model.startswith("o"))
            else "gemini" if self.model.startswith("gemini")
            else "anthropic"
        )
        try:
            return await _acomplete(
                provider=target,
                model=self.model,
                api_key=self.api_key,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            raise _map_litellm_error(e)

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str):
        from services.ai_service import EmergentProvider as _AISvcEmergent
        provider = _AISvcEmergent(api_key=self.api_key, model=self.model)
        try:
            async for delta in provider.generate_stream(system_prompt, user_prompt, session_id):
                yield delta
        except Exception as e:
            raise _map_litellm_error(e)


# ============================================================
# All adapters (registry uses this)
# ============================================================
ALL_ADAPTERS = [
    OpenAIProvider,
    AnthropicProvider,
    GeminiProvider,
    XAIProvider,
    GroqProvider,
    DeepSeekProvider,
    OpenRouterProvider,
    EmergentProvider,
]
