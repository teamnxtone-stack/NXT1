"""Multi-agent foundation for NXT1 (Phase 7).

Each agent is a thin wrapper around the existing provider abstraction with a
specialized system prompt and role. Agents share the same provider/model setup
(OpenAI / Claude / Emergent) but reason within their domain.

Today this is a clean abstraction; over time the agents can:
  - hold their own short-term memory (per-session)
  - call each other (e.g. ArchitectureAgent → BackendAgent for an endpoint)
  - get specialized tools (RuntimeAgent runs `try-it`, DevOpsAgent reads deploy logs)

The pattern is intentionally simple. Don't over-engineer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AgentResult:
    role: str
    text: str
    parsed: Optional[dict] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class BaseAgent:
    """Base agent class — holds a role, a system prompt, and runs a single
    completion against the active provider.
    """

    role: str = "generic"
    label: str = "Generic agent"
    system_prompt: str = "You are a helpful assistant. Respond concisely."

    def __init__(self, preferred_provider: Optional[str] = None):
        self.preferred_provider = preferred_provider

    async def run(self, user_prompt: str, session_id: Optional[str] = None,
                  system_prompt_override: Optional[str] = None) -> AgentResult:
        from . import ai_service as _ai  # local import to avoid cycles
        # Route the agent role to its preferred provider unless caller specified one
        provider = _ai.get_provider_for_task(self.role, explicit=self.preferred_provider)
        sid = session_id or f"{self.role}-{_ai.uuid.uuid4().hex[:8]}"
        sys_p = system_prompt_override or self.system_prompt
        raw = await provider.generate(sys_p, user_prompt, sid)
        parsed: Optional[dict] = None
        try:
            parsed = _ai.parse_ai_response(raw)
        except Exception:
            parsed = None
        return AgentResult(role=self.role, text=raw, parsed=parsed,
                           provider=provider.name, model=provider.model)


# ---------- Specialized agents ----------
class ArchitectureAgent(BaseAgent):
    role = "architecture"
    label = "Architecture agent"
    system_prompt = (
        "You are NXT1's architecture agent. Given a project's files and intent, "
        "propose a clean, scalable structure: which files exist, which routes "
        "are needed, what the data flow looks like, and which services/components "
        "should be split out. Output STRICT JSON: "
        '{"summary": "...", "files": [{"path": "...", "purpose": "..."}], '
        '"routes": [{"method": "...", "path": "..."}], "notes": "..."}'
    )


class FrontendAgent(BaseAgent):
    role = "frontend"
    label = "Frontend / UI agent"
    system_prompt = (
        "You are NXT1's frontend agent. You generate or refine premium dark-themed "
        "user interfaces: HTML+CSS+JS or React+Tailwind. Tasteful spacing, accessible, "
        "responsive, no external CDNs. Output STRICT JSON of the schema requested by the caller.\n\n"
        "PREMIUM UI DIRECTIVE: NXT1 ships a curated registry of premium UI blocks "
        "(Magic UI, Aceternity UI, Origin UI, shadcn/ui) at GET /api/ui-registry. "
        "ALL 17 BLOCKS HAVE REAL REACT SOURCE VENDORED IN THE PROJECT at "
        "`/components/ui/blocks/` — you can fetch the verbatim source via "
        "`GET /api/ui-registry/blocks/{block_id}/source`. When generating landing pages, "
        "hero sections, feature grids, pricing blocks, or marketing pages, you MUST:\n"
        "  1. Select an appropriate block id from the registry.\n"
        "  2. Copy the vendored source file into the generated app's "
        "`src/components/ui/blocks/` directory (preserve filename).\n"
        "  3. Import and compose those components instead of writing raw Tailwind.\n"
        "  4. Add `// nxt1-block: <id>` as a comment above each usage so the editor "
        "can hot-swap blocks later.\n"
        "NEVER emit a hero made of a raw `<div className=\"bg-gradient-to-br from-purple-500 to-pink-500\">`. "
        "Default to dark, premium, layered, animated."
    )


class BackendAgent(BaseAgent):
    role = "backend"
    label = "Backend / API agent"
    system_prompt = (
        "You are NXT1's backend agent. You generate FastAPI or Express APIs. "
        "Use proper HTTP methods, JSON bodies, validation, CORS, env vars from "
        "os.environ / process.env. Output STRICT JSON of the schema requested."
    )


class DebugAgent(BaseAgent):
    role = "debug"
    label = "Debugging / repair agent"
    system_prompt = (
        "You are NXT1's debugging agent. You receive a runtime error trace plus the "
        "relevant source files. Return STRICT JSON:\n"
        "{\n"
        '  "diagnosis": "<root cause in 2-4 sentences>",\n'
        '  "confidence": "high"|"medium"|"low",\n'
        '  "fix_summary": "<one-line description of the fix>",\n'
        '  "requires_approval": true|false,   // true if the fix changes API contract or deletes data\n'
        '  "files": [ { "path": "...", "before": "...", "after": "..." } ],\n'
        '  "post_fix_action": "restart_runtime"|"none",\n'
        '  "next_check": "<one-line: what should the user verify after applying>"\n'
        "}\n"
        "Only include `files` whose content you are confident about. Provide the FULL `after` content for each file (not a diff)."
    )


class DevOpsAgent(BaseAgent):
    role = "devops"
    label = "Deployment / DevOps agent"
    system_prompt = (
        "You are NXT1's deployment agent. Inspect deploy logs, env vars, build "
        "configurations, and produce a structured action plan. Output STRICT JSON: "
        '{"diagnosis": "...", "actions": [{"type": "...", "detail": "..."}], "requires_approval": false}'
    )


_REGISTRY: Dict[str, BaseAgent] = {}


def get_agent(role: str, preferred_provider: Optional[str] = None) -> BaseAgent:
    """Return an agent for a role. Roles: architecture, frontend, backend, debug, devops."""
    cls = {
        "architecture": ArchitectureAgent,
        "frontend": FrontendAgent,
        "backend": BackendAgent,
        "debug": DebugAgent,
        "devops": DevOpsAgent,
    }.get(role)
    if cls is None:
        raise ValueError(f"Unknown agent role: {role}")
    # Re-instantiate per call so provider override is respected. Cheap.
    return cls(preferred_provider=preferred_provider)


def list_agents() -> List[Dict[str, Any]]:
    return [
        {"role": r, "label": cls.label}
        for r, cls in (
            ("architecture", ArchitectureAgent),
            ("frontend", FrontendAgent),
            ("backend", BackendAgent),
            ("debug", DebugAgent),
            ("devops", DevOpsAgent),
        )
    ]
