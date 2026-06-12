"""Demo / regression: fillet + hole shape study on a bracket.

Validates the Phase-3 shape-study pipeline end-to-end using deterministic
static metrics (no external solver). Five candidates cover feasible and
manufacturing-rule-infeasible regions. The baseline geometry is never modified.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.design_study_ranking import (
    DESIGN_STUDY_CANDIDATE_RANKING_PATH,
    DESIGN_STUDY_SCORING_REPORT_PATH,
    rank_design_study_candidates,
)
from aieng.converters.design_study_execution import DESIGN_STUDY_ITERATIONS_PATH
from aieng.converters.optimization_recommendation import (
    OPTIMIZATION_RECOMMENDATION_PATH,
    explain_recommendation,
)
from aieng.converters.optimization_report import (
    OPTIMIZATION_REPORT_PATH,
    OPTIMIZATION_VARIABLES_PATH,
    build_optimization_report,
)


BASELINE_SHAPE_IR = {"representation": "brep_build123d", "parts": [{"id": "bracket"}]}


def _problem() -> dict[str, Any]:
    return {
        "format": "aieng.design_study_problem",
        "schema_version": "0.1",
        "id": "bracket_shape_study_001",
        "variables": [
            {
                "id": "fillet_r",
                "path": "shape_ir/params/FILLET_RADIUS",
                "type": "continuous",
                "current_value": 2.0,
                "min_value": 0.5,
                "max_value": 5.0,
                "unit": "mm",
                "safe_to_modify": True,
                "semantic_role": "fillet_radius",
            },
            {
                "id": "hole_d",
                "path": "shape_ir/params/HOLE_DIAMETER",
                "type": "continuous",
                "current_value": 8.0,
                "min_value": 2.0,
                "max_value": 20.0,
                "unit": "mm",
                "safe_to_modify": True,
                "semantic_role": "hole_diameter",
            },
            {
                "id": "wall_t",
                "path": "shape_ir/params/WALL_THICKNESS",
                "type": "continuous",
                "current_value": 3.0,
                "min_value": 1.0,
                "max_value": 8.0,
                "unit": "mm",
                "safe_to_modify": True,
                "semantic_role": "wall_thickness",
            },
        ],
        "constraints": [
            {"id": "c_stress", "type": "max_stress", "limit": 200.0, "unit": "MPa"},
            {"id": "c_deflection", "type": "max_deflection", "limit": 5.0, "unit": "mm"},
            {"id": "c_min_fillet", "type": "manufacturing_rule", "expr": "min_fillet_radius >= 2.0"},
            {"id": "c_hole_edge", "type": "manufacturing_rule", "expr": "hole_edge_distance >= 4.0"},
        ],
        "objective": {"sense": "minimize", "metric": "mass", "unit": "kg"},
        "baseline_metrics": {
            "mass_kg": 1.0,
            "max_stress": 150.0,
            "max_deflection": 2.0,
            "min_fillet_radius": 2.0,
            "hole_edge_distance": 10.0,
        },
        "settings": {"max_variables_per_candidate": 2, "require_reasoning": False},
    }


def _optimization_variables() -> dict[str, Any]:
    return {
        "format": "aieng.optimization_variables",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.2",
        "study_id": "bracket_shape_study_001",
        "source_problem_ref": "analysis/design_study_problem.json",
        "variables": [
            {
                "id": "fillet_r",
                "parameter_name": "FILLET_RADIUS",
                "cad_parameter_name": "FILLET_RADIUS",
                "semantic_role": "fillet_radius",
                "shape_bearing": True,
                "scope": "local",
                "binding_status": "unverified",
            },
            {
                "id": "hole_d",
                "parameter_name": "HOLE_DIAMETER",
                "cad_parameter_name": "HOLE_DIAMETER",
                "semantic_role": "hole_diameter",
                "shape_bearing": True,
                "scope": "local",
                "binding_status": "unverified",
            },
            {
                "id": "wall_t",
                "parameter_name": "WALL_THICKNESS",
                "cad_parameter_name": "WALL_THICKNESS",
                "semantic_role": "wall_thickness",
                "shape_bearing": False,
                "scope": "local",
                "binding_status": "unverified",
            },
        ],
    }


def _iteration(cid: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": cid,
        "execution_status": "evaluation_complete",
        "validation_status": "valid",
        "metrics": metrics,
        "recommendation": "refine_candidate",
        "baseline_modified": False,
        "candidate_workspace": f"candidates/{cid}/",
    }


def _write_pkg(tmp_path: Path) -> Path:
    pkg = tmp_path / "shape_study_bracket.aieng"
    problem = _problem()
    iterations = [
        # Baseline-like: feasible, no improvement.
        _iteration("c_baseline", {
            "mass_kg": 1.00, "max_stress": 150.0, "max_deflection": 2.0,
            "min_fillet_radius": 2.0, "hole_edge_distance": 10.0,
        }),
        # Light and within all manufacturing rules: should become the best candidate.
        _iteration("c_light_ok", {
            "mass_kg": 0.85, "max_stress": 170.0, "max_deflection": 2.5,
            "min_fillet_radius": 2.0, "hole_edge_distance": 6.0,
        }),
        # Manufacturing-rule violation: fillet radius too small.
        _iteration("c_small_fillet", {
            "mass_kg": 0.95, "max_stress": 160.0, "max_deflection": 2.1,
            "min_fillet_radius": 1.0, "hole_edge_distance": 10.0,
        }),
        # Manufacturing-rule violation: hole too close to edge.
        _iteration("c_hole_close", {
            "mass_kg": 0.80, "max_stress": 180.0, "max_deflection": 2.8,
            "min_fillet_radius": 2.0, "hole_edge_distance": 2.0,
        }),
        # Stress constraint violation.
        _iteration("c_thin_wall", {
            "mass_kg": 0.78, "max_stress": 250.0, "max_deflection": 3.2,
            "min_fillet_radius": 2.0, "hole_edge_distance": 6.0,
        }),
    ]
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Shape study bracket demo"}))
        zf.writestr("geometry/shape_ir.json", json.dumps(BASELINE_SHAPE_IR))
        zf.writestr("analysis/design_study_problem.json", json.dumps(problem))
        zf.writestr(OPTIMIZATION_VARIABLES_PATH, json.dumps(_optimization_variables()))
        zf.writestr(
            DESIGN_STUDY_ITERATIONS_PATH,
            json.dumps(
                {
                    "format": "aieng.design_study_iterations",
                    "format_version": "0.1.0",
                    "schema_version": "0.1",
                    "iterations": iterations,
                    "provenance": {"created_by": "test", "baseline_modified": False},
                }
            ),
        )
    return pkg


def _read(pkg: Path, name: str) -> Any:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


def test_shape_study_bracket_demo_end_to_end(tmp_path: Path) -> None:
    """Fillet + hole shape study: rank → recommend → report."""
    pkg = _write_pkg(tmp_path)
    original_baseline = _read(pkg, "geometry/shape_ir.json")

    # ── Rank: shape variables, manufacturing-rule violations, best candidate ──
    rank_res = rank_design_study_candidates(pkg)
    assert rank_res["status"] == "ok"
    assert rank_res["design_study_present"] is True
    assert rank_res["candidate_count"] == 5

    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["status"] == "ranked"
    by_id = {c["candidate_id"]: c for c in ranking["candidates"]}

    # Feasible candidate that improves mass should win.
    assert by_id["c_light_ok"]["feasibility"] == "feasible"
    assert by_id["c_light_ok"]["score"] > 0
    assert ranking["best_candidate_id"] == "c_light_ok"
    assert ranking["safe_to_accept"] is True

    # At least one manufacturing-rule rejection.
    assert by_id["c_small_fillet"]["feasibility"] == "infeasible"
    assert any(
        "min_fillet_radius" in v for v in by_id["c_small_fillet"]["constraint_violations"]
    )
    assert by_id["c_hole_close"]["feasibility"] == "infeasible"
    assert any(
        "hole_edge_distance" in v for v in by_id["c_hole_close"]["constraint_violations"]
    )

    # Stress-only rejection is also present.
    assert by_id["c_thin_wall"]["feasibility"] == "infeasible"
    assert any("stress" in v for v in by_id["c_thin_wall"]["constraint_violations"])

    # Baseline geometry untouched after ranking.
    assert _read(pkg, "geometry/shape_ir.json") == original_baseline

    # ── Recommend: advisory, approval-gated ──────────────────────────────────
    reco_res = explain_recommendation(pkg)
    assert reco_res["status"] == "ok"
    assert reco_res["recommended_candidate_id"] == "c_light_ok"
    assert reco_res["safe_to_accept"] is True
    assert reco_res["advisory_only"] is True
    assert reco_res["requires_human_review"] is True
    assert "human_approval_required" in reco_res["reason_codes"]

    recommendation = _read(pkg, OPTIMIZATION_RECOMMENDATION_PATH)
    assert recommendation["recommended_candidate_id"] == "c_light_ok"
    assert recommendation["safe_to_accept"] is True
    assert recommendation["advisory_only"] is True
    assert recommendation["requires_human_review"] is True

    # ── Report: flags shape study and aggregates advisory state ──────────────
    report_res = build_optimization_report(pkg)
    assert report_res["status"] == "ok"
    assert report_res["candidate_count"] == 5
    assert report_res["baseline_modified"] is False
    assert report_res["best_candidate_id"] == "c_light_ok"

    report = _read(pkg, OPTIMIZATION_REPORT_PATH)
    assert report["problem"]["shape_study"] is True
    assert report["problem"]["shape_bearing_variable_count"] == 2
    assert report["sources_present"]["variables"] is True
    assert report["recommendation"]["recommended_candidate_id"] == "c_light_ok"
    # No acceptance artifact → acceptance is unresolved / human-gated.
    assert report["acceptance"]["accepted_candidate_id"] is None
    assert report["acceptance"]["status"] is None

    # Baseline still untouched after all read-only aggregation.
    assert _read(pkg, "geometry/shape_ir.json") == original_baseline
