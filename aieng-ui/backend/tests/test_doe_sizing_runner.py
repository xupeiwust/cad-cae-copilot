"""Tests for multi-parameter DOE sizing study runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.doe_sizing_runner import (
    _generate_design_points,
    _safe_param_key,
    run_doe_sizing_study,
)
from app import project_io


def test_safe_param_key_and_parse() -> None:
    key = _safe_param_key("f_wall", "thickness")
    assert key == "f_wall#thickness"


def test_full_factorial_generates_cartesian_product() -> None:
    points = _generate_design_points(
        {"a": [1.0, 2.0], "b": [10.0, 20.0]},
        "full_factorial",
        budget=64,
    )
    assert len(points) == 4
    assert all("a" in p and "b" in p for p in points)


def test_full_factorial_respects_budget() -> None:
    with pytest.raises(ValueError, match="budget"):
        _generate_design_points(
            {"a": list(range(10)), "b": list(range(10))},
            "full_factorial",
            budget=64,
        )


def test_lhs_generates_requested_budget() -> None:
    points = _generate_design_points(
        {"a": [1.0, 2.0, 3.0], "b": [10.0, 20.0]},
        "lhs",
        budget=6,
        seed=42,
    )
    assert len(points) == 6
    # All values come from the supplied lists.
    for p in points:
        assert p["a"] in [1.0, 2.0, 3.0]
        assert p["b"] in [10.0, 20.0]


def _fake_evaluator(expected: dict[tuple[float, float], dict[str, float]]) -> Any:
    def evaluate(point: dict[str, float]) -> dict[str, Any]:
        key = (point["f_wall#thickness"], point["f_rib#thickness"])
        metrics = expected.get(key, {"mass": 10.0, "max_von_mises_stress": 100.0})
        return {
            "value": f"wall={point['f_wall#thickness']},rib={point['f_rib#thickness']}",
            "parameters": dict(point),
            "metrics": dict(metrics),
            "solver_executed": True,
            "error": None,
        }
    return evaluate


def _make_minimal_pkg(path: Path) -> None:
    import zipfile
    feature_graph = {
        "features": [
            {
                "id": "f_wall",
                "parameters": {
                    "thickness": {"current_value": 2.5, "min_value": 1.0, "max_value": 10.0, "cad_parameter_name": "WALL_THICKNESS"}
                },
            },
            {
                "id": "f_rib",
                "parameters": {
                    "thickness": {"current_value": 1.5, "min_value": 0.5, "max_value": 5.0, "cad_parameter_name": "RIB_THICKNESS"}
                },
            },
        ]
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("graph/feature_graph.json", json.dumps(feature_graph))


def test_doe_ranks_2_parameter_full_factorial(monkeypatch, tmp_path: Path) -> None:
    pkg = tmp_path / "proj.aieng"
    _make_minimal_pkg(pkg)
    monkeypatch.setattr(project_io, "get_project", lambda settings, pid: {"aieng_file": str(pkg)})
    monkeypatch.setattr(project_io, "resolve_project_path", lambda settings, pid, f: pkg)

    expected = {
        (2.0, 1.0): {"mass": 8.0, "max_von_mises_stress": 210.0},  # infeasible
        (2.0, 2.0): {"mass": 9.0, "max_von_mises_stress": 180.0},  # feasible
        (3.0, 1.0): {"mass": 10.0, "max_von_mises_stress": 150.0},  # feasible
        (3.0, 2.0): {"mass": 12.0, "max_von_mises_stress": 120.0},  # feasible
    }

    report = run_doe_sizing_study(
        None,
        "proj1",
        parameters=[
            {"featureId": "f_wall", "parameterName": "thickness", "values": [2.0, 3.0]},
            {"featureId": "f_rib", "parameterName": "thickness", "values": [1.0, 2.0]},
        ],
        method="full_factorial",
        objective="min_mass",
        stress_limit=200.0,
        evaluate_design_point=_fake_evaluator(expected),
    )

    assert report["status"] == "ok"
    assert report["method"] == "full_factorial"
    assert report["design_points_count"] == 4
    feasible = [v for v in report["variants"] if v["status"] == "feasible"]
    assert len(feasible) == 3
    # Best feasible is the lightest feasible point.
    assert report["recommended"]["parameters"]["f_wall#thickness"] == 2.0
    assert report["recommended"]["parameters"]["f_rib#thickness"] == 2.0


def test_doe_rejects_single_parameter() -> None:
    report = run_doe_sizing_study(
        None,
        "proj1",
        parameters=[{"featureId": "f_wall", "parameterName": "thickness", "values": [2.0, 3.0]}],
    )
    assert report["status"] == "error"
    assert report["code"] == "bad_input"
