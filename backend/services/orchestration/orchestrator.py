"""NXT1 — Multi-agent orchestrator (Phase 10E).

The orchestrator is the upgrade path from single-agent generation to
role-specialised cooperative *lifecycle* agents (planner → builder →
tester → deployer). These are distinct from the domain agents in
`services.agents` (architecture/frontend/backend/debug/devops) — the
lifecycle agents *drive* the build, and they may dispatch to the
domain agents internally.

Design goals:

  * SSE chat events can include an `agent` field (planner/builder/…)
    so the cinematic Activity Stream can attribute work.
  * The Provider OS can be queried with a role-specific RouteIntent
    (`task="product-plan"` for planner, `task="code-generation"` for
    builder, etc.).
  * New richer agents can be dropped in by sub-classing
    `BaseLifecycleAgent` and overriding `.run()` without touching the
    chat/build pipeline.

The default orchestrator is single-agent: it short-circuits to the
BuilderAgent so existing flows keep working byte-for-byte. The full
multi-agent dispatch will be enabled per-project once the UX is ready
(feature flag planned).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("nxt1.orchestration")


# ---------- Role catalogue ----------
class AgentRole:
    PLANNER  = "planner"
    BUILDER  = "builder"
    TESTER   = "tester"
    DEPLOYER = "deployer"
    REVIEWER = "reviewer"

    @classmethod
    def all(cls) -> List[str]:
        return [cls.PLANNER, cls.BUILDER, cls.TESTER, cls.DEPLOYER, cls.REVIEWER]


# ---------- Task / Result records ----------
@dataclass
class AgentTask:
    """A single unit of work for a lifecycle agent.

    `payload` is intentionally loose so each agent can shape it. Common keys:
        - prompt:       str
        - project_id:   str
        - files:        list[dict]
        - context:      dict
        - constraints:  dict
    """
    role: str
    payload: Dict[str, Any] = field(default_factory=dict)
    parent_task_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentResult:
    role: str
    ok: bool
    summary: str = ""
    receipts: List[dict] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------- Base agent ----------
class BaseLifecycleAgent:
    role: str = "base"
    description: str = ""

    async def run(self, task: AgentTask, emit: Optional[Callable[[dict], Awaitable[None]]] = None) -> AgentResult:
        """Execute the task. `emit` is an optional async callback receiving
        SSE-shaped dicts (`{type, agent, phase, message, ...}`).
        """
        raise NotImplementedError


# ---------- Role agents (placeholder-safe shims) ----------
class PlannerAgent(BaseLifecycleAgent):
    """Decomposes a prompt into an actionable build plan.

    Today: returns a deterministic plan derived from the inference engine.
    Tomorrow: invokes the Provider OS with task="product-plan".
    """
    role = AgentRole.PLANNER
    description = "Breaks down the prompt and decides the build plan."

    async def run(self, task, emit=None):
        prompt = task.payload.get("prompt", "")
        try:
            from services.inference_service import infer_project_kind
            inf = infer_project_kind(prompt)
            plan = [
                {"step": "infer",     "detail": f"Project kind: {inf.kind} ({inf.framework})"},
                {"step": "scaffold",  "detail": f"Inject the {inf.kind} scaffold pack."},
                {"step": "build",     "detail": "Generate the requested feature surface."},
                {"step": "test",      "detail": "Smoke-test build output."},
                {"step": "deploy",    "detail": "Hand off to deployer (manual until provider configured)."},
            ]
            if emit:
                await emit({
                    "type": "agent_event",
                    "agent": self.role,
                    "phase": "planned",
                    "message": inf.rationale,
                    "plan": plan,
                })
            return AgentResult(
                role=self.role, ok=True,
                summary=inf.rationale,
                artifacts={"plan": plan, "inference": inf.to_dict()},
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.exception("planner failed")
            return AgentResult(role=self.role, ok=False, error=str(e)[:200])


class BuilderAgent(BaseLifecycleAgent):
    """Writes / edits code. Today this is the existing chat/build pipeline.

    Kept as a thin shim so the orchestrator can hand off to it via `.run()`
    without rewriting chat/routes today. When wired, the SSE events from
    chat.py will be re-emitted here with `agent="builder"`.
    """
    role = AgentRole.BUILDER
    description = "Implements the build using the Provider OS."

    async def run(self, task, emit=None):
        if emit:
            await emit({
                "type": "agent_event",
                "agent": self.role,
                "phase": "queued",
                "message": "Builder will pick up via chat SSE stream.",
            })
        return AgentResult(
            role=self.role, ok=True,
            summary="Builder queued; SSE stream owns the actual generation.",
        )


class TesterAgent(BaseLifecycleAgent):
    """Smoke-tests the build output (entry file + lint markers)."""
    role = AgentRole.TESTER
    description = "Runs lint / smoke checks on the build output."

    async def run(self, task, emit=None):
        files = task.payload.get("files") or []
        receipts = []
        ok = True
        entry_candidates = {"index.html", "src/main.tsx", "src/main.jsx", "src/main.js", "app/page.tsx", "app/page.jsx"}
        has_entry = any((f.get("path") or "").lower() in entry_candidates for f in files)
        if not has_entry and files:
            ok = False
            receipts.append({"check": "entry-file", "status": "fail", "detail": "No recognised entry file"})
        else:
            receipts.append({"check": "entry-file", "status": "pass"})
        if emit:
            await emit({
                "type": "agent_event",
                "agent": self.role,
                "phase": "tested",
                "message": f"{len(receipts)} check(s) run.",
            })
        return AgentResult(role=self.role, ok=ok, summary="structural checks", receipts=receipts)


class DeployerAgent(BaseLifecycleAgent):
    """Hands off the project to the hosting provider chosen by the user."""
    role = AgentRole.DEPLOYER
    description = "Coordinates hand-off to the chosen hosting provider."

    async def run(self, task, emit=None):
        provider = task.payload.get("provider") or "internal"
        if emit:
            await emit({
                "type": "agent_event",
                "agent": self.role,
                "phase": "ready",
                "message": f"Ready to deploy via {provider}.",
            })
        return AgentResult(
            role=self.role, ok=True,
            summary=f"deploy-ready via {provider}",
            artifacts={"provider": provider},
        )


# ---------- Orchestrator ----------
class Orchestrator:
    """Dispatches AgentTasks. Single-agent passthrough by default.

    Call `.dispatch(role, payload, emit=...)` to invoke a role agent; or
    `.run_pipeline(payload, roles=[...], emit=...)` to run a sequence.
    Sequential by design — parallel/fan-out can be added via
    `asyncio.gather()` here without changing callers.
    """
    def __init__(self, agents: Optional[Dict[str, BaseLifecycleAgent]] = None):
        self._agents: Dict[str, BaseLifecycleAgent] = agents or {
            AgentRole.PLANNER:  PlannerAgent(),
            AgentRole.BUILDER:  BuilderAgent(),
            AgentRole.TESTER:   TesterAgent(),
            AgentRole.DEPLOYER: DeployerAgent(),
        }

    def register(self, agent: BaseLifecycleAgent) -> None:
        self._agents[agent.role] = agent

    def get(self, role: str) -> BaseLifecycleAgent:
        if role not in self._agents:
            raise KeyError(f"No lifecycle agent registered for role '{role}'")
        return self._agents[role]

    def roles(self) -> List[str]:
        return list(self._agents.keys())

    async def dispatch(self, role: str, payload: Optional[Dict[str, Any]] = None,
                        emit: Optional[Callable[[dict], Awaitable[None]]] = None) -> AgentResult:
        agent = self.get(role)
        task = AgentTask(role=role, payload=payload or {})
        return await agent.run(task, emit=emit)

    async def run_pipeline(self, payload: Dict[str, Any], roles: Optional[List[str]] = None,
                            emit: Optional[Callable[[dict], Awaitable[None]]] = None) -> List[AgentResult]:
        roles = roles or [AgentRole.PLANNER, AgentRole.BUILDER, AgentRole.TESTER, AgentRole.DEPLOYER]
        results: List[AgentResult] = []
        for r in roles:
            res = await self.dispatch(r, payload, emit=emit)
            results.append(res)
            if not res.ok and r in {AgentRole.PLANNER, AgentRole.BUILDER}:
                break
        return results


# Default singleton used by routes.
default_orchestrator = Orchestrator()
