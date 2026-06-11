"""Tests for design study candidate EXECUTION into a derived workspace (PR2).

Baseline geometry is NEVER overwritten. No optimizer/loop. Compile/evaluation is injected
and may be honestly partial. No candidate is auto-accepted into the baseline.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.design_study_execution import (
    DESIGN_STUDY_ITERATIONS_PATH,
    DESIGN_STUDY_REPORT_PATH,
    execute_design_study_candidate,
)

_BASELINE_SHAPE_IR = {
    "representation": "brep_build123d",
    "parts": [{"id": "blk", "type": "box",
               "params": {"WALL_THICKNESS": 3.0, "HEIGHT": 20.0}}],
}


def _problem(**ov):
    p = {
        "format": "aieng.design_study_problem", "schema_version": "0.1",
        "variables": [
            {"id": "wall_t", "path": "parts/0/params/WALL_THICKNESS", "type": "continuous",
             "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "unit": "mm",
             "safe_to_modify": True, "semantic_role": "wall_thickness"},
            {"id": "bolt_dia", "path": "parts/0/params/BOLT_DIA", "type": "discrete",
             "current_value": 6, "allowed_values": [4, 6, 8], "unit": "mm",
             "safe_to_modify": False, "semantic_role": "bolt_hole"},   # protected
            {"id": "ghost", "path": "parts/0/params/DOES_NOT_EXIST", "type": "continuous",
             "current_value": 1.0, "min_value": 0.0, "max_value": 5.0, "unit": "mm",
             "safe_to_modify": True, "semantic_role": "misc"},
        ],
        "settings": {"max_variables_per_candidate": 2, "require_reasoning": True},
    }
    p.update(ov)
    return p


def _candidate(cid, changes, reasoning="cut mass", **extra):
    return {"format": "aieng.design_candidate_patch", "candidate_id": cid,
            "reasoning": reasoning, "variable_changes": changes, **extra}


def _write_pkg(tmp_path: Path, *, problem=None, candidates=(), baseline=_BASELINE_SHAPE_IR,
               extra_members=None) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Study"}))
        if baseline is not None:
            zf.writestr("geometry/shape_ir.json", json.dumps(baseline))
        if problem is not None:
            zf.writestr("analysis/design_study_problem.json", json.dumps(problem))
        for cand in candidates:
            zf.writestr(f"patches/design_candidates/{cand['candidate_id']}.json", json.dumps(cand))
        for name, data in (extra_members or {}).items():
            zf.writestr(name, data)
    return pkg


def _read(pkg, name):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


def _baseline_unchanged(pkg):
    return _read(pkg, "geometry/shape_ir.json") == _BASELINE_SHAPE_IR


# ── valid candidate -> derived workspace ─────────────────────────────────────

def test_valid_candidate_creates_workspace_and_applies_change(tmp_path: Path):
    cand = _candidate("cand_ok", [{"variable_id": "wall_t", "new_value": 4.5}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])
    res = execute_design_study_candidate(pkg, "cand_ok")
    assert res["status"] == "ok"
    assert res["execution_status"] == "patch_applied"   # no recompiler -> stops at applied
    assert res["recommendation"] == "needs_more_evaluation"
    assert res["baseline_modified"] is False
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert "candidates/cand_ok/patch.json" in names
        assert "candidates/cand_ok/geometry/shape_ir.json" in names
        assert "candidates/cand_ok/provenance/candidate.json" in names
        assert "candidates/cand_ok/analysis/evaluation.json" in names
    # derived geometry has the new value; baseline does NOT
    derived = _read(pkg, "candidates/cand_ok/geometry/shape_ir.json")
    assert derived["parts"][0]["params"]["WALL_THICKNESS"] == 4.5
    assert _baseline_unchanged(pkg)


def test_patch_copied_into_workspace(tmp_path: Path):
    cand = _candidate("cand_ok", [{"variable_id": "wall_t", "new_value": 4.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])
    execute_design_study_candidate(pkg, "cand_ok")
    assert _read(pkg, "candidates/cand_ok/patch.json")["candidate_id"] == "cand_ok"
    prov = _read(pkg, "candidates/cand_ok/provenance/candidate.json")
    assert prov["based_on_problem"] == "analysis/design_study_problem.json"
    assert prov["baseline_modified"] is False
    assert prov["applied_changes"][0]["status"] == "applied"


def test_out_of_bounds_candidate_rejected_not_applied(tmp_path: Path):
    cand = _candidate("cand_oob", [{"variable_id": "wall_t", "new_value": 99.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])
    res = execute_design_study_candidate(pkg, "cand_oob")
    assert res["execution_status"] == "rejected" and res["recommendation"] == "reject_candidate"
    with zipfile.ZipFile(pkg) as zf:
        assert "candidates/cand_oob/geometry/shape_ir.json" not in zf.namelist()
    assert _baseline_unchanged(pkg)


def test_protected_variable_rejected_not_applied(tmp_path: Path):
    cand = _candidate("cand_prot", [{"variable_id": "bolt_dia", "new_value": 8}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])
    res = execute_design_study_candidate(pkg, "cand_prot")
    assert res["execution_status"] == "rejected"
    with zipfile.ZipFile(pkg) as zf:
        assert not any(n.startswith("candidates/cand_prot/geometry") for n in zf.namelist())
    assert _baseline_unchanged(pkg)


def test_unknown_shape_ir_path_fails_safely(tmp_path: Path):
    # 'ghost' is a valid, safe variable but its declared path is absent in the Shape IR
    cand = _candidate("cand_ghost", [{"variable_id": "ghost", "new_value": 2.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])
    res = execute_design_study_candidate(pkg, "cand_ghost")
    assert res["execution_status"] == "failed"
    assert res["recommendation"] == "request_user_input"
    with zipfile.ZipFile(pkg) as zf:
        assert "candidates/cand_ghost/geometry/shape_ir.json" not in zf.namelist()
    assert _baseline_unchanged(pkg)


# ── compile / evaluation via injected recompiler ─────────────────────────────

def test_no_recompiler_records_partial(tmp_path: Path):
    cand = _candidate("c", [{"variable_id": "wall_t", "new_value": 4.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])
    execute_design_study_candidate(pkg, "c")
    ev = _read(pkg, "candidates/c/analysis/evaluation.json")
    assert ev["evaluation_status"] == "partial" and ev["compile_status"] == "skipped"


def test_compile_success_records_manifest_and_verification(tmp_path: Path):
    cand = _candidate("c", [{"variable_id": "wall_t", "new_value": 4.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])
    seen = {}

    def fake_recompiler(shape_ir, ctx):
        seen["wt"] = shape_ir["parts"][0]["params"]["WALL_THICKNESS"]
        return {"compile_status": "compile_succeeded",
                "geometry_execution": {"executed": True, "geometry_kind": "brep"},
                "verification": {"geometry_kind": "brep", "status": "passed"},
                "metrics": {"executed": True, "volume_mm3": 1234.0}}

    res = execute_design_study_candidate(pkg, "c", recompiler=fake_recompiler)
    assert seen["wt"] == 4.0                      # recompiler saw the DERIVED value
    assert res["execution_status"] == "evaluation_complete"
    assert res["recommendation"] == "refine_candidate"   # never auto-accept in v0
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert "candidates/c/provenance/geometry_execution_manifest.json" in names
        assert "candidates/c/diagnostics/verification.json" in names
    assert _baseline_unchanged(pkg)


def test_compile_success_without_metrics_needs_more(tmp_path: Path):
    cand = _candidate("c", [{"variable_id": "wall_t", "new_value": 4.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])

    def fake(shape_ir, ctx):
        return {"compile_status": "compile_succeeded",
                "geometry_execution": {"executed": True}, "metrics": {}}

    res = execute_design_study_candidate(pkg, "c", recompiler=fake)
    assert res["execution_status"] == "compile_succeeded"
    assert res["recommendation"] == "needs_more_evaluation"


def test_compile_failure_records_and_baseline_safe(tmp_path: Path):
    cand = _candidate("c", [{"variable_id": "wall_t", "new_value": 4.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])

    def fake(shape_ir, ctx):
        return {"compile_status": "compile_failed", "errors": ["boom"]}

    res = execute_design_study_candidate(pkg, "c", recompiler=fake)
    assert res["execution_status"] == "compile_failed"
    assert res["recommendation"] == "compile_failed"
    ev = _read(pkg, "candidates/c/analysis/evaluation.json")
    assert ev["evaluation_status"] == "failed" and ev["errors"] == ["boom"]
    assert _baseline_unchanged(pkg)


def test_recompiler_exception_is_contained(tmp_path: Path):
    cand = _candidate("c", [{"variable_id": "wall_t", "new_value": 4.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])

    def boom(shape_ir, ctx):
        raise RuntimeError("kernel exploded")

    res = execute_design_study_candidate(pkg, "c", recompiler=boom)
    assert res["execution_status"] == "compile_failed"
    assert _baseline_unchanged(pkg)


def test_regression_diff_collateral_change_fails_candidate(tmp_path: Path):
    cand = _candidate("c", [{"variable_id": "wall_t", "new_value": 4.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])

    def fake(shape_ir, ctx):
        # make_candidate_recompiler would downgrade compile_status when it sees
        # collateral_change; emulate that contract here.
        return {
            "compile_status": "compile_failed",
            "geometry_execution": {"executed": True, "geometry_kind": "brep"},
            "metrics": {"executed": True, "volume_mm3": 1234.0},
            "errors": ["regression_diff flagged collateral_change on ['base_plate']"],
            "regression_diff": {
                "verdict": "collateral_change",
                "headline": "WARNING: unrelated part moved",
                "changed": [{"part": "base_plate", "expected": False}],
                "collateral_parts": ["base_plate"],
                "added": [], "removed": [], "unchanged_count": 0,
            },
        }

    res = execute_design_study_candidate(pkg, "c", recompiler=fake)
    assert res["execution_status"] == "compile_failed"
    assert res["recommendation"] == "compile_failed"
    ev = _read(pkg, "candidates/c/analysis/evaluation.json")
    assert ev["evaluation_status"] == "failed"
    assert ev["compile_status"] == "compile_failed"
    assert ev["regression_diff"]["verdict"] == "collateral_change"
    assert "collateral_change" in ev["errors"][0]
    assert _baseline_unchanged(pkg)


def test_regression_diff_clean_passes_candidate(tmp_path: Path):
    cand = _candidate("c", [{"variable_id": "wall_t", "new_value": 4.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])

    def fake(shape_ir, ctx):
        return {
            "compile_status": "compile_succeeded",
            "geometry_execution": {"executed": True, "geometry_kind": "brep"},
            "metrics": {"executed": True, "volume_mm3": 1234.0},
            "regression_diff": {
                "verdict": "clean",
                "headline": "1 part(s) changed as expected",
                "changed": [{"part": "base_plate", "expected": True}],
                "collateral_parts": [],
                "added": [], "removed": [], "unchanged_count": 1,
            },
        }

    res = execute_design_study_candidate(pkg, "c", recompiler=fake)
    assert res["execution_status"] == "evaluation_complete"
    ev = _read(pkg, "candidates/c/analysis/evaluation.json")
    assert ev["regression_diff"]["verdict"] == "clean"
    assert ev["compile_status"] == "compile_succeeded"
    assert _baseline_unchanged(pkg)


# ── iteration tracking + report ──────────────────────────────────────────────

def test_iterations_append_deterministically(tmp_path: Path):
    c1 = _candidate("c1", [{"variable_id": "wall_t", "new_value": 4.0}])
    c2 = _candidate("c2", [{"variable_id": "wall_t", "new_value": 5.0}])
    bad = _candidate("c3", [{"variable_id": "wall_t", "new_value": 99.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[c1, c2, bad])
    execute_design_study_candidate(pkg, "c1")
    execute_design_study_candidate(pkg, "c2")
    execute_design_study_candidate(pkg, "c3")
    iters = _read(pkg, DESIGN_STUDY_ITERATIONS_PATH)["iterations"]
    assert [i["iteration_id"] for i in iters] == ["iter_001", "iter_002", "iter_003"]
    assert [i["candidate_id"] for i in iters] == ["c1", "c2", "c3"]
    assert iters[2]["execution_status"] == "rejected"
    report = _read(pkg, DESIGN_STUDY_REPORT_PATH)
    assert report["iteration_count"] == 3
    assert report["by_execution_status"].get("rejected") == 1
    assert report["provenance"]["baseline_modified"] is False


def test_missing_candidate_records_request_input(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[])
    res = execute_design_study_candidate(pkg, "nope")
    assert res["execution_status"] == "failed" and res["recommendation"] == "request_user_input"
    assert _read(pkg, DESIGN_STUDY_REPORT_PATH)["iteration_count"] == 1


# ── part-scoped (assembly) candidate ─────────────────────────────────────────

def test_part_scoped_candidate_writes_only_selected_part_workspace(tmp_path: Path):
    part_ir = {"representation": "brep_build123d",
               "parts": [{"id": "bracket", "type": "box", "params": {"WALL_THICKNESS": 3.0}}]}
    problem = _problem(assembly_aware=True, selected_part_id="bracket")
    for v in problem["variables"]:
        v["part_id"] = "bracket"
    cand = _candidate("cand_part", [{"variable_id": "wall_t", "new_value": 4.0}],
                      selected_part_id="bracket")
    pkg = _write_pkg(tmp_path, problem=problem, candidates=[cand],
                     extra_members={"parts/bracket/geometry/shape_ir.json": json.dumps(part_ir)})
    res = execute_design_study_candidate(pkg, "cand_part")
    assert res["status"] == "ok" and res["execution_status"] == "patch_applied"
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert "candidates/cand_part/parts/bracket/geometry/shape_ir.json" in names
        assert "candidates/cand_part/geometry/shape_ir.json" not in names
        # baseline part Shape IR untouched
        assert json.loads(zf.read("parts/bracket/geometry/shape_ir.json")) == part_ir
    derived = _read(pkg, "candidates/cand_part/parts/bracket/geometry/shape_ir.json")
    assert derived["parts"][0]["params"]["WALL_THICKNESS"] == 4.0


# ── path-safety ──────────────────────────────────────────────────────────────

def test_candidate_id_sanitized(tmp_path: Path):
    # a path-traversal-y id sanitizes to "evil_id" (leading dots/slashes stripped)
    cand = _candidate("../evil id", [{"variable_id": "wall_t", "new_value": 4.0}])
    pkg = tmp_path / "s.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", json.dumps(_BASELINE_SHAPE_IR))
        zf.writestr("analysis/design_study_problem.json", json.dumps(_problem()))
        zf.writestr("patches/design_candidates/evil_id.json", json.dumps(cand))
    res = execute_design_study_candidate(pkg, "../evil id")
    assert res["candidate_workspace"] == "candidates/evil_id/"
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        # no path traversal, no absolute paths
        assert all(".." not in n and not n.startswith("/") for n in names)
        assert "candidates/evil_id/geometry/shape_ir.json" in names
