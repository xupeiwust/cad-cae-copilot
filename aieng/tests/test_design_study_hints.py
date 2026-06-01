"""Tests for advisory design-study candidate proposal hints."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.design_study_hints import (
    DESIGN_STUDY_CANDIDATE_HINTS_PATH,
    DESIGN_STUDY_CANDIDATE_HINTS_REPORT_PATH,
    build_design_study_candidate_hints,
)
from aieng.converters.design_study_execution import DESIGN_STUDY_ITERATIONS_PATH
from aieng.converters.design_study_ranking import DESIGN_STUDY_CANDIDATE_RANKING_PATH


def _problem(**overrides):
    p = {
        "format": "aieng.design_study_problem",
        "schema_version": "0.1",
        "id": "study_hints",
        "variables": [
            {"id": "wall_t", "name": "Wall thickness", "path": "parts/0/params/WALL_THICKNESS",
             "type": "continuous", "current_value": 3.0, "min_value": 2.0, "max_value": 8.0,
             "unit": "mm", "safe_to_modify": True, "semantic_role": "wall_thickness", "part_id": "bracket"},
            {"id": "rib_t", "path": "parts/0/params/RIB_THICKNESS",
             "type": "continuous", "current_value": 5.0, "min_value": 3.0, "max_value": 10.0,
             "unit": "mm", "safe_to_modify": True, "semantic_role": "rib_thickness", "part_id": "bracket"},
            {"id": "fillet_r", "path": "parts/0/params/FILLET_RADIUS",
             "type": "continuous", "current_value": 1.1, "min_value": 1.0, "max_value": 6.0,
             "unit": "mm", "safe_to_modify": True, "semantic_role": "fillet_radius", "part_id": "bracket"},
            {"id": "bolt_dia", "path": "parts/0/params/BOLT_DIA",
             "type": "discrete", "current_value": 8, "allowed_values": [6, 8, 10],
             "unit": "mm", "safe_to_modify": False, "semantic_role": "bolt_hole", "part_id": "bracket",
             "protected_reason": "mounting interface"},
        ],
        "constraints": [
            {"id": "c_stress", "type": "max_stress", "limit": 200.0, "unit": "MPa"},
            {"id": "c_defl", "type": "max_deflection", "limit": 5.0, "unit": "mm"},
        ],
        "objective": {"sense": "minimize", "metric": "volume"},
        "selected_part_id": "bracket",
    }
    p.update(overrides)
    return p


def _evaluation(*, status="complete", confidence="medium", stress_ok=True, defl_ok=True, proxy=False):
    ce = [
        {"id": "c_stress", "type": "max_stress", "metric": "max_stress",
         "actual": 180.0 if stress_ok else 260.0, "limit": 200.0,
         "status": "satisfied" if stress_ok else "violated"},
        {"id": "c_defl", "type": "max_deflection", "metric": "max_deflection",
         "actual": 4.0 if defl_ok else 7.0, "limit": 5.0,
         "status": "satisfied" if defl_ok else "violated"},
    ]
    return {
        "format": "aieng.design_study_candidate_evaluation",
        "evaluation_status": status,
        "confidence": confidence,
        "metrics": {
            "volume_mm3": 850.0,
            "max_stress": 180.0 if stress_ok else 260.0,
            "max_deflection": 4.0 if defl_ok else 7.0,
        },
        "constraint_evidence": ce,
        "honesty": {"proxy_derived": proxy, "contact_physics_modeled": False, "bolt_preload_modeled": False} if proxy else {},
        "baseline_modified": False,
    }


def _ranking(recommendation="refine_candidate", feasibility="feasible"):
    return {
        "format": "aieng.design_study.candidate_ranking.v0",
        "status": "ranked",
        "best_candidate_id": "c1",
        "safe_to_accept": recommendation == "accept_candidate",
        "candidates": [{
            "candidate_id": "c1",
            "feasibility": feasibility,
            "recommendation": recommendation,
            "score": 0.1,
            "confidence": "medium",
            "constraint_violations": [],
        }],
    }


def _write_pkg(tmp_path: Path, *, problem=None, extra_members=None) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Study"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"representation": "brep_build123d"}))
        if problem is not None:
            zf.writestr("analysis/design_study_problem.json", json.dumps(problem))
        for name, data in (extra_members or {}).items():
            if isinstance(data, (dict, list)):
                data = json.dumps(data)
            zf.writestr(name, data)
    return pkg


def _read(pkg: Path, name: str):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


def test_missing_problem_writes_insufficient_data(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=None)
    res = build_design_study_candidate_hints(pkg)
    assert res["status"] == "insufficient_data"
    assert _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_PATH)["status"] == "insufficient_data"
    assert _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_REPORT_PATH)["no_hints_reason"]


def test_protected_variable_and_near_bound_warning(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), extra_members={
        "candidates/c1/analysis/evaluation.json": _evaluation(stress_ok=True, defl_ok=True),
    })
    build_design_study_candidate_hints(pkg)
    hints = _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_PATH)
    protect = [h for h in hints["hints"] if h["type"] == "protect_parameter" and h["variable_id"] == "bolt_dia"]
    assert protect and protect[0]["suggested_direction"] == "avoid"
    assert protect[0]["do_not_modify"] is True
    fillet = [h for h in hints["hints"] if h["variable_id"] == "fillet_r"]
    assert any("lower bound" in " ".join(h["safety_notes"]) for h in fillet)


def test_selected_part_scope_skips_other_part_adjustment(tmp_path: Path):
    problem = _problem()
    problem["variables"].append(
        {"id": "other_wall", "path": "parts/1/params/WALL", "type": "continuous",
         "current_value": 4.0, "min_value": 2.0, "max_value": 8.0,
         "safe_to_modify": True, "semantic_role": "wall_thickness", "part_id": "other_part"}
    )
    pkg = _write_pkg(tmp_path, problem=problem, extra_members={
        "candidates/c1/analysis/evaluation.json": _evaluation(stress_ok=True, defl_ok=True),
    })
    build_design_study_candidate_hints(pkg)
    hints = _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_PATH)["hints"]
    assert not [h for h in hints if h["variable_id"] == "other_wall" and h["type"] == "adjust_parameter"]


def test_stress_violation_hints_outrank_mass_reduction(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), extra_members={
        "candidates/c1/analysis/evaluation.json": _evaluation(stress_ok=False, defl_ok=True),
        DESIGN_STUDY_CANDIDATE_RANKING_PATH: _ranking(feasibility="infeasible"),
    })
    build_design_study_candidate_hints(pkg)
    hints = _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_PATH)["hints"]
    first_adjust = next(h for h in hints if h["type"] == "adjust_parameter")
    assert first_adjust["priority"] == "high"
    assert first_adjust["suggested_direction"] == "increase"
    assert "stress" in first_adjust["reason"]
    assert not any(h["suggested_direction"] == "decrease" and h["priority"] == "high" for h in hints)


def test_low_confidence_proxy_evidence_lowers_confidence_and_adds_review_hint(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), extra_members={
        "candidates/c1/analysis/evaluation.json": _evaluation(confidence="low", proxy=True),
    })
    build_design_study_candidate_hints(pkg)
    hints = _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_PATH)["hints"]
    assert any(h["type"] == "request_user_input" and h["confidence"] == "low" for h in hints)
    assert any("bolt_preload_model" in " ".join(h["safety_notes"]) for h in hints)


def test_ranking_no_safe_best_produces_no_accept_hint(tmp_path: Path):
    """When ranking says no safe best candidate, hints must not suggest accept/adopt."""
    pkg = _write_pkg(tmp_path, problem=_problem(), extra_members={
        DESIGN_STUDY_CANDIDATE_RANKING_PATH: {
            "format": "aieng.design_study.candidate_ranking.v0",
            "status": "ranked",
            "best_candidate_id": None,
            "safe_to_accept": False,
            "candidates": [
                {"candidate_id": "c_bad", "feasibility": "failed", "score": -1.0,
                 "confidence": "low", "recommendation": "reject_candidate",
                 "constraint_violations": ["stress violation"]},
            ],
        },
    })
    build_design_study_candidate_hints(pkg)
    hints = _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_PATH)["hints"]
    # Critical invariant: no hint may suggest accepting or adopting a candidate
    # when the ranking says there is no safe best.
    assert not any(h["type"] in ("accept_candidate", "adopt_candidate") for h in hints)


def test_accepted_candidate_produces_stop_hint(tmp_path: Path):
    """When acceptance status is accepted, hints should produce stop/next-stage style hints,
    not aggressive parameter changes."""
    pkg = _write_pkg(tmp_path, problem=_problem(), extra_members={
        "analysis/design_study_acceptance.json": {
            "status": "accepted", "accepted_candidate_id": "c1",
            "baseline_modified": False, "promotion_mode": "derived_only",
        },
        "candidates/c1/analysis/evaluation.json": _evaluation(stress_ok=True, defl_ok=True),
    })
    build_design_study_candidate_hints(pkg)
    hints = _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_PATH)["hints"]
    stop_hints = [h for h in hints if h["type"] == "stop_no_safe_hint"]
    assert stop_hints, "Expected a stop/next-stage hint when candidate is already accepted"
    assert not any(h["type"] == "adjust_parameter" and h["priority"] == "high"
                   for h in hints), "No aggressive high-priority adjust hints when accepted"


def test_deflection_violation_suggests_stiffness_increase(tmp_path: Path):
    """If ranking rejects due to deflection, hints should suggest stiffness-related variables."""
    pkg = _write_pkg(tmp_path, problem=_problem(), extra_members={
        "candidates/c1/analysis/evaluation.json": _evaluation(defl_ok=False, stress_ok=True),
        DESIGN_STUDY_CANDIDATE_RANKING_PATH: {
            "format": "aieng.design_study.candidate_ranking.v0",
            "status": "ranked",
            "best_candidate_id": None,
            "safe_to_accept": False,
            "candidates": [
                {"candidate_id": "c1", "feasibility": "infeasible", "score": -0.5,
                 "confidence": "low", "recommendation": "reject_candidate",
                 "constraint_violations": ["deflection 7.0 > limit 5.0"]},
            ],
        },
    })
    build_design_study_candidate_hints(pkg)
    hints = _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_PATH)["hints"]
    stiffness_hints = [h for h in hints if h["type"] == "adjust_parameter"
                       and "deflection" in h.get("reason", "").lower()]
    assert stiffness_hints, "Expected stiffness-related hints for deflection violation"
    for h in stiffness_hints:
        assert h["suggested_direction"] == "increase"


def test_protected_variable_only_protect_hints(tmp_path: Path):
    """If a variable is protected, hints must only produce protect/avoid hints,
    never adjust_parameter suggestions targeting it."""
    pkg = _write_pkg(tmp_path, problem=_problem(), extra_members={
        "candidates/c1/analysis/evaluation.json": _evaluation(stress_ok=True, defl_ok=True),
    })
    build_design_study_candidate_hints(pkg)
    hints = _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_PATH)["hints"]
    bolt_adjust = [h for h in hints if h["type"] == "adjust_parameter" and h.get("variable_id") == "bolt_dia"]
    assert not bolt_adjust, "Protected bolt_dia must not receive adjust_parameter hints"
    bolt_protect = [h for h in hints if h["type"] == "protect_parameter" and h.get("variable_id") == "bolt_dia"]
    assert bolt_protect, "Protected bolt_dia must receive protect_parameter hints"
    assert all(h.get("do_not_modify") is True for h in bolt_protect)


def test_hint_count_limited_deterministically(tmp_path: Path):
    problem = _problem(variables=[
        {"id": f"wall_{i}", "path": f"parts/0/params/WALL_{i}", "type": "continuous",
         "current_value": 4.0, "min_value": 2.0, "max_value": 8.0,
         "safe_to_modify": True, "semantic_role": "wall_thickness", "part_id": "bracket"}
        for i in range(20)
    ])
    pkg = _write_pkg(tmp_path, problem=problem, extra_members={
        "candidates/c1/analysis/evaluation.json": _evaluation(stress_ok=True, defl_ok=True),
    })
    build_design_study_candidate_hints(pkg, max_hints=5)
    hints = _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_PATH)["hints"]
    assert len(hints) == 5
    assert [h["id"] for h in hints] == [f"hint_{i:03d}" for i in range(1, 6)]


def test_missing_metrics_produces_rerun_evaluation_hint(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), extra_members={
        "candidates/c1/analysis/evaluation.json": _evaluation(status="partial"),
        DESIGN_STUDY_ITERATIONS_PATH: {
            "iterations": [{"candidate_id": "c1", "execution_status": "patch_applied", "validation_status": "valid"}]
        },
        DESIGN_STUDY_CANDIDATE_RANKING_PATH: _ranking(recommendation="needs_more_evaluation", feasibility="unknown"),
    })
    build_design_study_candidate_hints(pkg)
    hints = _read(pkg, DESIGN_STUDY_CANDIDATE_HINTS_PATH)["hints"]
    assert any(h["type"] == "rerun_evaluation" for h in hints)
