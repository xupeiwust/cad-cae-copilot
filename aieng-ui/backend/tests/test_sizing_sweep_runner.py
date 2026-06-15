"""Tests for the parametric sizing-sweep orchestrator + opt.sizing_sweep wiring.

The per-variant build+solve step is injected so the orchestration is exercised
without Gmsh/CalculiX. A separate skip-gated check covers solve_package_static's
honest degradation when the solver tools are unavailable.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import app.project_io as project_io
from app.sizing_sweep_runner import run_sizing_sweep


@pytest.fixture
def fake_project(monkeypatch, tmp_path: Path):
    """Make get_project / resolve_project_path resolve to an existing dummy package."""
    pkg = tmp_path / "proj.aieng"
    pkg.write_bytes(b"PK\x03\x04")  # existence is all the orchestrator checks
    monkeypatch.setattr(project_io, "get_project", lambda settings, pid: {"aieng_file": str(pkg)})
    monkeypatch.setattr(project_io, "resolve_project_path", lambda settings, pid, f: pkg)
    return pkg


def _fake_evaluator(metric_by_value):
    """value → {value, metrics, solver_executed} from a {value: metrics} table."""
    def _ev(value):
        m = metric_by_value.get(value)
        if m is None:
            return {"value": value, "metrics": {}, "solver_executed": False, "error": "no result"}
        return {"value": value, "metrics": m, "solver_executed": True}
    return _ev


def test_sweep_recommends_lightest_feasible(fake_project) -> None:
    table = {
        2.0: {"max_von_mises_stress": 260.0, "mass": 1.0},   # infeasible
        3.0: {"max_von_mises_stress": 170.0, "mass": 1.5},   # feasible (lightest feasible)
        4.0: {"max_von_mises_stress": 120.0, "mass": 2.0},   # feasible (heavier)
    }
    report = run_sizing_sweep(
        None, "proj1",
        feature_id="f_wall", parameter_name="thickness",
        values=[2.0, 3.0, 4.0],
        objective="min_mass", stress_limit=200.0,
        evaluate_value=_fake_evaluator(table),
    )
    assert report["status"] == "ok"
    assert report["tool"] == "opt.sizing_sweep"
    assert report["recommended"]["value"] == 3.0
    assert report["safe_to_apply"] is True
    assert report["honesty"]["baseline_modified"] is False
    assert "cad.edit_parameter" in report["next_step"]
    assert report["swept_values"] == [2.0, 3.0, 4.0]


def test_sweep_no_feasible_variant(fake_project) -> None:
    table = {3.0: {"max_von_mises_stress": 300.0, "mass": 1.5}}
    report = run_sizing_sweep(
        None, "proj1",
        feature_id="f", parameter_name="t",
        values=[3.0], objective="min_mass", stress_limit=200.0,
        evaluate_value=_fake_evaluator(table),
    )
    assert report["status"] == "ok"
    assert report["recommended"] is None
    assert report["safe_to_apply"] is False
    assert "No value recommended" in report["next_step"]


def test_sweep_unsolved_variant_is_not_recommended(fake_project) -> None:
    table = {3.0: None, 4.0: {"max_von_mises_stress": 120.0, "mass": 2.0}}  # 3.0 fails to solve
    report = run_sizing_sweep(
        None, "proj1",
        feature_id="f", parameter_name="t",
        values=[3.0, 4.0], objective="min_mass", stress_limit=200.0,
        evaluate_value=_fake_evaluator(table),
    )
    assert report["recommended"]["value"] == 4.0
    # not all variants solved → overall credibility downgraded
    assert report["credibility"]["tier"] == "unverified"


def test_sweep_dedupes_and_rejects_empty(fake_project) -> None:
    empty = run_sizing_sweep(
        None, "proj1", feature_id="f", parameter_name="t",
        values=[], evaluate_value=_fake_evaluator({}),
    )
    assert empty["status"] == "error" and empty["code"] == "bad_input"


def test_sweep_caps_value_count(fake_project) -> None:
    report = run_sizing_sweep(
        None, "proj1", feature_id="f", parameter_name="t",
        values=[float(i) for i in range(26)],
        evaluate_value=_fake_evaluator({}),
    )
    assert report["status"] == "error" and report["code"] == "too_many_values"


def test_sweep_project_not_found(monkeypatch, tmp_path: Path) -> None:
    def _raise(settings, pid):
        raise KeyError("nope")
    monkeypatch.setattr(project_io, "get_project", _raise)
    report = run_sizing_sweep(
        None, "missing", feature_id="f", parameter_name="t",
        values=[1.0], evaluate_value=_fake_evaluator({1.0: {"mass": 1.0}}),
    )
    assert report["status"] == "error" and report["code"] == "project_not_found"


def test_sweep_missing_package(monkeypatch) -> None:
    monkeypatch.setattr(project_io, "get_project", lambda s, p: {"aieng_file": "x"})
    monkeypatch.setattr(project_io, "resolve_project_path", lambda s, p, f: None)
    report = run_sizing_sweep(
        None, "p", feature_id="f", parameter_name="t",
        values=[1.0], evaluate_value=_fake_evaluator({1.0: {"mass": 1.0}}),
    )
    assert report["status"] == "error" and report["code"] == "no_package"


def test_solve_package_static_degrades_when_tools_unavailable(tmp_path: Path) -> None:
    """Without Gmsh/CalculiX, solve_package_static must report honest failure,
    never a fake success."""
    from app.simulation_runner import check_simulation_tools, solve_package_static

    if check_simulation_tools()["ready"]:
        pytest.skip("Gmsh + CalculiX available — degradation path not exercised")
    result = solve_package_static(tmp_path / "nope.aieng")
    assert result["solver_executed"] is False
    assert result["status"] == "tools_unavailable"
    assert result["metrics"] == {}
