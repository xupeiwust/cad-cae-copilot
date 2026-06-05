"""Compact, topic-addressable agent onboarding derived from root AGENTS.md."""
from __future__ import annotations

from pathlib import Path
from typing import Any


QUICKSTART = """\
# aieng Workbench — MCP Quickstart

Use the `aieng-workbench` MCP tools as the primary interface. Do not browse
`aieng/src/` to discover runtime CAD capabilities; active CAD/CAE execution is
implemented in `aieng-ui/backend`.

## First three calls

1. `aieng.agent_readme` — this compact operational guide.
2. `aieng.list_projects` — discover project IDs.
3. `aieng.agent_context {project_id}` — inspect current geometry, pointers,
   stale-artifact warnings, CAE state, and suggested next steps.

## Core operating rules

- Use `cad.execute_build123d` for geometry creation/add/remove. Bind the final
  model to `result`; do not export manually. Name parts with `.label`, color
  them with `.color`, and declare editable dimensions as UPPER_SNAKE_CASE.
- Use `mode="append"` only after `cad.get_source` reports an existing base.
- Use `cad.edit_parameter` for pure dimensional changes and inspect its
  `regression_diff`.
- After CAD generation, inspect the returned four-view thumbnail plus
  `geometry_report`; do not judge geometry only from face counts.
- Use `@face:...`, `@feature:...`, `@part:...`, and `@artifact:...` pointers
  verbatim. Never invent a pointer.
- Inspect CAE readiness before simulation. Material, loads, and constraints are
  required. Never claim solver results unless `cae.run_solver` returned
  successful evidence.
- Approval-gated tools remain approval-gated. Never bypass or imply approval.
- A normal `cad.execute_build123d` call writes/updates the project's `.aieng`
  package by default. `write_files=false` is an explicit no-write exception.

## Common workflows

- Inspect: `aieng.agent_context` → `aieng.inspect_package` as needed.
- Build: context → `cad.get_source` → `cad.execute_build123d` → visual/numeric
  review → iterate → `cad.critique` for engineering parts.
- Modify dimension: context → `cad.list_editable_parameters` or source context
  → `cad.edit_parameter` → inspect `regression_diff`.
- Simulate: context/readiness → complete setup → `cae.prepare_solver_run` →
  generate input if needed → approved `cae.run_solver` → extract/postprocess.

## Detailed guides

Call `aieng.guide {topic}` only when the task needs more detail. Available
topics: `cad`, `cae`, `pointers`, `tools`, `workflows`, `package`, `fallback`,
`frontend`, `approvals`, `operators`, and `full`.

Before the first CAD modeling or geometry-edit action in a session, read
`aieng.guide {topic:"cad"}` once. Before the first simulation-planning or solver
action, read `aieng.guide {topic:"cae"}` once. Re-read a guide only if the session
lost that context or the guide changed. This preserves detailed discipline
without repeatedly spending tokens on unchanged guidance.

The MCP server enforces these category reads before CAD, CAE/post-processing/
topology-optimization, and package-lifecycle tools. If a read was skipped, the
tool returns `code: "guide_required"` with the exact `next_call` and does not
execute or request approval. Reading the `full` guide unlocks all categories.
"""


TOPIC_SECTIONS: dict[str, tuple[str, ...]] = {
    "cad": (
        "Real 3D CAD modeling (no API key needed)",
        "Industrial Design Mode — escape primitive stacking",
        "High-level helpers — prefer these over hand-rolled boilerplate",
        "Curve patterns — copy + adapt (when a helper doesn't fit)",
        "Engineering Mode — well-formed mechanical parts",
        "Pointer syntax — `@kind:id`",
        "B — CAD generation from scratch",
        "B2 — Incremental modeling (the sustainable loop)",
        "E — Parametric modification (design iteration)",
        "Approval-gated tools",
        "Stale-artifact warnings",
        "Common mistakes to avoid",
    ),
    "cae": (
        "Structural FEA (CalculiX)",
        "Pointer syntax — `@kind:id`",
        "CAE setup (no approval)",
        "Simulation execution (requires approval — runs external CalculiX)",
        "Post-processing (no approval)",
        "C — CAD → CAE simulation pipeline",
        "D — Inspect results and explain findings",
        "Approval-gated tools",
        "Stale-artifact warnings",
        "Assembly IR v0 (optional, multi-part)",
    ),
    "pointers": ("Pointer syntax — `@kind:id`",),
    "tools": (
        "STOP — read this first",
        "First three calls every session",
        "Tool taxonomy",
        "Approval-gated tools",
    ),
    "workflows": (
        "Pointer syntax — `@kind:id`",
        "Recommended workflows",
        "Approval-gated tools",
        "Stale-artifact warnings",
    ),
    "package": (
        "Package lifecycle",
        "Approval-gated tools",
        "Stale-artifact warnings",
        ".aieng package structure (reference)",
    ),
    "fallback": (
        "If the backend (port 8000) is unreachable",
        "Fallback mode — when you do not have MCP tools",
        "Common mistakes to avoid",
    ),
    "frontend": (
        "Workspace layout",
        "Development path rules",
        "Frontend maintainability rules",
    ),
    "approvals": (
        "Tool taxonomy",
        "Approval-gated tools",
        "If the backend (port 8000) is unreachable",
        "Environment variables (for MCP server operators)",
    ),
    "operators": (
        "Workspace layout",
        "Approval-gated tools",
        "If the backend (port 8000) is unreachable",
        "Environment variables (for MCP server operators)",
    ),
}


def canonical_agents_path() -> Path:
    parents = Path(__file__).resolve().parents
    backend_root = parents[1]
    workspace_root = parents[3]
    candidates = (workspace_root / "AGENTS.md", backend_root / "AGENTS.md")
    return next((path for path in candidates if path.exists()), candidates[0])


def read_full_guide() -> tuple[str, Path]:
    path = canonical_agents_path()
    if not path.exists():
        return "AGENTS.md not found.", path
    return path.read_text(encoding="utf-8"), path


def available_topics() -> list[str]:
    return [*TOPIC_SECTIONS, "full"]


def quickstart_result() -> dict[str, Any]:
    _, path = read_full_guide()
    return {
        "content": QUICKSTART,
        "path": str(path),
        "mode": "quickstart",
        "available_topics": available_topics(),
        "detail_hint": "MANDATORY: Call aieng.guide {topic} once per session before the first action of that category. Topic map — cad: geometry creation/edit, cae: simulation/solver, workflows: multi-step pipelines, approvals: gated tools, operators: admin actions, pointers: entity selection, package: import/export/lifecycle, fallback: non-MCP mode, frontend: UI development, tools: tool taxonomy, full: complete rules. Re-read only if session context was lost or the guide changed. Full reference: aieng.agent_readme {detail:'full'}."
    }


def full_result() -> dict[str, Any]:
    content, path = read_full_guide()
    return {
        "content": content,
        "path": str(path),
        "mode": "full",
        "available_topics": available_topics(),
    }


def guide_result(topic: str) -> dict[str, Any]:
    normalized = topic.strip().lower()
    if normalized == "full":
        return full_result()
    sections = TOPIC_SECTIONS.get(normalized)
    if not sections:
        return {
            "status": "error",
            "code": "unknown_guide_topic",
            "message": f"Unknown guide topic: {topic}",
            "available_topics": available_topics(),
        }
    content, path = read_full_guide()
    extracted = _extract_sections(content, sections)
    return {
        "content": extracted,
        "path": str(path),
        "mode": "topic",
        "topic": normalized,
        "sections": list(sections),
        "available_topics": available_topics(),
    }


def _extract_sections(markdown: str, requested: tuple[str, ...]) -> str:
    lines = markdown.splitlines()
    selected: list[str] = []
    requested_set = set(requested)
    active_level: int | None = None
    fence_marker: str | None = None
    for line in lines:
        stripped = line.lstrip()
        if fence_marker is not None:
            heading = None
            if stripped.startswith(fence_marker):
                fence_marker = None
        elif stripped.startswith("```") or stripped.startswith("~~~"):
            fence_marker = stripped[:3]
            heading = None
        else:
            heading = _heading(line)
        if heading:
            level, title = heading
            if active_level is not None and level <= active_level:
                active_level = None
            if title in requested_set:
                if selected and selected[-1] != "":
                    selected.append("")
                active_level = level
        if active_level is not None:
            selected.append(line)
    return "\n".join(selected).strip() or "Requested guide sections were not found in AGENTS.md."


def _heading(line: str) -> tuple[int, str] | None:
    stripped = line.lstrip()
    hashes = len(stripped) - len(stripped.lstrip("#"))
    if hashes < 1 or hashes > 6 or len(stripped) <= hashes or stripped[hashes] != " ":
        return None
    return hashes, stripped[hashes + 1 :].strip()
