from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "docs" / "canonical_engineering_scenarios.json"
DOC = ROOT / "docs" / "canonical_engineering_scenarios.md"
REQUIRED_PACK_IDS = {
    "value_demo_cantilever_real_cae",
    "fixture_plate_holes_fasteners_material",
    "mass_reduction_design_target_comparison",
    "mesh_diagnostics_failure_recovery",
    "sizing_sweep_ranked_candidates",
}


def _load_catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_canonical_engineering_scenario_catalog_is_structured() -> None:
    catalog = _load_catalog()

    assert catalog["schema_version"] == "0.1"
    assert catalog["policy"]["synthetic_results_as_real_evidence_allowed"] is False
    assert catalog["policy"]["real_tool_scenarios_must_be_skip_gated"] is True
    assert "must not mutate CAD" in catalog["policy"]["main_flow_safety"]

    scenarios = catalog["scenarios"]
    assert len(scenarios) >= 5
    ids = [scenario["id"] for scenario in scenarios]
    assert len(ids) == len(set(ids))

    required = {
        "id",
        "title",
        "priority",
        "capability_area",
        "status",
        "description",
        "entrypoints",
        "verification_commands",
        "expected_artifacts",
        "honesty_boundaries",
        "consumer_surfaces",
    }
    for scenario in scenarios:
        assert required <= set(scenario), scenario["id"]
        assert scenario["priority"] in {"P0", "P1", "P2"}
        assert scenario["entrypoints"], scenario["id"]
        assert scenario["verification_commands"], scenario["id"]
        assert scenario["expected_artifacts"], scenario["id"]
        assert scenario["honesty_boundaries"], scenario["id"]
        assert scenario["consumer_surfaces"], scenario["id"]


def test_canonical_engineering_scenarios_keep_real_tool_and_fixture_boundaries() -> None:
    catalog = _load_catalog()
    scenarios = catalog["scenarios"]

    assert any(
        command["ci_lightweight"]
        for scenario in scenarios
        for command in scenario["verification_commands"]
    )
    assert any(
        command.get("kind") == "real_tool_test" and command.get("skip_gated") is True
        for scenario in scenarios
        for command in scenario["verification_commands"]
    )

    value_demo = next(s for s in scenarios if s["id"] == "value_demo_cantilever_real_cae")
    assert "simulation/runs/value_demo_run_001/outputs/result.frd" in value_demo["expected_artifacts"]
    assert any("Synthetic fallback fields are a failed demo condition" in item for item in value_demo["honesty_boundaries"])

    for scenario in scenarios:
        text = " ".join(scenario["honesty_boundaries"]).lower()
        if "fixture" in text or "synthetic" in text:
            assert "real evidence" in text or "failed demo" in text or "solver evidence" in text


def test_canonical_engineering_scenario_doc_links_catalog_and_commands() -> None:
    doc = DOC.read_text(encoding="utf-8")

    assert "canonical_engineering_scenarios.json" in doc
    assert "python -m pytest aieng-ui/backend/tests/test_value_demo_packet.py -q" in doc
    assert "Preflight success is not solver success" in doc
    assert "must never be counted" in doc


def test_completed_canonical_scenarios_have_pack_runbooks() -> None:
    catalog = _load_catalog()
    completed_statuses = {"ci_regression", "operator_runbook"}

    for scenario in catalog["scenarios"]:
        if scenario["status"] not in completed_statuses:
            continue
        runbooks = [
            ROOT / entry
            for entry in scenario["entrypoints"]
            if entry.startswith("docs/") and entry.endswith(".md")
        ]
        assert runbooks, scenario["id"]
        assert any(path.exists() for path in runbooks), scenario["id"]


def test_current_five_canonical_scenario_packs_have_no_remaining_gaps() -> None:
    catalog = _load_catalog()
    by_id = {scenario["id"]: scenario for scenario in catalog["scenarios"]}

    assert REQUIRED_PACK_IDS <= set(by_id)
    for scenario_id in REQUIRED_PACK_IDS:
        scenario = by_id[scenario_id]
        assert scenario["status"] != "cataloged_gap"
        runbooks = [
            ROOT / entry
            for entry in scenario["entrypoints"]
            if entry.startswith("docs/") and entry.endswith(".md")
        ]
        assert runbooks, scenario["id"]
        assert any(path.exists() for path in runbooks), scenario["id"]


def test_design_and_sizing_pack_runbooks_preserve_honesty_boundaries() -> None:
    design = (ROOT / "docs" / "canonical-scenarios" / "design-study-demo.md").read_text(encoding="utf-8")
    sizing = (ROOT / "docs" / "canonical-scenarios" / "sizing-sweep-demo.md").read_text(encoding="utf-8")

    assert "python -m pytest aieng-ui/backend/tests/test_design_study_demo.py -q" in design
    assert "candidate-local static metrics" in design
    assert "not real solver evidence" in design
    assert "does not overwrite baseline" in design

    assert "python -m pytest aieng-ui/backend/tests/test_optimization_sizing_demo.py" in sizing
    assert "Static metrics are not solver evidence" in sizing
    assert "Baseline geometry remains unchanged" in sizing
    assert "No autonomous production design approval" in sizing


def test_fixture_and_mesh_pack_runbooks_preserve_honesty_boundaries() -> None:
    fixture = (ROOT / "docs" / "canonical-scenarios" / "fixture-fasteners-material.md").read_text(encoding="utf-8")
    mesh = (ROOT / "docs" / "canonical-scenarios" / "mesh-diagnostics-recovery.md").read_text(encoding="utf-8")

    assert "SocketHeadCapScrew" in fixture
    assert "standard_part" in fixture
    assert "does not model bolt preload" in fixture
    assert "not proof of preload" in fixture
    assert "Missing material must be reported as missing" in fixture

    assert "Preflight success is not solver success" in mesh
    assert "A prepared deck is not solver evidence" in mesh
    assert "Synthetic fields or fixture metrics must not be counted as real solver" in mesh
    assert "converged: null" in mesh
