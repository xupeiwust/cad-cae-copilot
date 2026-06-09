from __future__ import annotations

import pytest


def test_quickstart_is_compact_and_preserves_first_three_calls() -> None:
    from app import agent_guides

    result = agent_guides.quickstart_result()

    assert result["mode"] == "quickstart"
    assert len(result["content"]) < 8_000
    assert "aieng.agent_readme" in result["content"]
    assert "aieng.list_projects" in result["content"]
    assert "aieng.agent_context" in result["content"]
    assert "aieng.guide" in result["content"]
    assert "Before the first CAD modeling or geometry-edit action" in result["content"]
    assert "cad.confirm_modeling_plan" in result["content"]
    assert "AskUserQuestion" in result["content"]
    assert "request_user_input" in result["content"]
    assert "Re-read a guide only if" in result["content"]
    assert 'code: "guide_required"' in result["content"]


def test_full_guide_compatibility_mode_returns_canonical_agents_md() -> None:
    from app import agent_guides

    result = agent_guides.full_result()

    assert result["mode"] == "full"
    assert result["path"].endswith("AGENTS.md")
    assert len(result["content"]) > 50_000
    assert "## What the workbench can actually do" in result["content"]


def test_topic_guide_extracts_only_requested_sections() -> None:
    from app import agent_guides

    result = agent_guides.guide_result("pointers")

    assert result["mode"] == "topic"
    assert result["topic"] == "pointers"
    assert "## Pointer syntax" in result["content"]
    assert "## Fallback mode" not in result["content"]


def test_cad_topic_keeps_feedback_loop_after_python_comments() -> None:
    from app import agent_guides

    content = agent_guides.guide_result("cad")["content"]

    assert "# step 2, mode=append" in content
    assert "**Visual feedback (multi-view contact sheet).**" in content
    assert "**Iterate using fail-first review.**" in content
    assert "**Reference image calibration.**" in content
    assert "**Quantitative geometry report (`geometry_report`).**" in content
    assert "**Regression diff on every edit (`regression_diff`).**" in content
    assert "### B2 — Incremental modeling (the sustainable loop)" in content
    assert "## Approval-gated tools" in content
    assert "## Stale-artifact warnings" in content


@pytest.mark.parametrize(
    ("topic", "required_fragments"),
    [
        (
            "cae",
            (
                "## Pointer syntax — `@kind:id`",
                "**Free-form faces and CAE.**",
                "### C — CAD → CAE simulation pipeline",
                "### D — Inspect results and explain findings",
                "## Approval-gated tools",
                "## Stale-artifact warnings",
                "### Assembly IR v0 (optional, multi-part)",
                "contact_physics_modeled:false",
            ),
        ),
        (
            "frontend",
            (
                "## Workspace layout",
                "## Frontend maintainability rules",
                "### Agent run display state",
                "### Composer slash commands and @-mentions",
                "**Natural-language intent resolution",
            ),
        ),
        (
            "workflows",
            (
                "## Pointer syntax — `@kind:id`",
                "## Recommended workflows",
                "## Approval-gated tools",
                "## Stale-artifact warnings",
            ),
        ),
        (
            "tools",
            (
                "## STOP — read this first",
                "## First three calls every session",
                "## Tool taxonomy",
                "## Approval-gated tools",
            ),
        ),
        (
            "package",
            (
                "### Package lifecycle",
                "## Approval-gated tools",
                "## Stale-artifact warnings",
                "## .aieng package structure (reference)",
            ),
        ),
        (
            "approvals",
            (
                "## Tool taxonomy",
                "## Approval-gated tools",
                "## If the backend (port 8000) is unreachable",
                "`AIENG_MCP_MANAGED_APPROVAL`",
                "`AIENG_MCP_BLOCK_APPROVAL_TOOLS`",
            ),
        ),
        (
            "operators",
            (
                "## Workspace layout",
                "## Approval-gated tools",
                "## If the backend (port 8000) is unreachable",
                "## Environment variables (for MCP server operators)",
                "`AIENG_MCP_MANAGED_APPROVAL`",
                "`AIENG_MCP_REQUIRE_GUIDES`",
                "`AIENG_AGENTIC_PERMISSION_TOOL`",
            ),
        ),
    ],
)
def test_topic_guides_include_task_complete_operational_context(
    topic: str,
    required_fragments: tuple[str, ...],
) -> None:
    from app import agent_guides

    content = agent_guides.guide_result(topic)["content"]

    for fragment in required_fragments:
        assert fragment in content, f"{topic} guide is missing {fragment!r}"


def test_all_configured_topic_sections_exist_in_canonical_guide() -> None:
    from app import agent_guides

    markdown, _ = agent_guides.read_full_guide()

    for topic, sections in agent_guides.TOPIC_SECTIONS.items():
        content = agent_guides._extract_sections(markdown, sections)
        for section in sections:
            assert agent_guides._extract_sections(markdown, (section,)) != (
                "Requested guide sections were not found in AGENTS.md."
            ), f"{topic} references missing canonical section {section!r}"
        assert content != "Requested guide sections were not found in AGENTS.md."


def test_section_extraction_ignores_markdown_headings_inside_fences() -> None:
    from app import agent_guides

    markdown = """\
## Keep
```python
# This is Python, not a Markdown heading
value = 1
```
still kept
## Drop
not kept
"""

    extracted = agent_guides._extract_sections(markdown, ("Keep",))

    assert "still kept" in extracted
    assert "not kept" not in extracted


def test_unknown_topic_reports_available_topics() -> None:
    from app import agent_guides

    result = agent_guides.guide_result("mystery")

    assert result["status"] == "error"
    assert result["code"] == "unknown_guide_topic"
    assert "cad" in result["available_topics"]
