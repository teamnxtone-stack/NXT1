"""Tests for the hardened project create model — the validation surface
that was 422-ing the builder pipeline before Phase B.5."""
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database_eval")

from routes.projects import (   # noqa: E402
    FileItem,
    ProjectCreate,
    ProjectFull,
    ProjectMeta,
    _coerce_name,
)


def test_coerce_name_handles_none():
    assert _coerce_name(None) == "Untitled project"


def test_coerce_name_handles_empty():
    assert _coerce_name("") == "Untitled project"
    assert _coerce_name("   ") == "Untitled project"


def test_coerce_name_keeps_real_names():
    assert _coerce_name("My App") == "My App"
    assert _coerce_name("  Trim me  ") == "Trim me"


def test_project_create_accepts_null_name():
    """The exact case that produced 'Input should be a valid string' before."""
    p = ProjectCreate(name=None)
    assert p.name == "Untitled project"


def test_project_create_accepts_empty_body():
    """Empty `{}` POST body is the worst-case input the FE can produce."""
    p = ProjectCreate.model_validate({})
    # When the field is omitted, Pydantic uses the default; we accept either
    # the default None or the coerced friendly name — both are recoverable
    # at the route level.
    assert p.name in (None, "Untitled project")


def test_project_create_accepts_full_landing_payload():
    """The exact shape WorkspaceHome.handleStartFromTemplate posts today."""
    p = ProjectCreate.model_validate({
        "name": "My App",
        "prompt": "build a saas pricing page with react",
        "mode": "app",
        "scaffold_id": "react-vite",
        "framework": "react",
    })
    assert p.name == "My App"
    assert p.prompt == "build a saas pricing page with react"
    assert p.scaffold_id == "react-vite"
    assert p.resolve_scaffold_kind() == "react-vite"


def test_project_create_resolves_template_explicit():
    p = ProjectCreate(template="nextjs-tailwind")
    assert p.resolve_scaffold_kind() == "nextjs-tailwind"


def test_project_create_resolves_scaffold_id_alias():
    p = ProjectCreate(scaffold_id="next")
    assert p.resolve_scaffold_kind() == "nextjs-tailwind"


def test_project_create_resolves_via_prompt_chrome_ext():
    p = ProjectCreate(prompt="build a chrome extension that translates text")
    assert p.resolve_scaffold_kind() == "browser-extension"


def test_project_create_resolves_via_prompt_saas():
    p = ProjectCreate(prompt="build a saas with billing and dashboards")
    assert p.resolve_scaffold_kind() == "nextjs-tailwind"


def test_project_create_resolves_via_prompt_ai_chat():
    p = ProjectCreate(prompt="build an AI chatbot with streaming")
    assert p.resolve_scaffold_kind() == "ai-chat-streaming"


def test_project_create_returns_none_when_no_signal():
    p = ProjectCreate()
    assert p.resolve_scaffold_kind() is None


def test_file_item_accepts_null_content():
    f = FileItem(path="x.txt", content=None)
    assert f.content == ""


def test_file_item_strips_leading_slash():
    f = FileItem(path="/src/App.jsx", content="x")
    assert f.path == "src/App.jsx"


def test_file_item_fallback_empty_path():
    f = FileItem(path=None, content="data")
    assert f.path == "untitled.txt"


def test_project_meta_normalises_legacy_db_doc():
    """A legacy doc with name=None should NOT fail response serialisation."""
    doc = {
        "id": "abc",
        "name": None,
        "description": None,
        "created_at": None,
        "updated_at": None,
    }
    m = ProjectMeta.model_validate(doc)
    assert m.name == "Untitled project"
    assert m.description == ""
    assert m.created_at and "T" in m.created_at


def test_project_full_accepts_legacy_files_with_none_content():
    """End-to-end: response model + legacy file shapes."""
    doc = {
        "id": "abc",
        "name": "",                  # blank → coerced
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "files": [
            {"path": "a.js", "content": None},
            {"path": None,   "content": "ok"},
        ],
    }
    full = ProjectFull.model_validate(doc)
    assert full.name == "Untitled project"
    assert full.files[0].content == ""
    assert full.files[1].path == "untitled.txt"
