"""Tests for batch execution of sampled design-study candidates (#39).

Each candidate runs into its OWN derived workspace; the baseline is never
overwritten; a failed candidate is recorded cleanly and the batch continues.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.design_study_batch import (
    discover_candidate_ids,
    run_design_study_batch,
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


def _names(pkg) -> set[str]:
    with zipfile.ZipFile(pkg) as zf:
        return set(zf.namelist())


def _baseline_unchanged(pkg) -> bool:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read("geometry/shape_ir.json")) == _BASELINE_SHAPE_IR


# ── discovery ────────────────────────────────────────────────────────────────

def test_discover_prefers_listed_then_appends_on_disk(tmp_path: Path):
    study = {"format": "aieng.optimization_study", "candidate_ids": ["c2", "c1"]}
    pkg = _write_pkg(
        tmp_path,
        problem=_problem(),
        candidates=[_candidate("c1", [{"variable_id": "wall_t", "new_value": 4.0}]),
                    _candidate("c2", [{"variable_id": "wall_t", "new_value": 5.0}]),
                    _candidate("c3", [{"variable_id": "wall_t", "new_value": 6.0}])],
        extra_members={"analysis/optimization_study.json": json.dumps(study)},
    )
    ids = discover_candidate_ids(pkg)
    # listed order first (c2, c1), then on-disk extras sorted (c3)
    assert ids == ["c2", "c1", "c3"]


def test_discover_empty_when_no_candidates(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem())
    assert discover_candidate_ids(pkg) == []


# ── batch execution ──────────────────────────────────────────────────────────

def test_batch_runs_all_discovered_into_isolated_workspaces(tmp_path: Path):
    cands = [_candidate(f"cand_{i}", [{"variable_id": "wall_t", "new_value": 3.0 + i}])
             for i in range(3)]
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=cands)

    res = run_design_study_batch(pkg)  # no recompiler -> patch_applied
    assert res["status"] == "ok"
    assert res["requested"] == 3
    assert res["executed"] == 3
    assert res["succeeded"] == 3
    assert res["failed"] == 0
    assert res["baseline_modified"] is False
    assert res["claim_advancement"] == "none"

    names = _names(pkg)
    for i in range(3):
        assert f"candidates/cand_{i}/patch.json" in names
        assert f"candidates/cand_{i}/geometry/shape_ir.json" in names
        assert f"candidates/cand_{i}/analysis/evaluation.json" in names
    assert _baseline_unchanged(pkg)


def test_batch_runs_explicit_subset_only(tmp_path: Path):
    cands = [_candidate(f"cand_{i}", [{"variable_id": "wall_t", "new_value": 3.0 + i}])
             for i in range(3)]
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=cands)

    res = run_design_study_batch(pkg, candidate_ids=["cand_0", "cand_2"])
    assert res["executed"] == 2
    assert {r["candidate_id"] for r in res["results"]} == {"cand_0", "cand_2"}
    names = _names(pkg)
    assert "candidates/cand_1/patch.json" not in names


def test_batch_continues_past_a_failed_candidate(tmp_path: Path):
    # cand_bad references an unknown variable -> validation rejects it; the batch
    # must still run cand_good and report the failure cleanly.
    good = _candidate("cand_good", [{"variable_id": "wall_t", "new_value": 4.0}])
    bad = _candidate("cand_bad", [{"variable_id": "no_such_var", "new_value": 9.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[bad, good])

    res = run_design_study_batch(pkg)
    assert res["status"] == "ok"
    assert res["executed"] == 2
    # rejected (validation) is tracked separately from build failure
    assert res["succeeded"] == 1
    assert res["rejected"] == 1
    by_id = {r["candidate_id"]: r for r in res["results"]}
    assert by_id["cand_good"]["execution_status"] == "patch_applied"
    assert by_id["cand_bad"]["execution_status"] == "rejected"
    assert "constraint_violation" in by_id["cand_bad"]["reason_codes"]
    assert _baseline_unchanged(pkg)


def test_batch_records_compile_failure_as_build_failed(tmp_path: Path):
    cands = [_candidate("cand_ok", [{"variable_id": "wall_t", "new_value": 4.0}]),
             _candidate("cand_x", [{"variable_id": "wall_t", "new_value": 5.0}])]
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=cands)

    def _recompiler(shape_ir, ctx):
        if ctx["candidate_id"] == "cand_x":
            return {"compile_status": "compile_failed", "errors": ["boom"]}
        return {"compile_status": "compile_succeeded", "metrics": {"mass": 12.3}}

    res = run_design_study_batch(pkg, recompiler=_recompiler)
    assert res["executed"] == 2
    assert res["succeeded"] == 1
    assert res["failed"] == 1
    by_id = {r["candidate_id"]: r for r in res["results"]}
    assert by_id["cand_x"]["execution_status"] == "compile_failed"
    assert "candidate_build_failed" in by_id["cand_x"]["reason_codes"]
    assert _baseline_unchanged(pkg)


def test_batch_caps_and_reports_skipped(tmp_path: Path):
    cands = [_candidate(f"cand_{i}", [{"variable_id": "wall_t", "new_value": 3.0 + i}])
             for i in range(4)]
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=cands)

    res = run_design_study_batch(pkg, candidate_ids=[f"cand_{i}" for i in range(4)],
                                 max_candidates=2)
    assert res["executed"] == 2
    assert res["skipped"] == 2
    assert len(res["skipped_candidate_ids"]) == 2
    assert res["warnings"]


def test_batch_empty_when_no_candidates(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem())
    res = run_design_study_batch(pkg)
    assert res["status"] == "ok"
    assert res["executed"] == 0
    assert res["warnings"]


def test_batch_missing_package_errors(tmp_path: Path):
    res = run_design_study_batch(tmp_path / "nope.aieng")
    assert res["status"] == "error"
    assert res["code"] == "package_not_found"
    assert res["baseline_modified"] is False


def test_batch_rejects_non_list_candidate_ids(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem())
    res = run_design_study_batch(pkg, candidate_ids="cand_0")  # type: ignore[arg-type]
    assert res["status"] == "error"
    assert res["code"] == "invalid_candidate_ids"
    assert res["baseline_modified"] is False


def test_batch_rejects_negative_max_candidates(tmp_path: Path):
    cand = _candidate("cand_0", [{"variable_id": "wall_t", "new_value": 4.0}])
    pkg = _write_pkg(tmp_path, problem=_problem(), candidates=[cand])
    res = run_design_study_batch(pkg, max_candidates=-1)
    assert res["status"] == "error"
    assert res["code"] == "invalid_max_candidates"
    assert res["baseline_modified"] is False
    # nothing should have been executed
    assert "candidates/cand_0/patch.json" not in _names(pkg)


def test_batch_corrupt_package_errors_cleanly(tmp_path: Path):
    pkg = tmp_path / "corrupt.aieng"
    pkg.write_bytes(b"this is not a zip archive")
    res = run_design_study_batch(pkg)
    assert res["status"] == "ok"  # discovery yields no ids from an unreadable zip
    assert res["executed"] == 0
    assert res["baseline_modified"] is False
