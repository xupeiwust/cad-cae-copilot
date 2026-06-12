"""Tests for topology writeback → sizing-variable parameterization (#106)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from aieng import FORMAT_VERSION
from aieng.converters.topology_parameterization import (
    AUDIT_EVENTS_PATH,
    DESIGN_STUDY_PROBLEM_PATH,
    OPTIMIZATION_VARIABLES_PATH,
    TOPOLOGY_OPTIMIZATION_PATH,
    parameterize_topology_writeback,
)


def _make_pkg(tmp_path: Path, topo: dict[str, Any], shape_ir: dict[str, Any]) -> Path:
    pkg = tmp_path / "topo_param.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "topo param test"}))
        zf.writestr("geometry/shape_ir.json", json.dumps(shape_ir))
        zf.writestr(TOPOLOGY_OPTIMIZATION_PATH, json.dumps(topo))
    return pkg


def _topo_2d_contour() -> dict[str, Any]:
    return {
        "format": "aieng.topology_optimization",
        "schema_version": "0.1",
        "contract_version": "0.1",
        "dimension": "2d",
        "optimizer": {"name": "simp_2d", "method": "SIMP", "dimension": 2},
        "objective": "compliance_minimization",
        "problem": {"design_space_node": "plate", "volfrac": 0.5},
        "result": {},
    }


def _shape_ir_extruded(thickness: Any = 5.0) -> dict[str, Any]:
    return {
        "format": "aieng.shape_ir",
        "representation": "manifold_mesh",
        "model_id": "optimized_plate",
        "parts": [
            {
                "id": "optimized_plate",
                "label": "optimized_plate",
                "type": "extruded_region",
                "polygons": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
                "boundary": "polygon",
                "thickness": thickness,
                "origin": [0, 0, 0],
                "u_axis": "x",
                "v_axis": "y",
                "placed_in_frame": True,
                "source_optimization": {"optimizer": "simp_2d"},
            }
        ],
    }


def test_parameterizes_contour_extrusion(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path, _topo_2d_contour(), _shape_ir_extruded(5.0))
    res = parameterize_topology_writeback(pkg)

    assert res["status"] == "ok"
    assert res["baseline_modified"] is False
    assert res["variable_count"] == 1
    assert res["variables"] == ["extrusion_thickness"]
    assert DESIGN_STUDY_PROBLEM_PATH in res["artifacts"]
    assert OPTIMIZATION_VARIABLES_PATH in res["artifacts"]

    with zipfile.ZipFile(pkg, "r") as zf:
        problem = json.loads(zf.read(DESIGN_STUDY_PROBLEM_PATH))
        variables_doc = json.loads(zf.read(OPTIMIZATION_VARIABLES_PATH))
        audit_text = zf.read(AUDIT_EVENTS_PATH).decode("utf-8")

    assert problem["format"] == "aieng.design_study_problem"
    assert problem["id"].startswith("topo_to_sizing_")
    assert problem["provenance"]["from_topology_writeback"] is True
    assert problem["provenance"]["production_ready"] is False

    var = problem["variables"][0]
    assert var["id"] == "extrusion_thickness"
    assert var["type"] == "continuous"
    assert var["current_value"] == 5.0
    assert var["min_value"] == pytest.approx(2.5, rel=1e-6)
    assert var["max_value"] == pytest.approx(7.5, rel=1e-6)
    assert var["safe_to_modify"] is True

    assert variables_doc["format"] == "aieng.optimization_variables"
    assert variables_doc["schema_version"] == "0.2"
    assert variables_doc["design_study_problem_ref"] == DESIGN_STUDY_PROBLEM_PATH
    assert variables_doc["claim_policy"]["advisory_only"] is True
    assert variables_doc["claim_policy"]["baseline_unchanged"] is True

    resolved = variables_doc["variables"][0]
    assert resolved["id"] == "extrusion_thickness"
    assert resolved["binding_status"] == "bound"
    assert resolved["featureId"] == "optimized_plate"
    assert resolved["parameterName"] == "extrusion_thickness"
    assert resolved["shape_bearing"] is False

    events = [json.loads(line) for line in audit_text.strip().splitlines()]
    assert len(events) == 1
    assert events[0]["tool"] == "aieng.converters.topology_parameterization"
    assert events[0]["status"] == "completed"


def test_refuses_3d_topology_result(tmp_path: Path) -> None:
    topo = _topo_2d_contour()
    topo["dimension"] = "3d"
    pkg = _make_pkg(tmp_path, topo, _shape_ir_extruded(5.0))
    res = parameterize_topology_writeback(pkg)

    assert res["status"] == "needs_user_input"
    assert res["code"] == "3d_or_non_2d_not_supported"
    assert res["baseline_modified"] is False

    with zipfile.ZipFile(pkg, "r") as zf:
        assert DESIGN_STUDY_PROBLEM_PATH not in zf.namelist()
        assert OPTIMIZATION_VARIABLES_PATH not in zf.namelist()


def test_refuses_voxel_writeback(tmp_path: Path) -> None:
    shape_ir = _shape_ir_extruded(5.0)
    shape_ir["parts"][0]["type"] = "density_voxels"
    pkg = _make_pkg(tmp_path, _topo_2d_contour(), shape_ir)
    res = parameterize_topology_writeback(pkg)

    assert res["status"] == "needs_user_input"
    assert res["code"] == "no_stable_parameter"
    assert "density_voxels" in res["message"]


def test_refuses_missing_thickness(tmp_path: Path) -> None:
    shape_ir = _shape_ir_extruded(None)
    pkg = _make_pkg(tmp_path, _topo_2d_contour(), shape_ir)
    res = parameterize_topology_writeback(pkg)

    assert res["status"] == "needs_user_input"
    assert res["code"] == "no_stable_parameter"


def test_refuses_non_positive_thickness(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path, _topo_2d_contour(), _shape_ir_extruded(-1.0))
    res = parameterize_topology_writeback(pkg)

    assert res["status"] == "needs_user_input"
    assert res["code"] == "no_stable_parameter"


def test_returns_error_for_missing_package(tmp_path: Path) -> None:
    res = parameterize_topology_writeback(tmp_path / "missing.aieng")
    assert res["status"] == "error"
    assert res["code"] == "package_not_found"
