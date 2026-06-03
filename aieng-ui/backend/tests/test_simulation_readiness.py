"""Deterministic /simulate readiness report (v1.5) — pure helper coverage."""

from app.agent_autopilot.simulation_readiness import (
    build_simulation_readiness_report,
    REQUIRED_INPUTS,
)


def _statuses(report: dict) -> dict[str, str]:
    return {name: meta["status"] for name, meta in report["inputs"].items()}


def test_no_setup_is_not_found_with_required_missing() -> None:
    report = build_simulation_readiness_report(None)
    assert report["setup_source"] == "not_found"
    assert report["solver_executed"] is False
    assert report["ready_for_solver"] is False
    s = _statuses(report)
    assert s["material"] == "missing"
    assert s["loads"] == "missing"
    assert s["constraints"] == "missing"
    # Defaultable inputs still default even without a setup.
    assert s["analysis_type"] == "defaultable"
    assert s["mesh"] == "defaultable"
    assert s["solver"] == "defaultable"
    assert report["missing_required_inputs"] == list(REQUIRED_INPUTS)
    assert "Missing REQUIRED inputs" in report["summary"]
    assert "do NOT claim" in report["summary"]


def test_empty_cae_block_is_not_found() -> None:
    report = build_simulation_readiness_report({})
    assert report["setup_source"] == "not_found"
    assert report["missing_required_inputs"] == list(REQUIRED_INPUTS)


def test_partial_setup_material_only() -> None:
    report = build_simulation_readiness_report({"present": True, "materials_count": 1})
    assert report["setup_source"] == "cae_setup"
    s = _statuses(report)
    assert s["material"] == "present"
    assert s["loads"] == "missing"
    assert s["constraints"] == "missing"
    assert report["missing_required_inputs"] == ["loads", "constraints"]
    assert report["ready_for_solver"] is False


def test_complete_setup_is_ready_but_solver_not_run() -> None:
    cae = {
        "present": True,
        "materials": ["steel"],
        "loads": [{"type": "force", "magnitude": 500}],
        "boundary_conditions": [{"type": "fixed"}],
    }
    report = build_simulation_readiness_report(cae)
    assert report["setup_source"] == "cae_setup"
    s = _statuses(report)
    assert s["material"] == "present"
    assert s["loads"] == "present"
    assert s["constraints"] == "present"
    # mesh/solver/analysis_type are defaultable for planning.
    assert s["mesh"] == "defaultable"
    assert s["solver"] == "defaultable"
    assert s["analysis_type"] == "defaultable"
    assert report["missing_required_inputs"] == []
    assert report["ready_for_solver"] is True
    assert report["solver_executed"] is False
    assert "All required inputs" in report["summary"]
    assert "solver has NOT been run" in report["summary"]


def test_constraints_via_count_key() -> None:
    cae = {"materials_count": 1, "loads_count": 2, "constraints_count": 3}
    report = build_simulation_readiness_report(cae)
    assert _statuses(report)["constraints"] == "present"
    assert report["missing_required_inputs"] == []


def test_explicit_analysis_mesh_solver_present() -> None:
    cae = {
        "materials": ["al"],
        "loads": ["L1"],
        "boundary_conditions": ["B1"],
        "analysis_type": "modal",
        "mesh": {"element_size": 2.0},
        "solver": "CalculiX",
    }
    report = build_simulation_readiness_report(cae)
    s = _statuses(report)
    assert s["analysis_type"] == "present"
    assert s["mesh"] == "present"
    assert s["solver"] == "present"
    assert report["inputs"]["analysis_type"]["detail"] == "modal"
    assert report["defaultable_inputs"] == []


def test_explicitly_unavailable_mesh_and_solver_are_unknown() -> None:
    cae = {
        "materials": ["al"],
        "loads": ["L1"],
        "boundary_conditions": ["B1"],
        "mesh": False,  # explicitly unavailable
        "solver_status": {"available": False},
    }
    report = build_simulation_readiness_report(cae)
    s = _statuses(report)
    assert s["mesh"] == "unknown"
    assert s["solver"] == "unknown"
    # Required still satisfied — unknown defaultables do not block readiness.
    assert report["ready_for_solver"] is True


def test_fea_setup_draft_satisfies_required_inputs() -> None:
    cae = {
        "fea_setup_draft": {
            "material": {"name": "steel"},
            "load_cases": [{"force": 100}],
            "supports": [{"face": "f1"}],
        }
    }
    report = build_simulation_readiness_report(cae)
    assert report["setup_source"] == "cae_setup"
    assert report["missing_required_inputs"] == []


def test_mention_targets_known_unknown_and_unverified() -> None:
    report = build_simulation_readiness_report(
        {"materials": ["s"], "loads": ["l"], "boundary_conditions": ["b"]},
        mentioned_parts=["bracket", "ghost"],
        mentioned_artifacts=["model.glb"],
        available_parts=["bracket", "rib"],
        available_artifacts=None,  # cannot determine → unverified (None)
    )
    parts = {t["value"]: t["known"] for t in report["targets"]["parts"]}
    assert parts["bracket"] is True
    assert parts["ghost"] is False
    arts = {t["value"]: t["known"] for t in report["targets"]["artifacts"]}
    assert arts["model.glb"] is None
    assert "bracket (known)" in report["summary"]
    assert "ghost (NOT FOUND)" in report["summary"]
    assert "model.glb (unverified)" in report["summary"]
