"""Demo / regression: sizing-study + CAE validation on a recovered topology body.

Issue #108 end-to-end. Uses static metrics only (no external solver) and asserts
honest handling of missing CAE stress/displacement.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng.converters.design_study_batch import (
    run_design_study_batch,
    run_design_study_evaluation_batch,
)
from aieng.converters.design_study_ranking import rank_design_study_candidates
from aieng.converters.optimization_recommendation import explain_recommendation
from aieng.converters.optimization_report import build_optimization_report
from aieng.converters.optimization_sampler import sample_candidates_package
from aieng.converters.topology_to_sizing import topology_to_sizing


def _make_pkg(tmp_path: Path) -> Path:
    pkg = tmp_path / "topology_sizing_demo.aieng"
    shape_ir = {
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
                "thickness": 5.0,
                "origin": [0, 0, 0],
                "u_axis": "x",
                "v_axis": "y",
                "placed_in_frame": True,
                "source_optimization": {"optimizer": "simp_2d"},
            }
        ],
    }
    topo = {
        "format": "aieng.topology_optimization",
        "schema_version": "0.1",
        "contract_version": "0.1",
        "dimension": "2d",
        "optimizer": {"name": "simp_2d", "method": "SIMP", "dimension": 2},
        "objective": "compliance_minimization",
        "problem": {"design_space_node": "plate", "volfrac": 0.5},
        "result": {},
    }
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("manifest.json", json.dumps({
            "format": "aieng.package",
            "format_version": "0.1.0",
            "resources": {},
        }))
        zf.writestr("metadata.json", json.dumps({"name": "topology sizing demo"}))
        zf.writestr("geometry/shape_ir.json", json.dumps(shape_ir))
        zf.writestr("analysis/topology_optimization.json", json.dumps(topo))
    return pkg


def _volume_recompiler(shape_ir: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
    """Analytical volume/mass for a single extruded square region.

    Simulates compilation without an external CAD/CAE solver.
    """
    part = shape_ir["parts"][0]
    thickness = part["thickness"]
    pts = part["polygons"][0]
    area = abs(
        sum(
            (pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1])
            for i in range(len(pts) - 1)
        )
    ) / 2.0
    volume = area * float(thickness)
    return {
        "compile_status": "compile_succeeded",
        "geometry_execution": {"executed": True, "geometry_kind": "analytical"},
        "verification": {"passed": True, "checks": []},
        "metrics": {"volume_mm3": volume, "mass_kg": volume * 2.7e-6},
        "errors": [],
        "warnings": [],
    }


def test_topology_sizing_demo_end_to_end_static_metrics(tmp_path: Path) -> None:
    """Recovered body → sizing study → candidates → rank → recommendation → report."""
    pkg = _make_pkg(tmp_path)
    original_baseline = _read(pkg, "geometry/shape_ir.json")

    # 1. Topology result → sizing study envelope.
    t2s = topology_to_sizing(pkg)
    assert t2s["status"] == "ok"
    assert t2s["baseline_modified"] is False

    # 2. Propose candidates from the recovered thickness variable.
    sample = sample_candidates_package(pkg, algorithm="grid", max_candidates=5)
    assert sample["status"] == "ok"
    assert sample["candidate_count"] >= 1

    # 3. Execute candidates with the analytical recompiler.
    exec_res = run_design_study_batch(pkg, recompiler=_volume_recompiler)
    assert exec_res["status"] == "ok"

    # 4. Evaluate (no external CAE — static metrics only).
    eval_res = run_design_study_evaluation_batch(pkg)
    assert eval_res["status"] == "ok"

    # 5. Rank candidates by volume objective.
    rank_res = rank_design_study_candidates(pkg)
    assert rank_res["status"] == "ok"
    assert rank_res["candidate_count"] >= 1

    # 6. Advisory recommendation.
    rec_res = explain_recommendation(pkg)
    assert rec_res["status"] == "ok"
    assert rec_res["baseline_modified"] is False

    # 7. Aggregate report.
    rep_res = build_optimization_report(pkg)
    assert rep_res["status"] == "ok"
    assert rep_res["baseline_modified"] is False

    report = _read(pkg, "diagnostics/optimization_report.json")
    assert report["sources_present"]["ranking"] is True
    assert report["sources_present"]["recommendation"] is True
    assert report["problem"]["shape_bearing_variable_count"] == 0
    assert report["problem"]["variable_count"] == 1

    # Topology→sizing chain is preserved in the report.
    assert report["topology_to_sizing_chain"] is not None
    assert report["topology_to_sizing_chain"]["production_ready"] is False
    assert report["ranking"]["best_candidate_id"] is not None

    # Honest CAE absence: stress/displacement are missing, not fabricated.
    candidate_rows = report["candidates"]
    assert len(candidate_rows) >= 1
    for row in candidate_rows:
        assert row["metrics"].get("volume_mm3") is not None
        assert row["metrics"].get("max_stress") is None

    # Baseline geometry was never touched.
    assert _read(pkg, "geometry/shape_ir.json") == original_baseline


def _read(pkg: Path, name: str) -> Any:
    with zipfile.ZipFile(pkg, "r") as zf:
        return json.loads(zf.read(name))
