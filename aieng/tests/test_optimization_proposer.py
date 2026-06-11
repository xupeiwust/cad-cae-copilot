"""Tests for the deterministic local-refinement proposer (#62)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.optimization_proposer import (
    DESIGN_CANDIDATES_DIR,
    propose_next_candidates,
)


def _variables_doc():
    return {
        "format": "aieng.optimization_variables", "schema_version": "0.2",
        "variables": [
            {"id": "wall_t", "type": "continuous", "min_value": 2.0, "max_value": 8.0,
             "current_value": 5.0, "safe_to_modify": True},
            {"id": "fillet_r", "type": "continuous", "min_value": 1.0, "max_value": 4.0,
             "current_value": 2.0, "safe_to_modify": True},
        ],
    }


def _ranking(best_id):
    return {
        "format": "aieng.design_study.candidate_ranking.v0", "status": "ranked",
        "best_candidate_id": best_id, "safe_to_accept": True,
        "candidates": [{"rank": 1, "candidate_id": best_id, "feasibility": "feasible",
                        "score": 0.2, "confidence": "high"}],
    }


def _incumbent_patch(cid, wall, fillet):
    return {"format": "aieng.design_candidate_patch", "candidate_id": cid,
            "variable_changes": [{"variable_id": "wall_t", "new_value": wall},
                                 {"variable_id": "fillet_r", "new_value": fillet}]}


def _pkg(tmp_path, *, ranking=None, incumbent=None, history=None) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "S"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
        zf.writestr("analysis/optimization_variables.json", json.dumps(_variables_doc()))
        if ranking is not None:
            zf.writestr("analysis/design_study_candidate_ranking.json", json.dumps(ranking))
        if incumbent is not None:
            cid, wall, fillet = incumbent
            zf.writestr(f"{DESIGN_CANDIDATES_DIR}{cid}.json",
                        json.dumps(_incumbent_patch(cid, wall, fillet)))
        if history is not None:
            zf.writestr("analysis/optimization_iterations.json", json.dumps(history))
    return pkg


def _patches(pkg):
    out = {}
    with zipfile.ZipFile(pkg) as zf:
        for n in zf.namelist():
            if n.startswith(DESIGN_CANDIDATES_DIR) and n.endswith(".json"):
                out[n] = json.loads(zf.read(n))
    return out


def _vals(patch):
    return {c["variable_id"]: c["new_value"] for c in patch["variable_changes"]}


# ── trust-region local refinement ────────────────────────────────────────────

def test_refines_around_incumbent_within_bounds(tmp_path: Path):
    pkg = _pkg(tmp_path, ranking=_ranking("inc"), incumbent=("inc", 5.0, 2.0))
    res = propose_next_candidates(pkg, count=4, shrink=0.5, seed=1)
    assert res["status"] == "ok"
    assert res["strategy"] == "trust_region"
    assert res["candidate_count"] == 4
    assert "local_refinement" in res["reason_codes"]
    assert res["baseline_modified"] is False
    # all proposed values respect variable bounds
    for n, patch in _patches(pkg).items():
        if "inc.json" in n:
            continue
        v = _vals(patch)
        assert 2.0 <= v["wall_t"] <= 8.0
        assert 1.0 <= v["fillet_r"] <= 4.0


def test_radius_shrinks_with_iteration(tmp_path: Path):
    # iteration 0 (no history) → radius 1.0; iteration 2 → radius 0.25
    hist = {"iterations": [{"index": 1}, {"index": 2}]}
    pkg = _pkg(tmp_path, ranking=_ranking("inc"), incumbent=("inc", 5.0, 2.0), history=hist)
    res = propose_next_candidates(pkg, count=3, shrink=0.5, seed=1)
    assert res["radius_fraction"] == 0.25
    assert "trust_region_shrink" in res["reason_codes"]
    # tighter radius → wall values stay near the incumbent (5.0 ± 0.25*6/2 = ±0.75)
    for n, patch in _patches(pkg).items():
        if "inc.json" in n:
            continue
        assert abs(_vals(patch)["wall_t"] - 5.0) <= 0.75 + 1e-9


def test_no_incumbent_falls_back_to_lhs(tmp_path: Path):
    # ranking present but no best_candidate_id → fallback
    ranking = {"format": "aieng.design_study.candidate_ranking.v0", "status": "ranked",
               "best_candidate_id": None, "candidates": []}
    pkg = _pkg(tmp_path, ranking=ranking)
    res = propose_next_candidates(pkg, count=3, seed=2)
    assert res["status"] == "ok"
    assert res["strategy"] == "lhs_fallback"
    assert "no_incumbent_fallback" in res["reason_codes"]
    assert res["candidate_count"] == 3


def test_no_ranking_at_all_falls_back(tmp_path: Path):
    pkg = _pkg(tmp_path)  # variables only
    res = propose_next_candidates(pkg, count=2, seed=0)
    assert res["status"] == "ok"
    assert res["strategy"] == "lhs_fallback"


def test_deterministic_given_seed(tmp_path: Path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    pkg1 = _pkg(a, ranking=_ranking("inc"), incumbent=("inc", 5.0, 2.0))
    propose_next_candidates(pkg1, count=3, seed=42)
    pkg2 = _pkg(b, ranking=_ranking("inc"), incumbent=("inc", 5.0, 2.0))
    propose_next_candidates(pkg2, count=3, seed=42)
    v1 = sorted(_vals(p)["wall_t"] for n, p in _patches(pkg1).items() if "inc.json" not in n)
    v2 = sorted(_vals(p)["wall_t"] for n, p in _patches(pkg2).items() if "inc.json" not in n)
    assert v1 == v2 and len(v1) == 3


def test_integer_variable_rounds(tmp_path: Path):
    vars_doc = {"format": "aieng.optimization_variables", "variables": [
        {"id": "n_holes", "type": "integer", "min_value": 2, "max_value": 8,
         "current_value": 4, "safe_to_modify": True}]}
    pkg = tmp_path / "s.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", "{}")
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
        zf.writestr("analysis/optimization_variables.json", json.dumps(vars_doc))
        zf.writestr("analysis/design_study_candidate_ranking.json", json.dumps(_ranking("inc")))
        zf.writestr(f"{DESIGN_CANDIDATES_DIR}inc.json",
                    json.dumps({"format": "aieng.design_candidate_patch", "candidate_id": "inc",
                                "variable_changes": [{"variable_id": "n_holes", "new_value": 4}]}))
    res = propose_next_candidates(pkg, count=3, seed=1)
    assert res["status"] == "ok"
    for n, patch in _patches(pkg).items():
        if "inc.json" in n:
            continue
        assert isinstance(_vals(patch)["n_holes"], int)


def test_missing_variables_errors(tmp_path: Path):
    pkg = tmp_path / "s.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", "{}")
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
    res = propose_next_candidates(pkg, count=2)
    assert res["status"] == "error"
    assert res["code"] == "missing_variables"


def test_missing_package_errors(tmp_path: Path):
    res = propose_next_candidates(tmp_path / "nope.aieng", count=2)
    assert res["status"] == "error"
    assert res["code"] == "package_not_found"
