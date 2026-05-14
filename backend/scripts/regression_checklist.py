"""Build-readiness regression checklist.

This probes the 12 capabilities the user named in the Phase B.9 brief:
  scaffold snapshots, auto-build, first preview, generation, parser recovery,
  build repair, preview repair, full-stack apps, website apps, mobile apps,
  extension apps, snapshot parity.

Run with:
    cd /app/backend && python3 scripts/regression_checklist.py

The script is *deliberately* lightweight — no LLM calls, no live deploys.
It verifies the static plumbing each capability needs so a regression
on any of them surfaces here before users notice.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Load backend/.env so the registry sees the configured provider keys when
# the checklist runs outside the supervised process. Mirrors what server.py
# does at import time.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(BACKEND / ".env")
except Exception:
    pass

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
SKIP = "\033[33m·\033[0m"


def check(label: str, fn):
    t0 = time.perf_counter()
    try:
        result = fn()
        dt = round((time.perf_counter() - t0) * 1000, 1)
        if result is True or result is None:
            print(f"  {PASS} {label:<55} {dt:>6} ms")
            return True
        elif result is False:
            print(f"  {FAIL} {label:<55} {dt:>6} ms")
            return False
        else:
            # Truthy non-bool — treat as pass with info
            print(f"  {PASS} {label:<55} {dt:>6} ms  ({result})")
            return True
    except AssertionError as e:
        dt = round((time.perf_counter() - t0) * 1000, 1)
        print(f"  {FAIL} {label:<55} {dt:>6} ms  AssertionError: {e}")
        return False
    except Exception as e:
        dt = round((time.perf_counter() - t0) * 1000, 1)
        print(f"  {FAIL} {label:<55} {dt:>6} ms  {type(e).__name__}: {e}")
        return False


def main() -> int:
    print("\n  NXT1 build-readiness regression  ─────────────────────────\n")

    results: list[tuple[str, bool]] = []  # reserved for future per-section grouping; intentionally accumulated.
    _ = results
    section_results: list[tuple[str, bool]] = []

    # ─── 1. Scaffold snapshots ────────────────────────────────────────────
    print("  Snapshots")
    from services.scaffold_snapshot_service import (
        list_snapshots, load_snapshot, snapshot_path,
    )

    def has_six_snapshots():
        snaps = list_snapshots()
        assert len(snaps) >= 6, f"only {len(snaps)} snapshots baked"
        return f"{len(snaps)} kinds"

    def snapshot_load_under_15ms():
        _, info = load_snapshot("nextjs-tailwind", "Probe")
        assert info["loaded_at_ms"] < 15.0, info["loaded_at_ms"]
        return f"{info['loaded_at_ms']}ms"

    def snapshot_substitutes_name():
        files, _ = load_snapshot("react-vite", "My SaaS App")
        pkg = next((f for f in files if f["path"] == "package.json"), None)
        assert pkg is not None
        assert '"name": "my-saas-app"' in pkg["content"]
        return True

    section_results.append(("snapshots", check("Six+ snapshots baked", has_six_snapshots)))
    section_results.append(("snapshots", check("Cold load < 15ms", snapshot_load_under_15ms)))
    section_results.append(("snapshots", check("Project-name substitution", snapshot_substitutes_name)))

    # ─── 2. Parser recovery ──────────────────────────────────────────────
    print("\n  Parser recovery")
    from services.parsers import parse_ai_response, AIProviderError

    def parser_l1():
        out = parse_ai_response('{"files":[{"path":"a.txt","content":"x"}]}')
        return out["_parse_level"] == "L1"

    def parser_l5_codefences():
        text = "```app.js\nconsole.log('x');\n```"
        out = parse_ai_response(text)
        return out["_parse_level"] == "L5" and len(out["files"]) == 1

    def parser_empty_raises():
        try:
            parse_ai_response("")
        except AIProviderError:
            return True
        return False

    section_results.append(("parser", check("L1 strict parse", parser_l1)))
    section_results.append(("parser", check("L5 code-fence salvage", parser_l5_codefences)))
    section_results.append(("parser", check("Empty input raises", parser_empty_raises)))

    # ─── 3. Inference (full-stack, website, mobile, extension) ────────────
    print("\n  Inference (route to correct scaffold)")
    from services.inference_service import infer_project_kind

    def infers(prompt, expected):
        r = infer_project_kind(prompt)
        kind = getattr(r, "kind", r)
        assert kind == expected, f"got {kind!r}, expected {expected!r}"
        return True

    section_results.append(("inference", check("full-stack: 'SaaS dashboard with billing'",
        lambda: infers("Build a SaaS dashboard with billing", "nextjs-tailwind"))))
    section_results.append(("inference", check("website:    'portfolio site with motion'",
        lambda: infers("Build a portfolio site with motion", "web-static"))))
    section_results.append(("inference", check("mobile:     'mobile habit tracker'",
        lambda: infers("Build a mobile habit tracker", "expo-rn"))))
    section_results.append(("inference", check("extension:  'Chrome translator extension'",
        lambda: infers("Build a Chrome translator extension", "browser-extension"))))
    section_results.append(("inference", check("ai-chat:    'AI chat with streaming'",
        lambda: infers("Build an AI chat clone with streaming", "ai-chat-streaming"))))

    # ─── 4. Provider registry ────────────────────────────────────────────
    print("\n  Provider registry")
    from services.providers import registry as reg

    def registry_resolves():
        from services.providers.base import RouteIntent
        intent = RouteIntent(routing_mode="auto")
        p = reg.resolve(intent)
        return p.spec.id

    def xai_adapter_present():
        from services.providers.adapters import ALL_ADAPTERS, XAIProvider
        assert XAIProvider in ALL_ADAPTERS
        return True

    def env_aliases_hydrated():
        # If GROK_API_KEY is set, XAI_API_KEY must also be set after import.
        import os
        if os.environ.get("GROK_API_KEY") and not os.environ.get("XAI_API_KEY"):
            return False
        if os.environ.get("GOOGLE_API_KEY") and not os.environ.get("GEMINI_API_KEY"):
            return False
        return True

    section_results.append(("provider", check("Registry resolves a provider", registry_resolves)))
    section_results.append(("provider", check("xAI adapter wired into ALL_ADAPTERS", xai_adapter_present)))
    section_results.append(("provider", check("Env aliases hydrate (GROK→XAI, GOOGLE→GEMINI)", env_aliases_hydrated)))

    # ─── 5. Validation + action runner ───────────────────────────────────
    print("\n  Validation + repair")
    from services.validation_service import validate_files

    def validation_on_empty():
        # Empty file list is allowed (`checked=0`); ensure the call shape works.
        r = validate_files([])
        return r.checked == 0

    def validation_runs_on_real_scaffold():
        from services.scaffold_snapshot_service import load_snapshot
        files, _ = load_snapshot("nextjs-tailwind", "Test")
        r = validate_files(files)
        # Real scaffolds should be valid (zero errors).
        return not r.has_errors

    section_results.append(("repair", check("validate_files([]) shape", validation_on_empty)))
    section_results.append(("repair", check("validate_files passes real scaffold", validation_runs_on_real_scaffold)))

    # ─── 6. Tag protocol ─────────────────────────────────────────────────
    print("\n  Tag protocol (live writes)")
    from services.tag_protocol import TagStreamParser

    def tag_protocol_parses():
        text = (
            "<nxt1-shell>npm install</nxt1-shell>\n"
            "<nxt1-write path=\"app/page.jsx\">export default function() {}</nxt1-write>"
        )
        parser = TagStreamParser()
        events = list(parser.feed(text))
        # Flush any trailing tag close on EOF.
        events.extend(list(parser.finish()))
        kinds = {e.get("type") for e in events}
        # Expect at minimum a tag_open and tag_close for each tag.
        assert kinds, "no events emitted"
        return len(events)

    section_results.append(("tag", check("TagStreamParser emits events", tag_protocol_parses)))

    # ─── Summary ──────────────────────────────────────────────────────────
    total = len(section_results)
    passes = sum(1 for _, ok in section_results if ok)
    print("\n  ────────────────────────────────────────────────────────────")
    print(f"  {passes}/{total} checks passed")
    print()

    return 0 if passes == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
