"""Tests for the backend design-study candidate solver glue.

The heavy compile (recompile_shape_ir_package) and solve (solve_package_static)
are monkeypatched so the assembly logic + honest-degradation contract are tested
without build123d / Gmsh / CalculiX. Asserts the baseline package is never mutated.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import app.cad_generation as cad_generation
import app.candidate_solver as candidate_solver
import app.simulation_runner as simulation_runner
from app.candidate_solver import solve_candidate_geometry


def _pkg_with_candidate(tmp_path: Path, *, candidate_id="c1", with_geometry=True) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Study"}))
        zf.writestr("geometry/shape_ir.json", json.dumps({"representation": "brep_build123d", "baseline": True}))
        zf.writestr("simulation/setup.yaml", "mesh:\n  target_size_mm: 2.0\n")
        zf.writestr("simulation/cae_mapping.json", json.dumps({"mappings": [{"face_id": "f_top"}]}))
        if with_geometry:
            zf.writestr(
                f"candidates/{candidate_id}/geometry/shape_ir.json",
                json.dumps({"representation": "brep_build123d", "candidate": True}),
            )
    return pkg


def _baseline_shape_ir(pkg: Path) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read("geometry/shape_ir.json"))


_COMPUTED = {
    "schema_version": "0.1",
    "metrics_source": {"tool": "frd_parser_v1", "software": "CalculiX"},
    "load_cases": [{"id": "lc1", "metrics": {"max_von_mises_stress": {"value": 150.0, "unit": "MPa"}}}],
}


def test_solve_candidate_success(tmp_path, monkeypatch):
    pkg = _pkg_with_candidate(tmp_path)
    swapped = {}

    def fake_recompile(package_path, timeout=120, use_cache=True):
        # the candidate Shape IR must have been overlaid into the temp package
        with zipfile.ZipFile(package_path) as zf:
            swapped["ir"] = json.loads(zf.read("geometry/shape_ir.json"))
        return {"status": "ok"}

    def fake_solve(package_path, mesh_size_mm=None, timeout=180, **kwargs):
        return {"solver_executed": True, "status": "success", "metrics": {}, "computed_metrics": _COMPUTED}

    monkeypatch.setattr(cad_generation, "recompile_shape_ir_package", fake_recompile)
    monkeypatch.setattr(simulation_runner, "solve_package_static", fake_solve)

    out = solve_candidate_geometry(pkg, "c1")
    assert out["solver_executed"] is True
    assert out["computed_metrics"]["metrics_source"]["software"] == "CalculiX"
    # the temp package was recompiled with the CANDIDATE Shape IR, not the baseline
    assert swapped["ir"].get("candidate") is True
    # baseline package geometry untouched
    assert _baseline_shape_ir(pkg).get("baseline") is True


def test_solve_candidate_missing_geometry(tmp_path):
    pkg = _pkg_with_candidate(tmp_path, with_geometry=False)
    out = solve_candidate_geometry(pkg, "c1")
    assert out["solver_executed"] is False
    assert out["status"] == "no_candidate_geometry"


def test_solve_candidate_compile_failure_is_honest(tmp_path, monkeypatch):
    pkg = _pkg_with_candidate(tmp_path)

    def boom(package_path, timeout=120, use_cache=True):
        raise RuntimeError("build123d exploded")

    monkeypatch.setattr(cad_generation, "recompile_shape_ir_package", boom)
    out = solve_candidate_geometry(pkg, "c1")
    assert out["solver_executed"] is False
    assert out["status"] == "compile_failed"
    assert _baseline_shape_ir(pkg).get("baseline") is True


def test_solve_candidate_stale_topology_is_honest(tmp_path, monkeypatch):
    pkg = _pkg_with_candidate(tmp_path)
    monkeypatch.setattr(cad_generation, "recompile_shape_ir_package", lambda p, timeout=120, use_cache=True: {"status": "ok"})
    monkeypatch.setattr(
        simulation_runner, "solve_package_static",
        lambda p, mesh_size_mm=None, timeout=180, **kwargs: {
            "solver_executed": False, "status": "stale_topology_references",
            "error": "CAE face references do not match current topology", "metrics": {},
        },
    )
    out = solve_candidate_geometry(pkg, "c1")
    assert out["solver_executed"] is False
    assert out["status"] == "stale_topology_references"
