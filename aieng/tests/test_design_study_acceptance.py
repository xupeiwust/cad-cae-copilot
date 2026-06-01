"""Tests for design study candidate ACCEPTANCE v0 (PR4).

Acceptance is explicit, gated by eligibility, and never overwrites baseline geometry.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.design_study_acceptance import (
    DESIGN_STUDY_ACCEPTANCE_PATH,
    DESIGN_STUDY_ACCEPTANCE_REPORT_PATH,
    _check_eligibility,
    accept_design_study_candidate,
)
from aieng.converters.design_study_execution import DESIGN_STUDY_ITERATIONS_PATH
from aieng.converters.design_study_ranking import DESIGN_STUDY_CANDIDATE_RANKING_PATH


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
        ],
        "objective": {"sense": "minimize", "metric": "mass"},
        "baseline_metrics": {"mass_kg": 1.0},
    }
    p.update(overrides)
    return p


def _ranking(candidates, best_id=None, safe=False):
    return {
        "format": "aieng.design_study.candidate_ranking.v0",
        "status": "ranked",
        "candidates": candidates,
        "best_candidate_id": best_id,
        "safe_to_accept": safe,
    }


def _ranked_cand(cid, feasibility="feasible", confidence="high", score=0.2):
    return {
        "candidate_id": cid,
        "feasibility": feasibility,
        "confidence": confidence,
        "score": score,
        "recommendation": "accept_candidate" if (confidence == "high" and score > 0) else "refine_candidate",
        "metrics_used": {},
        "constraint_violations": [],
        "objective_delta": {},
        "reasons": [],
    }


def _iteration(cid, execution_status="evaluation_complete", metrics=None):
    return {
        "candidate_id": cid,
        "execution_status": execution_status,
        "metrics": metrics or {"mass_kg": 0.8, "max_stress": 150.0},
        "baseline_modified": False,
    }


def _write_pkg(tmp_path: Path, *, problem=None, ranking=None, iterations=None,
               candidate_ws=None, extra_members=None) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Study"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"representation": "brep_build123d"}))
        if problem is not None:
            zf.writestr("analysis/design_study_problem.json", json.dumps(problem))
        if ranking is not None:
            zf.writestr(DESIGN_STUDY_CANDIDATE_RANKING_PATH, json.dumps(ranking))
        if iterations is not None:
            doc = {
                "format": "aieng.design_study_iterations",
                "format_version": "0.1.0",
                "schema_version": "0.1",
                "iterations": iterations,
            }
            zf.writestr(DESIGN_STUDY_ITERATIONS_PATH, json.dumps(doc))
        for cid, ws_data in (candidate_ws or {}).items():
            for name, data in ws_data.items():
                zf.writestr(f"candidates/{cid}/{name}", json.dumps(data) if isinstance(data, (dict, list)) else data)
        for name, data in (extra_members or {}).items():
            if isinstance(data, (dict, list)):
                data = json.dumps(data)
            zf.writestr(name, data)
    return pkg


def _read(pkg, name):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


# ── unit: eligibility ─────────────────────────────────────────────────────────

def test_eligibility_best_and_safe():
    r = _ranking([_ranked_cand("c1")], best_id="c1", safe=True)
    el = _check_eligibility(r, "c1", _iteration("c1"), override_unsafe=False)
    assert el["eligible"] is True
    assert el["status"] == "accepted"


def test_eligibility_not_best_not_safe_rejected():
    r = _ranking([_ranked_cand("c1"), _ranked_cand("c2")], best_id="c1", safe=False)
    el = _check_eligibility(r, "c2", _iteration("c2"), override_unsafe=False)
    assert el["eligible"] is False
    assert el["status"] == "needs_user_input"
    assert any("not best_candidate_id" in reason for reason in el["reasons"])


def test_eligibility_override_unsafe():
    r = _ranking([_ranked_cand("c1"), _ranked_cand("c2")], best_id="c1", safe=False)
    el = _check_eligibility(r, "c2", _iteration("c2"), override_unsafe=True)
    assert el["eligible"] is True
    assert any("override_unsafe" in w for w in el["warnings"])


def test_eligibility_best_but_not_safe_needs_input():
    r = _ranking([_ranked_cand("c1")], best_id="c1", safe=False)
    el = _check_eligibility(r, "c1", _iteration("c1"), override_unsafe=False)
    assert el["eligible"] is False
    assert el["status"] == "needs_user_input"


def test_eligibility_failed_rejected():
    r = _ranking([_ranked_cand("c1", feasibility="failed")], best_id="c1", safe=True)
    el = _check_eligibility(r, "c1", _iteration("c1"), override_unsafe=False)
    assert el["eligible"] is False
    assert el["status"] == "rejected"


def test_eligibility_infeasible_rejected():
    r = _ranking([_ranked_cand("c1", feasibility="infeasible")], best_id="c1", safe=True)
    el = _check_eligibility(r, "c1", _iteration("c1"), override_unsafe=False)
    assert el["eligible"] is False
    assert el["status"] == "rejected"


def test_eligibility_unknown_rejected():
    r = _ranking([_ranked_cand("c1", feasibility="unknown")], best_id="c1", safe=True)
    el = _check_eligibility(r, "c1", _iteration("c1"), override_unsafe=False)
    assert el["eligible"] is False
    assert el["status"] == "rejected"


def test_eligibility_missing_ranking():
    el = _check_eligibility(None, "c1", _iteration("c1"), override_unsafe=False)
    assert el["eligible"] is False
    assert el["status"] == "needs_user_input"


def test_eligibility_missing_candidate_in_ranking():
    r = _ranking([_ranked_cand("c1")], best_id="c1", safe=True)
    el = _check_eligibility(r, "ghost", _iteration("ghost"), override_unsafe=False)
    assert el["eligible"] is False
    assert el["status"] == "rejected"


def test_eligibility_missing_iteration():
    r = _ranking([_ranked_cand("c1")], best_id="c1", safe=True)
    el = _check_eligibility(r, "c1", None, override_unsafe=False)
    assert el["eligible"] is False
    assert el["status"] == "rejected"


# ── integration: acceptance ───────────────────────────────────────────────────

def test_accept_safe_best_candidate(tmp_path: Path):
    ranking = _ranking(
        [_ranked_cand("c1", score=0.2, confidence="high")],
        best_id="c1", safe=True,
    )
    ws = {
        "c1": {
            "patch.json": {"candidate_id": "c1"},
            "geometry/shape_ir.json": {"representation": "brep_build123d", "parts": []},
            "analysis/evaluation.json": {"metrics": {"mass_kg": 0.8}},
        }
    }
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=ranking,
        iterations=[_iteration("c1")], candidate_ws=ws,
    )
    res = accept_design_study_candidate(pkg, "c1")
    assert res["status"] == "ok"
    assert res["accepted"] is True
    assert res["baseline_modified"] is False

    # Acceptance artifact
    acc = _read(pkg, DESIGN_STUDY_ACCEPTANCE_PATH)
    assert acc["status"] == "accepted"
    assert acc["accepted_candidate_id"] == "c1"
    assert acc["baseline_modified"] is False
    assert acc["promotion_mode"] == "derived_only"

    # Report
    report = _read(pkg, DESIGN_STUDY_ACCEPTANCE_REPORT_PATH)
    assert report["accepted"] is True
    assert report["eligibility_checks"]["eligible"] is True
    assert report["artifact_existence_checks"]["patch"] is True

    # Accepted workspace exists
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert "accepted/c1/patch.json" in names
        assert "accepted/c1/geometry/shape_ir.json" in names
        assert "accepted/c1/analysis/evaluation.json" in names
        assert "accepted/c1/provenance/acceptance.json" in names

    # Provenance
    prov = _read(pkg, "accepted/c1/provenance/acceptance.json")
    assert prov["accepted_candidate_id"] == "c1"
    assert prov["baseline_modified"] is False


def test_accept_baseline_unchanged(tmp_path: Path):
    baseline = {"representation": "brep_build123d", "parts": [{"id": "blk"}]}
    ranking = _ranking([_ranked_cand("c1")], best_id="c1", safe=True)
    ws = {
        "c1": {
            "patch.json": {"candidate_id": "c1"},
            "geometry/shape_ir.json": {"parts": [{"id": "changed"}]},
            "analysis/evaluation.json": {},
        }
    }
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=ranking,
        iterations=[_iteration("c1")], candidate_ws=ws,
        extra_members={"geometry/shape_ir.json": json.dumps(baseline)},
    )
    accept_design_study_candidate(pkg, "c1")
    assert _read(pkg, "geometry/shape_ir.json") == baseline


def test_accept_non_best_requires_override(tmp_path: Path):
    ranking = _ranking(
        [_ranked_cand("c1", score=0.3), _ranked_cand("c2", score=0.1)],
        best_id="c1", safe=True,
    )
    ws = {
        "c2": {
            "patch.json": {"candidate_id": "c2"},
            "geometry/shape_ir.json": {},
            "analysis/evaluation.json": {},
        }
    }
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=ranking,
        iterations=[_iteration("c2")], candidate_ws=ws,
    )
    # Without override — rejected
    res = accept_design_study_candidate(pkg, "c2")
    assert res["accepted"] is False
    assert res["status"] == "needs_user_input"

    # With override — accepted
    res = accept_design_study_candidate(pkg, "c2", override_unsafe=True)
    assert res["accepted"] is True


def test_accept_failed_candidate_rejected(tmp_path: Path):
    ranking = _ranking(
        [_ranked_cand("c1", feasibility="failed", score=-1.0)],
        best_id="c1", safe=False,
    )
    ws = {
        "c1": {
            "patch.json": {},
            "geometry/shape_ir.json": {},
            "analysis/evaluation.json": {},
        }
    }
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=ranking,
        iterations=[_iteration("c1", execution_status="compile_failed")],
        candidate_ws=ws,
    )
    res = accept_design_study_candidate(pkg, "c1", override_unsafe=True)
    assert res["accepted"] is False
    assert res["status"] == "rejected"
    acc = _read(pkg, DESIGN_STUDY_ACCEPTANCE_PATH)
    assert acc["status"] == "rejected"
    assert acc["accepted_candidate_id"] is None


def test_accept_infeasible_candidate_rejected(tmp_path: Path):
    ranking = _ranking(
        [_ranked_cand("c1", feasibility="infeasible", score=-0.5)],
        best_id="c1", safe=False,
    )
    ws = {
        "c1": {
            "patch.json": {},
            "geometry/shape_ir.json": {},
            "analysis/evaluation.json": {},
        }
    }
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=ranking,
        iterations=[_iteration("c1")], candidate_ws=ws,
    )
    res = accept_design_study_candidate(pkg, "c1", override_unsafe=True)
    assert res["accepted"] is False
    assert res["status"] == "rejected"


def test_accept_unknown_candidate_rejected(tmp_path: Path):
    ranking = _ranking(
        [_ranked_cand("c1", feasibility="unknown", score=0.0, confidence="low")],
        best_id="c1", safe=False,
    )
    ws = {
        "c1": {
            "patch.json": {},
            "geometry/shape_ir.json": {},
            "analysis/evaluation.json": {},
        }
    }
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=ranking,
        iterations=[_iteration("c1")], candidate_ws=ws,
    )
    res = accept_design_study_candidate(pkg, "c1", override_unsafe=True)
    assert res["accepted"] is False
    assert res["status"] == "rejected"


def test_accept_missing_ranking_needs_input(tmp_path: Path):
    ws = {"c1": {"patch.json": {}, "geometry/shape_ir.json": {}, "analysis/evaluation.json": {}}}
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=None,
        iterations=[_iteration("c1")], candidate_ws=ws,
    )
    res = accept_design_study_candidate(pkg, "c1")
    assert res["accepted"] is False
    assert res["status"] == "needs_user_input"
    assert any("ranking" in r.lower() for r in res["reasons"])


def test_accept_missing_artifacts_fails_honestly(tmp_path: Path):
    ranking = _ranking([_ranked_cand("c1")], best_id="c1", safe=True)
    # No candidate workspace artifacts
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=ranking,
        iterations=[_iteration("c1")], candidate_ws={},
    )
    res = accept_design_study_candidate(pkg, "c1")
    assert res["accepted"] is False
    assert res["status"] == "rejected"
    assert any("missing" in r.lower() for r in res["reasons"])


def test_accept_package_not_found():
    res = accept_design_study_candidate("/nonexistent/path/study.aieng", "c1")
    assert res["status"] == "failed"


def test_accept_does_not_create_viewer_artifacts(tmp_path: Path):
    ranking = _ranking([_ranked_cand("c1")], best_id="c1", safe=True)
    ws = {
        "c1": {
            "patch.json": {},
            "geometry/shape_ir.json": {},
            "analysis/evaluation.json": {},
        }
    }
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=ranking,
        iterations=[_iteration("c1")], candidate_ws=ws,
    )
    accept_design_study_candidate(pkg, "c1")
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert not any("viewer" in n for n in names)
        assert not any("preview" in n for n in names)
        # geometry/shape_ir.json at root is baseline, NOT the accepted one
        root_shape_ir = json.loads(zf.read("geometry/shape_ir.json"))
        assert root_shape_ir == {"representation": "brep_build123d"}


def test_accept_report_contents(tmp_path: Path):
    ranking = _ranking([_ranked_cand("c1", score=0.2)], best_id="c1", safe=True)
    ws = {"c1": {"patch.json": {}, "geometry/shape_ir.json": {}, "analysis/evaluation.json": {}}}
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=ranking,
        iterations=[_iteration("c1")], candidate_ws=ws,
    )
    accept_design_study_candidate(pkg, "c1")
    report = _read(pkg, DESIGN_STUDY_ACCEPTANCE_REPORT_PATH)
    assert report["candidate_id"] == "c1"
    assert report["accepted"] is True
    assert report["eligibility_checks"]["ranking_exists"] is True
    assert report["eligibility_checks"]["candidate_in_ranking"] is True
    assert report["eligibility_checks"]["feasibility"] == "feasible"
    assert report["eligibility_checks"]["safe_to_accept"] is True
    assert report["eligibility_checks"]["is_best_candidate"] is True
    assert report["artifact_existence_checks"]["patch"] is True
    assert report["artifact_existence_checks"]["shape_ir"] is True
    assert report["artifact_existence_checks"]["evaluation"] is True
    assert report["provenance"]["baseline_modified"] is False


def test_accept_reasoning_passed_through(tmp_path: Path):
    ranking = _ranking([_ranked_cand("c1")], best_id="c1", safe=True)
    ws = {"c1": {"patch.json": {}, "geometry/shape_ir.json": {}, "analysis/evaluation.json": {}}}
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=ranking,
        iterations=[_iteration("c1")], candidate_ws=ws,
    )
    res = accept_design_study_candidate(
        pkg, "c1", accepted_by="human", reasoning="best mass reduction with safe margins"
    )
    assert res["accepted"] is True
    acc = _read(pkg, DESIGN_STUDY_ACCEPTANCE_PATH)
    assert acc["accepted_by"] == "human"
    assert acc["reasoning"] == "best mass reduction with safe margins"
    prov = _read(pkg, "accepted/c1/provenance/acceptance.json")
    assert prov["accepted_by"] == "human"
    assert prov["reasoning"] == "best mass reduction with safe margins"


def test_accept_best_not_safe_override_needed(tmp_path: Path):
    """Best candidate but safe_to_accept=false still needs override_unsafe."""
    ranking = _ranking([_ranked_cand("c1")], best_id="c1", safe=False)
    ws = {"c1": {"patch.json": {}, "geometry/shape_ir.json": {}, "analysis/evaluation.json": {}}}
    pkg = _write_pkg(
        tmp_path, problem=_problem(), ranking=ranking,
        iterations=[_iteration("c1")], candidate_ws=ws,
    )
    res = accept_design_study_candidate(pkg, "c1")
    assert res["accepted"] is False
    assert res["status"] == "needs_user_input"
    assert any("safe_to_accept=false" in r for r in res["reasons"])

    # With override it should work
    res2 = accept_design_study_candidate(pkg, "c1", override_unsafe=True)
    assert res2["accepted"] is True
