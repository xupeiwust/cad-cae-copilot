"""Tests for the optimization study summary report (#43).

The report aggregates existing package artifacts and is reconstructable from
them. It is read-only with respect to engineering state and never modifies the
baseline.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.optimization_report import (
    OPTIMIZATION_REPORT_PATH,
    build_optimization_report,
)

_BASELINE = {"representation": "brep_build123d", "parts": [{"id": "base"}]}


def _problem():
    return {
        "format": "aieng.design_study_problem", "schema_version": "0.1", "id": "study_001",
        "variables": [
            {"id": "wall_t", "path": "parts/0/params/WALL_THICKNESS", "type": "continuous",
             "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "safe_to_modify": True},
        ],
        "constraints": [{"id": "stress_limit", "type": "max_stress", "limit": 200.0}],
        "objective": {"sense": "minimize", "metric": "mass"},
    }


def _ranking():
    return {
        "format": "aieng.design_study.candidate_ranking.v0", "status": "ranked",
        "objective": {"sense": "minimize", "metric": "mass"},
        "best_candidate_id": "cand_good", "safe_to_accept": True, "next_action": "accept_candidate",
        "candidates": [
            {"rank": 1, "candidate_id": "cand_good", "feasibility": "feasible", "confidence": "high",
             "score": 0.2, "recommendation": "accept_candidate", "metrics_used": {"mass_kg": 0.8},
             "constraint_violations": [], "objective_delta": {"metric": "mass", "delta_percent": 20.0},
             "reasons": []},
            {"rank": 2, "candidate_id": "cand_bad", "feasibility": "failed", "confidence": "low",
             "score": -1.0, "recommendation": "reject_candidate", "metrics_used": {},
             "constraint_violations": [], "objective_delta": {}, "reasons": ["compile failed"]},
        ],
    }


def _iterations():
    return {
        "format": "aieng.design_study_iterations", "schema_version": "0.1",
        "iterations": [
            {"candidate_id": "cand_good", "execution_status": "evaluation_complete",
             "recommendation": "refine_candidate", "metrics": {"mass_kg": 0.8}},
            {"candidate_id": "cand_bad", "execution_status": "compile_failed",
             "recommendation": "compile_failed", "metrics": {}},
        ],
    }


def _write_pkg(tmp_path: Path, members: dict[str, Any]) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Study"}))
        zf.writestr("geometry/shape_ir.json", json.dumps(_BASELINE))
        for name, data in members.items():
            zf.writestr(name, json.dumps(data) if isinstance(data, (dict, list)) else data)
    return pkg


def _read(pkg, name):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


def _full_members():
    return {
        "analysis/design_study_problem.json": _problem(),
        "analysis/design_study_candidate_ranking.json": _ranking(),
        "analysis/design_study_iterations.json": _iterations(),
        "analysis/optimization_recommendation.json": {
            "headline": "Recommend candidate cand_good",
            "recommended_candidate_id": "cand_good",
            "reason_codes": ["advisory_recommendation", "human_approval_required"],
        },
        "analysis/design_study_acceptance.json": {
            "status": "accepted", "accepted_candidate_id": "cand_good",
            "promotion_mode": "derived_only",
        },
        "candidates/cand_good/analysis/evaluation.json": {
            "candidate_id": "cand_good", "evaluation_status": "complete",
            "feasibility": "feasible", "metrics": {"mass_kg": 0.8, "max_stress": 150.0}},
        "candidates/cand_bad/analysis/evaluation.json": {
            "candidate_id": "cand_bad", "evaluation_status": "insufficient_data",
            "feasibility": "failed", "metrics": {}},
    }


# ── full study ───────────────────────────────────────────────────────────────

def test_full_study_report(tmp_path: Path):
    pkg = _write_pkg(tmp_path, _full_members())
    res = build_optimization_report(pkg)
    assert res["status"] == "ok"
    assert res["candidate_count"] == 2
    assert res["failed_candidate_count"] == 1
    assert res["best_candidate_id"] == "cand_good"
    assert res["accepted_candidate_id"] == "cand_good"
    assert res["baseline_modified"] is False
    # core stages present in this fixture are not reported missing
    for stage in ("problem", "iterations", "ranking", "recommendation", "acceptance"):
        assert stage not in res["missing_stages"]

    doc = _read(pkg, OPTIMIZATION_REPORT_PATH)
    assert doc["problem"]["id"] == "study_001"
    assert doc["problem"]["objective"]["metric"] == "mass"
    assert {c["candidate_id"] for c in doc["candidates"]} == {"cand_good", "cand_bad"}
    # metrics pulled from per-candidate evaluation
    good = [c for c in doc["candidates"] if c["candidate_id"] == "cand_good"][0]
    assert good["metrics"]["max_stress"] == 150.0
    assert good["rank"] == 1
    # failed candidate captured separately
    assert [f["candidate_id"] for f in doc["failed_candidates"]] == ["cand_bad"]
    assert doc["feasibility_summary"].get("feasible") == 1
    assert doc["feasibility_summary"].get("failed") == 1
    assert doc["recommendation"]["recommended_candidate_id"] == "cand_good"
    assert doc["acceptance"]["accepted_candidate_id"] == "cand_good"
    assert doc["honesty"]["production_sign_off"] is False
    # baseline untouched
    assert _read(pkg, "geometry/shape_ir.json") == _BASELINE


def test_report_surfaces_shape_study(tmp_path: Path):
    members = _full_members()
    members["analysis/optimization_variables.json"] = {
        "format": "aieng.optimization_variables", "schema_version": "0.2",
        "variables": [
            {"id": "wall_t", "shape_bearing": False},
            {"id": "fillet_r", "shape_bearing": True},
            {"id": "hole_d", "shape_bearing": True},
        ],
    }
    pkg = _write_pkg(tmp_path, members)
    build_optimization_report(pkg)
    doc = _read(pkg, OPTIMIZATION_REPORT_PATH)
    assert doc["problem"]["shape_study"] is True
    assert doc["problem"]["shape_bearing_variable_count"] == 2


def test_report_shape_study_false_when_no_shape_vars(tmp_path: Path):
    members = _full_members()
    members["analysis/optimization_variables.json"] = {
        "format": "aieng.optimization_variables", "schema_version": "0.2",
        "variables": [
            {"id": "wall_t", "shape_bearing": False},
        ],
    }
    pkg = _write_pkg(tmp_path, members)
    build_optimization_report(pkg)
    doc = _read(pkg, OPTIMIZATION_REPORT_PATH)
    assert doc["problem"]["shape_study"] is False
    assert doc["problem"]["shape_bearing_variable_count"] == 0


def test_report_shape_study_false_when_no_variables_artifact(tmp_path: Path):
    members = {k: v for k, v in _full_members().items() if k != "analysis/optimization_variables.json"}
    pkg = _write_pkg(tmp_path, members)
    build_optimization_report(pkg)
    doc = _read(pkg, OPTIMIZATION_REPORT_PATH)
    assert doc["problem"]["shape_study"] is False
    assert doc["problem"]["shape_bearing_variable_count"] == 0


# ── reproducibility: building twice yields the same artifact ─────────────────

def test_report_is_reproducible(tmp_path: Path):
    pkg = _write_pkg(tmp_path, _full_members())
    build_optimization_report(pkg)
    first = _read(pkg, OPTIMIZATION_REPORT_PATH)
    build_optimization_report(pkg)
    second = _read(pkg, OPTIMIZATION_REPORT_PATH)
    assert first == second


# ── partial study: honest about missing stages ──────────────────────────────

def test_partial_study_reports_missing_stages(tmp_path: Path):
    # problem + iterations only — no ranking/recommendation/acceptance yet
    pkg = _write_pkg(tmp_path, {
        "analysis/design_study_problem.json": _problem(),
        "analysis/design_study_iterations.json": _iterations(),
        "candidates/cand_good/analysis/evaluation.json": {
            "candidate_id": "cand_good", "feasibility": "feasible", "metrics": {"mass_kg": 0.8}},
    })
    res = build_optimization_report(pkg)
    assert res["status"] == "ok"
    assert res["best_candidate_id"] is None
    assert "ranking" in res["missing_stages"]
    assert "recommendation" in res["missing_stages"]
    assert "acceptance" in res["missing_stages"]
    doc = _read(pkg, OPTIMIZATION_REPORT_PATH)
    assert doc["sources_present"]["ranking"] is False
    assert doc["sources_present"]["iterations"] is True
    assert doc["candidate_count"] == 2  # both iterations counted


# ── guards ───────────────────────────────────────────────────────────────────

def test_no_study_is_insufficient_data(tmp_path: Path):
    pkg = _write_pkg(tmp_path, {})  # baseline only, no study artifacts
    res = build_optimization_report(pkg)
    assert res["status"] == "insufficient_data"
    assert res["code"] == "no_study"


def test_missing_package_errors(tmp_path: Path):
    res = build_optimization_report(tmp_path / "nope.aieng")
    assert res["status"] == "error"
    assert res["code"] == "package_not_found"


# ── Pareto-front surfacing ───────────────────────────────────────────────────

def _pareto_ranking():
    return {
        "format": "aieng.design_study.candidate_ranking.v0",
        "status": "ranked",
        "objectives": [
            {"sense": "minimize", "metric": "mass"},
            {"sense": "minimize", "metric": "max_stress"},
        ],
        "best_candidate_id": None,
        "safe_to_accept": False,
        "next_action": "request_user_input",
        "candidates": [
            {"rank": 1, "candidate_id": "cand_light_weak", "feasibility": "feasible",
             "confidence": "medium", "score": 0.1, "recommendation": "refine_candidate",
             "metrics_used": {"mass_kg": 0.7, "max_stress": 190.0},
             "constraint_violations": [], "objective_delta": {}, "reasons": []},
            {"rank": 2, "candidate_id": "cand_heavy_strong", "feasibility": "feasible",
             "confidence": "medium", "score": 0.05, "recommendation": "refine_candidate",
             "metrics_used": {"mass_kg": 1.1, "max_stress": 120.0},
             "constraint_violations": [], "objective_delta": {}, "reasons": []},
            {"rank": 3, "candidate_id": "cand_dominated", "feasibility": "feasible",
             "confidence": "low", "score": -0.1, "recommendation": "reject_candidate",
             "metrics_used": {"mass_kg": 1.0, "max_stress": 180.0},
             "constraint_violations": [], "objective_delta": {}, "reasons": []},
        ],
        "pareto_front": {
            "status": "ok",
            "objective_metrics": ["mass", "max_stress"],
            "front_candidate_ids": ["cand_light_weak", "cand_heavy_strong"],
            "front": [
                {"candidate_id": "cand_light_weak", "rank": 1,
                 "objective_values": {"mass": 0.7, "max_stress": 190.0}},
                {"candidate_id": "cand_heavy_strong", "rank": 2,
                 "objective_values": {"mass": 1.1, "max_stress": 120.0}},
            ],
            "dominated_candidate_ids": ["cand_dominated"],
            "limitations": ["test limitation"],
        },
    }


def test_report_surfaces_pareto_front_from_ranking(tmp_path: Path):
    members = {
        "analysis/design_study_problem.json": {
            "format": "aieng.design_study_problem", "schema_version": "0.1", "id": "study_pareto",
            "variables": [
                {"id": "wall_t", "path": "parts/0/params/WALL_THICKNESS", "type": "continuous",
                 "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "safe_to_modify": True},
            ],
            "constraints": [{"id": "stress_limit", "type": "max_stress", "limit": 200.0}],
            "objectives": [
                {"sense": "minimize", "metric": "mass"},
                {"sense": "minimize", "metric": "max_stress"},
            ],
        },
        "analysis/design_study_candidate_ranking.json": _pareto_ranking(),
        "analysis/design_study_iterations.json": {
            "format": "aieng.design_study_iterations", "schema_version": "0.1",
            "iterations": [
                {"candidate_id": "cand_light_weak", "execution_status": "evaluation_complete"},
                {"candidate_id": "cand_heavy_strong", "execution_status": "evaluation_complete"},
                {"candidate_id": "cand_dominated", "execution_status": "evaluation_complete"},
            ],
        },
    }
    pkg = _write_pkg(tmp_path, members)
    res = build_optimization_report(pkg)
    assert res["status"] == "ok"

    doc = _read(pkg, OPTIMIZATION_REPORT_PATH)
    assert doc["pareto_front"] is not None
    assert doc["sources_present"]["pareto_front"] is True
    assert doc["pareto_front"]["status"] == "ok"
    assert doc["pareto_front"]["objective_metrics"] == ["mass", "max_stress"]
    assert set(doc["pareto_front"]["front_candidate_ids"]) == {"cand_light_weak", "cand_heavy_strong"}
    assert doc["pareto_front"]["dominated_candidate_ids"] == ["cand_dominated"]
    front = doc["pareto_front"]["front"]
    assert len(front) == 2
    by_id = {f["candidate_id"]: f for f in front}
    assert by_id["cand_light_weak"]["objective_values"] == {"mass": 0.7, "max_stress": 190.0}
    assert by_id["cand_heavy_strong"]["objective_values"] == {"mass": 1.1, "max_stress": 120.0}


def test_report_falls_back_to_ranking_pareto_when_artifact_is_malformed(tmp_path: Path) -> None:
    members = {
        "analysis/design_study_problem.json": {
            "format": "aieng.design_study_problem", "schema_version": "0.1", "id": "study_pareto",
            "variables": [
                {"id": "wall_t", "path": "parts/0/params/WALL_THICKNESS", "type": "continuous",
                 "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "safe_to_modify": True},
            ],
            "constraints": [{"id": "stress_limit", "type": "max_stress", "limit": 200.0}],
            "objectives": [
                {"sense": "minimize", "metric": "mass"},
                {"sense": "minimize", "metric": "max_stress"},
            ],
        },
        "analysis/design_study_candidate_ranking.json": _pareto_ranking(),
        "analysis/pareto_front.json": {"format": "aieng.pareto_front", "status": "ok"},  # malformed
        "analysis/design_study_iterations.json": {
            "format": "aieng.design_study_iterations", "schema_version": "0.1",
            "iterations": [
                {"candidate_id": "cand_light_weak", "execution_status": "evaluation_complete"},
                {"candidate_id": "cand_heavy_strong", "execution_status": "evaluation_complete"},
                {"candidate_id": "cand_dominated", "execution_status": "evaluation_complete"},
            ],
        },
    }
    pkg = _write_pkg(tmp_path, members)
    res = build_optimization_report(pkg)
    assert res["status"] == "ok"

    doc = _read(pkg, OPTIMIZATION_REPORT_PATH)
    assert doc["sources_present"]["pareto_front"] is True
    assert doc["pareto_front"]["status"] == "ok"
    assert doc["pareto_front"]["objective_metrics"] == ["mass", "max_stress"]
    assert set(doc["pareto_front"]["front_candidate_ids"]) == {"cand_light_weak", "cand_heavy_strong"}
    assert doc["pareto_front"]["dominated_candidate_ids"] == ["cand_dominated"]


def test_report_pareto_front_none_for_single_objective(tmp_path: Path):
    pkg = _write_pkg(tmp_path, _full_members())
    build_optimization_report(pkg)
    doc = _read(pkg, OPTIMIZATION_REPORT_PATH)
    assert doc["pareto_front"] is None
    assert doc["sources_present"]["pareto_front"] is False
