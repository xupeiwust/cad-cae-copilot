"""Tests for the advisory recommendation/explanation layer (#41).

Reads an existing ranking artifact and composes a reason-coded recommendation.
Advisory only: never accepts a candidate, never modifies the baseline.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.optimization_recommendation import (
    OPTIMIZATION_RECOMMENDATION_PATH,
    explain_recommendation,
)
from aieng.optimization_artifacts import OPTIMIZATION_REASON_CODES

DESIGN_STUDY_CANDIDATE_RANKING_PATH = "analysis/design_study_candidate_ranking.json"
DESIGN_STUDY_SCORING_REPORT_PATH = "diagnostics/design_study_scoring_report.json"


def _write_pkg(tmp_path: Path, *, ranking=None, scoring=None) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Study"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
        if ranking is not None:
            zf.writestr(DESIGN_STUDY_CANDIDATE_RANKING_PATH, json.dumps(ranking))
        if scoring is not None:
            zf.writestr(DESIGN_STUDY_SCORING_REPORT_PATH, json.dumps(scoring))
    return pkg


def _read(pkg, name):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


def _feasible_ranking():
    return {
        "format": "aieng.design_study.candidate_ranking.v0",
        "status": "ranked",
        "objective": {"metric": "mass", "sense": "minimize"},
        "constraints": [{"id": "stress_limit", "type": "max_stress", "limit": 200.0}],
        "best_candidate_id": "cand_good",
        "safe_to_accept": True,
        "next_action": "accept_candidate",
        "candidates": [
            {
                "rank": 1, "candidate_id": "cand_good", "feasibility": "feasible",
                "score": 0.18, "confidence": "high", "recommendation": "accept_candidate",
                "metrics_used": {"mass_kg": 0.82, "max_stress": 150.0},
                "constraint_violations": [],
                "objective_delta": {"metric": "mass", "baseline_value": 1.0,
                                    "candidate_value": 0.82, "delta_percent": 18.0,
                                    "delta_absolute": 0.18},
                "reasons": ["18% lighter; all constraints satisfied"],
            },
            {
                "rank": 2, "candidate_id": "cand_meh", "feasibility": "feasible",
                "score": 0.05, "confidence": "medium", "recommendation": "refine_candidate",
                "metrics_used": {"mass_kg": 0.95}, "constraint_violations": [],
                "objective_delta": {"metric": "mass", "baseline_value": 1.0,
                                    "candidate_value": 0.95, "delta_percent": 5.0},
                "reasons": [],
            },
        ],
    }


# ── happy path: a clear feasible winner ──────────────────────────────────────

def test_recommends_feasible_winner_with_metrics_and_caveats(tmp_path: Path):
    pkg = _write_pkg(tmp_path, ranking=_feasible_ranking())
    res = explain_recommendation(pkg)
    assert res["status"] == "ok"
    assert res["recommended_candidate_id"] == "cand_good"
    assert res["safe_to_accept"] is True
    assert res["advisory_only"] is True
    assert res["requires_human_review"] is True
    assert res["baseline_modified"] is False
    # reason codes always include advisory + human approval gate
    assert "advisory_recommendation" in res["reason_codes"]
    assert "human_approval_required" in res["reason_codes"]

    doc = _read(pkg, OPTIMIZATION_RECOMMENDATION_PATH)
    assert doc["recommended_candidate_id"] == "cand_good"
    # objective delta surfaced in rationale
    assert any("18" in r for r in doc["rationale"])
    assert any("mass" in r for r in doc["rationale"])
    # alternative listed
    assert doc["alternatives"][0]["candidate_id"] == "cand_meh"
    assert doc["honesty"]["production_sign_off"] is False


# ── no viable candidate ──────────────────────────────────────────────────────

def test_no_viable_candidate_explains_why(tmp_path: Path):
    ranking = {
        "status": "ranked",
        "objective": {"metric": "mass", "sense": "minimize"},
        "best_candidate_id": None,
        "safe_to_accept": False,
        "next_action": "no_viable_candidate",
        "candidates": [
            {"rank": 1, "candidate_id": "c_bad", "feasibility": "infeasible",
             "score": -0.5, "confidence": "low", "constraint_violations": ["max_stress 260 > 200"],
             "metrics_used": {"max_stress": 260.0}, "objective_delta": {}, "reasons": []},
        ],
    }
    scoring = {"reasons_for_no_best_candidate": ["all candidates violate max_stress"]}
    pkg = _write_pkg(tmp_path, ranking=ranking, scoring=scoring)
    res = explain_recommendation(pkg)
    assert res["status"] == "ok"
    assert res["recommended_candidate_id"] is None
    assert res["safe_to_accept"] is False
    assert "needs_user_input" in res["reason_codes"]
    doc = _read(pkg, OPTIMIZATION_RECOMMENDATION_PATH)
    assert any("max_stress" in r for r in doc["rationale"])


# ── unknown feasibility → needs more evaluation + missing-metric caveat ──────

def test_unknown_feasibility_flags_missing_metric(tmp_path: Path):
    ranking = {
        "status": "ranked",
        "objective": {"metric": "mass", "sense": "minimize"},
        "best_candidate_id": None,
        "safe_to_accept": False,
        "next_action": "run_more_evaluation",
        "candidates": [
            {"rank": 1, "candidate_id": "c_unk", "feasibility": "unknown",
             "score": 0.0, "confidence": "low", "constraint_violations": [],
             "metrics_used": {"mass_kg": 0.9}, "objective_delta": {}, "reasons": []},
        ],
    }
    pkg = _write_pkg(tmp_path, ranking=ranking)
    res = explain_recommendation(pkg)
    assert "needs_more_evaluation" in res["reason_codes"]
    assert "missing_metric" in res["reason_codes"]
    doc = _read(pkg, OPTIMIZATION_RECOMMENDATION_PATH)
    assert any("missing CAE metrics" in c for c in doc["caveats"])


# ── guards ───────────────────────────────────────────────────────────────────

def test_no_ranking_asks_to_rank_first(tmp_path: Path):
    pkg = _write_pkg(tmp_path)  # no ranking artifact
    res = explain_recommendation(pkg)
    assert res["status"] == "needs_user_input"
    assert res["code"] == "no_ranking"
    assert res["baseline_modified"] is False


def test_missing_package_errors(tmp_path: Path):
    res = explain_recommendation(tmp_path / "nope.aieng")
    assert res["status"] == "error"
    assert res["code"] == "package_not_found"


# ── reason-code vocabulary integrity ─────────────────────────────────────────

def test_all_emitted_reason_codes_are_in_shared_vocabulary(tmp_path: Path):
    # exercise the richest path and assert every code is canonical
    pkg = _write_pkg(tmp_path, ranking=_feasible_ranking())
    res = explain_recommendation(pkg)
    assert set(res["reason_codes"]) <= OPTIMIZATION_REASON_CODES
