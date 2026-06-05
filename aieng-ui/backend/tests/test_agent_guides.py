from __future__ import annotations


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
    assert "Re-read a guide only if" in result["content"]


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


def test_unknown_topic_reports_available_topics() -> None:
    from app import agent_guides

    result = agent_guides.guide_result("mystery")

    assert result["status"] == "error"
    assert result["code"] == "unknown_guide_topic"
    assert "cad" in result["available_topics"]
