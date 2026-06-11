"""Tests for batch evaluation of executed design-study candidates (#40).

Reuses the existing single-candidate evaluator per candidate. Missing CAE
metrics are recorded honestly (unknown / insufficient_data), never fabricated.
The baseline is never modified.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.design_study_batch import (
    discover_executed_candidate_ids,
    run_design_study_evaluation_batch,
)

_BASELINE_SHAPE_IR = {
    "representation": "brep_build123d",
    "parts": [{"id": "blk", "type": "box", "params": {"WALL_THICKNESS": 3.0}}],
}


def _problem(**ov):
    p = {
        "format": "aieng.design_study_problem", "schema_version": "0.1",
        "variables": [
            {"id": "wall_t", "path": "parts/0/params/WALL_THICKNESS", "type": "continuous",
             "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "unit": "mm",
             "safe_to_modify": True, "semantic_role": "wall_thickness"},
        ],
        "constraints": [
            {"id": "stress_limit", "type": "max_stress", "limit": 200.0, "unit": "MPa"},
        ],
        "objective": {"metric": "mass", "sense": "minimize"},
        "settings": {"max_variables_per_candidate": 1, "require_reasoning": True},
    }
    p.update(ov)
    return p


def _write_pkg(tmp_path: Path, *, problem=None, workspaces=(), baseline=_BASELINE_SHAPE_IR) -> Path:
    """workspaces: iterable of (cid, static_metrics_dict | None)."""
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Study"}))
        if baseline is not None:
            zf.writestr("geometry/shape_ir.json", json.dumps(baseline))
        if problem is not None:
            zf.writestr("analysis/design_study_problem.json", json.dumps(problem))
        for cid, metrics in workspaces:
            # a derived workspace must at least carry patch.json (marks "executed")
            zf.writestr(f"candidates/{cid}/patch.json", json.dumps({"candidate_id": cid}))
            zf.writestr(f"candidates/{cid}/geometry/shape_ir.json", json.dumps(baseline))
            if metrics is not None:
                zf.writestr(f"candidates/{cid}/analysis/static_metrics.json", json.dumps(metrics))
    return pkg


def _baseline_unchanged(pkg) -> bool:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read("geometry/shape_ir.json")) == _BASELINE_SHAPE_IR


# ── discovery ────────────────────────────────────────────────────────────────

def test_discover_executed_only_finds_workspaces(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(),
                     workspaces=[("cand_a", {"mass_kg": 1.0}), ("cand_b", None)])
    assert sorted(discover_executed_candidate_ids(pkg)) == ["cand_a", "cand_b"]


def test_discover_executed_empty_without_workspaces(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem())
    assert discover_executed_candidate_ids(pkg) == []


# ── batch evaluation: with metrics (the "CAE-backed" path) ───────────────────

def test_batch_eval_complete_with_metrics(tmp_path: Path):
    pkg = _write_pkg(
        tmp_path, problem=_problem(),
        workspaces=[("cand_ok", {"mass_kg": 1.2, "max_stress": 150.0})],
    )
    res = run_design_study_evaluation_batch(pkg)
    assert res["status"] == "ok"
    assert res["evaluated"] == 1
    assert res["complete"] == 1
    assert res["feasibility"].get("feasible") == 1
    assert res["baseline_modified"] is False
    # evaluation artifact written into the candidate workspace
    with zipfile.ZipFile(pkg) as zf:
        ev = json.loads(zf.read("candidates/cand_ok/analysis/evaluation.json"))
    assert ev["metrics"]["max_stress"] == 150.0
    assert _baseline_unchanged(pkg)


def test_batch_eval_marks_violation_infeasible(tmp_path: Path):
    pkg = _write_pkg(
        tmp_path, problem=_problem(),
        workspaces=[("cand_hi", {"mass_kg": 1.0, "max_stress": 250.0})],  # > 200 limit
    )
    res = run_design_study_evaluation_batch(pkg)
    assert res["complete"] == 1
    assert res["feasibility"].get("infeasible") == 1


# ── honest missing-metric handling (the #40 core requirement) ────────────────



def test_batch_eval_marks_critique_violation_infeasible(tmp_path: Path):
    """A thin wall in candidate geometry yields constraint_violation reason code."""
    pkg = _write_pkg(
        tmp_path, problem=_problem(),
        workspaces=[("cand_thin", {"mass_kg": 1.0, "max_stress": 150.0})],
    )
    # Inject candidate geometry maps so critique can run.
    import zipfile as _zf
    with _zf.ZipFile(pkg, "a") as zf:
        zf.writestr(
            "candidates/cand_thin/geometry/topology_map.json",
            json.dumps({"entities": [{"id": "b1", "type": "solid", "name": "base_plate",
                                       "bounding_box": [0, 0, 0, 100, 80, 1.5]}]}),
        )
        zf.writestr(
            "candidates/cand_thin/graph/feature_graph.json",
            json.dumps({"features": [{"id": "f1", "type": "named_part", "name": "base_plate",
                                      "geometry_refs": {"body": "b1"}}]}),
        )

    res = run_design_study_evaluation_batch(pkg)
    assert res["evaluated"] == 1
    assert res["feasibility"].get("infeasible") == 1
    by_id = {r["candidate_id"]: r for r in res["results"]}
    assert "constraint_violation" in by_id["cand_thin"]["reason_codes"]
    ev = json.loads(_zf.ZipFile(pkg).read("candidates/cand_thin/analysis/evaluation.json"))
    assert ev["critique_blocking"] is True
    assert any(c["rule"] == "min_wall_thickness" for c in ev["constraint_evidence"] if c["status"] == "violated")

def test_batch_eval_missing_cae_metric_is_unknown_not_fabricated(tmp_path: Path):
    # mass present but the stress constraint's metric is absent -> partial + unknown
    pkg = _write_pkg(
        tmp_path, problem=_problem(),
        workspaces=[("cand_partial", {"mass_kg": 1.0})],
    )
    res = run_design_study_evaluation_batch(pkg)
    assert res["evaluated"] == 1
    assert res["partial"] == 1
    assert res["feasibility"].get("unknown") == 1
    by_id = {r["candidate_id"]: r for r in res["results"]}
    assert "missing_metric" in by_id["cand_partial"]["reason_codes"]
    # constraint recorded as unknown, NOT a fabricated pass/fail
    with zipfile.ZipFile(pkg) as zf:
        ev = json.loads(zf.read("candidates/cand_partial/analysis/evaluation.json"))
    stress = [c for c in ev["constraint_evidence"] if c.get("type") == "max_stress"][0]
    assert stress["status"] == "unknown"
    assert "max_stress" not in ev["metrics"]
    assert res["warnings"]  # surfaces the honest-incompleteness warning


def test_batch_eval_no_metrics_is_insufficient_data(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), workspaces=[("cand_empty", None)])
    res = run_design_study_evaluation_batch(pkg)
    assert res["insufficient_data"] == 1
    assert res["feasibility"].get("unknown") == 1


# ── batch mechanics: subset, cap, continue-past-failure ──────────────────────

def test_batch_eval_explicit_subset(tmp_path: Path):
    pkg = _write_pkg(
        tmp_path, problem=_problem(),
        workspaces=[("c0", {"mass_kg": 1.0}), ("c1", {"mass_kg": 2.0}), ("c2", {"mass_kg": 3.0})],
    )
    res = run_design_study_evaluation_batch(pkg, candidate_ids=["c0", "c2"])
    assert res["evaluated"] == 2
    assert {r["candidate_id"] for r in res["results"]} == {"c0", "c2"}


def test_batch_eval_caps_and_reports_skipped(tmp_path: Path):
    ws = [(f"c{i}", {"mass_kg": float(i)}) for i in range(4)]
    pkg = _write_pkg(tmp_path, problem=_problem(), workspaces=ws)
    res = run_design_study_evaluation_batch(pkg, candidate_ids=[f"c{i}" for i in range(4)],
                                            max_candidates=2)
    assert res["evaluated"] == 2
    assert res["skipped"] == 2
    assert res["warnings"]


def test_batch_eval_continues_past_a_failed_candidate(tmp_path: Path):
    pkg = _write_pkg(
        tmp_path, problem=_problem(),
        workspaces=[("good", {"mass_kg": 1.0}), ("boom", {"mass_kg": 2.0})],
    )

    def _flaky_eval(package_path, cid):
        if cid == "boom":
            raise RuntimeError("evaluator blew up")
        from aieng.converters.design_study_evaluation import evaluate_design_study_candidate
        return evaluate_design_study_candidate(package_path, cid)

    res = run_design_study_evaluation_batch(pkg, evaluator=_flaky_eval)
    assert res["evaluated"] == 2
    assert res["failed"] == 1
    by_id = {r["candidate_id"]: r for r in res["results"]}
    assert by_id["boom"]["status"] == "failed"
    assert "candidate_evaluation_failed" in by_id["boom"]["reason_codes"]
    assert _baseline_unchanged(pkg)


# ── CAE path: cae=true runs the CAE step first (injected) ────────────────────

def test_batch_eval_cae_runs_cae_step_first(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), workspaces=[("cand_ok", {"mass_kg": 1.0})])
    calls: list[str] = []

    def _fake_cae(package_path, cid, **kw):
        calls.append(cid)
        return {"status": "ok", "candidate_id": cid, "solver_status": "skipped"}

    res = run_design_study_evaluation_batch(pkg, cae=True, cae_evaluator=_fake_cae)
    assert res["status"] == "ok"
    assert calls == ["cand_ok"]
    by_id = {r["candidate_id"]: r for r in res["results"]}
    assert by_id["cand_ok"]["cae_status"] == "ok"


# ── input guards / errors ────────────────────────────────────────────────────

def test_batch_eval_empty_when_no_executed_candidates(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem())
    res = run_design_study_evaluation_batch(pkg)
    assert res["status"] == "ok"
    assert res["evaluated"] == 0
    assert res["warnings"]


def test_batch_eval_rejects_non_list_candidate_ids(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), workspaces=[("c0", {"mass_kg": 1.0})])
    res = run_design_study_evaluation_batch(pkg, candidate_ids="c0")  # type: ignore[arg-type]
    assert res["status"] == "error"
    assert res["code"] == "invalid_candidate_ids"


def test_batch_eval_rejects_negative_max(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), workspaces=[("c0", {"mass_kg": 1.0})])
    res = run_design_study_evaluation_batch(pkg, max_candidates=-1)
    assert res["status"] == "error"
    assert res["code"] == "invalid_max_candidates"


def test_batch_eval_missing_package_errors(tmp_path: Path):
    res = run_design_study_evaluation_batch(tmp_path / "nope.aieng")
    assert res["status"] == "error"
    assert res["code"] == "package_not_found"
    assert res["baseline_modified"] is False
