"""Deterministic /simulate solver workflow state (v3) — pure helper coverage."""

from app.agent_autopilot.simulation_workflow import (
    build_simulation_workflow_state,
    final_claims_results,
)


def _readiness(*, ready: bool, missing=None, targets=None) -> dict:
    return {
        "ready_for_solver": ready,
        "missing_required_inputs": missing or [],
        "targets": targets or {"parts": [], "artifacts": []},
    }


def test_incomplete_setup_blocks_prepare() -> None:
    wf = build_simulation_workflow_state(_readiness(ready=False, missing=["material", "loads"]))
    assert wf["ready_to_prepare_solver_run"] is False
    assert wf["solver_deck_prepared"] is False
    assert wf["ready_to_run_solver"] is False
    assert wf["solver_executed"] is False
    assert wf["solver_status"] == "blocked_missing_inputs"
    assert wf["missing_required_inputs"] == ["material", "loads"]


def test_complete_setup_ready_to_prepare() -> None:
    wf = build_simulation_workflow_state(_readiness(ready=True))
    assert wf["ready_to_prepare_solver_run"] is True
    assert wf["solver_deck_prepared"] is False
    assert wf["ready_to_run_solver"] is False
    assert wf["solver_run_approval_required"] is False
    assert wf["solver_status"] == "ready_to_prepare"


def test_prepared_deck_is_ready_to_run_with_approval() -> None:
    wf = build_simulation_workflow_state(
        _readiness(ready=True),
        prepared={"deck_path": "cae/sim.inp", "manifest_path": "cae/manifest.json"},
    )
    assert wf["solver_deck_prepared"] is True
    assert wf["deck_path"] == "cae/sim.inp"
    assert wf["manifest_path"] == "cae/manifest.json"
    assert wf["ready_to_run_solver"] is True
    assert wf["solver_run_approval_required"] is True
    assert wf["solver_executed"] is False
    assert wf["solver_status"] == "deck_prepared"


def test_executed_success_reports_results() -> None:
    wf = build_simulation_workflow_state(
        _readiness(ready=True),
        prepared={"deck_path": "cae/sim.inp"},
        executed={"status": "completed", "result_artifacts": ["results/stress.frd"]},
    )
    assert wf["solver_executed"] is True
    assert wf["solver_status"] == "executed"
    assert wf["result_artifacts"] == ["results/stress.frd"]
    assert wf["ready_to_run_solver"] is False  # already ran


def test_executed_failure_is_not_executed() -> None:
    wf = build_simulation_workflow_state(
        _readiness(ready=True),
        prepared={"deck_path": "cae/sim.inp"},
        executed={"status": "error", "error": "solver diverged"},
    )
    assert wf["solver_executed"] is False
    assert wf["solver_status"] == "failed"
    assert wf["result_artifacts"] == []


def test_unknown_target_blocks_prepare_and_run() -> None:
    targets = {"parts": [{"value": "ghost", "known": False}], "artifacts": []}
    wf = build_simulation_workflow_state(_readiness(ready=True, targets=targets))
    assert wf["blocked_targets"] == ["ghost"]
    assert wf["ready_to_prepare_solver_run"] is False
    assert wf["ready_to_run_solver"] is False
    assert wf["solver_status"] == "blocked_unknown_target"


def test_prepared_but_unknown_target_still_not_runnable() -> None:
    targets = {"parts": [{"value": "ghost", "known": False}], "artifacts": []}
    wf = build_simulation_workflow_state(
        _readiness(ready=True, targets=targets),
        prepared={"deck_path": "cae/sim.inp"},
    )
    # A blocked target overrides a prepared deck — not runnable.
    assert wf["ready_to_run_solver"] is False
    assert wf["solver_status"] == "blocked_unknown_target"


def test_no_readiness_is_not_runnable() -> None:
    wf = build_simulation_workflow_state(None)
    assert wf["ready_to_prepare_solver_run"] is False
    assert wf["solver_status"] == "not_run"


def test_final_claims_results_detector() -> None:
    assert final_claims_results("The max stress is 120 MPa under load.") is True
    assert final_claims_results("Von Mises peaks at the fillet.") is True
    assert final_claims_results("仿真结果显示应力集中在根部。") is True
    # Plan / not-run text must NOT trip the detector.
    assert final_claims_results("Plan: setup -> mesh -> solver. The solver has NOT run yet.") is False
    assert final_claims_results("I will prepare the deck and request approval to run the solver.") is False
    assert final_claims_results("") is False
    assert final_claims_results(None) is False
