"""Quick smoke tests for Phase 10D inference expansion.

Run with:
    cd /app/backend && python3 -m pytest tests/test_inference_expanded.py -v
or simply:
    cd /app/backend && python3 tests/test_inference_expanded.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.inference_service import infer_project_kind  # noqa: E402


def expect(prompt: str, kind: str, *, signals: dict | None = None) -> None:
    res = infer_project_kind(prompt, existing_signals=signals)
    ok = res.kind == kind
    flag = "✓" if ok else "✗"
    print(f"  {flag} {kind:24s} ← {prompt[:60]!r}  → got {res.kind} (conf={res.confidence})")
    assert ok, f"expected {kind}, got {res.kind} for prompt={prompt!r}"


def test_tauri_keyword() -> None:
    expect("Build a Tauri desktop app for note taking", "tauri-desktop")
    expect("I want a Mac app for password vaulting", "tauri-desktop")
    expect("Build a native desktop app for screenshots", "tauri-desktop")


def test_turborepo_keyword() -> None:
    expect("Build a Turborepo monorepo with apps and packages", "turborepo-monorepo")
    expect("Set up pnpm workspaces with shared UI components", "turborepo-monorepo")


def test_existing_signals_tauri() -> None:
    expect(
        "Add a settings page",
        "tauri-desktop",
        signals={"framework": "tauri"},
    )
    expect(
        "Refactor the sidebar",
        "tauri-desktop",
        signals={"files": ["src-tauri/tauri.conf.json", "src/App.tsx"]},
    )


def test_existing_signals_turborepo() -> None:
    expect(
        "Move the marketing site to its own app",
        "turborepo-monorepo",
        signals={"files": ["turbo.json", "pnpm-workspace.yaml", "apps/web/package.json"]},
    )


def test_existing_signals_expo_router() -> None:
    expect(
        "Add a profile tab",
        "expo-rn",
        signals={"files": ["app.json", "app/_layout.tsx", "app/(tabs)/index.tsx"]},
    )


def test_existing_keywords_remain_intact() -> None:
    # Regression: previous keywords still classify correctly.
    expect("Build a Chrome extension that summarises pages", "browser-extension")
    expect("Build a Next.js SaaS with billing", "nextjs-tailwind")
    expect("Build an AI chat clone with streaming", "ai-chat-streaming")
    expect("Build a React app for a kanban board", "react-vite")
    expect("Build a mobile app with Expo", "expo-rn")


def test_mobile_product_nouns_route_to_expo() -> None:
    # 2026-05-13 regression: "mobile habit tracker" used to classify as
    # web-static because none of the rule's keywords matched bare "mobile".
    # We added a `mobile + product-noun` regex; ensure it routes correctly
    # without firing on the false-positive forms.
    expect("Build a mobile habit tracker", "expo-rn")
    expect("Build a mobile workout app", "expo-rn")
    expect("ios app for tracking workouts", "expo-rn")
    expect("habit tracker", "expo-rn")
    # NEGATIVE: bare "mobile-friendly" must NOT route to expo-rn.
    res = infer_project_kind("Build a mobile-friendly portfolio site")
    assert res.kind != "expo-rn", res
    res = infer_project_kind("Build a responsive landing page")
    assert res.kind != "expo-rn", res


if __name__ == "__main__":
    suites = [
        test_tauri_keyword,
        test_turborepo_keyword,
        test_existing_signals_tauri,
        test_existing_signals_turborepo,
        test_existing_signals_expo_router,
        test_existing_keywords_remain_intact,
        test_mobile_product_nouns_route_to_expo,
    ]
    failures = 0
    for fn in suites:
        print(f"\n• {fn.__name__}")
        try:
            fn()
        except AssertionError as e:
            failures += 1
            print(f"  FAIL: {e}")
    print(f"\n{'PASS' if failures == 0 else 'FAIL'} — {failures} failure(s)")
    sys.exit(1 if failures else 0)
