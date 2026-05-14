"""NXT1 Provider OS — multi-LLM registry, routing, and failover.

Public API:
    registry.list_specs() -> list[ProviderSpec]
    registry.available()  -> list[str]
    registry.get(provider_id, model=None) -> BaseProvider
    registry.health_status() -> dict
    route(intent: RouteIntent) -> BaseProvider (with failover chain)

Each adapter lives in its own module under this package. Adapters expose a
ProviderSpec describing their capabilities, latency tier, default models, and
streaming support so the UI and routing layer can make informed choices
without reaching into provider internals.

This package replaces the ad-hoc provider selection that previously lived in
ai_service.py. ai_service.py now delegates here for all provider concerns.
"""
from .base import (
    BaseProvider,
    ProviderSpec,
    ProviderError,
    ProviderAuthError,
    ProviderTimeout,
    ProviderRateLimit,
    ProviderUnavailable,
    ProviderBadResponse,
    RouteIntent,
    LatencyTier,
)
from .registry import registry, route

__all__ = [
    "BaseProvider",
    "ProviderSpec",
    "ProviderError",
    "ProviderAuthError",
    "ProviderTimeout",
    "ProviderRateLimit",
    "ProviderUnavailable",
    "ProviderBadResponse",
    "RouteIntent",
    "LatencyTier",
    "registry",
    "route",
]
