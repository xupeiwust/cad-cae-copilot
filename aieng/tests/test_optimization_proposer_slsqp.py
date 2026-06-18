"""Tests for the SLSQP optimizer proposer (#65)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from aieng.converters.optimization_proposer import DESIGN_CANDIDATES_DIR
from aieng.converters.optimization_proposer_slsqp import (
    _compute_gradient_fd,
    _fd_perturbation_value,
    _has_scipy,
    _read_all_patches,
    _evaluated_points,
    _slsqp_next_point,
    propose_slsqp_candidates,
)


_scipy_available = _has_scipy()
scipy_required = pytest.mark.skipif(
    not _scipy_available,
    reason="scipy is not installed (optional optimization dependency)",
)


def _variables_doc(*, integer=False):
    vars_ = [
        {"id": "wall_t", "type": "continuous", "min_value": 2.0, "max_value": 8.0,
         "current_value": 5.0, "safe_to_modify": True},
        {"id": "fillet_r", "type": "continuous", "min_value": 1.0, "max_value": 4.0,
         "current_value": 2.0, "safe_to_modify": True},
    ]
    if integer:
        # Use a wide range so integer FD perturbation actually changes the value
        vars_.append(
            {"id": "n_holes", "type": "integer", "min_value": 0, "max_value": 100,
             "current_value": 50, "safe_to_modify": True}
        )
    return {"format": "aieng.optimization_variables", "schema_version": "0.1", "variables": vars_}


def _ranking(best_id, scores=None):
    scores = scores or {}
    candidates = []
    for cid, score in scores.items():
        candidates.append({
            "rank": 1, "candidate_id": cid, "feasibility": "feasible",
            "score": score, "confidence": "high",
        })
    return {
        "format": "aieng.design_study.candidate_ranking.v0", "status": "ranked",
        "best_candidate_id": best_id, "safe_to_accept": True,
        "candidates": candidates,
    }


def _patch(cid, **vals):
    changes = [{"variable_id": k, "new_value": v} for k, v in vals.items()]
    return {"format": "aieng.design_candidate_patch", "candidate_id": cid,
            "variable_changes": changes}


def _pkg(tmp_path, *, ranking=None, patches=None, variables=None, history=None) -> Path:
    pkg = tmp_path / "study.aieng"
    patches = patches or {}
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "S"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
        zf.writestr("analysis/optimization_variables.json",
                    json.dumps(variables or _variables_doc()))
        if ranking is not None:
            zf.writestr("analysis/design_study_candidate_ranking.json", json.dumps(ranking))
        if history is not None:
            zf.writestr("analysis/optimization_iterations.json", json.dumps(history))
        for cid, p in patches.items():
            zf.writestr(f"{DESIGN_CANDIDATES_DIR}{cid}.json", json.dumps(p))
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


# ── helpers ───────────────────────────────────────────────────────────────────


@scipy_required
def test_has_scipy():
    # When scipy is present, the proposer can use the real SLSQP backend.
    assert _has_scipy() is True


def test_fd_perturbation_value():
    var = {"id": "x", "type": "continuous", "min_value": 0.0, "max_value": 10.0}
    # dx = 0.01 * 10 = 0.1
    assert _fd_perturbation_value(var, 5.0, 0.01, 1) == 5.1
    assert _fd_perturbation_value(var, 5.0, 0.01, -1) == 4.9
    # clamping
    assert _fd_perturbation_value(var, 9.99, 0.01, 1) == 10.0
    assert _fd_perturbation_value(var, 0.01, 0.01, -1) == 0.0


def test_fd_perturbation_value_integer():
    var = {"id": "n", "type": "integer", "min_value": 2, "max_value": 8}
    assert isinstance(_fd_perturbation_value(var, 4, 0.01, 1), int)


def test_read_all_patches(tmp_path: Path):
    pkg = _pkg(tmp_path, patches={"c1": _patch("c1", wall_t=3.0), "c2": _patch("c2", wall_t=4.0)})
    with zipfile.ZipFile(pkg) as zf:
        patches = _read_all_patches(zf, set(zf.namelist()))
    assert set(patches.keys()) == {"c1", "c2"}


def test_evaluated_points():
    patches = {"c1": _patch("c1", wall_t=3.0, fillet_r=1.5),
               "c2": _patch("c2", wall_t=4.0, fillet_r=2.0)}
    ranking = _ranking("c1", {"c1": 0.5, "c2": 0.3})
    ev = _evaluated_points(patches, ranking)
    assert ev["c1"]["score"] == 0.5
    assert ev["c1"]["values"]["wall_t"] == 3.0


def test_compute_gradient_fd_central():
    incumbent = {"wall_t": 5.0, "fillet_r": 2.0}
    safe_vars = [
        {"id": "wall_t", "type": "continuous", "min_value": 2.0, "max_value": 8.0},
        {"id": "fillet_r", "type": "continuous", "min_value": 1.0, "max_value": 4.0},
    ]
    # central difference: forward and backward points evaluated
    evaluated = {
        "inc": {"values": incumbent, "score": 0.0},
        "f": {"values": {"wall_t": 5.06, "fillet_r": 2.0}, "score": 0.12},
        "b": {"values": {"wall_t": 4.94, "fillet_r": 2.0}, "score": -0.12},
    }
    grad, missing = _compute_gradient_fd(incumbent, safe_vars, evaluated, fd_frac=0.01)
    # dx = 0.01 * 6 = 0.06
    assert grad["wall_t"] == pytest.approx((0.12 - (-0.12)) / (2 * 0.06), rel=1e-9)
    assert "wall_t" not in missing
    # fillet_r has no perturbation data → missing
    assert grad["fillet_r"] is None
    assert "fillet_r" in missing


def test_compute_gradient_fd_forward_only():
    incumbent = {"wall_t": 5.0}
    safe_vars = [
        {"id": "wall_t", "type": "continuous", "min_value": 2.0, "max_value": 8.0},
    ]
    evaluated = {
        "inc": {"values": incumbent, "score": 0.0},
        "f": {"values": {"wall_t": 5.06}, "score": 0.12},
    }
    grad, missing = _compute_gradient_fd(incumbent, safe_vars, evaluated, fd_frac=0.01)
    assert grad["wall_t"] == pytest.approx((0.12 - 0.0) / 0.06, rel=1e-9)
    assert not missing


@scipy_required
def test_slsqp_next_point():
    incumbent = {"wall_t": 5.0, "fillet_r": 2.0}
    safe_vars = [
        {"id": "wall_t", "type": "continuous", "min_value": 2.0, "max_value": 8.0},
        {"id": "fillet_r", "type": "continuous", "min_value": 1.0, "max_value": 4.0},
    ]
    gradient = {"wall_t": 1.0, "fillet_r": 0.5}
    nxt = _slsqp_next_point(incumbent, safe_vars, gradient)
    assert len(nxt) == 2
    # With positive gradients the model wants to move in the positive direction,
    # but because we minimize the negative model the optimizer moves along the
    # gradient direction as far as bounds allow.
    assert nxt[0] >= 5.0  # wall_t should increase
    assert nxt[1] >= 2.0  # fillet_r should increase


@scipy_required
def test_slsqp_next_point_respects_bounds():
    incumbent = {"wall_t": 7.9}
    safe_vars = [
        {"id": "wall_t", "type": "continuous", "min_value": 2.0, "max_value": 8.0},
    ]
    gradient = {"wall_t": 10.0}
    nxt = _slsqp_next_point(incumbent, safe_vars, gradient)
    assert nxt[0] <= 8.0 + 1e-6


# ── integration: propose_slsqp_candidates ─────────────────────────────────────


def test_missing_package_errors():
    res = propose_slsqp_candidates(Path("/nonexistent/study.aieng"), count=1)
    assert res["status"] == "error"
    assert res["code"] == "package_not_found"


def test_missing_variables_errors(tmp_path: Path):
    pkg = tmp_path / "s.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", "{}")
    res = propose_slsqp_candidates(pkg, count=1)
    assert res["status"] == "error"
    assert res["code"] == "missing_variables"


@scipy_required
def test_no_incumbent_falls_back_to_lhs(tmp_path: Path):
    ranking = _ranking(None, {})
    pkg = _pkg(tmp_path, ranking=ranking)
    res = propose_slsqp_candidates(pkg, count=3, seed=0)
    assert res["status"] == "ok"
    assert res["strategy"] == "lhs_fallback"
    assert res["candidate_count"] == 3
    assert "no_incumbent_fallback" in res["reason_codes"]


@scipy_required
def test_incumbent_without_score_proposes_baseline_eval(tmp_path: Path):
    pkg = _pkg(
        tmp_path,
        ranking=_ranking("inc", {}),
        patches={"inc": _patch("inc", wall_t=5.0, fillet_r=2.0)},
    )
    res = propose_slsqp_candidates(pkg, count=1)
    assert res["status"] == "ok"
    assert res["strategy"] == "slsqp_baseline_eval"
    assert res["candidate_count"] == 1
    patches = _patches(pkg)
    assert any("slsqp_baseline" in n for n in patches)


@scipy_required
def test_fd_collection_when_gradient_missing(tmp_path: Path):
    pkg = _pkg(
        tmp_path,
        ranking=_ranking("inc", {"inc": 0.0}),
        patches={"inc": _patch("inc", wall_t=5.0, fillet_r=2.0)},
    )
    res = propose_slsqp_candidates(pkg, count=2, fd_frac=0.01)
    assert res["status"] == "ok"
    assert res["strategy"] == "slsqp_fd_collection"
    assert res["candidate_count"] == 2
    assert "no_gradient_available" in res["reason_codes"]
    patches = _patches(pkg)
    fd_names = [n for n in patches if "slsqp_fd" in n]
    assert len(fd_names) == 2
    # Each FD candidate should differ from incumbent in exactly one variable
    for n in fd_names:
        v = _vals(patches[n])
        diff_count = sum(1 for k in v if v[k] != {"wall_t": 5.0, "fillet_r": 2.0}[k])
        assert diff_count == 1


@scipy_required
def test_slsqp_step_when_gradient_available(tmp_path: Path):
    # Provide forward evaluations for both variables so gradients are complete
    pkg = _pkg(
        tmp_path,
        ranking=_ranking("inc", {
            "inc": 0.0,
            "f_wall": 0.12,
            "f_fillet": 0.08,
        }),
        patches={
            "inc": _patch("inc", wall_t=5.0, fillet_r=2.0),
            "f_wall": _patch("f_wall", wall_t=5.06, fillet_r=2.0),
            "f_fillet": _patch("f_fillet", wall_t=5.0, fillet_r=2.03),
        },
    )
    res = propose_slsqp_candidates(pkg, count=1, fd_frac=0.01)
    assert res["status"] == "ok"
    assert res["strategy"] == "slsqp"
    assert res["candidate_count"] == 1
    patches = _patches(pkg)
    slsqp_names = [n for n in patches if "cand_slsqp_iter" in n]
    assert len(slsqp_names) == 1
    v = _vals(patches[slsqp_names[0]])
    assert 2.0 <= v["wall_t"] <= 8.0
    assert 1.0 <= v["fillet_r"] <= 4.0


@scipy_required
def test_slsqp_step_integer_rounding(tmp_path: Path):
    # Provide forward evaluations for ALL variables so gradients are complete
    # n_holes range [0, 100], center 50, dx = 1.0, forward = 51
    pkg = _pkg(
        tmp_path,
        ranking=_ranking("inc", {
            "inc": 0.0,
            "f_wall": 0.12,
            "f_fillet": 0.08,
            "f_n": 0.1,
        }),
        patches={
            "inc": _patch("inc", wall_t=5.0, fillet_r=2.0, n_holes=50),
            "f_wall": _patch("f_wall", wall_t=5.06, fillet_r=2.0, n_holes=50),
            "f_fillet": _patch("f_fillet", wall_t=5.0, fillet_r=2.03, n_holes=50),
            "f_n": _patch("f_n", wall_t=5.0, fillet_r=2.0, n_holes=51),
        },
        variables=_variables_doc(integer=True),
    )
    res = propose_slsqp_candidates(pkg, count=1, fd_frac=0.01)
    assert res["status"] == "ok"
    assert res["strategy"] == "slsqp"
    patches = _patches(pkg)
    slsqp_name = next((n for n in patches if "cand_slsqp_iter" in n), None)
    assert slsqp_name is not None, "No SLSQP candidate found in patches"
    n_holes = _vals(patches[slsqp_name]).get("n_holes")
    assert isinstance(n_holes, int)


def test_baseline_never_modified(tmp_path: Path):
    pkg = _pkg(
        tmp_path,
        ranking=_ranking("inc", {"inc": 0.0}),
        patches={"inc": _patch("inc", wall_t=5.0, fillet_r=2.0)},
    )
    res = propose_slsqp_candidates(pkg, count=1)
    assert res["baseline_modified"] is False


def test_graceful_fallback_when_scipy_missing(tmp_path: Path):
    ranking = _ranking(None, {})
    pkg = _pkg(tmp_path, ranking=ranking)
    with patch("aieng.converters.optimization_proposer_slsqp._has_scipy", return_value=False):
        res = propose_slsqp_candidates(pkg, count=2, seed=0)
    assert res["status"] == "ok"
    assert res["strategy"] == "lhs_fallback"
    assert "no_surrogate_available" in res["reason_codes"]
