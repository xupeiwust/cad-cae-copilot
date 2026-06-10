"""Tests for the iterative-loop convergence verdict + iteration history (#61)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.optimization_convergence import (
    OPTIMIZATION_ITERATIONS_PATH,
    evaluate_convergence,
    record_iteration_and_check,
    resolve_convergence_config,
)
from aieng.optimization_artifacts import OPTIMIZATION_REASON_CODES


def _it(obj, *, feasible=True, evals=4, failures=0, had_success=True):
    return {"feasible": feasible, "incumbent_objective": obj,
            "evaluations_total": evals, "failures_this_round": failures,
            "had_success": had_success}


# ── pure evaluate_convergence ─────────────────────────────────────────────────

def test_empty_history_continues():
    v = evaluate_convergence([], resolve_convergence_config(None))
    assert v["converged"] is False
    assert v["verdict"] == "continue"


def test_still_improving_continues():
    cfg = resolve_convergence_config(None)  # min_rel_improvement=0.01, patience=2
    its = [_it(1.0, evals=4), _it(0.8, evals=8), _it(0.6, evals=12)]
    assert evaluate_convergence(its, cfg)["verdict"] == "continue"


def test_objective_delta_converges_after_patience():
    cfg = resolve_convergence_config(None)
    # two consecutive <1% improvements over 3 feasible points
    its = [_it(0.810, evals=4), _it(0.805, evals=8), _it(0.804, evals=12)]
    v = evaluate_convergence(its, cfg)
    assert v["converged"] is True
    assert v["verdict"] == "converged"
    assert "converged_objective_delta" in v["reason_codes"]


def test_eval_budget_stops():
    cfg = resolve_convergence_config(None)  # max_evaluations=200
    v = evaluate_convergence([_it(1.0, evals=250)], cfg)
    assert v["verdict"] == "stop_budget"
    assert "budget_exhausted" in v["reason_codes"]


def test_max_iterations_stops():
    cfg = resolve_convergence_config({"budget": {"max_iterations": 3, "max_candidates": 999}})
    its = [_it(1.0 - i * 0.2, evals=4 * (i + 1)) for i in range(3)]
    v = evaluate_convergence(its, cfg)
    assert "budget_exhausted" in v["reason_codes"]


def test_no_feasible_after_patience_asks_user():
    cfg = resolve_convergence_config(None)  # feasible_patience=3
    its = [_it(None, feasible=False) for _ in range(3)]
    v = evaluate_convergence(its, cfg)
    assert v["verdict"] == "stop_no_feasible"
    assert "needs_user_input" in v["reason_codes"]


def test_consecutive_failures_stop():
    cfg = resolve_convergence_config(None)  # max_consecutive_failures=3
    its = [_it(None, feasible=False, failures=4, had_success=False) for _ in range(3)]
    v = evaluate_convergence(its, cfg)
    assert "max_consecutive_failures" in v["reason_codes"]


def test_proposer_exhausted_short_circuits():
    cfg = resolve_convergence_config(None)
    v = evaluate_convergence([_it(0.8)], cfg, proposer_exhausted=True)
    assert v["verdict"] == "stop_proposer_exhausted"
    assert "proposer_exhausted" in v["reason_codes"]


def test_config_thresholds_sourced_from_study():
    cfg = resolve_convergence_config({"convergence": {"min_rel_improvement": 0.5, "patience": 1}})
    # with a huge required improvement, a small gain is "no progress" after patience=1
    its = [_it(1.0, evals=4), _it(0.95, evals=8)]
    v = evaluate_convergence(its, cfg)
    assert v["verdict"] == "converged"


def test_all_reason_codes_in_shared_vocabulary():
    cfg = resolve_convergence_config(None)
    seen = set()
    for v in (
        evaluate_convergence([_it(0.81), _it(0.805), _it(0.804)], cfg),
        evaluate_convergence([_it(1.0, evals=999)], cfg),
        evaluate_convergence([_it(None, feasible=False)] * 3, cfg),
        evaluate_convergence([_it(0.8)], cfg, proposer_exhausted=True),
    ):
        seen.update(v["reason_codes"])
    assert seen <= OPTIMIZATION_REASON_CODES


# ── record_iteration_and_check (package I/O) ──────────────────────────────────

def _ranking(best_id, obj, *, feasible=True):
    feas = "feasible" if feasible else "unknown"
    return {
        "format": "aieng.design_study.candidate_ranking.v0", "status": "ranked",
        "best_candidate_id": best_id, "safe_to_accept": feasible,
        "candidates": [
            {"rank": 1, "candidate_id": best_id, "feasibility": feas, "score": 0.2,
             "confidence": "high", "objective_delta": {"metric": "mass", "candidate_value": obj}},
        ],
    }


def _pkg(tmp_path: Path, *, ranking=None, history=None, study=None) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "S"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
        if ranking is not None:
            zf.writestr("analysis/design_study_candidate_ranking.json", json.dumps(ranking))
        if history is not None:
            zf.writestr(OPTIMIZATION_ITERATIONS_PATH, json.dumps(history))
        if study is not None:
            zf.writestr("analysis/optimization_study.json", json.dumps(study))
    return pkg


def _read(pkg, name):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


def test_record_appends_iteration_and_returns_verdict(tmp_path: Path):
    pkg = _pkg(tmp_path, ranking=_ranking("cand_a", 0.8))
    res = record_iteration_and_check(pkg)
    assert res["status"] == "ok"
    assert res["iteration_index"] == 1
    assert res["incumbent_candidate_id"] == "cand_a"
    assert res["incumbent_objective"] == 0.8
    assert res["feasible"] is True
    assert res["baseline_modified"] is False
    doc = _read(pkg, OPTIMIZATION_ITERATIONS_PATH)
    assert len(doc["iterations"]) == 1
    assert doc["iterations"][0]["convergence_verdict"] == "continue"


def test_record_accumulates_and_converges(tmp_path: Path):
    pkg = _pkg(tmp_path, ranking=_ranking("c1", 0.810))
    record_iteration_and_check(pkg)
    # update ranking to a near-identical objective each round
    for obj in (0.805, 0.804):
        members = {"analysis/design_study_candidate_ranking.json":
                   (json.dumps(_ranking("c1", obj)) + "\n").encode()}
        # rewrite ranking
        tmp = pkg.with_suffix(".t.aieng")
        with zipfile.ZipFile(pkg) as src, zipfile.ZipFile(tmp, "w") as dst:
            for i in src.infolist():
                if i.filename not in members:
                    dst.writestr(i, src.read(i.filename))
            for n, d in members.items():
                dst.writestr(n, d)
        tmp.replace(pkg)
        res = record_iteration_and_check(pkg)
    assert res["converged"] is True
    assert "converged_objective_delta" in res["reason_codes"]


def test_record_without_ranking_asks_to_rank(tmp_path: Path):
    pkg = _pkg(tmp_path)
    res = record_iteration_and_check(pkg)
    assert res["status"] == "needs_user_input"
    assert res["code"] == "no_ranking"


def test_record_missing_package(tmp_path: Path):
    res = record_iteration_and_check(tmp_path / "nope.aieng")
    assert res["status"] == "error"
    assert res["code"] == "package_not_found"
