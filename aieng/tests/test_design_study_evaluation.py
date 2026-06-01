"""Tests for design-study candidate evaluation from solver-neutral evidence."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.design_study_evaluation import evaluate_design_study_candidate
from aieng.converters.design_study_ranking import (
    DESIGN_STUDY_CANDIDATE_RANKING_PATH,
    rank_design_study_candidates,
)
from aieng.converters.design_study_execution import DESIGN_STUDY_ITERATIONS_PATH


def _problem(**overrides):
    p = {
        "format": "aieng.design_study_problem",
        "schema_version": "0.1",
        "id": "study_eval",
        "objective": {"sense": "minimize", "metric": "mass"},
        "baseline_metrics": {"mass_kg": 2.0},
        "constraints": [
            {"id": "c_stress", "type": "max_stress", "limit": 200.0, "unit": "MPa"},
            {"id": "c_defl", "type": "max_deflection", "limit": 5.0, "unit": "mm"},
            {"id": "c_sf", "type": "min_safety_factor", "limit": 1.5},
            {"id": "c_mfg", "type": "manufacturability", "hint": "keep printable"},
        ],
    }
    p.update(overrides)
    return p


def _iterations(cids):
    return {
        "format": "aieng.design_study_iterations",
        "format_version": "0.1.0",
        "schema_version": "0.1",
        "iterations": [
            {
                "iteration_id": f"iter_{i:03d}",
                "candidate_id": cid,
                "execution_status": "patch_applied",
                "validation_status": "valid",
                "metrics": {},
                "baseline_modified": False,
                "candidate_workspace": f"candidates/{cid}/",
            }
            for i, cid in enumerate(cids, start=1)
        ],
    }


def _write_pkg(tmp_path: Path, *, members: dict[str, object], problem=None, iterations=None) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Study"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"representation": "brep_build123d"}))
        zf.writestr("analysis/design_study_problem.json", json.dumps(problem or _problem()))
        if iterations is not None:
            zf.writestr(DESIGN_STUDY_ITERATIONS_PATH, json.dumps(iterations))
        for name, data in members.items():
            if isinstance(data, (dict, list)):
                data = json.dumps(data)
            zf.writestr(name, data)
    return pkg


def _read(pkg: Path, name: str):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


def test_evaluate_candidate_normalizes_worst_case_neutral_metrics(tmp_path: Path):
    computed = {
        "format": "aieng.cae.computed_metrics",
        "load_cases": [
            {
                "id": "lc_low",
                "results": [
                    {"result_type": "stress", "metric": "max_von_mises_stress", "max": 150.0, "unit": "MPa"},
                    {"result_type": "displacement", "metric": "max_displacement", "max": 2.0, "unit": "mm"},
                    {"result_type": "safety", "metric": "minimum_safety_factor", "min": 2.1},
                ],
            },
            {
                "id": "lc_worst",
                "results": [
                    {"result_type": "stress", "metric": "max_von_mises_stress", "max": 190.0, "unit": "MPa"},
                    {"result_type": "displacement", "metric": "max_displacement", "max": 4.0, "unit": "mm"},
                    {"result_type": "safety", "metric": "minimum_safety_factor", "min": 1.6},
                ],
            },
        ],
    }
    static = {"mass_kg": 1.6, "volume_mm3": 900.0, "interfaces_preserved": True}
    pkg = _write_pkg(tmp_path, members={
        "candidates/c1/patch.json": {"candidate_id": "c1"},
        "candidates/c1/analysis/computed_metrics.json": computed,
        "candidates/c1/analysis/static_metrics.json": static,
    })

    res = evaluate_design_study_candidate(pkg, "c1")
    assert res["status"] == "ok"
    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    assert ev["metrics"]["max_stress"] == 190.0
    assert ev["normalized_metrics"]["max_stress"]["load_case_id"] == "lc_worst"
    assert ev["normalized_metrics"]["max_stress"]["unit"] == "MPa"
    assert ev["metrics"]["min_safety_factor"] == 1.6
    assert ev["metrics"]["mass_kg"] == 1.6
    assert ev["feasibility"] == "feasible"
    assert any(c["status"] == "warning_only" for c in ev["constraint_evidence"])
    report = _read(pkg, "candidates/c1/diagnostics/evaluation_report.json")
    assert report["constraint_summary"]["violated"] == 0


def test_evaluate_candidate_marks_violations_and_proxy_confidence(tmp_path: Path):
    assembly = {
        "format": "aieng.cae.computed_metrics",
        "load_cases": [
            {"id": "assembly_lc", "results": [
                {"result_type": "stress", "metric": "max_von_mises_stress", "max": 260.0, "unit": "MPa"},
                {"result_type": "displacement", "metric": "max_displacement", "max": 6.5, "unit": "mm"},
            ]}
        ],
    }
    pkg = _write_pkg(tmp_path, members={
        "candidates/c_proxy/patch.json": {"candidate_id": "c_proxy"},
        "candidates/c_proxy/analysis/assembly_computed_metrics.json": assembly,
    })

    evaluate_design_study_candidate(pkg, "c_proxy")
    ev = _read(pkg, "candidates/c_proxy/analysis/evaluation.json")
    assert ev["feasibility"] == "infeasible"
    assert ev["confidence"] == "medium"
    assert ev["honesty"]["proxy_derived"] is True
    assert ev["honesty"]["contact_physics_modeled"] is False
    assert {c["id"] for c in ev["constraint_evidence"] if c["status"] == "violated"} == {"c_stress", "c_defl"}


def test_ranking_builds_candidate_evaluation_from_existing_static_metrics(tmp_path: Path):
    pkg = _write_pkg(
        tmp_path,
        iterations=_iterations(["c_good"]),
        members={
            "candidates/c_good/patch.json": {"candidate_id": "c_good"},
            "candidates/c_good/analysis/static_metrics.json": {
                "mass_kg": 1.5,
                "max_stress": 100.0,
                "max_deflection": 1.0,
                "min_safety_factor": 2.0,
            },
        },
    )

    res = rank_design_study_candidates(pkg)
    assert res["status"] == "ok"
    assert "candidates/c_good/analysis/evaluation.json" in res["artifacts"]
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    cand = ranking["candidates"][0]
    assert cand["candidate_id"] == "c_good"
    assert cand["feasibility"] == "feasible"
    assert cand["score"] > 0
