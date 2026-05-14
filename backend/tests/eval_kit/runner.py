"""Eval-kit runner — drives a single fixture through the builder pipeline.

A fixture is a small JSON file describing:

  {
    "id": "blank-pricing-page",
    "title": "Build a pricing page from a blank scaffold",
    "starting_files": [ { "path": "index.html", "content": "<html>…</html>" } ],
    "user_message": "Build a modern pricing page with three tiers.",
    "protocol": "tag" | "json" | "auto",
    "expected": {
        "paths_present": ["index.html"],
        "paths_created": ["styles/pricing.css"],
        "keywords_in_any": ["Starter", "Pro", "Enterprise"],
        "no_validation_errors": true,
        "max_files_changed": 12
    }
  }

`run_fixture()` calls the same generator the API uses (no HTTP round-trip)
and returns a structured `FixtureResult` that the scorer can grade.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from services import ai_service
from services.ai_service_tag import generate_project_stream_tag
from services.validation_service import diff_paths, validate_files

logger = logging.getLogger("nxt1.evalkit")


@dataclass
class Fixture:
    id: str
    title: str
    user_message: str
    starting_files: List[Dict[str, str]] = field(default_factory=list)
    protocol: str = "auto"        # "tag" | "json" | "auto"
    provider: Optional[str] = None
    expected: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Fixture":
        return Fixture(
            id=d["id"], title=d["title"], user_message=d["user_message"],
            starting_files=d.get("starting_files") or [],
            protocol=d.get("protocol") or "auto",
            provider=d.get("provider"),
            expected=d.get("expected") or {},
        )


@dataclass
class FixtureResult:
    fixture_id: str
    protocol_used: str
    success: bool
    files: List[Dict[str, str]] = field(default_factory=list)
    explanation: str = ""
    notes: str = ""
    provider: Optional[str] = None
    model: Optional[str] = None
    receipts: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    raw_events: List[Dict[str, Any]] = field(default_factory=list)
    paths_changed: List[str] = field(default_factory=list)
    validation: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _resolve_protocol(fixture: Fixture) -> str:
    """`auto` → 'tag' for non-empty starting files (incremental), else 'json'."""
    if fixture.protocol in {"tag", "json"}:
        return fixture.protocol
    if fixture.starting_files and len(fixture.starting_files) > 5:
        return "tag"
    return "json"


async def _drive_stream(stream, raw_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    final: Dict[str, Any] = {"success": False}
    async for ev in stream:
        raw_events.append(ev)
        t = ev.get("type")
        if t == "done":
            final.update({
                "success": True,
                "files": ev.get("files") or [],
                "explanation": ev.get("explanation") or "",
                "notes": ev.get("notes") or "",
                "provider": ev.get("provider"),
                "model": ev.get("model"),
                "receipts": ev.get("receipts") or [],
            })
            break
        if t == "error":
            final.update({"success": False, "error": ev.get("message", "unknown")})
            break
        if t == "cancelled":
            final.update({"success": False, "error": "cancelled"})
            break
    return final


async def run_fixture(fixture: Fixture) -> FixtureResult:
    """Drive `fixture` through the builder pipeline. Returns a structured
    result suitable for `Scorer.score()`.
    """
    import time
    protocol = _resolve_protocol(fixture)
    raw_events: List[Dict[str, Any]] = []
    started = time.monotonic()

    if protocol == "tag":
        stream = generate_project_stream_tag(
            user_message=fixture.user_message,
            current_files=fixture.starting_files,
            history=[],
            project_id=f"eval-{fixture.id}",
            preferred_provider=fixture.provider,
        )
    else:
        stream = ai_service.generate_project_stream(
            user_message=fixture.user_message,
            current_files=fixture.starting_files,
            history=[],
            project_id=f"eval-{fixture.id}",
            preferred_provider=fixture.provider,
        )

    out = await _drive_stream(stream, raw_events)
    duration_ms = int((time.monotonic() - started) * 1000)

    result = FixtureResult(
        fixture_id=fixture.id,
        protocol_used=protocol,
        success=bool(out.get("success")),
        files=out.get("files") or [],
        explanation=out.get("explanation", ""),
        notes=out.get("notes", ""),
        provider=out.get("provider"),
        model=out.get("model"),
        receipts=out.get("receipts") or [],
        error=out.get("error"),
        raw_events=raw_events,
        duration_ms=duration_ms,
    )
    # Compute diff + validation post-hoc.
    if result.files:
        result.paths_changed = diff_paths(fixture.starting_files, result.files)
        report = validate_files(result.files, only_paths=result.paths_changed)
        result.validation = report.to_dict()
    return result


def load_fixtures(directory: Optional[str] = None) -> List[Fixture]:
    """Load every fixture JSON in `directory` (default: `./fixtures/`)."""
    here = Path(__file__).resolve().parent
    d = Path(directory) if directory else (here / "fixtures")
    if not d.exists():
        return []
    out: List[Fixture] = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(Fixture.from_dict(json.loads(p.read_text())))
        except Exception as e:
            logger.warning(f"skipping malformed fixture {p}: {e}")
    return out


def has_provider_configured() -> bool:
    """Best-effort: do we have ANY usable provider env var?
    The full eval (which makes real LLM calls) is skipped without one.
    """
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
              "GROQ_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
              "EMERGENT_LLM_KEY"):
        if (os.environ.get(k) or "").strip():
            return True
    return False


__all__ = ["Fixture", "FixtureResult", "run_fixture", "load_fixtures",
            "has_provider_configured"]
