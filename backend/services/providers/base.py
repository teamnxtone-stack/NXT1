"""Provider OS — base interfaces, metadata, and error taxonomy.

All adapters inherit BaseProvider and expose a ProviderSpec. The registry
uses ProviderSpec to make routing decisions without instantiating a provider
until it's actually needed.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Awaitable, Callable, List, Optional


# ---------- Error taxonomy ----------
class ProviderError(Exception):
    """Base provider error. Subclasses let the routing layer decide whether
    to retry, fail over, or surface to the user."""


class ProviderAuthError(ProviderError):
    """Provider rejected the API key. Never retry; never fail over to the
    same key."""


class ProviderTimeout(ProviderError):
    """Provider exceeded the configured timeout. Eligible for retry/failover."""


class ProviderRateLimit(ProviderError):
    """Provider returned 429 / overloaded. Eligible for retry/failover with
    backoff."""


class ProviderUnavailable(ProviderError):
    """Provider returned 5xx / network error / not configured. Eligible for
    failover to next chain entry."""


class ProviderBadResponse(ProviderError):
    """Provider returned a malformed/unparseable response (e.g. invalid JSON
    after retries). Caller should surface to user with raw preview."""


# ---------- Tier metadata ----------
class LatencyTier(str, Enum):
    FAST = "fast"          # ≤ 1s preferred (Groq, Haiku, gpt-4o-mini)
    BALANCED = "balanced"  # 1-5s typical (Sonnet, GPT-4.1, Gemini Flash)
    REASONING = "reasoning"  # multi-step / long-context (Opus, o1, R1)


# ---------- Spec ----------
@dataclass(frozen=True)
class ProviderSpec:
    """Static, declarative metadata about a provider.

    The registry uses this to:
      - render the UI model picker
      - route by tier / capability
      - build failover chains by similarity

    No runtime state lives here — health/availability is computed by the
    registry from env config and recent errors.
    """
    id: str                                 # "openai" / "anthropic" / "gemini" / ...
    display_name: str                       # "OpenAI"
    default_model: str                      # e.g. "gpt-4.1"
    models: List[str] = field(default_factory=list)
    tier: LatencyTier = LatencyTier.BALANCED
    streaming: bool = True
    json_mode: bool = True
    supports_vision: bool = False
    supports_tools: bool = False
    context_window: int = 128_000
    requires_env: List[str] = field(default_factory=list)  # e.g. ["OPENAI_API_KEY"]
    tags: List[str] = field(default_factory=list)          # ["code", "orchestration", ...]
    # Sensible failover targets (provider ids) when this provider errors.
    # The registry filters these by availability at routing time.
    failover_targets: List[str] = field(default_factory=list)
    # Cost tier placeholder — 0.0 (free/local) … 1.0 (premium).
    cost_tier: float = 0.5
    # Reliability hint — used by tie-breaks in failover chains.
    reliability: float = 0.9
    # Human-readable note (shown in tooltips / admin panels).
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "default_model": self.default_model,
            "models": list(self.models),
            "tier": self.tier.value,
            "streaming": self.streaming,
            "json_mode": self.json_mode,
            "supports_vision": self.supports_vision,
            "supports_tools": self.supports_tools,
            "context_window": self.context_window,
            "requires_env": list(self.requires_env),
            "tags": list(self.tags),
            "failover_targets": list(self.failover_targets),
            "cost_tier": self.cost_tier,
            "reliability": self.reliability,
            "note": self.note,
        }


# ---------- Base provider ----------
class BaseProvider:
    """Abstract base for every LLM adapter.

    Adapters must implement `generate` and `generate_stream`. The default
    `generate_stream` falls back to `generate` and yields the result as a
    single chunk so consumers always work regardless of upstream support.
    """
    spec: ProviderSpec

    def __init__(self, api_key: str, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model or self.spec.default_model
        self._last_error_at: Optional[float] = None
        self._last_error: Optional[str] = None

    @property
    def name(self) -> str:
        return self.spec.id

    def mark_error(self, err: BaseException) -> None:
        self._last_error_at = time.time()
        self._last_error = f"{type(err).__name__}: {err}"[:240]

    def health(self) -> dict:
        return {
            "id": self.spec.id,
            "model": self.model,
            "last_error_at": self._last_error_at,
            "last_error": self._last_error,
        }

    async def generate(self, system_prompt: str, user_prompt: str, session_id: str) -> str:
        raise NotImplementedError

    async def generate_stream(self, system_prompt: str, user_prompt: str, session_id: str) -> AsyncIterator[str]:
        # Default streaming = single-shot generate yielded as one chunk so
        # consumers always see at least one delta. Override for real SSE.
        text = await self.generate(system_prompt, user_prompt, session_id)
        yield text


# ---------- Routing intent ----------
@dataclass
class RouteIntent:
    """What the caller wants. The registry uses this to pick a provider."""
    routing_mode: str = "auto"          # "manual" | "auto"
    explicit_provider: Optional[str] = None
    explicit_model: Optional[str] = None
    task: Optional[str] = None          # "code-generation" | "debug" | "narration" | ...
    tier: Optional[LatencyTier] = None  # speed/balanced/reasoning preference
    requires_streaming: bool = False
    requires_json: bool = False
    requires_vision: bool = False


# ---------- Helpers ----------
async def with_timeout(coro: Awaitable, seconds: float) -> object:
    """asyncio.wait_for that re-maps TimeoutError to ProviderTimeout."""
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError as e:
        raise ProviderTimeout(f"Provider exceeded {seconds}s timeout") from e
