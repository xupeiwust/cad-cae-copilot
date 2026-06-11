"""Tests for the Bayesian optimisation proposer (Issue #66)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from aieng.converters.optimization_proposer_bayesian import (
    _has_skopt,
    propose_bayesian_candidates,
)
from aieng.converters.optimization_proposer import DESIGN_CANDIDATES_DIR

_bayesian_available = _has_skopt()
pytestmark = pytest.mark.skipif(not _bayesian_available, reason="scikit-optimize required")


def _ranking_with_scores(candidates):
    """Build a ranking with scores populated for each candidate."""
    ranked_cands = []
    best_id = None
    best_score = None
    for i, (cid, score, feas) in enumerate(candidates):
        ranked_cands.append({
            "rank": i + 1,
            "candidate_id": cid,
            "feasibility": "feasible" if feas else "infeasible",
            "score": score,
            "confidence": "high",
        })
        if feas and (best_score is None or score > best_score):
            best_score = score
            best_id = cid
    return {
        "format": "aieng.design_study.candidate_ranking.v0",
        "status": "ranked",
        "best_candidate_id": best_id,
        "safe_to_accept": best_id is not None,
        "objective": {"sense": "minimize", "metric": "mass"},
        "candidates": ranked_cands,
    }


def _pkg_for_bayesian(tmp_path, ranking=None, problem=None, history=None, extra_patches=None):
    pkg = tmp_path / "study.aieng"
    variables_doc = {
        "format": "aieng.optimization_variables",
        "schema_version": "0.1",
        "variables": [
            {"id": "wall_t", "type": "continuous", "min_value": 2.0, "max_value": 8.0,
             "current_value": 5.0, "safe_to_modify": True},
            {"id": "fillet_r", "type": "continuous", "min_value": 1.0, "max_value": 4.0,
             "current_value": 2.0, "safe_to_modify": True},
        ],
    }
    default_problem = {
        "format": "aieng.design_study_problem",
        "schema_version": "0.1",
        "id": "ds_001",
        "variables": variables_doc["variables"],
        "objective": {"sense": "minimize", "metric": "mass"},
        "constraints": [],
        "settings": {},
    }
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "S"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
        zf.writestr("analysis/optimization_variables.json", json.dumps(variables_doc))
        zf.writestr("analysis/design_study_problem.json", json.dumps(problem or default_problem))
        if ranking is not None:
            zf.writestr("analysis/design_study_candidate_ranking.json", json.dumps(ranking))
        if history is not None:
            zf.writestr("analysis/optimization_iterations.json", json.dumps(history))
        for cid, changes in (extra_patches or {}).items():
            zf.writestr(f"{DESIGN_CANDIDATES_DIR}{cid}.json",
                        json.dumps({"format": "aieng.design_candidate_patch",
                                    "candidate_id": cid, "variable_changes": changes}))
    return pkg


# ── graceful fallback ─────────────────────────────────────────────────────────


def test_bayesian_fallback_without_ranking(tmp_path: Path):
    """No ranking → no observations → fallback to LHS."""
    pkg = _pkg_for_bayesian(tmp_path)
    res = propose_bayesian_candidates(pkg, count=3, seed=1)
    assert res["status"] == "ok"
    assert res["strategy"] == "lhs_fallback"
    assert "no_incumbent_fallback" in res["reason_codes"]
    assert res["candidate_count"] == 3


def test_bayesian_fallback_with_discrete_variable(tmp_path: Path):
    """Discrete safe variable triggers fallback because skopt works best in R^n."""
    pkg = tmp_path / "study.aieng"
    variables_doc = {
        "format": "aieng.optimization_variables",
        "schema_version": "0.1",
        "variables": [
            {"id": "wall_t", "type": "continuous", "min_value": 2.0, "max_value": 8.0,
             "current_value": 5.0, "safe_to_modify": True},
            {"id": "material", "type": "categorical", "allowed_values": ["al", "st"],
             "current_value": "al", "safe_to_modify": True},
        ],
    }
    ranking = _ranking_with_scores([("c1", 0.1, True), ("c2", 0.2, True), ("c3", 0.0, True)])
    patches = {
        "c1": [{"variable_id": "wall_t", "new_value": 3.0}, {"variable_id": "material", "new_value": 0.0}],
        "c2": [{"variable_id": "wall_t", "new_value": 5.0}, {"variable_id": "material", "new_value": 0.0}],
        "c3": [{"variable_id": "wall_t", "new_value": 7.0}, {"variable_id": "material", "new_value": 0.0}],
    }
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "S"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
        zf.writestr("analysis/optimization_variables.json", json.dumps(variables_doc))
        zf.writestr("analysis/design_study_problem.json", json.dumps({
            "format": "aieng.design_study_problem", "schema_version": "0.1", "id": "ds_001",
            "variables": variables_doc["variables"], "objective": {"sense": "minimize", "metric": "mass"},
            "constraints": [], "settings": {},
        }))
        zf.writestr("analysis/design_study_candidate_ranking.json", json.dumps(ranking))
        for cid, changes in patches.items():
            zf.writestr(f"{DESIGN_CANDIDATES_DIR}{cid}.json",
                        json.dumps({"format": "aieng.design_candidate_patch",
                                    "candidate_id": cid, "variable_changes": changes}))

    res = propose_bayesian_candidates(pkg, count=2, seed=1)
    assert res["status"] == "ok"
    assert res["strategy"] == "lhs_fallback"
    assert "no_surrogate_available" in res["reason_codes"]


def test_bayesian_fallback_too_few_observations(tmp_path: Path):
    """With < 3 scored observations we must fall back."""
    ranking = _ranking_with_scores([("c1", 0.1, True)])
    patches = {
        "c1": [{"variable_id": "wall_t", "new_value": 3.0}, {"variable_id": "fillet_r", "new_value": 1.0}],
    }
    pkg = _pkg_for_bayesian(tmp_path, ranking=ranking, extra_patches=patches)
    res = propose_bayesian_candidates(pkg, count=2, seed=1)
    assert res["status"] == "ok"
    assert res["strategy"] == "lhs_fallback"
    assert "no_surrogate_available" in res["reason_codes"]


def test_bayesian_missing_package(tmp_path: Path):
    res = propose_bayesian_candidates(tmp_path / "nope.aieng", count=2)
    assert res["status"] == "error"
    assert res["code"] == "package_not_found"


# ── surrogate path ────────────────────────────────────────────────────────────


def test_bayesian_runs_surrogate_path(tmp_path: Path):
    """With enough continuous data the BO proposer should emit bayesian candidates."""
    candidates = [
        ("c1", -0.5, True),   # far corner (bad score)
        ("c2", 0.5, True),    # middle (good score)
        ("c3", -0.5, True),   # far corner (bad score)
        ("c4", 0.0, True),    # medium
        ("c5", 0.0, True),    # medium
    ]
    ranking = _ranking_with_scores(candidates)
    patches = {
        "c1": [{"variable_id": "wall_t", "new_value": 2.0}, {"variable_id": "fillet_r", "new_value": 1.0}],
        "c2": [{"variable_id": "wall_t", "new_value": 5.0}, {"variable_id": "fillet_r", "new_value": 2.0}],
        "c3": [{"variable_id": "wall_t", "new_value": 8.0}, {"variable_id": "fillet_r", "new_value": 4.0}],
        "c4": [{"variable_id": "wall_t", "new_value": 3.0}, {"variable_id": "fillet_r", "new_value": 2.0}],
        "c5": [{"variable_id": "wall_t", "new_value": 7.0}, {"variable_id": "fillet_r", "new_value": 2.0}],
    }
    pkg = _pkg_for_bayesian(tmp_path, ranking=ranking, extra_patches=patches)
    res = propose_bayesian_candidates(pkg, count=2, seed=42)
    assert res["status"] == "ok"
    if _has_skopt():
        assert res["strategy"] == "bayesian"
        assert "select_bayesian" in res["reason_codes"]
        assert res["candidate_count"] == 2
        # Verify candidates respect bounds
        with zipfile.ZipFile(pkg, "r") as zf:
            for cid in res["candidate_ids"]:
                patch = json.loads(zf.read(f"{DESIGN_CANDIDATES_DIR}{cid}.json"))
                vals = {c["variable_id"]: c["new_value"] for c in patch["variable_changes"]}
                assert 2.0 <= vals["wall_t"] <= 8.0
                assert 1.0 <= vals["fillet_r"] <= 4.0
    else:
        assert res["strategy"] == "lhs_fallback"


def test_bayesian_proposal_moves_toward_good_region(tmp_path: Path):
    """On a simple 1-D problem BO should propose near the best observed region."""
    # One variable, scores peak at wall_t=5.0
    pkg = tmp_path / "study.aieng"
    variables_doc = {
        "format": "aieng.optimization_variables",
        "schema_version": "0.1",
        "variables": [
            {"id": "wall_t", "type": "continuous", "min_value": 2.0, "max_value": 8.0,
             "current_value": 5.0, "safe_to_modify": True},
        ],
    }
    ranking = _ranking_with_scores([
        ("c1", -0.8, True),   # wall_t=2.0  -> bad
        ("c2", 0.8, True),    # wall_t=5.0  -> best
        ("c3", -0.8, True),   # wall_t=8.0  -> bad
        ("c4", 0.0, True),    # wall_t=3.0  -> medium
        ("c5", 0.0, True),    # wall_t=7.0  -> medium
    ])
    patches = {
        "c1": [{"variable_id": "wall_t", "new_value": 2.0}],
        "c2": [{"variable_id": "wall_t", "new_value": 5.0}],
        "c3": [{"variable_id": "wall_t", "new_value": 8.0}],
        "c4": [{"variable_id": "wall_t", "new_value": 3.0}],
        "c5": [{"variable_id": "wall_t", "new_value": 7.0}],
    }
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "S"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
        zf.writestr("analysis/optimization_variables.json", json.dumps(variables_doc))
        zf.writestr("analysis/design_study_problem.json", json.dumps({
            "format": "aieng.design_study_problem", "schema_version": "0.1", "id": "ds_001",
            "variables": variables_doc["variables"], "objective": {"sense": "minimize", "metric": "mass"},
            "constraints": [], "settings": {},
        }))
        zf.writestr("analysis/design_study_candidate_ranking.json", json.dumps(ranking))
        for cid, changes in patches.items():
            zf.writestr(f"{DESIGN_CANDIDATES_DIR}{cid}.json",
                        json.dumps({"format": "aieng.design_candidate_patch",
                                    "candidate_id": cid, "variable_changes": changes}))

    res = propose_bayesian_candidates(pkg, count=1, seed=42)
    assert res["status"] == "ok"
    if _has_skopt():
        with zipfile.ZipFile(pkg, "r") as zf:
            patch = json.loads(zf.read(f"{DESIGN_CANDIDATES_DIR}{res['candidate_ids'][0]}.json"))
            val = patch["variable_changes"][0]["new_value"]
            # Should be closer to 5.0 than to the extremes (2.0 or 8.0)
            assert 3.5 <= val <= 6.5


def test_bayesian_proposer_via_algorithm_dispatch(tmp_path: Path):
    """optimization_proposer.propose_next_candidates dispatches to bayesian."""
    from aieng.converters.optimization_proposer import propose_next_candidates

    candidates = [
        ("c1", -0.5, True),
        ("c2", 0.5, True),
        ("c3", -0.5, True),
        ("c4", 0.0, True),
        ("c5", 0.0, True),
    ]
    ranking = _ranking_with_scores(candidates)
    patches = {
        "c1": [{"variable_id": "wall_t", "new_value": 2.0}, {"variable_id": "fillet_r", "new_value": 1.0}],
        "c2": [{"variable_id": "wall_t", "new_value": 5.0}, {"variable_id": "fillet_r", "new_value": 2.0}],
        "c3": [{"variable_id": "wall_t", "new_value": 8.0}, {"variable_id": "fillet_r", "new_value": 4.0}],
        "c4": [{"variable_id": "wall_t", "new_value": 3.0}, {"variable_id": "fillet_r", "new_value": 2.0}],
        "c5": [{"variable_id": "wall_t", "new_value": 7.0}, {"variable_id": "fillet_r", "new_value": 2.0}],
    }
    pkg = _pkg_for_bayesian(tmp_path, ranking=ranking, extra_patches=patches)
    res = propose_next_candidates(pkg, algorithm="bayesian", count=1, seed=7)
    assert res["status"] == "ok"
    if _has_skopt():
        assert res["strategy"] == "bayesian"
        assert "select_bayesian" in res["reason_codes"]
