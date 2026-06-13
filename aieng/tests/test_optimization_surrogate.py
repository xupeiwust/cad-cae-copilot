"""Surrogate-assisted candidate proposal with honesty gates (#205)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.design_study import DESIGN_CANDIDATES_DIR, DESIGN_STUDY_PROBLEM_PATH
from aieng.converters.design_study_ranking import DESIGN_STUDY_CANDIDATE_RANKING_PATH
from aieng.converters.optimization_surrogate import (
    SURROGATE_PROPOSALS_PATH,
    propose_surrogate_candidates,
    write_surrogate_proposals,
)


def _var(vid: str, lo: float, hi: float, *, safe: bool = True) -> dict:
    return {"id": vid, "path": f"$.{vid}", "type": "continuous",
            "min_value": lo, "max_value": hi, "safe_to_modify": safe}


def _problem(*vars_) -> dict:
    return {
        "format": "aieng.design_study_problem", "schema_version": "0.1", "name": "s",
        "variables": list(vars_),
        "objective": {"sense": "minimize", "metric": "mass"},
    }


def _patch(cid: str, **vals) -> dict:
    return {
        "format": "aieng.design_candidate_patch", "candidate_id": cid,
        "variable_changes": [{"variable_id": k, "new_value": v} for k, v in vals.items()],
    }


def _ranking(scores: dict[str, float]) -> dict:
    return {"candidates": [{"candidate_id": cid, "score": s, "feasibility": "feasible"}
                           for cid, s in scores.items()]}


def _evaluated_patches(n: int = 4) -> dict[str, dict]:
    pts = {"c1": (2.0, 1.0), "c2": (8.0, 1.0), "c3": (2.0, 9.0), "c4": (8.0, 9.0), "c5": (5.0, 5.0)}
    return {cid: _patch(cid, x1=xy[0], x2=xy[1]) for cid, xy in list(pts.items())[:n]}


_SCORES = {"c1": 0.2, "c2": 0.6, "c3": 0.4, "c4": 0.9, "c5": 0.7}


def test_surrogate_proposes_with_uncertainty_and_advisory_flags() -> None:
    problem = _problem(_var("x1", 0, 10), _var("x2", 0, 10))
    patches = _evaluated_patches(4)
    res = propose_surrogate_candidates(problem, patches, _ranking(_SCORES), n_proposals=3)

    assert res["status"] == "ok"
    assert res["surrogate"]["kind"] == "gp_rbf_numpy"
    assert res["surrogate"]["deterministic"] is True
    assert res["training_evidence"]["n_train"] == 4
    assert len(res["proposals"]) == 3
    for p in res["proposals"]:
        ids = {c["variable_id"] for c in p["variable_changes"]}
        assert ids == {"x1", "x2"}
        for c in p["variable_changes"]:
            assert 0 <= c["new_value"] <= 10  # within bounds
        pred = p["surrogate_prediction"]
        assert "uncertainty_std" in pred and pred["uncertainty_std"] >= 0
        assert pred["advisory"] is True
        assert pred["is_solver_evidence"] is False
    # predictions are explicitly not verification evidence
    assert res["honesty"]["is_solver_evidence"] is False
    assert res["honesty"]["predictions_are_verification_evidence"] is False
    assert res["honesty"]["baseline_modified"] is False


def test_surrogate_proposal_is_deterministic() -> None:
    problem = _problem(_var("x1", 0, 10), _var("x2", 0, 10))
    patches = _evaluated_patches(4)
    a = propose_surrogate_candidates(problem, patches, _ranking(_SCORES), n_proposals=3)
    b = propose_surrogate_candidates(problem, patches, _ranking(_SCORES), n_proposals=3)
    assert a["proposals"] == b["proposals"]


def test_degrades_when_evidence_too_sparse() -> None:
    problem = _problem(_var("x1", 0, 10), _var("x2", 0, 10))
    patches = _evaluated_patches(2)  # only 2 evaluated < _MIN_TRAIN
    res = propose_surrogate_candidates(problem, patches, _ranking({"c1": 0.2, "c2": 0.6}), n_proposals=3)
    assert res["status"] == "needs_more_evidence"
    assert "insufficient_evaluated_evidence" in res["reason_codes"]
    assert res["proposals"] == []


def test_degrades_when_no_safe_variables() -> None:
    problem = _problem(_var("x1", 0, 10, safe=False), _var("x2", 0, 10, safe=False))
    res = propose_surrogate_candidates(problem, _evaluated_patches(4), _ranking(_SCORES), n_proposals=3)
    assert res["status"] == "needs_more_evidence"
    assert "no_safe_variables" in res["reason_codes"]


def test_write_surrogate_proposals_is_advisory_and_non_mutating(tmp_path: Path) -> None:
    problem = _problem(_var("x1", 0, 10), _var("x2", 0, 10))
    patches = _evaluated_patches(4)
    pkg = tmp_path / "study.aieng"
    geometry_bytes = b'{"representation": "brep_build123d"}'
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "study"}))
        zf.writestr("geometry/shape_ir.json", geometry_bytes)
        zf.writestr(DESIGN_STUDY_PROBLEM_PATH, json.dumps(problem))
        zf.writestr(DESIGN_STUDY_CANDIDATE_RANKING_PATH, json.dumps(_ranking(_SCORES)))
        for cid, patch in patches.items():
            zf.writestr(f"{DESIGN_CANDIDATES_DIR}{cid}.json", json.dumps(patch))

    res = write_surrogate_proposals(pkg, n_proposals=2)
    assert res["status"] == "ok"
    assert res["n_proposals"] == 2
    assert res["baseline_modified"] is False

    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert SURROGATE_PROPOSALS_PATH in names
        # baseline geometry untouched
        assert zf.read("geometry/shape_ir.json") == geometry_bytes
        # proposed patches are valid + advisory + not applied
        patch_files = [n for n in names if n.startswith(f"{DESIGN_CANDIDATES_DIR}surrogate_")]
        assert len(patch_files) == 2
        p0 = json.loads(zf.read(sorted(patch_files)[0]))
        assert p0["format"] == "aieng.design_candidate_patch"
        assert p0["variable_changes"]
        assert p0["provenance"]["applied"] is False
        assert p0["provenance"]["is_solver_evidence"] is False
