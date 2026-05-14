"""Unit tests for the NXT1 tag-protocol parser + apply layer."""
import pytest

from services.tag_protocol import (
    ApplyResult,
    TagApplyError,
    TagStreamParser,
    apply_tag_action,
)


def _events(parser: TagStreamParser, chunks):
    """Drive the parser with a list of string chunks; return all events."""
    out = []
    for c in chunks:
        out.extend(parser.feed(c))
    out.extend(parser.finish())
    return out


# ─── parser tests ──────────────────────────────────────────────────────────

def test_parser_simple_write_one_chunk():
    p = TagStreamParser()
    src = '<nxt1-write path="a.txt">hello</nxt1-write>'
    evs = _events(p, [src])
    types = [e["type"] for e in evs]
    assert "tag_open" in types and "tag_close" in types
    close = [e for e in evs if e["type"] == "tag_close"][0]
    assert close["tag"] == "nxt1-write"
    assert close["attrs"]["path"] == "a.txt"
    assert close["content"] == "hello"


def test_parser_write_split_across_chunks():
    p = TagStreamParser()
    src = '<nxt1-write path="a.txt">hello world</nxt1-write>'
    # Split deliberately mid-tag and mid-close
    chunks = [src[:6], src[6:18], src[18:30], src[30:]]
    evs = _events(p, chunks)
    close = [e for e in evs if e["type"] == "tag_close"][0]
    assert close["content"] == "hello world"


def test_parser_streams_write_chunks_live():
    p = TagStreamParser()
    src = '<nxt1-write path="big.txt">aaa bbb ccc ddd</nxt1-write>'
    chunks = [src[:30], src[30:45], src[45:]]
    evs = _events(p, chunks)
    chunk_events = [e for e in evs if e["type"] == "tag_chunk"]
    assert chunk_events, "expected tag_chunk events for streaming write"
    # All chunk deltas concatenated must equal the final content
    final = "".join(c["delta"] for c in chunk_events)
    close = [e for e in evs if e["type"] == "tag_close"][0]
    assert final == close["content"] == "aaa bbb ccc ddd"


def test_parser_self_closing_rename():
    p = TagStreamParser()
    evs = _events(p, ['<nxt1-rename from="a.txt" to="b.txt" />'])
    close = [e for e in evs if e["type"] == "tag_close"][0]
    assert close["tag"] == "nxt1-rename"
    assert close["attrs"] == {"from": "a.txt", "to": "b.txt"}


def test_parser_self_closing_delete_no_slash_is_accepted():
    """SELF_CLOSING_TAGS get auto-closed even if the model forgets the trailing /."""
    p = TagStreamParser()
    evs = _events(p, ['<nxt1-delete path="x.txt">'])
    close = [e for e in evs if e["type"] == "tag_close"][0]
    assert close["tag"] == "nxt1-delete"
    assert close["attrs"]["path"] == "x.txt"


def test_parser_edit_with_search_replace():
    p = TagStreamParser()
    src = """<nxt1-edit path="src/App.jsx">
  <search>const x = 1</search>
  <replace>const x = 2</replace>
</nxt1-edit>"""
    evs = _events(p, [src])
    close = [e for e in evs if e["type"] == "tag_close"][0]
    assert close["tag"] == "nxt1-edit"
    assert close["children"]["search"] == "const x = 1"
    assert close["children"]["replace"] == "const x = 2"


def test_parser_deps_install():
    p = TagStreamParser()
    src = '<nxt1-deps action="install">react-icons lucide-react</nxt1-deps>'
    evs = _events(p, [src])
    close = [e for e in evs if e["type"] == "tag_close"][0]
    assert close["attrs"]["action"] == "install"
    assert close["content"].strip() == "react-icons lucide-react"


def test_parser_prose_between_tags_emits_prose_event():
    p = TagStreamParser()
    src = 'Here is the change:\n<nxt1-write path="a.txt">x</nxt1-write>\nDone.'
    evs = _events(p, [src])
    prose_events = [e for e in evs if e["type"] == "prose"]
    assert prose_events
    text = "".join(e["text"] for e in prose_events)
    assert "Here is the change" in text and "Done." in text


def test_parser_unclosed_tag_at_end_surfaces_error():
    p = TagStreamParser()
    src = '<nxt1-write path="a.txt">partial content but no close'
    evs = _events(p, [src])
    err = [e for e in evs if e["type"] == "parse_error"]
    assert err, "expected parse_error for unclosed tag"


def test_parser_multiple_actions_in_order():
    p = TagStreamParser()
    src = """<nxt1-write path="a.txt">A</nxt1-write>
<nxt1-write path="b.txt">B</nxt1-write>
<nxt1-delete path="c.txt" />
<nxt1-explanation>did stuff</nxt1-explanation>"""
    evs = _events(p, [src])
    closes = [e for e in evs if e["type"] == "tag_close"]
    assert [e["tag"] for e in closes] == [
        "nxt1-write", "nxt1-write", "nxt1-delete", "nxt1-explanation"
    ]


# ─── apply tests ───────────────────────────────────────────────────────────

def test_apply_write_creates_then_edits():
    state = ApplyResult(files=[])
    # Create
    apply_tag_action(state, {
        "type": "tag_close", "tag": "nxt1-write",
        "attrs": {"path": "a.txt"}, "content": "hello"
    })
    assert state.files == [{"path": "a.txt", "content": "hello"}]
    assert state.receipts[0]["action"] == "created"
    # Overwrite
    apply_tag_action(state, {
        "type": "tag_close", "tag": "nxt1-write",
        "attrs": {"path": "a.txt"}, "content": "world"
    })
    assert state.files == [{"path": "a.txt", "content": "world"}]
    assert state.receipts[-1]["action"] == "edited"


def test_apply_edit_replaces_unique_snippet():
    state = ApplyResult(files=[
        {"path": "App.jsx", "content": "const title = 'old';\nexport default App;"}
    ])
    apply_tag_action(state, {
        "type": "tag_close", "tag": "nxt1-edit",
        "attrs": {"path": "App.jsx"},
        "children": {"search": "const title = 'old';",
                     "replace": "const title = 'new';"},
    })
    assert state.files[0]["content"] == "const title = 'new';\nexport default App;"
    assert state.receipts[-1]["action"] == "edited"


def test_apply_edit_rejects_ambiguous_search():
    state = ApplyResult(files=[
        {"path": "App.jsx", "content": "x\nx\nx"}
    ])
    with pytest.raises(TagApplyError):
        apply_tag_action(state, {
            "type": "tag_close", "tag": "nxt1-edit",
            "attrs": {"path": "App.jsx"},
            "children": {"search": "x", "replace": "y"},
        })
    # File untouched
    assert state.files[0]["content"] == "x\nx\nx"


def test_apply_edit_rejects_missing_snippet():
    state = ApplyResult(files=[
        {"path": "App.jsx", "content": "alpha\nbeta\n"}
    ])
    with pytest.raises(TagApplyError):
        apply_tag_action(state, {
            "type": "tag_close", "tag": "nxt1-edit",
            "attrs": {"path": "App.jsx"},
            "children": {"search": "gamma", "replace": "delta"},
        })


def test_apply_rename_then_delete():
    state = ApplyResult(files=[
        {"path": "a.txt", "content": "hello"}
    ])
    apply_tag_action(state, {
        "type": "tag_close", "tag": "nxt1-rename",
        "attrs": {"from": "a.txt", "to": "b.txt"}, "content": "",
    })
    assert state.files == [{"path": "b.txt", "content": "hello"}]
    apply_tag_action(state, {
        "type": "tag_close", "tag": "nxt1-delete",
        "attrs": {"path": "b.txt"}, "content": "",
    })
    assert state.files == []


def test_apply_deps_install_and_uninstall():
    state = ApplyResult(files=[])
    apply_tag_action(state, {
        "type": "tag_close", "tag": "nxt1-deps",
        "attrs": {"action": "install"}, "content": "react-icons lucide-react",
    })
    apply_tag_action(state, {
        "type": "tag_close", "tag": "nxt1-deps",
        "attrs": {"action": "uninstall"}, "content": "moment",
    })
    assert state.deps_install == ["react-icons", "lucide-react"]
    assert state.deps_uninstall == ["moment"]


def test_apply_explanation_and_notes_captured():
    state = ApplyResult(files=[])
    apply_tag_action(state, {
        "type": "tag_close", "tag": "nxt1-explanation",
        "attrs": {}, "content": "added Hero",
    })
    apply_tag_action(state, {
        "type": "tag_close", "tag": "nxt1-notes",
        "attrs": {}, "content": "run yarn add",
    })
    assert state.explanation == "added Hero"
    assert state.notes == "run yarn add"


def test_full_pipeline_parser_then_apply():
    """End-to-end: stream a multi-action response and verify final file state."""
    state = ApplyResult(files=[
        {"path": "src/App.jsx", "content": "const title = 'Old';"}
    ])
    p = TagStreamParser()
    src = """<nxt1-edit path="src/App.jsx">
  <search>const title = 'Old';</search>
  <replace>const title = 'Brand new';</replace>
</nxt1-edit>
<nxt1-write path="src/Footer.jsx">export default () => <footer>(c) NXT1</footer>;</nxt1-write>
<nxt1-explanation>Renamed title and added footer.</nxt1-explanation>"""
    for ev in p.feed(src):
        if ev["type"] == "tag_close":
            apply_tag_action(state, ev)
    for ev in p.finish():
        if ev["type"] == "tag_close":
            apply_tag_action(state, ev)
    paths = {f["path"] for f in state.files}
    assert paths == {"src/App.jsx", "src/Footer.jsx"}
    app = next(f for f in state.files if f["path"] == "src/App.jsx")
    assert "Brand new" in app["content"]
    assert state.explanation == "Renamed title and added footer."
    assert any(r["action"] == "edited" and r["path"] == "src/App.jsx"
                for r in state.receipts)
    assert any(r["action"] == "created" and r["path"] == "src/Footer.jsx"
                for r in state.receipts)
