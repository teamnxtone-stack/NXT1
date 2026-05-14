"""Extract the Agents + OpenClaw skill catalogues into a single JSON.

Both source repos use YAML-frontmatter + Markdown body for each unit
(agent or skill). This script walks both trees, parses the frontmatter
once, normalises to a single shape, and writes the merged catalog to
`backend/data/agents_catalog.json`.

We DO NOT redistribute the body text — the catalog only stores the
machine-readable metadata + a short description. The full prompts stay
in the source repos. NXT1 only consumes the catalog to render its
browsing UI.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path("/app")
AGENTS_REPO = Path("/tmp/zips/agents/agents-main")
OPENCLAW_REPO = Path("/tmp/zips/openclaw/openclaw-main")
OUT_PATH = ROOT / "backend" / "data" / "agents_catalog.json"

# Normalize category labels from the plugin folder name.
def humanize(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.replace("_", "-").split("-"))


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse very simple YAML-frontmatter (one-level k:v pairs).
    We don't pull pyyaml — both source repos only emit flat scalars.
    """
    m = FRONTMATTER_RE.match(text or "")
    if not m:
        return {}, (text or "")
    fm_raw, body = m.group(1), m.group(2)
    out: dict = {}
    cur_key = None
    cur_val: list[str] = []
    for line in fm_raw.splitlines():
        # Continuation: line starts with whitespace and we have a key being built.
        if line.startswith((" ", "\t")) and cur_key is not None:
            cur_val.append(line.strip())
            continue
        if ":" in line:
            if cur_key is not None:
                out[cur_key] = " ".join(cur_val).strip()
            k, v = line.split(":", 1)
            cur_key = k.strip()
            cur_val = [v.strip()]
        # else ignore
    if cur_key is not None:
        out[cur_key] = " ".join(cur_val).strip()
    return out, body


def first_h1_or_first_line(body: str, fallback: str) -> str:
    for line in (body or "").splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:160]
    return fallback


def gather_agents() -> list[dict]:
    out: list[dict] = []
    plugins_dir = AGENTS_REPO / "plugins"
    if not plugins_dir.exists():
        return out
    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not plugin_dir.is_dir():
            continue
        agents_dir = plugin_dir / "agents"
        if not agents_dir.exists():
            continue
        category = humanize(plugin_dir.name)
        for md in sorted(agents_dir.glob("*.md")):
            try:
                text = md.read_text(encoding="utf-8")
            except Exception:
                continue
            fm, body = parse_frontmatter(text)
            name = fm.get("name") or md.stem
            desc = fm.get("description") or first_h1_or_first_line(body, "")
            # Trim noisy "Use PROACTIVELY..." tail that shows in many agents.
            desc_clean = re.split(r"\bUse PROACTIVELY\b", desc, maxsplit=1)[0].strip()
            if desc_clean.endswith("."):
                pass
            elif desc_clean:
                desc_clean = desc_clean.rstrip(",;:") + "."
            out.append({
                "id":        f"agent::{plugin_dir.name}::{md.stem}",
                "kind":      "agent",
                "source":    "agents",
                "name":      name,
                "slug":      md.stem,
                "category":  category,
                "plugin":    plugin_dir.name,
                "model":     fm.get("model") or "inherit",
                "description": desc_clean[:280] or "Specialised AI agent.",
                # Full body (the system prompt the agent runs with). Limited
                # to 18KB to keep the catalog tractable; almost every agent
                # is well under that.
                "system_prompt": (body or "").strip()[:18000],
            })
    return out


def gather_skills() -> list[dict]:
    out: list[dict] = []
    skills_dir = OPENCLAW_REPO / "skills"
    if not skills_dir.exists():
        return out
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        md_path = skill_dir / "SKILL.md"
        text = ""
        if md_path.exists():
            try:
                text = md_path.read_text(encoding="utf-8")
            except Exception:
                pass
        fm, body = parse_frontmatter(text)
        # OpenClaw SKILL.md has no frontmatter — fall back to the first H1
        # ("# Canvas Skill") and the first non-empty paragraph.
        title = (fm.get("name") or
                 (next((ln.strip().lstrip("#").strip()
                        for ln in (body or text).splitlines()
                        if ln.strip().startswith("#")), "")) or
                 skill_dir.name.replace("-", " ").title())
        # First paragraph after the H1 for description.
        desc = ""
        lines = (body or text).splitlines()
        seen_h1 = False
        para: list[str] = []
        for ln in lines:
            if ln.strip().startswith("#"):
                if seen_h1 and para:
                    break
                seen_h1 = True
                continue
            if not seen_h1:
                continue
            if not ln.strip():
                if para:
                    break
                continue
            para.append(ln.strip())
            if sum(len(p) for p in para) > 240:
                break
        desc = " ".join(para).strip()[:280] or "OpenClaw skill."
        out.append({
            "id":          f"skill::{skill_dir.name}",
            "kind":        "skill",
            "source":      "openclaw",
            "name":        title.removesuffix(" Skill").strip(),
            "slug":        skill_dir.name,
            "category":    "Personal Assistant",
            "channel":     None,
            "description": desc,
            # OpenClaw skill body becomes the system prompt when the user
            # asks "use this skill to ..." through NXT1. Limited to 18KB.
            "system_prompt": ((body or text) or "").strip()[:18000],
        })
    return out


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    agents = gather_agents()
    skills = gather_skills()
    catalog = {
        "version": 1,
        "generated_from": ["wshobson/agents", "openclaw/openclaw"],
        "agents_count": len(agents),
        "skills_count": len(skills),
        "items": agents + skills,
    }
    OUT_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
    cats = sorted({i["category"] for i in catalog["items"]})
    print(f"Wrote {OUT_PATH}")
    print(f"  {len(agents)} agents · {len(skills)} skills · {len(cats)} categories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
