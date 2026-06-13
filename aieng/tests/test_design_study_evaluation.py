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


def _topology_map(body_id="b1", name="base_plate", bbox=None, extra_entities=None):
    entities = []
    if bbox is not None:
        entities.append({"id": body_id, "type": "solid", "name": name, "bounding_box": bbox})
    if extra_entities:
        entities.extend(extra_entities)
    return {"entities": entities}


def _feature_graph(*features):
    return {"features": list(features)}


def _named_part(name, body_id):
    return {"id": f"feat_{body_id}", "type": "named_part", "name": name,
            "geometry_refs": {"body": body_id}}


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



def test_evaluate_candidate_with_critique_violation_marks_infeasible(tmp_path: Path):
    """A thin wall in candidate geometry becomes a constraint_violation."""
    pkg = _write_pkg(tmp_path, members={
        "candidates/c_thin/patch.json": {"candidate_id": "c_thin"},
        "candidates/c_thin/analysis/evaluation.json": {
            "compile_status": "compile_succeeded",
            "metrics": {"mass_kg": 1.2},
        },
        "candidates/c_thin/analysis/static_metrics.json": {
            "mass_kg": 1.2,
            "max_stress": 80.0,
            "max_deflection": 1.0,
            "min_safety_factor": 2.0,
        },
        "candidates/c_thin/geometry/topology_map.json": _topology_map(
            "b1", "back_plate", [0, 0, 0, 100, 80, 1.5]
        ),
        "candidates/c_thin/graph/feature_graph.json": _feature_graph(
            _named_part("back_plate", "b1")
        ),
    })

    res = evaluate_design_study_candidate(pkg, "c_thin")
    assert res["status"] == "ok"
    assert res["feasibility"] == "infeasible"
    assert res["critique_blocking"] is True
    ev = _read(pkg, "candidates/c_thin/analysis/evaluation.json")
    assert ev["feasibility"] == "infeasible"
    assert ev["critique_blocking"] is True
    assert ev["critique"]["verdict"] == "fails_audit"
    violated = [c for c in ev["constraint_evidence"] if c["status"] == "violated"]
    assert any(c["rule"] == "min_wall_thickness" for c in violated)
    report = _read(pkg, "candidates/c_thin/diagnostics/evaluation_report.json")
    assert report["critique"]["blocking"] is True
    assert report["constraint_summary"]["violated"] >= 1


def test_evaluate_candidate_clean_geometry_unaffected(tmp_path: Path):
    """A candidate that passes critique stays feasible."""
    pkg = _write_pkg(tmp_path, members={
        "candidates/c_clean/patch.json": {"candidate_id": "c_clean"},
        "candidates/c_clean/analysis/evaluation.json": {
            "compile_status": "compile_succeeded",
            "metrics": {"mass_kg": 1.5},
        },
        "candidates/c_clean/analysis/static_metrics.json": {
            "mass_kg": 1.5,
            "max_stress": 80.0,
            "max_deflection": 1.0,
            "min_safety_factor": 2.0,
        },
        "candidates/c_clean/geometry/topology_map.json": _topology_map(
            "b1", "base_plate", [0, 0, 0, 100, 80, 5.0]
        ),
        "candidates/c_clean/graph/feature_graph.json": _feature_graph(
            _named_part("base_plate", "b1"),
            {"id": "mh1", "type": "mounting_hole", "name": "hole_1",
             "parameters": {"hole_diameter_mm": 6.0}, "geometry_refs": {"body": "b1"}},
        ),
    })

    res = evaluate_design_study_candidate(pkg, "c_clean")
    assert res["status"] == "ok"
    assert res["feasibility"] == "feasible"
    assert res["critique_blocking"] is False
    ev = _read(pkg, "candidates/c_clean/analysis/evaluation.json")
    assert ev["critique"]["verdict"] == "passes"


def test_evaluate_candidate_missing_geometry_with_compile_expected_is_unknown(tmp_path: Path):
    """If compile succeeded but topo/fg are missing, feasibility is honestly unknown."""
    pkg = _write_pkg(tmp_path, members={
        "candidates/c_nogeo/patch.json": {"candidate_id": "c_nogeo"},
        "candidates/c_nogeo/analysis/evaluation.json": {
            "compile_status": "compile_succeeded",
            "metrics": {"mass_kg": 1.5},
        },
        "candidates/c_nogeo/analysis/static_metrics.json": {"mass_kg": 1.5},
    })

    res = evaluate_design_study_candidate(pkg, "c_nogeo")
    assert res["status"] == "ok"
    assert res["feasibility"] == "unknown"
    ev = _read(pkg, "candidates/c_nogeo/analysis/evaluation.json")
    assert ev["critique"] is None
    assert any("not available for cad.critique" in w for w in ev["warnings"])


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


# ── multi-load-case evidence ingestion (#201) ─────────────────────────────────

def test_evaluate_candidate_surfaces_per_metric_controlling_load_case(tmp_path: Path):
    """Different load cases control different metrics; the controlling case +
    the cases considered are surfaced (not just buried in normalized_metrics)."""
    computed = {
        "format": "aieng.cae.computed_metrics",
        "load_cases": [
            {"id": "lc_a", "results": [
                {"result_type": "stress", "metric": "max_von_mises_stress", "max": 190.0, "unit": "MPa"},
                {"result_type": "displacement", "metric": "max_displacement", "max": 2.0, "unit": "mm"},
                {"result_type": "safety", "metric": "minimum_safety_factor", "min": 2.4},
            ]},
            {"id": "lc_b", "results": [
                {"result_type": "stress", "metric": "max_von_mises_stress", "max": 150.0, "unit": "MPa"},
                {"result_type": "displacement", "metric": "max_displacement", "max": 4.0, "unit": "mm"},
                {"result_type": "safety", "metric": "minimum_safety_factor", "min": 1.7},
            ]},
        ],
    }
    pkg = _write_pkg(tmp_path, members={
        "candidates/c1/patch.json": {"candidate_id": "c1"},
        "candidates/c1/analysis/computed_metrics.json": computed,
    })

    res = evaluate_design_study_candidate(pkg, "c1")
    assert res["status"] == "ok"
    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    # Worst-case across load cases: max for stress/deflection, min for safety.
    assert ev["metrics"]["max_stress"] == 190.0
    assert ev["metrics"]["max_deflection"] == 4.0
    assert ev["metrics"]["min_safety_factor"] == 1.7
    summary = {item["metric"]: item for item in ev["load_case_summary"]}
    assert summary["max_stress"]["controlling_load_case_id"] == "lc_a"
    assert summary["max_deflection"]["controlling_load_case_id"] == "lc_b"
    assert summary["min_safety_factor"]["controlling_load_case_id"] == "lc_b"
    assert summary["max_stress"]["load_cases_considered"] == ["lc_a", "lc_b"]
    assert ev["load_cases_considered"] == ["lc_a", "lc_b"]
    report = _read(pkg, "candidates/c1/diagnostics/evaluation_report.json")
    assert report["controlling_load_cases"]["max_stress"] == "lc_a"
    assert report["controlling_load_cases"]["min_safety_factor"] == "lc_b"
    assert report["load_cases_considered"] == ["lc_a", "lc_b"]


def test_evaluate_candidate_single_load_case_backward_compatible(tmp_path: Path):
    """A single load case still evaluates, and the summary names that one case."""
    computed = {
        "format": "aieng.cae.computed_metrics",
        "load_cases": [
            {"id": "lc_only", "results": [
                {"result_type": "stress", "metric": "max_von_mises_stress", "max": 120.0, "unit": "MPa"},
                {"result_type": "safety", "metric": "minimum_safety_factor", "min": 2.0},
            ]},
        ],
    }
    pkg = _write_pkg(tmp_path, members={
        "candidates/c1/patch.json": {"candidate_id": "c1"},
        "candidates/c1/analysis/computed_metrics.json": computed,
    })

    evaluate_design_study_candidate(pkg, "c1")
    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    assert ev["metrics"]["max_stress"] == 120.0  # unchanged single-case behaviour
    summary = {item["metric"]: item for item in ev["load_case_summary"]}
    assert summary["max_stress"]["controlling_load_case_id"] == "lc_only"
    assert summary["max_stress"]["load_cases_considered"] == ["lc_only"]
    assert ev["load_cases_considered"] == ["lc_only"]


def test_evaluate_candidate_missing_load_case_metric_stays_unknown(tmp_path: Path):
    """A metric absent from every load case is never fabricated; its constraint
    stays `unknown` and it is reported missing."""
    computed = {
        "format": "aieng.cae.computed_metrics",
        "load_cases": [
            {"id": "lc1", "results": [{"result_type": "stress", "metric": "max_von_mises_stress", "max": 100.0, "unit": "MPa"}]},
            {"id": "lc2", "results": [{"result_type": "stress", "metric": "max_von_mises_stress", "max": 120.0, "unit": "MPa"}]},
        ],
    }
    pkg = _write_pkg(tmp_path, members={
        "candidates/c1/patch.json": {"candidate_id": "c1"},
        "candidates/c1/analysis/computed_metrics.json": computed,
    })

    evaluate_design_study_candidate(pkg, "c1")
    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    assert ev["metrics"]["max_stress"] == 120.0
    assert "min_safety_factor" not in ev["metrics"]  # not fabricated
    metrics_in_summary = {item["metric"] for item in ev["load_case_summary"]}
    assert "max_stress" in metrics_in_summary
    assert "min_safety_factor" not in metrics_in_summary
    sf = [c for c in ev["constraint_evidence"] if c.get("type") == "min_safety_factor"]
    assert sf and sf[0]["status"] == "unknown"
    report = _read(pkg, "candidates/c1/diagnostics/evaluation_report.json")
    assert "min_safety_factor" in report["metrics_missing"]
