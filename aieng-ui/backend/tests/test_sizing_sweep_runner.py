"""Tests for the parametric sizing-sweep orchestrator + opt.sizing_sweep wiring.

The per-variant build+solve step is injected so the orchestration is exercised
without Gmsh/CalculiX. A separate skip-gated check covers solve_package_static's
honest degradation when the solver tools are unavailable.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

import app.project_io as project_io
from app.sizing_sweep_runner import SIZING_SWEEP_REPORT_PATH, run_sizing_sweep


@pytest.fixture
def fake_project(monkeypatch, tmp_path: Path):
    """Make get_project / resolve_project_path resolve to an existing dummy package."""
    pkg = tmp_path / "proj.aieng"
    pkg.write_bytes(b"PK\x03\x04")  # existence is all the orchestrator checks
    monkeypatch.setattr(project_io, "get_project", lambda settings, pid: {"aieng_file": str(pkg)})
    monkeypatch.setattr(project_io, "resolve_project_path", lambda settings, pid, f: pkg)
    return pkg


@pytest.fixture
def valid_project(monkeypatch, tmp_path: Path):
    """Make get_project / resolve_project_path resolve to a valid .aieng package."""
    pkg = tmp_path / "proj.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"version": "0.1.0"}))
        zf.writestr("graph/feature_graph.json", json.dumps({"features": []}))
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


def _make_pkg_with_feature_graph(tmp_path: Path) -> Path:
    import json
    import zipfile

    pkg = tmp_path / "proj.aieng"
    feature_graph = {
        "features": [
            {
                "id": "f_wall",
                "parameters": {
                    "thickness": {
                        "current_value": 3.0,
                        "min_value": 2.0,
                        "max_value": 8.0,
                        "cad_parameter_name": "THICKNESS",
                    }
                },
            }
        ]
    }
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("graph/feature_graph.json", json.dumps(feature_graph))
    return pkg


def test_sweep_expands_range_with_steps(monkeypatch, tmp_path: Path) -> None:
    pkg = _make_pkg_with_feature_graph(tmp_path)
    monkeypatch.setattr(project_io, "get_project", lambda settings, pid: {"aieng_file": str(pkg)})
    monkeypatch.setattr(project_io, "resolve_project_path", lambda settings, pid, f: pkg)

    table = {v: {"max_von_mises_stress": 100.0, "mass": float(v)} for v in [2.0, 3.0, 4.0, 5.0, 6.0]}
    report = run_sizing_sweep(
        None, "proj1",
        feature_id="f_wall", parameter_name="thickness",
        range={"min": 2.0, "max": 6.0, "steps": 5},
        objective="min_mass", stress_limit=200.0,
        evaluate_value=_fake_evaluator(table),
    )
    assert report["status"] == "ok"
    assert report["swept_values"] == [2.0, 3.0, 4.0, 5.0, 6.0]
    assert report["range"]["min"] == 2.0
    assert report["recommended"]["value"] == 2.0


def test_sweep_expands_range_with_step_and_clamps(monkeypatch, tmp_path: Path) -> None:
    pkg = _make_pkg_with_feature_graph(tmp_path)
    monkeypatch.setattr(project_io, "get_project", lambda settings, pid: {"aieng_file": str(pkg)})
    monkeypatch.setattr(project_io, "resolve_project_path", lambda settings, pid, f: pkg)

    # Range extends beyond declared max (8.0); should clamp to 8.
    table = {v: {"max_von_mises_stress": 100.0, "mass": float(v)} for v in [2.0, 4.0, 6.0, 8.0]}
    report = run_sizing_sweep(
        None, "proj1",
        feature_id="f_wall", parameter_name="thickness",
        range={"min": 1.0, "max": 10.0, "step": 2.0},
        objective="min_mass", stress_limit=200.0,
        evaluate_value=_fake_evaluator(table),
    )
    assert report["status"] == "ok"
    assert report["swept_values"] == [2.0, 4.0, 6.0, 8.0]


def test_sweep_range_rejects_too_many_steps(monkeypatch, tmp_path: Path) -> None:
    pkg = _make_pkg_with_feature_graph(tmp_path)
    monkeypatch.setattr(project_io, "get_project", lambda settings, pid: {"aieng_file": str(pkg)})
    monkeypatch.setattr(project_io, "resolve_project_path", lambda settings, pid, f: pkg)

    report = run_sizing_sweep(
        None, "proj1",
        feature_id="f_wall", parameter_name="thickness",
        range={"min": 2.0, "max": 8.0, "steps": 30},
        evaluate_value=_fake_evaluator({}),
    )
    assert report["status"] == "error"
    assert report["code"] == "too_many_values"
    assert "25" in report["message"]


def test_sweep_apply_winner_calls_edit_parameter(monkeypatch, tmp_path: Path) -> None:
    pkg = _make_pkg_with_feature_graph(tmp_path)
    monkeypatch.setattr(project_io, "get_project", lambda settings, pid: {"aieng_file": str(pkg)})
    monkeypatch.setattr(project_io, "resolve_project_path", lambda settings, pid, f: pkg)

    table = {
        2.0: {"max_von_mises_stress": 260.0, "mass": 1.0},
        3.0: {"max_von_mises_stress": 170.0, "mass": 1.5},
        4.0: {"max_von_mises_stress": 120.0, "mass": 2.0},
    }

    applied = {}

    def fake_edit(settings, project_id, feature_id, parameter_name, new_value, **kwargs):
        applied.update({"project_id": project_id, "feature_id": feature_id, "value": new_value})
        return {"status": "ok", "regression_diff": {"verdict": "clean"}}

    monkeypatch.setattr("app.cad_generation.edit_build123d_parameter", fake_edit)

    report = run_sizing_sweep(
        None, "proj1",
        feature_id="f_wall", parameter_name="thickness",
        values=[2.0, 3.0, 4.0],
        objective="min_mass", stress_limit=200.0,
        apply_winner=True,
        evaluate_value=_fake_evaluator(table),
    )
    assert report["status"] == "ok"
    assert report["apply_status"] == "ok"
    assert report["baseline_modified"] is True
    assert report["applied_value"] == 3.0
    assert applied["value"] == 3.0
    assert report["regression_diff"]["verdict"] == "clean"


def test_sweep_apply_winner_honestly_reports_edit_failure(monkeypatch, tmp_path: Path) -> None:
    pkg = _make_pkg_with_feature_graph(tmp_path)
    monkeypatch.setattr(project_io, "get_project", lambda settings, pid: {"aieng_file": str(pkg)})
    monkeypatch.setattr(project_io, "resolve_project_path", lambda settings, pid, f: pkg)

    table = {3.0: {"max_von_mises_stress": 170.0, "mass": 1.5}}

    def fake_edit(*args, **kwargs):
        return {"status": "error", "message": "build failed"}

    monkeypatch.setattr("app.cad_generation.edit_build123d_parameter", fake_edit)

    report = run_sizing_sweep(
        None, "proj1",
        feature_id="f_wall", parameter_name="thickness",
        values=[3.0],
        objective="min_mass", stress_limit=200.0,
        apply_winner=True,
        evaluate_value=_fake_evaluator(table),
    )
    assert report["status"] == "ok"
    assert report["apply_status"] == "error"
    assert report["baseline_modified"] is False
    assert "build failed" in report["apply_error"]


def test_sweep_persists_report_to_package(valid_project: Path) -> None:
    table = {
        2.0: {"max_von_mises_stress": 260.0, "mass": 1.0},
        3.0: {"max_von_mises_stress": 170.0, "mass": 1.5},
        4.0: {"max_von_mises_stress": 120.0, "mass": 2.0},
    }
    report = run_sizing_sweep(
        None, "proj1",
        feature_id="f_wall", parameter_name="thickness",
        values=[2.0, 3.0, 4.0],
        objective="min_mass", stress_limit=200.0,
        evaluate_value=_fake_evaluator(table),
    )
    assert report["status"] == "ok"
    assert report["artifact_path"] == SIZING_SWEEP_REPORT_PATH
    assert "artifact_write_error" not in report

    with zipfile.ZipFile(valid_project, "r") as zf:
        assert SIZING_SWEEP_REPORT_PATH in zf.namelist()
        persisted = json.loads(zf.read(SIZING_SWEEP_REPORT_PATH).decode("utf-8"))
    assert persisted["tool"] == "opt.sizing_sweep"
    assert persisted["recommended"]["value"] == 3.0
