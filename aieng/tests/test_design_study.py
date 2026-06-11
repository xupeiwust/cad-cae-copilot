"""Tests for design study problem contract + candidate patch validation v0.

Contract + validation only — no patch is applied, no geometry recompiled, no CAE run,
no optimization/search. Baseline geometry is never modified.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.design_study import (
    DESIGN_STUDY_CANDIDATE_VALIDATION_PATH,
    DESIGN_STUDY_PROBLEM_DIAGNOSTICS_PATH,
    process_design_study_package,
    validate_design_candidate_patch,
    validate_design_study_problem,
)


def _problem(**overrides):
    p = {
        "format": "aieng.design_study_problem", "schema_version": "0.1",
        "variables": [
            {"id": "wall_t", "path": "shape_ir/params/WALL_THICKNESS", "type": "continuous",
             "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "unit": "mm",
             "safe_to_modify": True, "semantic_role": "wall_thickness"},
            {"id": "rib_count", "path": "shape_ir/params/RIB_COUNT", "type": "integer",
             "current_value": 2, "min_value": 1, "max_value": 6, "unit": "count",
             "safe_to_modify": True, "semantic_role": "rib"},
            {"id": "bolt_dia", "path": "shape_ir/params/BOLT_DIA", "type": "discrete",
             "current_value": 6, "allowed_values": [4, 5, 6, 8, 10], "unit": "mm",
             "safe_to_modify": False, "semantic_role": "bolt_hole"},  # protected + unsafe
        ],
        "constraints": [{"id": "c1", "expr": "wall_t >= 2.5", "note": "recorded only"}],
        "objective": {"sense": "minimize", "metric": "mass"},
        "settings": {"max_variables_per_candidate": 2, "require_reasoning": True},
    }
    p.update(overrides)
    return p


def _candidate(changes, reasoning="reduce mass while keeping stiffness", **extra):
    return {"format": "aieng.design_candidate_patch", "candidate_id": "cand_001",
            "reasoning": reasoning, "variable_changes": changes, **extra}


# ── problem validation ────────────────────────────────────────────────────────

def test_valid_single_part_problem():
    d = validate_design_study_problem(_problem())
    assert d["status"] == "passed", d["errors"] + d["warnings"]
    assert d["summary"]["variable_count"] == 3
    assert d["summary"]["safe_to_modify_count"] == 2
    assert d["summary"]["protected_count"] == 1
    assert d["summary"]["constraint_count"] == 1 and d["summary"]["has_objective"] is True


def test_valid_assembly_selected_part_problem():
    p = _problem(assembly_aware=True, selected_part_id="bracket")
    for v in p["variables"]:
        v["part_id"] = "bracket"
    d = validate_design_study_problem(p)
    assert d["status"] == "passed", d["errors"] + d["warnings"]
    assert d["summary"]["assembly_aware"] is True
    assert d["summary"]["selected_part_id"] == "bracket"


def test_problem_no_variables_fails():
    d = validate_design_study_problem({"format": "aieng.design_study_problem", "variables": []})
    assert d["status"] == "failed" and any("no variables" in e for e in d["errors"])


def test_problem_bad_bounds_and_type_fail():
    p = _problem()
    p["variables"][0]["min_value"] = 9.0  # min > max
    p["variables"][1]["type"] = "nonsense"
    d = validate_design_study_problem(p)
    assert d["status"] == "failed"
    assert any("min_value > max_value" in e for e in d["errors"])
    assert any("invalid type" in e for e in d["errors"])


def test_problem_non_dict_fails():
    assert validate_design_study_problem(None)["status"] == "failed"


# ── candidate validation ──────────────────────────────────────────────────────

def test_valid_candidate_passes_and_normalizes():
    rec = validate_design_candidate_patch(
        _problem(), _candidate([{"variable_id": "wall_t", "new_value": 4.5},
                                {"variable_id": "rib_count", "new_value": 4.0}]))
    assert rec["status"] == "valid", rec["errors"]
    assert rec["applied"] is False and rec["baseline_modified"] is False
    norm = {c["variable_id"]: c for c in rec["normalized_changes"]}
    assert norm["wall_t"]["new_value"] == 4.5 and norm["wall_t"]["old_value"] == 3.0
    # integer normalized from 4.0 -> 4
    assert norm["rib_count"]["new_value"] == 4 and isinstance(norm["rib_count"]["new_value"], int)


def test_protected_variable_rejected():
    rec = validate_design_candidate_patch(
        _problem(), _candidate([{"variable_id": "bolt_dia", "new_value": 8}]))
    assert rec["status"] == "rejected"
    assert any("protected" in e for e in rec["errors"])


def test_out_of_bounds_rejected():
    rec = validate_design_candidate_patch(
        _problem(), _candidate([{"variable_id": "wall_t", "new_value": 99.0}]))
    assert rec["status"] == "rejected"
    assert any("out of bounds" in e for e in rec["errors"])


def test_unknown_variable_rejected():
    rec = validate_design_candidate_patch(
        _problem(), _candidate([{"variable_id": "ghost", "new_value": 1.0}]))
    assert rec["status"] == "rejected"
    assert any("unknown variable" in e for e in rec["errors"])


def test_too_many_variables_rejected():
    rec = validate_design_candidate_patch(
        _problem(), _candidate([{"variable_id": "wall_t", "new_value": 4.0},
                                {"variable_id": "rib_count", "new_value": 3},
                                {"variable_id": "wall_t", "new_value": 5.0}]))  # 3 > max 2
    assert rec["status"] == "rejected"
    assert any("too many variables" in e for e in rec["errors"])


def test_missing_reasoning_rejected_when_required():
    rec = validate_design_candidate_patch(
        _problem(), _candidate([{"variable_id": "wall_t", "new_value": 4.0}], reasoning=""))
    assert rec["status"] == "rejected"
    assert any("reasoning is missing" in e for e in rec["errors"])


def test_missing_reasoning_warns_when_not_required():
    p = _problem()
    p["settings"]["require_reasoning"] = False
    rec = validate_design_candidate_patch(
        p, _candidate([{"variable_id": "wall_t", "new_value": 4.0}], reasoning=""))
    assert rec["status"] == "valid_with_warnings"
    assert any("reasoning is missing" in w for w in rec["warnings"])


def test_discrete_invalid_value_rejected():
    p = _problem()
    p["variables"][2]["safe_to_modify"] = True
    p["variables"][2]["semantic_role"] = "fastener_size"  # un-protect it
    rec = validate_design_candidate_patch(
        p, _candidate([{"variable_id": "bolt_dia", "new_value": 7}]))  # 7 not in allowed
    assert rec["status"] == "rejected"
    assert any("not in allowed_values" in e for e in rec["errors"])


def test_unsafe_variable_rejected():
    p = _problem()
    p["variables"][0]["safe_to_modify"] = False
    rec = validate_design_candidate_patch(
        p, _candidate([{"variable_id": "wall_t", "new_value": 4.0}]))
    assert rec["status"] == "rejected"
    assert any("not safe_to_modify" in e for e in rec["errors"])


def test_assembly_scope_violation_rejected():
    p = _problem(assembly_aware=True, selected_part_id="bracket")
    p["variables"][0]["part_id"] = "bracket"
    p["variables"][0]["safe_to_modify"] = True
    p["variables"][1]["part_id"] = "lid"   # different part
    p["variables"][1]["safe_to_modify"] = True
    rec = validate_design_candidate_patch(
        p, _candidate([{"variable_id": "rib_count", "new_value": 3}], selected_part_id="bracket"))
    assert rec["status"] == "rejected"
    assert any("outside selected_part_id" in e for e in rec["errors"])


# ── package integration ──────────────────────────────────────────────────────

def _write_pkg(tmp_path: Path, *, problem=None, candidates=None) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", json.dumps({"representation": "brep_build123d"}))
        if problem is not None:
            zf.writestr("analysis/design_study_problem.json", json.dumps(problem))
        for cand in candidates or []:
            zf.writestr(f"patches/design_candidates/{cand['candidate_id']}.json", json.dumps(cand))
    return pkg


def test_package_without_problem_unaffected(tmp_path: Path):
    pkg = _write_pkg(tmp_path)
    before = set(zipfile.ZipFile(pkg).namelist())
    result = process_design_study_package(pkg)
    after = set(zipfile.ZipFile(pkg).namelist())
    assert result["design_study_present"] is False and before == after


def test_package_validates_problem_and_candidates(tmp_path: Path):
    good = _candidate([{"variable_id": "wall_t", "new_value": 4.0}])
    bad = {"format": "aieng.design_candidate_patch", "candidate_id": "cand_bad",
           "reasoning": "x", "variable_changes": [{"variable_id": "bolt_dia", "new_value": 8}]}
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[good, bad])
    result = process_design_study_package(pkg)
    assert result["design_study_present"] is True and result["problem_status"] == "passed"
    assert result["candidate_count"] == 2
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert DESIGN_STUDY_PROBLEM_DIAGNOSTICS_PATH in names
        assert DESIGN_STUDY_CANDIDATE_VALIDATION_PATH in names
        # baseline geometry untouched
        assert json.loads(zf.read("geometry/shape_ir.json"))["representation"] == "brep_build123d"
        diag = json.loads(zf.read(DESIGN_STUDY_CANDIDATE_VALIDATION_PATH))
        by_id = {c["candidate_id"]: c for c in diag["candidates"]}
        assert by_id["cand_001"]["status"] == "valid"
        assert by_id["cand_bad"]["status"] == "rejected"
        assert all(c["applied"] is False for c in diag["candidates"])
        assert diag["provenance"]["optimization_executed"] is False


def test_validate_signals_sampling_when_no_candidates_exist(tmp_path: Path) -> None:
    """When safe-to-modify variables exist but no candidates, the validation
    output should flag sampling_available and suggest the sampler tool."""
    from aieng.converters.optimization_sampler import sample_candidates_package

    problem = _problem()
    variables_doc = {
        "format": "aieng.optimization_variables", "schema_version": "0.2",
        "study_id": "test", "design_study_problem_ref": "analysis/design_study_problem.json",
        "variables": [
            {"id": "wall_t", "path": "shape_ir/params/WALL_THICKNESS", "type": "continuous",
             "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "allowed_values": None,
             "unit": "mm", "scope": "local", "safe_to_modify": True,
             "featureId": "feat_wall", "parameterName": "thickness", "cad_parameter_name": "WALL_THICKNESS",
             "binding_status": "bound", "candidate_ids": []},
        ],
        "candidate_ids": [],
        "provenance": {"created_at": "2026-06-10T00:00:00Z", "created_by": "test",
                       "claim_advancement": "none"},
        "claim_policy": {"advisory_only": True, "baseline_unchanged": True,
                         "human_approval_required_for_acceptance": True, "claim_advancement": "none"},
    }
    # Ensure no candidates directory contents
    pkg = tmp_path / "no_candidates.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "No Candidates"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({}))
        zf.writestr("analysis/design_study_problem.json", json.dumps(problem))
        zf.writestr("analysis/optimization_variables.json", json.dumps(variables_doc))
        # No patches/design_candidates/

    result = process_design_study_package(pkg)
    assert result["design_study_present"] is True
    assert result["candidate_count"] == 0
    assert result.get("sampling_available") is True
    assert "sampling_suggestion" in result
    assert "opt.propose_candidates" in result["sampling_suggestion"]

    # Now sample, then validate again — sampling_available should be gone
    sampler_result = sample_candidates_package(pkg, algorithm="random", count=3, seed=42)
    assert sampler_result["status"] == "ok"
    assert sampler_result["candidate_count"] == 3

    result2 = process_design_study_package(pkg)
    assert result2["candidate_count"] == 3
    assert result2.get("sampling_available") is not True  # no longer suggests sampling
