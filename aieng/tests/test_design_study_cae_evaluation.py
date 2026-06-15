"""Tests for design-study candidate CAE evaluation request v0.

Explicit, candidate-local, conservative. Solver execution is disabled by default.
Baseline artifacts are never overwritten.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.design_study_cae_evaluation import (
    CANDIDATE_CAE_DIAGNOSTICS_REL,
    CANDIDATE_CAE_EVALUATION_REQUEST_REL,
    CANDIDATE_CAE_MAPPING_REL,
    CANDIDATE_CAE_SETUP_REL,
    request_design_study_candidate_cae_evaluation,
)
from aieng.converters.design_study_execution import (
    CANDIDATE_WORKSPACE_ROOT,
    DESIGN_STUDY_ITERATIONS_PATH,
)
from aieng.converters.design_study_ranking import DESIGN_STUDY_CANDIDATE_RANKING_PATH


# ── helpers ───────────────────────────────────────────────────────────────────


def _problem(**overrides):
    p = {
        "format": "aieng.design_study_problem", "schema_version": "0.1",
        "id": "study_cae",
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


def _write_pkg(tmp_path: Path, *, problem=None, baseline_setup=None, baseline_mapping=None,
               candidate_ws=None, iterations=None, extra_members=None) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Study"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"representation": "brep_build123d"}))
        if problem is not None:
            zf.writestr("analysis/design_study_problem.json", json.dumps(problem))
        if baseline_setup is not None:
            zf.writestr("simulation/setup.yaml", baseline_setup)
        if baseline_mapping is not None:
            zf.writestr("simulation/cae_mapping.json", json.dumps(baseline_mapping))
        if iterations is not None:
            zf.writestr(DESIGN_STUDY_ITERATIONS_PATH, json.dumps(iterations))
        for cid, ws_data in (candidate_ws or {}).items():
            for name, data in ws_data.items():
                zf.writestr(f"{CANDIDATE_WORKSPACE_ROOT}{cid}/{name}",
                            json.dumps(data) if isinstance(data, (dict, list)) else data)
        for name, data in (extra_members or {}).items():
            if isinstance(data, (dict, list)):
                data = json.dumps(data)
            zf.writestr(name, data)
    return pkg


def _read(pkg: Path, name: str):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


def _baseline_unchanged(pkg: Path) -> bool:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read("geometry/shape_ir.json")) == {"representation": "brep_build123d"}


def _read_baseline_setup(pkg: Path) -> str | None:
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        if "simulation/setup.yaml" not in names:
            return None
        return zf.read("simulation/setup.yaml").decode("utf-8")


# ── Part A: request artifact ──────────────────────────────────────────────────


def test_request_created_for_existing_candidate(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), candidate_ws={
        "c1": {"geometry/shape_ir.json": {"representation": "brep_build123d"}},
    }, baseline_setup="mesh:\n  size: 2.0\n")
    res = request_design_study_candidate_cae_evaluation(pkg, "c1")
    assert res["status"] == "ok"
    assert res["candidate_id"] == "c1"
    assert res["baseline_modified"] is False

    req = _read(pkg, f"{CANDIDATE_WORKSPACE_ROOT}c1/{CANDIDATE_CAE_EVALUATION_REQUEST_REL}")
    assert req["format"] == "aieng.design_study.candidate_cae_evaluation_request.v0"
    assert req["candidate_id"] == "c1"
    assert req["mode"] == "prepare_only"
    assert req["allow_solver_execution"] is False
    assert req["baseline_modified"] is False


def test_missing_candidate_returns_failed(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem())
    res = request_design_study_candidate_cae_evaluation(pkg, "ghost")
    assert res["status"] == "failed"
    assert "candidate workspace not found" in res["reason"]
    assert res["baseline_modified"] is False


# ── Part C: setup derivation ──────────────────────────────────────────────────


def test_prepare_only_derives_candidate_local_setup(tmp_path: Path):
    baseline_setup = "mesh:\n  size: 2.0\n"
    baseline_mapping = {"mappings": [{"face_id": "f_top"}]}
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup=baseline_setup,
                     baseline_mapping=baseline_mapping, candidate_ws={
                         "c1": {"geometry/shape_ir.json": {"representation": "brep_build123d"}},
                     })
    res = request_design_study_candidate_cae_evaluation(pkg, "c1", mode="prepare_only")
    assert res["status"] == "ok"
    assert res["setup_status"] == "derived"
    assert res["solver_status"] == "skipped"

    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert "candidates/c1/simulation/setup.yaml" in names
        assert "candidates/c1/simulation/cae_mapping.json" in names
        assert zf.read("candidates/c1/simulation/setup.yaml").decode("utf-8") == baseline_setup

    # Baseline setup unchanged
    assert _read_baseline_setup(pkg) == baseline_setup
    assert _baseline_unchanged(pkg)


def test_missing_baseline_setup_returns_needs_user_input(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), candidate_ws={
        "c1": {"geometry/shape_ir.json": {"representation": "brep_build123d"}},
    })
    res = request_design_study_candidate_cae_evaluation(pkg, "c1", mode="prepare_only")
    assert res["status"] == "needs_user_input"
    assert "baseline simulation/setup.yaml not found" in res["reason"]
    assert res["baseline_modified"] is False


# ── Part D: normalize existing ────────────────────────────────────────────────


def test_normalize_existing_reads_candidate_local_metrics(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup="mesh:\n  size: 2.0\n",
                     candidate_ws={
                         "c1": {
                             "geometry/shape_ir.json": {"representation": "brep_build123d"},
                             "analysis/computed_metrics.json": {
                                 "load_cases": [
                                     {"id": "lc1", "results": [
                                         {"result_type": "stress", "metric": "max_von_mises_stress",
                                          "max": 150.0, "unit": "MPa"},
                                     ]}
                                 ]
                             },
                         },
                     })
    res = request_design_study_candidate_cae_evaluation(pkg, "c1", mode="normalize_existing")
    assert res["status"] == "ok"
    assert res["normalization_status"] == "ok"
    assert res["evaluation_status"] == "complete"

    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    assert ev["metrics"]["max_stress"] == 150.0
    assert ev["feasibility"] == "feasible"
    assert ev["baseline_modified"] is False


def test_candidate_local_metrics_preferred_over_baseline(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup="mesh:\n  size: 2.0\n",
                     candidate_ws={
                         "c1": {
                             "geometry/shape_ir.json": {"representation": "brep_build123d"},
                             "analysis/computed_metrics.json": {
                                 "load_cases": [
                                     {"id": "lc1", "results": [
                                         {"result_type": "stress", "metric": "max_von_mises_stress",
                                          "max": 180.0, "unit": "MPa"},
                                     ]}
                                 ]
                             },
                         },
                     },
                     extra_members={
                         "analysis/computed_metrics.json": json.dumps({
                             "load_cases": [
                                 {"id": "lc1", "results": [
                                     {"result_type": "stress", "metric": "max_von_mises_stress",
                                      "max": 999.0, "unit": "MPa"},
                                 ]}
                             ]
                         }),
                     })
    res = request_design_study_candidate_cae_evaluation(pkg, "c1", mode="normalize_existing")
    assert res["status"] == "ok"

    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    # Candidate-local metric (180) should be used, not baseline (999)
    assert ev["metrics"]["max_stress"] == 180.0


def test_malformed_candidate_metrics_degrade_honestly(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup="mesh:\n  size: 2.0\n",
                     candidate_ws={
                         "c1": {
                             "geometry/shape_ir.json": {"representation": "brep_build123d"},
                             "analysis/computed_metrics.json": "not valid json",
                         },
                     })
    res = request_design_study_candidate_cae_evaluation(pkg, "c1", mode="normalize_existing")
    assert res["status"] == "ok"
    # Evaluation should handle malformed gracefully
    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    assert ev["evaluation_status"] in ("insufficient_data", "partial")
    assert ev["baseline_modified"] is False


def test_missing_results_produces_insufficient_data(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup="mesh:\n  size: 2.0\n",
                     candidate_ws={
                         "c1": {"geometry/shape_ir.json": {"representation": "brep_build123d"}},
                     })
    res = request_design_study_candidate_cae_evaluation(pkg, "c1", mode="normalize_existing")
    assert res["status"] == "ok"
    assert res["normalization_status"] == "insufficient_data"
    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    assert ev["evaluation_status"] == "insufficient_data"


# ── Part E/F: solver execution ────────────────────────────────────────────────


def test_allow_solver_execution_false_never_runs_solver(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup="mesh:\n  size: 2.0\n",
                     candidate_ws={
                         "c1": {"geometry/shape_ir.json": {"representation": "brep_build123d"}},
                     })
    res = request_design_study_candidate_cae_evaluation(
        pkg, "c1", mode="run_if_available", allow_solver_execution=False
    )
    assert res["status"] == "ok"
    assert res["solver_status"] == "skipped"
    assert "allow_solver_execution is false" in str(res["warnings"])


def test_solver_unavailable_produces_skipped_diagnostics(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup="mesh:\n  size: 2.0\n",
                     candidate_ws={
                         "c1": {"geometry/shape_ir.json": {"representation": "brep_build123d"}},
                     })
    res = request_design_study_candidate_cae_evaluation(
        pkg, "c1", mode="run_if_available", allow_solver_execution=True
    )
    assert res["status"] == "ok"
    assert res["solver_status"] == "skipped"
    diag = _read(pkg, f"candidates/c1/{CANDIDATE_CAE_DIAGNOSTICS_REL}")
    assert diag["solver_execution_status"] == "skipped"
    assert diag["baseline_modified"] is False


# ── Part G: ranking refresh ───────────────────────────────────────────────────


def test_ranking_refresh_happens_only_when_requested(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup="mesh:\n  size: 2.0\n",
                     candidate_ws={
                         "c1": {"geometry/shape_ir.json": {"representation": "brep_build123d"}},
                     })
    res = request_design_study_candidate_cae_evaluation(
        pkg, "c1", mode="normalize_existing", allow_ranking_refresh=False
    )
    assert res["status"] == "ok"
    assert res["ranking_refresh_status"] == "skipped"


def test_ranking_refresh_when_requested(tmp_path: Path):
    iters = {
        "format": "aieng.design_study_iterations",
        "format_version": "0.1.0",
        "schema_version": "0.1",
        "iterations": [
            {"candidate_id": "c1", "execution_status": "patch_applied",
             "validation_status": "valid", "metrics": {}, "baseline_modified": False},
        ],
    }
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup="mesh:\n  size: 2.0\n",
                     iterations=iters, candidate_ws={
                         "c1": {
                             "geometry/shape_ir.json": {"representation": "brep_build123d"},
                             "analysis/computed_metrics.json": {
                                 "load_cases": [
                                     {"id": "lc1", "results": [
                                         {"result_type": "stress", "metric": "max_von_mises_stress",
                                          "max": 150.0, "unit": "MPa"},
                                     ]}
                                 ]
                             },
                         },
                     })
    res = request_design_study_candidate_cae_evaluation(
        pkg, "c1", mode="normalize_existing", allow_ranking_refresh=True
    )
    assert res["status"] == "ok"
    assert res["ranking_refresh_status"] == "ok"
    ranking = _read(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["status"] == "ranked"


# ── Part I: diagnostics ───────────────────────────────────────────────────────


def test_diagnostics_written_with_all_status_fields(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup="mesh:\n  size: 2.0\n",
                     candidate_ws={
                         "c1": {"geometry/shape_ir.json": {"representation": "brep_build123d"}},
                     })
    res = request_design_study_candidate_cae_evaluation(pkg, "c1", mode="prepare_only")
    assert res["status"] == "ok"

    diag = _read(pkg, f"candidates/c1/{CANDIDATE_CAE_DIAGNOSTICS_REL}")
    assert diag["format"] == "aieng.design_study.candidate_cae_evaluation_diagnostics"
    assert diag["candidate_id"] == "c1"
    assert diag["setup_derivation_status"] == "derived"
    assert diag["solver_execution_status"] == "skipped"
    assert diag["candidate_local_only"] is True
    assert diag["baseline_modified"] is False
    assert "limitations" in diag


# ── Part C: baseline immutability ─────────────────────────────────────────────


def test_baseline_geometry_setup_analysis_remain_unchanged(tmp_path: Path):
    baseline_setup = "mesh:\n  size: 2.0\n"
    baseline_metrics = {"load_cases": [{"id": "lc1", "results": []}]}
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup=baseline_setup,
                     candidate_ws={
                         "c1": {"geometry/shape_ir.json": {"representation": "brep_build123d"}},
                     },
                     extra_members={
                         "analysis/computed_metrics.json": json.dumps(baseline_metrics),
                     })
    request_design_study_candidate_cae_evaluation(pkg, "c1", mode="normalize_existing")

    # Baseline geometry
    assert _baseline_unchanged(pkg)
    # Baseline setup
    assert _read_baseline_setup(pkg) == baseline_setup
    # Baseline computed_metrics
    with zipfile.ZipFile(pkg) as zf:
        assert json.loads(zf.read("analysis/computed_metrics.json")) == baseline_metrics


# ── Part K: endpoint integration ──────────────────────────────────────────────

def test_endpoint_writes_expected_candidate_local_diagnostics(tmp_path: Path):
    pkg = _write_pkg(tmp_path, problem=_problem(), baseline_setup="mesh:\n  size: 2.0\n",
                     candidate_ws={
                         "c1": {"geometry/shape_ir.json": {"representation": "brep_build123d"}},
                     })
    res = request_design_study_candidate_cae_evaluation(pkg, "c1")
    assert res["status"] == "ok"

    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert f"candidates/c1/{CANDIDATE_CAE_EVALUATION_REQUEST_REL}" in names
        assert f"candidates/c1/{CANDIDATE_CAE_DIAGNOSTICS_REL}" in names
        assert f"candidates/c1/{CANDIDATE_CAE_SETUP_REL}" in names
        # No package-level simulation artifacts created for candidate eval
        assert "simulation/candidate_solver_input.inp" not in names


# ── injected solver_fn (real-solve wiring) ────────────────────────────────────


def _solver_doc(stress=150.0, disp=0.5):
    """A computed_metrics doc shaped like the FRD/DAT extractor output."""
    return {
        "schema_version": "0.1",
        "metrics_source": {"tool": "frd_parser_v1", "software": "CalculiX", "source_files": ["x.frd"]},
        "load_cases": [{"id": "lc1", "metrics": {
            "max_von_mises_stress": {"value": stress, "unit": "MPa"},
            "max_displacement": {"value": disp, "unit": "mm"},
        }}],
        "warnings": [],
    }


def _candidate_pkg(tmp_path: Path) -> Path:
    return _write_pkg(tmp_path, problem=_problem(), baseline_setup="mesh:\n  size: 2.0\n",
                      baseline_mapping={"mappings": [{"face_id": "f_top"}]},
                      candidate_ws={"c1": {"geometry/shape_ir.json": {"representation": "brep_build123d"}}})


def test_solver_fn_writes_metrics_and_reports_solver_executed(tmp_path: Path):
    pkg = _candidate_pkg(tmp_path)
    calls = []

    def fake_solver(package_path, candidate_id):
        calls.append(candidate_id)
        return {"solver_executed": True, "computed_metrics": _solver_doc(stress=150.0)}

    res = request_design_study_candidate_cae_evaluation(
        pkg, "c1", mode="run_if_available", allow_solver_execution=True, solver_fn=fake_solver,
    )
    assert res["status"] == "ok"
    assert res["solver_status"] == "completed"
    assert calls == ["c1"]

    # candidate-local computed_metrics written from the solve
    cm = _read(pkg, "candidates/c1/analysis/computed_metrics.json")
    assert cm["metrics_source"]["software"] == "CalculiX"

    # evaluation reports the solve honestly + uses the real metric
    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    assert ev["honesty"]["solver_executed"] is True
    assert ev["metrics"]["max_stress"] == 150.0
    assert ev["baseline_modified"] is False
    assert _baseline_unchanged(pkg)
    # provenance.solver_executed lives in the evaluation report
    report = _read(pkg, "candidates/c1/diagnostics/evaluation_report.json")
    assert report["provenance"]["solver_executed"] is True


def test_solver_fn_absent_skips_honestly(tmp_path: Path):
    pkg = _candidate_pkg(tmp_path)
    res = request_design_study_candidate_cae_evaluation(
        pkg, "c1", mode="run_if_available", allow_solver_execution=True, solver_fn=None,
    )
    assert res["solver_status"] == "skipped"
    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    assert ev["honesty"]["solver_executed"] is False


def test_solver_fn_failure_is_honest(tmp_path: Path):
    pkg = _candidate_pkg(tmp_path)

    def failing_solver(package_path, candidate_id):
        return {"solver_executed": False, "error": "CalculiX returned non-zero"}

    res = request_design_study_candidate_cae_evaluation(
        pkg, "c1", mode="run_if_available", allow_solver_execution=True, solver_fn=failing_solver,
    )
    assert res["solver_status"] == "failed"
    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    assert ev["honesty"]["solver_executed"] is False
    assert _baseline_unchanged(pkg)


def test_solver_fn_raising_is_caught(tmp_path: Path):
    pkg = _candidate_pkg(tmp_path)

    def boom(package_path, candidate_id):
        raise RuntimeError("mesh blew up")

    res = request_design_study_candidate_cae_evaluation(
        pkg, "c1", mode="run_if_available", allow_solver_execution=True, solver_fn=boom,
    )
    assert res["status"] == "ok"  # request itself completes; solve failed honestly
    assert res["solver_status"] == "failed"
    ev = _read(pkg, "candidates/c1/analysis/evaluation.json")
    assert ev["honesty"]["solver_executed"] is False


def test_solver_not_run_when_execution_not_allowed(tmp_path: Path):
    pkg = _candidate_pkg(tmp_path)

    def fake_solver(package_path, candidate_id):
        raise AssertionError("solver_fn must not be called when allow_solver_execution is False")

    res = request_design_study_candidate_cae_evaluation(
        pkg, "c1", mode="run_if_available", allow_solver_execution=False, solver_fn=fake_solver,
    )
    assert res["solver_status"] == "skipped"
