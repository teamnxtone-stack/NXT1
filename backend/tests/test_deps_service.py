"""Tests for deps_service.apply_deps_to_files."""
from services.deps_service import apply_deps_to_files


def test_install_adds_deps_to_root_package_json():
    files = [
        {"path": "package.json",
         "content": '{\n  "name": "x",\n  "dependencies": { "react": "^18.0.0" }\n}\n'},
    ]
    r = apply_deps_to_files(files, install=["react-icons", "lucide-react"])
    assert r.target_path == "package.json"
    assert r.installed == ["react-icons", "lucide-react"]
    import json
    parsed = json.loads(r.files[0]["content"])
    assert parsed["dependencies"]["react-icons"] == "latest"
    assert parsed["dependencies"]["lucide-react"] == "latest"
    # Preserved existing
    assert parsed["dependencies"]["react"] == "^18.0.0"
    # 2-space indent preserved, trailing newline preserved
    assert r.files[0]["content"].endswith("\n")
    assert '\n  "name"' in r.files[0]["content"]


def test_install_respects_at_version():
    files = [{"path": "package.json", "content": "{}"}]
    r = apply_deps_to_files(files, install=["react@^18.2.0", "@scope/pkg@1.0.0"])
    import json
    parsed = json.loads(r.files[0]["content"])
    assert parsed["dependencies"]["react"] == "^18.2.0"
    assert parsed["dependencies"]["@scope/pkg"] == "1.0.0"


def test_uninstall_removes_from_both_blocks():
    files = [{
        "path": "package.json",
        "content": '{"dependencies":{"react":"^18"},"devDependencies":{"vite":"^5"}}',
    }]
    r = apply_deps_to_files(files, uninstall=["react", "vite"])
    import json
    parsed = json.loads(r.files[0]["content"])
    assert "react" not in parsed.get("dependencies", {})
    assert "vite" not in parsed.get("devDependencies", {})
    assert sorted(r.uninstalled) == ["react", "vite"]


def test_no_package_json_emits_warning():
    files = [{"path": "index.html", "content": "<!doctype html>"}]
    r = apply_deps_to_files(files, install=["react"])
    assert r.warning is not None
    assert r.installed == []
    assert r.files == files     # unchanged


def test_picks_root_over_nested():
    files = [
        {"path": "frontend/package.json", "content": '{"dependencies":{}}'},
        {"path": "package.json", "content": '{"dependencies":{}}'},
    ]
    r = apply_deps_to_files(files, install=["foo"])
    assert r.target_path == "package.json"
    # Nested unchanged
    assert '"foo"' not in files[0]["content"]


def test_idempotent_when_no_changes():
    files = [{"path": "package.json", "content": "{}"}]
    r = apply_deps_to_files(files, install=[], uninstall=[])
    assert r.files == files
    assert r.installed == []
    assert r.uninstalled == []


def test_malformed_package_json_recovers_to_empty():
    files = [{"path": "package.json", "content": "{not-json"}]
    r = apply_deps_to_files(files, install=["react"])
    # We resilient-parse to {} then re-emit valid JSON
    import json
    parsed = json.loads(r.files[0]["content"])
    assert parsed["dependencies"]["react"] == "latest"
