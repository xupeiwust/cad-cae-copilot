from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


SKILLS_ROOT = Path(__file__).resolve().parents[4] / "aieng-agent-skills" / "skills"
_DESCRIPTION_LIMIT = 420
_INTRO_LIMIT = 100
_SECTION_LIMIT = 130
_EXCERPT_LIMIT = 560
_PREFERRED_HEADINGS = {
    "purpose",
    "what this skill does",
    "when to use / when not to use",
    "operating rules",
    "hard rules",
}


def _truncate(text: str, limit: int) -> str:
    clean = "\n".join(line.rstrip() for line in text.strip().splitlines() if line.strip())
    if len(clean) <= limit:
        return clean
    suffix = "...[truncated]"
    if limit <= len(suffix):
        return clean[:limit]
    return f"{clean[: limit - len(suffix)]}{suffix}"


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    return meta if isinstance(meta, dict) else {}, parts[2]


def _first_sections(body: str) -> str:
    """Return compact trigger/rule excerpts from a SKILL.md file."""
    lines = body.strip().splitlines()
    chunks: list[str] = []
    intro: list[str] = []
    idx = 0
    while idx < len(lines) and not lines[idx].startswith("## "):
        intro.append(lines[idx])
        idx += 1
    if intro:
        chunks.append(_truncate("\n".join(intro), _INTRO_LIMIT))

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if not line.startswith("## "):
            idx += 1
            continue
        heading = line[3:].strip().lower()
        if heading not in _PREFERRED_HEADINGS:
            idx += 1
            continue
        section = [line]
        idx += 1
        while idx < len(lines) and not lines[idx].startswith("## "):
            section.append(lines[idx])
            idx += 1
        chunks.append(_truncate("\n".join(section), _SECTION_LIMIT))
    return _truncate("\n".join(chunks), _EXCERPT_LIMIT)


@lru_cache(maxsize=1)
def discover_project_skills() -> list[dict[str, Any]]:
    """Discover project-local AIENG behavior skills.

    These are not executable tools. They are compact behavior contracts injected
    into the local-agent prompt so the agent can choose the right workflow before
    calling runtime tools.
    """
    if not SKILLS_ROOT.exists():
        return []
    skills: list[dict[str, Any]] = []
    for skill_file in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        meta, body = _split_frontmatter(text)
        name = str(meta.get("name") or skill_file.parent.name)
        description = str(meta.get("description") or "")
        skills.append(
            {
                "name": name,
                "description": _truncate(description, _DESCRIPTION_LIMIT),
                "source_path": str(skill_file.relative_to(SKILLS_ROOT.parent.parent)),
                "instruction_excerpt": _first_sections(body),
            }
        )
    return skills


def project_skill_context() -> dict[str, Any]:
    skills = discover_project_skills()
    return {
        "root": str(SKILLS_ROOT),
        "activation_policy": (
            "Before planning or selecting a tool, compare the user's objective "
            "against each skill description. Apply matching skills as behavior "
            "contracts, but do not invent tools from them. If a skill describes "
            "legacy CLI flow that conflicts with active workbench tools, prefer "
            "the active workbench runtime unless the user explicitly requests "
            "the legacy/schema-bound workflow."
        ),
        "skills": skills,
    }


__all__ = ["discover_project_skills", "project_skill_context"]
