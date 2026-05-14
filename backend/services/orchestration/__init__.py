"""NXT1 — Multi-agent orchestration (foundation, Phase 10E).

This package introduces a *cooperative* agent protocol (planner → builder
→ tester → deployer) on top of the existing per-role agents in
`services.agents` (architecture / frontend / backend / debug / devops).

The two packages serve complementary purposes:

  services.agents          — stateless role-specialised LLM agents.
  services.orchestration   — lifecycle agents that drive a build
                              end-to-end and stream attribution.

This additive layer lets the UI render an Activity Stream where each
step is attributed to a lifecycle agent, without rewriting any existing
endpoints. The default orchestrator is back-compat (single-agent build).
"""
from .orchestrator import (
    AgentRole,
    AgentTask,
    AgentResult,
    BaseLifecycleAgent,
    PlannerAgent,
    BuilderAgent,
    TesterAgent,
    DeployerAgent,
    Orchestrator,
    default_orchestrator,
)

__all__ = [
    "AgentRole",
    "AgentTask",
    "AgentResult",
    "BaseLifecycleAgent",
    "PlannerAgent",
    "BuilderAgent",
    "TesterAgent",
    "DeployerAgent",
    "Orchestrator",
    "default_orchestrator",
]
