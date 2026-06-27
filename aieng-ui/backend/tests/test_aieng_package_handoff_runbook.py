from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = ROOT / "docs" / "aieng-package-handoff.md"
README = ROOT / "README.md"


def test_package_handoff_runbook_defines_send_receive_flow() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "## Send" in text
    assert "## Receive" in text
    assert "## Safe Agent Prompt" in text
    assert "## Honesty Boundary" in text
    assert "Mission Control" in text
    assert "review support packet" in text
    assert "existing approval gates" in text


def test_package_handoff_runbook_names_evidence_members_and_claim_boundary() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    required_members = [
        "manifest.json",
        "geometry/topology_map.json",
        "graph/feature_graph.json",
        "simulation/setup.yaml",
        "simulation/cae_mapping.json",
        "results/evidence_index.json",
        "results/result_summary.json",
        "results/computed_metrics.json",
        "provenance/tool_trace.json",
        "validation/evidence_report.json",
        "ai/claim_map.json",
        "README_FOR_AI.md",
        "ai/summary.md",
    ]
    for member in required_members:
        assert member in text

    assert "Package completeness is not certification" in text
    assert "A solver preflight is not solver execution" in text
    assert "A result artifact is evidence, not automatic claim advancement" in text
    assert "Do not mutate CAD" in text
    assert "Report only evidence-backed facts" in text


def test_package_handoff_docs_avoid_overclaiming_language() -> None:
    text = RUNBOOK.read_text(encoding="utf-8").lower()

    forbidden = [
        "production-ready",
        "production ready",
        "certified package",
        "certified results",
        "guaranteed safe",
        "guarantees safety",
    ]
    for phrase in forbidden:
        assert phrase not in text


def test_readme_links_package_handoff_runbook() -> None:
    text = README.read_text(encoding="utf-8")

    assert "docs/aieng-package-handoff.md" in text
    assert "portable engineering evidence passport" in text
