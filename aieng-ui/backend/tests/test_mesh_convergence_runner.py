"""Tests for the mesh-convergence orchestrator + cae.mesh_convergence wiring.

Per-size solves are injected so the orchestration runs without Gmsh/CalculiX.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import app.project_io as project_io
from app.mesh_convergence_runner import run_mesh_convergence


@pytest.fixture
def fake_project(monkeypatch, tmp_path: Path):
    pkg = tmp_path / "proj.aieng"
    pkg.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(project_io, "get_project", lambda s, p: {"aieng_file": str(pkg)})
    monkeypatch.setattr(project_io, "resolve_project_path", lambda s, p, f: pkg)
    return pkg


def _evaluator(table):
    """size → solve result from {size: {metric: value}} table; missing size → failed solve."""
    def _ev(size):
        m = table.get(size)
        if m is None:
            return {"size": size, "metrics": {}, "solver_executed": False, "error": "solve failed"}
        return {"size": size, "metrics": m, "solver_executed": True}
    return _ev


def test_convergence_reports_per_metric_and_overall(fake_project) -> None:
    # converged stress series (phi=10+h^2 at fine h), flat-ish displacement
    table = {
        1.0: {"max_von_mises_stress": 11.0, "max_displacement": 2.0},
        0.5: {"max_von_mises_stress": 10.25, "max_displacement": 2.0},
        0.25: {"max_von_mises_stress": 10.0625, "max_displacement": 2.0},
    }
    report = run_mesh_convergence(
        None, "proj1", mesh_sizes=[1.0, 0.5, 0.25],
        evaluate_value=_evaluator(table),
    )
    assert report["status"] == "ok"
    assert report["tool"] == "cae.mesh_convergence"
    assert report["solved_count"] == 3
    assert report["convergence"]["max_von_mises_stress"]["converged"] is True
    assert report["convergence"]["max_displacement"]["verdict"] == "converged_flat"
    assert report["overall_verdict"] == "converged"
    assert report["honesty"]["baseline_modified"] is False
    # coarse → fine ordering for readability
    assert report["mesh_sizes"] == [1.0, 0.5, 0.25]


def test_not_converged_overall(fake_project) -> None:
    table = {
        4.0: {"max_von_mises_stress": 26.0},
        2.0: {"max_von_mises_stress": 14.0},
        1.0: {"max_von_mises_stress": 11.0},
    }
    report = run_mesh_convergence(
        None, "proj1", mesh_sizes=[4.0, 2.0, 1.0],
        metrics=["max_von_mises_stress"],
        evaluate_value=_evaluator(table),
    )
    assert report["convergence"]["max_von_mises_stress"]["converged"] is False
    assert report["overall_verdict"] == "not_converged"
    assert "finer mesh" in report["next_step"]


def test_failed_solve_is_dropped_from_analysis(fake_project) -> None:
    table = {4.0: {"max_von_mises_stress": 26.0}, 2.0: None, 1.0: {"max_von_mises_stress": 11.0}}
    report = run_mesh_convergence(
        None, "proj1", mesh_sizes=[4.0, 2.0, 1.0],
        metrics=["max_von_mises_stress"],
        evaluate_value=_evaluator(table),
    )
    assert report["solved_count"] == 2
    # two usable grids → relative-change-only (no GCI)
    assert report["convergence"]["max_von_mises_stress"]["verdict"] == "two_grid_relative_change_only"


def test_requires_two_sizes(fake_project) -> None:
    r = run_mesh_convergence(None, "proj1", mesh_sizes=[1.0], evaluate_value=_evaluator({}))
    assert r["status"] == "error" and r["code"] == "bad_input"


def test_caps_level_count(fake_project) -> None:
    r = run_mesh_convergence(
        None, "proj1", mesh_sizes=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        evaluate_value=_evaluator({}),
    )
    assert r["status"] == "error" and r["code"] == "too_many_levels"


def test_no_package(monkeypatch) -> None:
    monkeypatch.setattr(project_io, "get_project", lambda s, p: {"aieng_file": "x"})
    monkeypatch.setattr(project_io, "resolve_project_path", lambda s, p, f: None)
    r = run_mesh_convergence(None, "p", mesh_sizes=[1.0, 2.0], evaluate_value=_evaluator({}))
    assert r["status"] == "error" and r["code"] == "no_package"
