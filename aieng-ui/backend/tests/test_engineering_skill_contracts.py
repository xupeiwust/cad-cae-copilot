"""Contract checks for agent-facing CAD/CAE skill catalog (#429)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parents[3] / "aieng-agent-skills" / "skills" / "engineering_skill_contracts.json"
SKILLS_DIR = CATALOG_PATH.parent

EXPECTED_SKILLS = {
    "cae-preflight",
    "design-target-review",
    "cad-mod-propose-verify",
    "solver-run-orchestrate",
    "evidence-report-synthesize",
}

MUTATING_OR_RESULT_TOOLS = {
    "cad.edit_parameter",
    "cad.execute_build123d",
    "cae.run_solver",
    "cae.extract_solver_results",
    "cae.extract_field_regions",
    "postprocess.refresh_cae_summary",
    "report.generate_engineering_report",
    "target.compare_design_targets",
}


def _catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_engineering_skill_contract_catalog_exists_and_lists_initial_skills() -> None:
    catalog = _catalog()
    assert catalog["format_version"] == "0.1.0"
    assert catalog["catalog_id"] == "aieng.engineering_skill_contracts"
    assert {skill["id"] for skill in catalog["skills"]} == EXPECTED_SKILLS


def test_each_skill_contract_has_required_fail_closed_fields() -> None:
    for skill in _catalog()["skills"]:
        assert skill["title"]
        assert skill["purpose"]
        assert skill["required_inputs"], skill["id"]
        assert skill["allowed_tools"], skill["id"]
        assert skill["refusal_conditions"], skill["id"]
        assert skill["outputs"], skill["id"]
        assert skill["verification_scenario"], skill["id"]
        assert skill["claim_advancement"] == "none"
        assert any("missing" in item.lower() or "approval" in item.lower() for item in skill["refusal_conditions"])


def test_mutating_or_result_writing_skills_require_approval() -> None:
    for skill in _catalog()["skills"]:
        allowed_tools = set(skill["allowed_tools"])
        evidence_written = list(skill["evidence_written"])
        writes_report_or_results = any(path.startswith(("results/", "reports/")) for path in evidence_written)
        touches_mutating_tool = bool(allowed_tools & MUTATING_OR_RESULT_TOOLS)
        if writes_report_or_results or touches_mutating_tool:
            assert skill["approval_required"] is True, skill["id"]


def test_solver_or_cad_skills_keep_approval_and_preflight_boundaries() -> None:
    by_id = {skill["id"]: skill for skill in _catalog()["skills"]}
    solver = by_id["solver-run-orchestrate"]
    cad = by_id["cad-mod-propose-verify"]
    report = by_id["evidence-report-synthesize"]

    assert "structural_adapter.preflight" in solver["allowed_tools"]
    assert any("approval" in item.lower() for item in solver["refusal_conditions"])
    assert any("FreeCADCmd" in item or "CalculiX" in item for item in solver["required_inputs"])
    assert "cad.confirm_modeling_plan" in cad["allowed_tools"]
    assert any("protected" in item.lower() for item in cad["refusal_conditions"])
    assert any("claim" in item.lower() for item in report["refusal_conditions"])


def test_global_safety_rules_forbid_overclaiming_and_bypass() -> None:
    rules = " ".join(_catalog()["global_safety_rules"]).lower()
    assert "approval gates" in rules
    assert "do not bypass" in rules
    assert "do not advance engineering claims" in rules
    assert "certification" in rules


def test_existing_cae_skills_point_agents_to_contract_catalog() -> None:
    for rel_path in [
        "aieng-cad-cae-copilot/SKILL.md",
        "aieng-closed-loop-copilot/SKILL.md",
    ]:
        text = (SKILLS_DIR / rel_path).read_text(encoding="utf-8")
        assert "engineering_skill_contracts.json" in text
        assert "approval" in text.lower()
