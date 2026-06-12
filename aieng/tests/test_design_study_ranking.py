"""Tests for design study candidate RANKING and COMPARISON v0 (PR3).

Ranking compares already-executed candidates — it does NOT execute new candidates,
does NOT recompile geometry, does NOT run CAE, and does NOT modify baseline geometry.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.design_study_ranking import (
    DESIGN_STUDY_CANDIDATE_RANKING_PATH,
    DESIGN_STUDY_SCORING_REPORT_PATH,
    PARETO_FRONT_PATH,
    _build_ranking,
    _build_scoring_report,
    _classify_feasibility,
    _score_candidate,
    rank_design_study_candidates,
)
from aieng.converters.design_study_execution import DESIGN_STUDY_ITERATIONS_PATH


# ── helpers ───────────────────────────────────────────────────────────────────

def _problem(**overrides):
    p = {
        "format": "aieng.design_study_problem", "schema_version": "0.1",
        "id": "study_001",
        "variables": [
            {"id": "wall_t", "path": "shape_ir/params/WALL_THICKNESS", "type": "continuous",
             "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "unit": "mm",
             "safe_to_modify": True, "semantic_role": "wall_thickness"},
        ],
        "constraints": [
            {"id": "c_stress", "type": "max_stress", "limit": 200.0, "unit": "MPa"},
            {"id": "c_deflection", "type": "max_deflection", "limit": 5.0, "unit": "mm"},
        ],
        "objective": {"sense": "minimize", "metric": "mass"},
        "settings": {"max_variables_per_candidate": 2, "require_reasoning": True},
    }
    p.update(overrides)
    return p


def _iteration(cid, execution_status, metrics=None, validation_status="valid"):
    return {
        "candidate_id": cid,
        "execution_status": execution_status,
        "validation_status": validation_status,
        "metrics": metrics or {},
        "recommendation": "refine_candidate",
        "baseline_modified": False,
        "candidate_workspace": f"candidates/{cid}/",
    }


def _write_pkg(tmp_path: Path, *, problem=None, iterations=None,
               extra_members=None) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Study"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"representation": "brep_build123d"}))
        if problem is not None:
            zf.writestr("analysis/design_study_problem.json", json.dumps(problem))
        if iterations is not None:
            doc = {
                "format": "aieng.design_study_iterations",
                "format_version": "0.1.0",
                "schema_version": "0.1",
                "iterations": iterations,
                "provenance": {"created_by": "test", "baseline_modified": False},
            }
            zf.writestr(DESIGN_STUDY_ITERATIONS_PATH, json.dumps(doc))
        for name, data in (extra_members or {}).items():
            if isinstance(data, (dict, list)):
                data = json.dumps(data)
            zf.writestr(name, data)
    return pkg


def _read(pkg, name):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


# ── unit: feasibility classification ──────────────────────────────────────────

def test_feasibility_rejected_is_failed():
    it = _iteration("c1", "rejected", validation_status="rejected")
    feas, reasons, _ = _classify_feasibility(it, _problem(), {})
    assert feas == "failed"
    assert any("rejected" in r for r in reasons)


def test_feasibility_compile_failed_is_failed():
    it = _iteration("c1", "compile_failed")
    feas, reasons, _ = _classify_feasibility(it, _problem(), {})
    assert feas == "failed"
    assert any("compile failed" in r for r in reasons)


def test_feasibility_missing_metrics_is_unknown():
    it = _iteration("c1", "evaluation_complete")
    feas, reasons, _ = _classify_feasibility(it, _problem(), {})
    assert feas == "unknown"
    assert any("no metrics" in r for r in reasons)


def test_feasibility_constraint_violation_is_infeasible():
    it = _iteration("c1", "evaluation_complete")
    metrics = {"max_stress": 250.0, "mass_kg": 1.0}  # stress exceeds 200
    feas, reasons, _ = _classify_feasibility(it, _problem(), metrics)
    assert feas == "infeasible"
    assert any("stress" in r for r in reasons)


def test_feasibility_satisfied_is_feasible():
    it = _iteration("c1", "evaluation_complete")
    metrics = {"max_stress": 150.0, "max_deflection": 3.0, "mass_kg": 1.0}
    feas, reasons, _ = _classify_feasibility(it, _problem(), metrics)
    assert feas == "feasible"
    assert any("satisfied" in r for r in reasons)


def test_feasibility_partial_metrics_unknown():
    """A candidate with only geometry metrics but no objective metric is unknown."""
    it = _iteration("c1", "evaluation_complete")
    metrics = {"executed": True, "geometry_kind": "brep"}  # no mass
    feas, _, warnings = _classify_feasibility(it, _problem(), metrics)
    assert feas == "unknown"


# ── unit: scoring ─────────────────────────────────────────────────────────────

def test_score_failed_candidate_is_penalized():
    score, conf, delta, reasons = _score_candidate(
        _iteration("c1", "rejected"), _problem(), {}, {}, "failed"
    )
    assert score == -1.0
    assert conf == "low"


def test_score_infeasible_candidate_is_penalized():
    score, conf, delta, reasons = _score_candidate(
        _iteration("c1", "evaluation_complete"), _problem(), {}, {}, "infeasible"
    )
    assert score == -0.5
    assert conf == "low"


def test_score_unknown_candidate_is_neutral():
    score, conf, delta, reasons = _score_candidate(
        _iteration("c1", "evaluation_complete"), _problem(), {}, {}, "unknown"
    )
    assert score == 0.0
    assert conf == "low"


def test_score_reduce_mass_improvement():
    """Lower mass vs baseline should score positively."""
    it = _iteration("c1", "evaluation_complete")
    metrics = {"mass_kg": 0.8, "max_stress": 150.0, "max_deflection": 3.0}
    baseline = {"mass_kg": 1.0}
    score, conf, delta, reasons = _score_candidate(
        it, _problem(objective={"sense": "minimize", "metric": "mass"}),
        metrics, baseline, "feasible"
    )
    assert score > 0  # 1 - 0.8/1.0 = 0.2
    assert delta["delta_percent"] == -20.0
    assert conf == "high"


def test_score_reduce_volume_improvement():
    """Lower volume vs baseline should score positively for reduce_volume."""
    it = _iteration("c1", "evaluation_complete")
    metrics = {"volume_mm3": 800.0, "max_stress": 150.0}
    baseline = {"volume_mm3": 1000.0}
    score, conf, delta, reasons = _score_candidate(
        it, _problem(objective={"sense": "minimize", "metric": "volume"}),
        metrics, baseline, "feasible"
    )
    assert score > 0  # 1 - 800/1000 = 0.2
    assert delta["delta_percent"] == -20.0


def test_score_stress_violation_still_scores_objective():
    """Even if constraints make it infeasible, the objective score is computed
    for the ranking layer — the feasibility layer handles the rejection."""
    it = _iteration("c1", "evaluation_complete")
    metrics = {"mass_kg": 0.8, "max_stress": 250.0}
    baseline = {"mass_kg": 1.0}
    score, conf, delta, reasons = _score_candidate(
        it, _problem(), metrics, baseline, "infeasible"
    )
    assert score == -0.5  # infeasible penalty, not objective-based


def test_score_safety_factor_higher_is_better():
    it = _iteration("c1", "evaluation_complete")
    metrics = {"min_safety_factor": 2.5, "max_stress": 150.0}
    baseline = {"min_safety_factor": 2.0}
    score, conf, delta, reasons = _score_candidate(
        it, _problem(objective={"sense": "maximize", "metric": "safety_factor"}),
        metrics, baseline, "feasible"
    )
    assert score > 0  # 2.5/2.0 - 1 = 0.25
    assert delta["delta_percent"] == 25.0


def test_score_balanced_objective():
    it = _iteration("c1", "evaluation_complete")
    metrics = {"mass_kg": 0.9, "volume_mm3": 900.0, "max_stress": 150.0}
    baseline = {"mass_kg": 1.0, "volume_mm3": 1000.0}
    score, conf, delta, reasons = _score_candidate(
        it, _problem(objective={"sense": "balanced", "metric": "balanced"}),
        metrics, baseline, "feasible"
    )
    # mass: 1 - 0.9/1.0 = 0.1, volume: 1 - 900/1000 = 0.1, avg = 0.1
    assert score > 0
    assert conf == "low"  # only 2 sub-metrics available


def test_score_proxy_only_penalty():
    """Metrics with only 'executed' and no objective metric score neutral with low confidence."""
    it = _iteration("c1", "evaluation_complete")
    metrics = {"executed": True, "geometry_kind": "brep"}
    baseline = {}
    score, conf, delta, reasons = _score_candidate(
        it, _problem(), metrics, baseline, "feasible"
    )
    assert score == 0.0  # no objective metric available
    assert conf == "low"
    # When objective metric IS present but only proxy data exists, penalty applies
    metrics2 = {"executed": True, "geometry_kind": "brep", "mass_kg": 0.9}
    score2, conf2, delta2, reasons2 = _score_candidate(
        it, _problem(), metrics2, {"mass_kg": 1.0}, "feasible"
    )
    assert score2 < 0.2  # proxy penalty of 0.5 applied to base 0.2 -> -0.3
    assert any("proxy" in r for r in reasons2)


def test_score_missing_baseline_is_medium_confidence():
    it = _iteration("c1", "evaluation_complete")
    metrics = {"mass_kg": 0.8, "max_stress": 150.0, "max_deflection": 3.0}
    score, conf, delta, reasons = _score_candidate(
        it, _problem(), metrics, {}, "feasible"
    )
    assert conf == "medium"  # has metrics but no baseline
    assert score == 0.0  # no baseline means no ratio


# ── unit: ranking assembly ────────────────────────────────────────────────────

def test_build_ranking_empty_candidates():
    ranking = _build_ranking(_problem(), [], {})
    assert ranking["status"] == "insufficient_data"
    assert ranking["best_candidate_id"] is None
    assert ranking["safe_to_accept"] is False


def test_build_ranking_orders_by_score():
    cands = [
        {"candidate_id": "c_low", "score": -0.5, "feasibility": "infeasible",
         "confidence": "low", "recommendation": "reject_candidate",
         "metrics_used": {}, "metrics_missing": [], "constraint_violations": [],
         "objective_delta": {}, "reasons": [],
         "execution_status": "", "validation_status": ""},
        {"candidate_id": "c_high", "score": 0.3, "feasibility": "feasible",
         "confidence": "high", "recommendation": "accept_candidate",
         "metrics_used": {}, "metrics_missing": [], "constraint_violations": [],
         "objective_delta": {}, "reasons": [],
         "execution_status": "", "validation_status": ""},
        {"candidate_id": "c_mid", "score": 0.1, "feasibility": "feasible",
         "confidence": "medium", "recommendation": "refine_candidate",
         "metrics_used": {}, "metrics_missing": [], "constraint_violations": [],
         "objective_delta": {}, "reasons": [],
         "execution_status": "", "validation_status": ""},
    ]
    ranking = _build_ranking(_problem(), cands, {"mass_kg": 1.0})
    assert ranking["status"] == "ranked"
    ids = [c["candidate_id"] for c in ranking["candidates"]]
    assert ids == ["c_high", "c_mid", "c_low"]
    assert ranking["best_candidate_id"] == "c_high"
    assert ranking["safe_to_accept"] is True
    assert ranking["next_action"] == "accept_candidate"


def test_build_ranking_no_safe_best():
    cands = [
        {"candidate_id": "c1", "score": 0.05, "feasibility": "feasible",
         "confidence": "medium", "recommendation": "refine_candidate",
         "metrics_used": {}, "metrics_missing": [], "constraint_violations": [],
         "objective_delta": {}, "reasons": [],
         "execution_status": "", "validation_status": ""},
    ]
    ranking = _build_ranking(_problem(), cands, {})
    assert ranking["best_candidate_id"] == "c1"
    assert ranking["safe_to_accept"] is False
    assert ranking["next_action"] == "run_more_evaluation"


def test_build_ranking_all_unknown():
    cands = [
        {"candidate_id": "c1", "score": 0.0, "feasibility": "unknown",
         "confidence": "low", "recommendation": "needs_more_evaluation",
         "metrics_used": {}, "metrics_missing": [], "constraint_violations": [],
         "objective_delta": {}, "reasons": [],
         "execution_status": "", "validation_status": ""},
    ]
    ranking = _build_ranking(_problem(), cands, {})
    assert ranking["best_candidate_id"] is None
    assert ranking["next_action"] == "run_more_evaluation"


def test_build_ranking_all_failed():
    cands = [
        {"candidate_id": "c1", "score": -1.0, "feasibility": "failed",
         "confidence": "low", "recommendation": "reject_candidate",
         "metrics_used": {}, "metrics_missing": [], "constraint_violations": [],
         "objective_delta": {}, "reasons": [],
         "execution_status": "", "validation_status": ""},
    ]
    ranking = _build_ranking(_problem(), cands, {})
    assert ranking["best_candidate_id"] is None
    assert ranking["next_action"] == "no_viable_candidate"


# ── integration: package-level ranking ────────────────────────────────────────

def test_rank_no_candidates_insufficient_data(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem())
    res = rank_design_study_candidates(pkg)
    assert res["status"] == "insufficient_data"
    assert res["reason"] == "no executed candidates found"
    # Artifacts written even for insufficient data
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["status"] == "insufficient_data"
    report = _read(pkg, DESIGN_STUDY_SCORING_REPORT_PATH)
    assert report["candidates_loaded"] == 0


def test_rank_failed_candidate_ranks_as_failed(tmp_path: Path):
    iters = [
        _iteration("c1", "rejected", validation_status="rejected"),
    ]
    pkg = _write_pkg(tmp_path, problem=_problem(), iterations=iters)
    res = rank_design_study_candidates(pkg)
    assert res["status"] == "ok"
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    c = ranking["candidates"][0]
    assert c["feasibility"] == "failed"
    assert c["recommendation"] == "reject_candidate"
    assert c["score"] == -1.0


def test_rank_compile_failed_is_failed(tmp_path: Path):
    iters = [
        _iteration("c1", "compile_failed", metrics={}),
    ]
    pkg = _write_pkg(tmp_path, problem=_problem(), iterations=iters)
    res = rank_design_study_candidates(pkg)
    assert res["status"] == "ok"
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    c = ranking["candidates"][0]
    assert c["feasibility"] == "failed"
    assert c["recommendation"] == "reject_candidate"


def test_rank_missing_metrics_unknown(tmp_path: Path):
    iters = [
        _iteration("c1", "evaluation_complete", metrics={}),
    ]
    pkg = _write_pkg(tmp_path, problem=_problem(), iterations=iters)
    res = rank_design_study_candidates(pkg)
    assert res["status"] == "ok"
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    c = ranking["candidates"][0]
    assert c["feasibility"] == "unknown"
    assert c["recommendation"] == "needs_more_evaluation"


def test_rank_reduce_volume_ranks_correctly(tmp_path: Path):
    """Candidate with lower volume and no violations ranks above baseline/other."""
    iters = [
        _iteration("c_baseline", "evaluation_complete",
                   metrics={"volume_mm3": 1000.0, "max_stress": 150.0}),
        _iteration("c_lower", "evaluation_complete",
                   metrics={"volume_mm3": 800.0, "max_stress": 150.0}),
        _iteration("c_higher", "evaluation_complete",
                   metrics={"volume_mm3": 1200.0, "max_stress": 150.0}),
    ]
    problem = _problem(
        objective={"sense": "minimize", "metric": "volume"},
        baseline_metrics={"volume_mm3": 1000.0},
    )
    pkg = _write_pkg(tmp_path, problem=problem, iterations=iters)
    res = rank_design_study_candidates(pkg)
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    ids = [c["candidate_id"] for c in ranking["candidates"]]
    # c_lower (score +0.2) > c_baseline (score 0.0) > c_higher (score -0.2)
    assert ids == ["c_lower", "c_baseline", "c_higher"]
    assert ranking["best_candidate_id"] == "c_lower"


def test_rank_stress_violation_infeasible_despite_lower_mass(tmp_path: Path):
    """A candidate with lower mass but stress violation is infeasible."""
    iters = [
        _iteration("c_good", "evaluation_complete",
                   metrics={"mass_kg": 1.0, "max_stress": 150.0}),
        _iteration("c_bad", "evaluation_complete",
                   metrics={"mass_kg": 0.7, "max_stress": 250.0}),
    ]
    pkg = _write_pkg(tmp_path, problem=_problem(), iterations=iters)
    res = rank_design_study_candidates(pkg)
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    by_id = {c["candidate_id"]: c for c in ranking["candidates"]}
    assert by_id["c_bad"]["feasibility"] == "infeasible"
    assert by_id["c_bad"]["recommendation"] == "reject_candidate"
    assert by_id["c_good"]["feasibility"] == "feasible"
    # c_good should rank above c_bad (feasible scores higher than infeasible)
    assert ranking["candidates"][0]["candidate_id"] == "c_good"


def test_rank_no_best_when_none_safe(tmp_path: Path):
    """best_candidate_id is null when no candidate is safe/feasible."""
    iters = [
        _iteration("c1", "rejected", validation_status="rejected"),
        _iteration("c2", "compile_failed"),
    ]
    pkg = _write_pkg(tmp_path, problem=_problem(), iterations=iters)
    res = rank_design_study_candidates(pkg)
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["best_candidate_id"] is None
    assert ranking["safe_to_accept"] is False
    assert ranking["next_action"] == "no_viable_candidate"


def test_rank_best_set_when_feasible_improvement(tmp_path: Path):
    """best_candidate_id is set when one feasible candidate clearly improves objective."""
    iters = [
        _iteration("c1", "evaluation_complete",
                   metrics={"mass_kg": 0.8, "max_stress": 150.0, "max_deflection": 3.0}),
    ]
    problem = _problem(baseline_metrics={"mass_kg": 1.0})
    pkg = _write_pkg(tmp_path, problem=problem, iterations=iters)
    res = rank_design_study_candidates(pkg)
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["best_candidate_id"] == "c1"
    assert ranking["safe_to_accept"] is True
    assert ranking["next_action"] == "accept_candidate"


def test_rank_baseline_unchanged(tmp_path: Path):
    """Ranking does not modify baseline geometry or create candidate geometry."""
    baseline = {"representation": "brep_build123d", "parts": [{"id": "blk"}]}
    iters = [
        _iteration("c1", "evaluation_complete",
                   metrics={"mass_kg": 0.9, "max_stress": 150.0}),
    ]
    pkg = _write_pkg(tmp_path, problem=_problem(), iterations=iters,
                     extra_members={"geometry/shape_ir.json": json.dumps(baseline)})
    rank_design_study_candidates(pkg)
    # Baseline unchanged
    assert _read(pkg, "geometry/shape_ir.json") == baseline
    # No new candidate geometry created
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert not any(n.startswith("candidates/") and "geometry" in n for n in names)


def test_rank_reads_evaluation_artifact(tmp_path: Path):
    """Ranking reads per-candidate evaluation.json when available."""
    iters = [
        _iteration("c1", "evaluation_complete", metrics={"volume_mm3": 500.0}),
    ]
    extra = {
        "candidates/c1/analysis/evaluation.json": json.dumps({
            "metrics": {"volume_mm3": 500.0, "mass_kg": 0.5},
        }),
    }
    problem = _problem(
        objective={"sense": "minimize", "metric": "volume"},
        baseline_metrics={"volume_mm3": 1000.0},
    )
    pkg = _write_pkg(tmp_path, problem=problem, iterations=iters, extra_members=extra)
    res = rank_design_study_candidates(pkg)
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    c = ranking["candidates"][0]
    assert c["metrics_used"]["mass_kg"] == 0.5
    assert c["objective_delta"]["delta_percent"] == -50.0


def test_rank_reads_manifest_and_verification(tmp_path: Path):
    iters = [
        _iteration("c1", "evaluation_complete", metrics={}),
    ]
    extra = {
        "candidates/c1/provenance/geometry_execution_manifest.json": json.dumps({
            "volume_mm3": 600.0, "mass_kg": 0.6, "geometry_kind": "brep",
        }),
        "candidates/c1/diagnostics/verification.json": json.dumps({
            "status": "passed",
        }),
    }
    problem = _problem(
        objective={"sense": "minimize", "metric": "mass"},
        baseline_metrics={"mass_kg": 1.0},
    )
    pkg = _write_pkg(tmp_path, problem=problem, iterations=iters, extra_members=extra)
    res = rank_design_study_candidates(pkg)
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    c = ranking["candidates"][0]
    assert c["feasibility"] == "feasible"
    assert c["score"] > 0  # 1 - 0.6/1.0 = 0.4
    report = _read(pkg, DESIGN_STUDY_SCORING_REPORT_PATH)
    assert report["candidates_loaded"] == 1


def test_rank_proxy_only_lowers_confidence(tmp_path: Path):
    iters = [
        _iteration("c1", "evaluation_complete",
                   metrics={"executed": True, "geometry_kind": "brep"}),
    ]
    pkg = _write_pkg(tmp_path, problem=_problem(), iterations=iters)
    rank_design_study_candidates(pkg)
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    c = ranking["candidates"][0]
    assert c["feasibility"] == "unknown"
    assert c["confidence"] == "low"


def test_rank_no_problem_insufficient_data(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=None)
    res = rank_design_study_candidates(pkg)
    assert res["status"] == "insufficient_data"
    assert res["design_study_present"] is False


def test_rank_scoring_report_contents(tmp_path: Path):
    iters = [
        _iteration("c_good", "evaluation_complete",
                   metrics={"mass_kg": 0.8, "max_stress": 150.0}),
        _iteration("c_bad", "evaluation_complete",
                   metrics={"mass_kg": 0.7, "max_stress": 250.0}),
        _iteration("c_unknown", "evaluation_complete", metrics={}),
    ]
    pkg = _write_pkg(tmp_path, problem=_problem(baseline_metrics={"mass_kg": 1.0}), iterations=iters)
    rank_design_study_candidates(pkg)
    report = _read(pkg, DESIGN_STUDY_SCORING_REPORT_PATH)
    assert report["candidates_loaded"] == 3
    assert report["candidates_failed"] == 0
    assert report["candidates_unknown"] == 1
    assert report["constraint_evaluation_summary"]["violations_found"] == 1
    assert len(report["reasons_for_no_best_candidate"]) == 0  # c_good is feasible + high confidence
    assert report["provenance"]["baseline_modified"] is False


def test_rank_package_not_found():
    res = rank_design_study_candidates("/nonexistent/path/study.aieng")
    assert res["status"] == "failed"


def test_ranking_missing_metrics_never_recommends_accept(tmp_path: Path):
    """Missing metrics must not produce an accept_candidate recommendation."""
    iters = [
        _iteration("c1", "evaluation_complete", metrics={}),
    ]
    pkg = _write_pkg(tmp_path, problem=_problem(baseline_metrics={"mass_kg": 1.0}), iterations=iters)
    res = rank_design_study_candidates(pkg)
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    c = ranking["candidates"][0]
    assert c["feasibility"] == "unknown"
    assert c["recommendation"] != "accept_candidate"
    assert c["confidence"] == "low"


# ── determinism ───────────────────────────────────────────────────────────────

def test_rank_is_deterministic(tmp_path: Path):
    """Same inputs produce same ranking order every time."""
    iters = [
        _iteration("c_a", "evaluation_complete",
                   metrics={"mass_kg": 0.9, "max_stress": 150.0}),
        _iteration("c_b", "evaluation_complete",
                   metrics={"mass_kg": 0.8, "max_stress": 150.0}),
        _iteration("c_c", "evaluation_complete",
                   metrics={"mass_kg": 1.1, "max_stress": 150.0}),
    ]
    problem = _problem(baseline_metrics={"mass_kg": 1.0})
    pkg = _write_pkg(tmp_path, problem=problem, iterations=iters)

    res1 = rank_design_study_candidates(pkg)
    ranking1 = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)

    # Run again — should produce identical result
    res2 = rank_design_study_candidates(pkg)
    ranking2 = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)

    assert [c["candidate_id"] for c in ranking1["candidates"]] == [
        c["candidate_id"] for c in ranking2["candidates"]
    ]
    assert ranking1["best_candidate_id"] == ranking2["best_candidate_id"]
    for c1, c2 in zip(ranking1["candidates"], ranking2["candidates"]):
        assert c1["score"] == c2["score"]
        assert c1["feasibility"] == c2["feasibility"]


# ── multi-objective Pareto integration ────────────────────────────────────────

def test_rank_multi_objective_writes_pareto_front(tmp_path: Path):
    """A two-objective problem triggers Pareto-front computation and artifact writing."""
    problem = _problem(
        objectives=[
            {"sense": "minimize", "metric": "mass"},
            {"sense": "minimize", "metric": "stress"},
        ],
        constraints=[],  # keep candidates feasible so dominated set is non-empty
        baseline_metrics={"mass_kg": 1.0, "max_stress": 150.0},
    )
    iters = [
        _iteration("c1", "evaluation_complete",
                   metrics={"mass_kg": 1.0, "max_stress": 200.0}),
        _iteration("c2", "evaluation_complete",
                   metrics={"mass_kg": 2.0, "max_stress": 100.0}),
        _iteration("c3", "evaluation_complete",
                   metrics={"mass_kg": 3.0, "max_stress": 300.0}),
    ]
    pkg = _write_pkg(tmp_path, problem=problem, iterations=iters)
    res = rank_design_study_candidates(pkg)

    assert PARETO_FRONT_PATH in res["artifacts"]
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["pareto_front"]["status"] == "ok"
    assert set(ranking["pareto_front"]["front_candidate_ids"]) == {"c1", "c2"}
    assert ranking["pareto_front"]["dominated_candidate_ids"] == ["c3"]
    assert ranking["pareto_front"]["objective_metrics"] == ["mass", "stress"]
    assert any("not a proven surface" in lim for lim in ranking["limitations"])

    pareto = _read(pkg, PARETO_FRONT_PATH)
    assert pareto["format"] == "aieng.pareto_front"
    assert pareto["candidate_count"] == 3


def test_rank_single_objective_unchanged(tmp_path: Path):
    """Single-objective studies remain unchanged and do not write a Pareto artifact."""
    iters = [
        _iteration("c1", "evaluation_complete",
                   metrics={"mass_kg": 0.8, "max_stress": 150.0}),
        _iteration("c2", "evaluation_complete",
                   metrics={"mass_kg": 1.1, "max_stress": 150.0}),
    ]
    pkg = _write_pkg(tmp_path, problem=_problem(baseline_metrics={"mass_kg": 1.0}), iterations=iters)
    res = rank_design_study_candidates(pkg)

    assert PARETO_FRONT_PATH not in res["artifacts"]
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert "pareto_front" not in ranking
    # Classic single-objective limitation remains present.
    assert any("No Pareto optimization or search is performed" in lim for lim in ranking["limitations"])


def test_rank_multi_objective_infeasible_excluded_from_front(tmp_path: Path):
    """Infeasible candidates are excluded from the Pareto frontier."""
    problem = _problem(
        objectives=[
            {"sense": "minimize", "metric": "mass"},
            {"sense": "minimize", "metric": "stress"},
        ],
    )
    iters = [
        _iteration("c_feas", "evaluation_complete",
                   metrics={"mass_kg": 1.0, "max_stress": 150.0}),
        _iteration("c_infeas", "evaluation_complete",
                   metrics={"mass_kg": 0.5, "max_stress": 250.0}),  # stress violation
    ]
    pkg = _write_pkg(tmp_path, problem=problem, iterations=iters)
    res = rank_design_study_candidates(pkg)

    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["pareto_front"]["status"] == "insufficient_data"
    assert ranking["pareto_front"]["front_candidate_ids"] == []
