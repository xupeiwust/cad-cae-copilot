"""Tests for deterministic optimizer selection (#101)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.optimizer_selector import (
    _LOW_DIMENSIONAL_THRESHOLD,
    _surrogate_available,
    select_optimizer,
)
from aieng.optimization_artifacts import validate_optimization_artifact


def _provenance() -> dict:
    return {
        "created_at": "2026-06-10T00:00:00Z",
        "created_by": "test",
        "claim_advancement": "none",
    }


def _claim_policy() -> dict:
    return {
        "advisory_only": True,
        "baseline_unchanged": True,
        "human_approval_required_for_acceptance": True,
        "claim_advancement": "none",
    }


def _variable(
    *,
    vid: str,
    vtype: str,
    min_value: float | None = None,
    max_value: float | None = None,
    allowed_values: list | None = None,
) -> dict:
    return {
        "id": vid,
        "path": f"parts/0/params/{vid.upper()}",
        "type": vtype,
        "featureId": f"feat_{vid}",
        "parameterName": vid,
        "cad_parameter_name": vid.upper(),
        "binding_status": "bound",
        "current_value": 5.0 if allowed_values is None else (allowed_values[0] if allowed_values else None),
        "min_value": min_value,
        "max_value": max_value,
        "allowed_values": allowed_values,
        "unit": "mm" if vtype != "categorical" else None,
        "scope": "local",
        "safe_to_modify": True,
        "candidate_ids": [],
    }


def _variables_doc(variables: list[dict]) -> dict:
    return {
        "format": "aieng.optimization_variables",
        "schema_version": "0.2",
        "study_id": "opt_study_001",
        "design_study_problem_ref": "analysis/design_study_problem.json",
        "design_study_problem_id": "study_source_001",
        "variables": variables,
        "candidate_ids": [],
        "provenance": _provenance(),
        "claim_policy": _claim_policy(),
    }


def _study_doc(*, algorithm_name: str | None = None, max_solver_runs: int | None = None) -> dict:
    algorithm: dict = {"name": algorithm_name or "manual", "phase": 1, "bounded_step": True, "seed": None}
    budget: dict = {"max_candidates": 20, "max_iterations": 5}
    if max_solver_runs is not None:
        budget["max_solver_runs"] = max_solver_runs
    return {
        "format": "aieng.optimization_study",
        "schema_version": "0.1",
        "study_id": "opt_study_001",
        "design_study_problem_ref": "analysis/design_study_problem.json",
        "design_study_problem_id": "study_source_001",
        "algorithm": algorithm,
        "sampling": {"requested_candidate_count": 5, "max_candidate_count": 20, "seed": None},
        "budget": budget,
        "status": "defined",
        "artifact_refs": {
            "variables": "analysis/optimization_variables.json",
            "objectives": "analysis/optimization_objectives.json",
            "constraints": "analysis/optimization_constraints.json",
            "decision_log": "analysis/optimization_decision_log.json",
        },
        "candidate_ids": [],
        "provenance": _provenance(),
        "claim_policy": _claim_policy(),
    }


def _make_package(tmp_path: Path, variables: list[dict], study: dict | None = None) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", "{}")
        zf.writestr("analysis/optimization_variables.json", json.dumps(_variables_doc(variables)))
        if study is not None:
            zf.writestr("analysis/optimization_study.json", json.dumps(study))
    return pkg


def _read_decision_log(pkg: Path) -> dict:
    with zipfile.ZipFile(pkg, "r") as zf:
        return json.loads(zf.read("analysis/optimization_decision_log.json"))


def test_selects_slsqp_for_continuous_low_dim(tmp_path: Path) -> None:
    variables = [_variable(vid="wall_t", vtype="continuous", min_value=2.0, max_value=8.0)]
    pkg = _make_package(tmp_path, variables, _study_doc())
    result = select_optimizer(pkg)
    assert result["status"] == "ok"
    assert result["optimizer"] == "slsqp"
    assert "select_slsqp" in result["reason_codes"]
    assert "continuous_smooth_problem" in result["reason_codes"]
    assert result["baseline_modified"] is False


def test_selects_genetic_for_discrete_variable(tmp_path: Path) -> None:
    variables = [_variable(vid="mat", vtype="categorical", allowed_values=["al", "steel"])]
    pkg = _make_package(tmp_path, variables, _study_doc())
    result = select_optimizer(pkg)
    assert result["status"] == "ok"
    assert result["optimizer"] == "genetic"
    assert "select_genetic" in result["reason_codes"]
    assert "discrete_variables_present" in result["reason_codes"]


def test_selects_bayesian_for_expensive_cae_when_surrogate_available(tmp_path: Path) -> None:
    variables = [_variable(vid="wall_t", vtype="continuous", min_value=2.0, max_value=8.0)]
    pkg = _make_package(tmp_path, variables, _study_doc(max_solver_runs=5))
    result = select_optimizer(pkg)
    if _surrogate_available():
        assert result["optimizer"] == "bayesian"
        assert "select_bayesian" in result["reason_codes"]
        assert "expensive_cae_eval" in result["reason_codes"]
    else:
        assert result["optimizer"] == "trust_region"
        assert "no_surrogate_available" in result["reason_codes"]
        assert "expensive_cae_eval" in result["reason_codes"]


def test_user_selected_override(tmp_path: Path) -> None:
    variables = [_variable(vid="wall_t", vtype="continuous", min_value=2.0, max_value=8.0)]
    pkg = _make_package(tmp_path, variables, _study_doc())
    result = select_optimizer(pkg, user_selected="genetic")
    assert result["optimizer"] == "genetic"
    assert "user_selected" in result["reason_codes"]


def test_study_configured_optimizer_is_honored(tmp_path: Path) -> None:
    variables = [_variable(vid="wall_t", vtype="continuous", min_value=2.0, max_value=8.0)]
    pkg = _make_package(tmp_path, variables, _study_doc(algorithm_name="bayesian"))
    result = select_optimizer(pkg)
    assert result["optimizer"] == "bayesian"
    assert "user_selected" in result["reason_codes"]


def test_invalid_user_selected_returns_error(tmp_path: Path) -> None:
    variables = [_variable(vid="wall_t", vtype="continuous", min_value=2.0, max_value=8.0)]
    pkg = _make_package(tmp_path, variables, _study_doc())
    result = select_optimizer(pkg, user_selected="magic")
    assert result["status"] == "error"
    assert result["code"] == "invalid_optimizer"


def test_discrete_takes_precedence_over_cae(tmp_path: Path) -> None:
    variables = [_variable(vid="mat", vtype="categorical", allowed_values=["al", "steel"])]
    pkg = _make_package(tmp_path, variables, _study_doc(max_solver_runs=10))
    result = select_optimizer(pkg)
    assert result["optimizer"] == "genetic"


def test_appends_to_existing_decision_log(tmp_path: Path) -> None:
    variables = [_variable(vid="wall_t", vtype="continuous", min_value=2.0, max_value=8.0)]
    pkg = _make_package(tmp_path, variables, _study_doc())

    first = select_optimizer(pkg)
    assert first["status"] == "ok"
    log1 = _read_decision_log(pkg)
    assert len(log1["entries"]) == 1

    second = select_optimizer(pkg)
    assert second["status"] == "ok"
    log2 = _read_decision_log(pkg)
    assert len(log2["entries"]) == 2
    assert log2["entries"][0]["decision_id"] != log2["entries"][1]["decision_id"]


def test_decision_log_validates_against_schema(tmp_path: Path) -> None:
    variables = [_variable(vid="wall_t", vtype="continuous", min_value=2.0, max_value=8.0)]
    pkg = _make_package(tmp_path, variables, _study_doc())
    select_optimizer(pkg)
    log = _read_decision_log(pkg)
    assert validate_optimization_artifact("decision_log", log) == []


def test_missing_package_returns_error(tmp_path: Path) -> None:
    result = select_optimizer(tmp_path / "missing.aieng")
    assert result["status"] == "error"
    assert result["code"] == "package_not_found"


def test_missing_variables_returns_error(tmp_path: Path) -> None:
    pkg = tmp_path / "empty.aieng"
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", "{}")
    result = select_optimizer(pkg)
    assert result["status"] == "error"
    assert result["code"] == "missing_variables"


def test_high_dimensional_defaults_to_trust_region(tmp_path: Path) -> None:
    variables = [
        _variable(vid=f"x{i}", vtype="continuous", min_value=0.0, max_value=1.0)
        for i in range(_LOW_DIMENSIONAL_THRESHOLD + 1)
    ]
    pkg = _make_package(tmp_path, variables, _study_doc())
    result = select_optimizer(pkg)
    assert result["status"] == "ok"
    assert result["optimizer"] == "trust_region"
