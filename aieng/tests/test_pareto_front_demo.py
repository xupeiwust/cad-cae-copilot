"""Demo / regression: 2-objective Pareto study (mass vs stress).

This is the canonical backend demo for the Phase-5 Pareto-aware workflow.
It builds a small design-study package, ranks the candidates, asks for an
advisory recommendation, and aggregates an optimization report — all without
running an external solver or modifying the baseline.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng.converters.design_study_ranking import (
    DESIGN_STUDY_CANDIDATE_RANKING_PATH,
    DESIGN_STUDY_SCORING_REPORT_PATH,
    PARETO_FRONT_PATH,
    rank_design_study_candidates,
)
from aieng.converters.design_study_execution import DESIGN_STUDY_ITERATIONS_PATH
from aieng.converters.optimization_recommendation import (
    OPTIMIZATION_RECOMMENDATION_PATH,
    explain_recommendation,
)
from aieng.converters.optimization_report import (
    OPTIMIZATION_REPORT_PATH,
    build_optimization_report,
)


BASELINE_SHAPE_IR = {"representation": "brep_build123d", "parts": [{"id": "bracket"}]}


def _problem() -> dict[str, Any]:
    return {
        "format": "aieng.design_study_problem",
        "schema_version": "0.1",
        "id": "pareto_demo_001",
        "variables": [
            {
                "id": "wall_t",
                "path": "shape_ir/params/WALL_THICKNESS",
                "type": "continuous",
                "current_value": 3.0,
                "min_value": 1.0,
                "max_value": 8.0,
                "unit": "mm",
                "safe_to_modify": True,
            },
        ],
        "constraints": [
            {"id": "c_stress", "type": "max_stress", "limit": 200.0, "unit": "MPa"},
        ],
        # Keep the legacy single-objective field absent to prove the workflow is
        # driven by the explicit objectives array.
        "objectives": [
            {"sense": "minimize", "metric": "mass", "unit": "kg"},
            {"sense": "minimize", "metric": "max_stress", "unit": "MPa"},
        ],
        "baseline_metrics": {"mass_kg": 1.0, "max_stress": 200.0},
        "settings": {"max_variables_per_candidate": 1, "require_reasoning": False},
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
    pkg = tmp_path / "pareto_demo.aieng"
    problem = _problem()
    iterations = [
        # Light and weak: low mass, higher stress but still feasible.
        _iteration("c_light", {"mass_kg": 0.70, "max_stress": 190.0}),
        # Heavy and strong: high mass, very low stress.
        _iteration("c_heavy", {"mass_kg": 1.10, "max_stress": 120.0}),
        # Dominated: worse than c_light in both mass and stress.
        _iteration("c_dominated", {"mass_kg": 1.00, "max_stress": 195.0}),
        # Extra evaluated candidate to satisfy the ≥5-candidate demo requirement.
        _iteration("c_extra", {"mass_kg": 0.95, "max_stress": 150.0}),
        # Infeasible: stress exceeds the constraint limit; must be excluded.
        _iteration("c_infeasible", {"mass_kg": 0.60, "max_stress": 210.0}),
    ]
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Pareto demo"}))
        zf.writestr("geometry/shape_ir.json", json.dumps(BASELINE_SHAPE_IR))
        zf.writestr("analysis/design_study_problem.json", json.dumps(problem))
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


def test_pareto_demo_end_to_end(tmp_path: Path) -> None:
    """Mass-vs-stress Pareto demo: rank → recommend → report."""
    pkg = _write_pkg(tmp_path)
    original_baseline = _read(pkg, "geometry/shape_ir.json")

    # ── Rank: Pareto front should be identified advisory-only ─────────────────
    rank_res = rank_design_study_candidates(pkg)
    assert rank_res["status"] == "ok"
    assert rank_res["design_study_present"] is True
    assert rank_res["candidate_count"] == 5
    assert PARETO_FRONT_PATH in rank_res["artifacts"]

    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["status"] == "ranked"
    assert ranking["best_candidate_id"] is None
    assert ranking["safe_to_accept"] is False
    assert ranking["next_action"] == "request_user_input"
    assert ranking["pareto_front"]["status"] == "ok"
    assert set(ranking["pareto_front"]["front_candidate_ids"]) == {"c_light", "c_heavy", "c_extra"}
    assert ranking["pareto_front"]["dominated_candidate_ids"] == ["c_dominated"]
    assert ranking["pareto_front"]["objective_metrics"] == ["mass", "max_stress"]

    # Embedded front summary must be present for downstream explanation.
    front = ranking["pareto_front"]["front"]
    assert len(front) == 3
    by_id = {item["candidate_id"]: item for item in front}
    assert by_id["c_light"]["objective_values"] == {"mass": 0.70, "max_stress": 190.0}
    assert by_id["c_heavy"]["objective_values"] == {"mass": 1.10, "max_stress": 120.0}
    assert by_id["c_extra"]["objective_values"] == {"mass": 0.95, "max_stress": 150.0}

    # The standalone artifact mirrors the ranking block and uses the proven
    # value_1 / value_2 shape from optimization_pareto.py.
    pareto_artifact = _read(pkg, PARETO_FRONT_PATH)
    assert pareto_artifact["format"] == "aieng.pareto_front"
    assert pareto_artifact["claim_policy"]["advisory_only"] is True
    assert {item["candidate_id"] for item in pareto_artifact["front"]} == {"c_light", "c_heavy", "c_extra"}

    # Baseline geometry was never touched.
    assert _read(pkg, "geometry/shape_ir.json") == original_baseline

    # ── Recommend: advisory trade-off set, no single global winner ────────────
    reco_res = explain_recommendation(pkg)
    assert reco_res["status"] == "ok"
    assert reco_res["recommended_candidate_id"] is None
    assert reco_res["safe_to_accept"] is False
    assert reco_res["next_action"] == "request_user_input"
    assert "advisory_trade_off_set" in reco_res["reason_codes"]

    recommendation = _read(pkg, OPTIMIZATION_RECOMMENDATION_PATH)
    assert recommendation["recommended_candidate_id"] is None
    assert recommendation["safe_to_accept"] is False
    assert recommendation["next_action"] == "request_user_input"
    assert len(recommendation["alternatives"]) == 3
    assert recommendation["pareto_front"]["objective_metrics"] == ["mass", "max_stress"]

    # Wording discipline: the explanation must not promote a global optimum.
    combined_text = " ".join(
        [recommendation["headline"]]
        + recommendation["rationale"]
        + recommendation["caveats"]
    ).lower()
    assert "optimal" not in combined_text
    assert "best" not in combined_text
    assert any("approval-gated" in c for c in recommendation["caveats"])
    assert any("proven pareto surface" in c.lower() for c in recommendation["caveats"])

    # ── Report: aggregates the Pareto frontier transparently ─────────────────
    report_res = build_optimization_report(pkg)
    assert report_res["status"] == "ok"
    assert report_res["candidate_count"] == 5
    assert report_res["baseline_modified"] is False
    assert "pareto_front" not in report_res["missing_stages"]

    report = _read(pkg, OPTIMIZATION_REPORT_PATH)
    assert report["sources_present"]["pareto_front"] is True
    assert report["pareto_front"]["status"] == "ok"
    assert set(report["pareto_front"]["front_candidate_ids"]) == {"c_light", "c_heavy", "c_extra"}

    # Honesty: the report does not claim a solver ran or a candidate was accepted.
    assert report["honesty"]["production_sign_off"] is False
    assert report["honesty"]["baseline_modified"] is False
    assert report["acceptance"] is None or report["acceptance"].get("accepted_candidate_id") is None

    # Baseline is still untouched after all read-only aggregation steps.
    assert _read(pkg, "geometry/shape_ir.json") == original_baseline
