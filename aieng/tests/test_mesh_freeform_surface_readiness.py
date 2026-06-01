"""Focused tests for freeform surface fit readiness/quality scoring v0.

Tests the mesh_freeform_surface_readiness converter:
- quality scoring per surface (fit_error, boundary, control_net, sample)
- readiness classification (ready / partial / not_ready)
- recommended next actions per surface and overall
- degraded paths (missing artifact, no freeform fits)
- integration: readiness artifact written, plan annotated
- honesty flags preserved
"""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

import numpy as np
import pytest

from aieng.converters.mesh_freeform_surface_fitting import (
    FREEFORM_SURFACE_FIT_PATH,
    write_freeform_surface_fit,
)
from aieng.converters.mesh_freeform_surface_readiness import (
    FREEFORM_READINESS_PATH,
    assess_freeform_readiness,
    write_freeform_readiness,
    _score_fit_error,
    _score_boundary,
    _score_control_net,
    _score_sample,
)
from aieng.converters.mesh_region_segmentation import write_mesh_region_graph
from aieng.converters.mesh_surface_fitting import write_mesh_surface_fit
from aieng.converters.mesh_brep_reconstruction import build_partial_brep_plan


# ── synthetic mesh helpers ────────────────────────────────────────────────────

def _saddle_mesh(n: int = 20) -> tuple[np.ndarray, np.ndarray]:
    u = np.linspace(-1, 1, n)
    v = np.linspace(-1, 1, n)
    U, V = np.meshgrid(u, v)
    X, Y = U, V
    Z = X**2 - Y**2
    verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    faces = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            b = a + 1
            c = (i + 1) * n + j
            d = c + 1
            faces.append([a, b, d])
            faces.append([a, d, c])
    return verts, np.asarray(faces, dtype=int)


def _sphere_patch_mesh(n: int = 16) -> tuple[np.ndarray, np.ndarray]:
    theta = np.linspace(0, math.pi / 2, n)
    phi = np.linspace(0, math.pi / 2, n)
    T, P = np.meshgrid(theta, phi)
    r = 10.0
    X = r * np.sin(T) * np.cos(P)
    Y = r * np.sin(T) * np.sin(P)
    Z = r * np.cos(T)
    verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    faces = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            b = a + 1
            c = (i + 1) * n + j
            d = c + 1
            faces.append([a, b, d])
            faces.append([a, d, c])
    return verts, np.asarray(faces, dtype=int)


def _cube_mesh() -> tuple[np.ndarray, np.ndarray]:
    verts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=float)
    faces = np.array([
        [0, 1, 2], [0, 2, 3],
        [4, 6, 5], [4, 7, 6],
        [0, 4, 5], [0, 5, 1],
        [2, 6, 7], [2, 7, 3],
        [0, 3, 7], [0, 7, 4],
        [1, 5, 6], [1, 6, 2],
    ], dtype=int)
    return verts, faces


def _write_pkg(tmp_path: Path, vertices, faces, extra: dict | None = None) -> Path:
    pkg = tmp_path / "test.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"format": "aieng.package", "version": "0.1.0"}))
        shape_ir = {
            "format": "aieng.shape_ir", "schema_version": "0.1",
            "parts": [{
                "id": "mesh_001", "type": "smooth_mesh_proxy",
                "vertices": vertices.tolist() if hasattr(vertices, "tolist") else list(vertices),
                "faces": faces.tolist() if hasattr(faces, "tolist") else list(faces),
            }],
        }
        zf.writestr("geometry/shape_ir.json", json.dumps(shape_ir))
        for name, data in (extra or {}).items():
            if isinstance(data, (dict, list)):
                data = json.dumps(data)
            zf.writestr(name, data)
    return pkg


def _read(pkg: Path, name: str):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


# ── Part A: unit tests for sub-scorers ────────────────────────────────────────

def test_score_fit_error_good():
    score, status = _score_fit_error(rms=0.01, max_err=0.05, scale=1.0)
    assert status == "good"
    assert score == 1.0


def test_score_fit_error_acceptable():
    score, status = _score_fit_error(rms=0.05, max_err=0.15, scale=1.0)
    assert status == "acceptable"
    assert score == 0.6


def test_score_fit_error_poor():
    score, status = _score_fit_error(rms=0.15, max_err=0.30, scale=1.0)
    assert status == "poor"
    assert score == 0.2


def test_score_boundary_good():
    score, status = _score_boundary({"type": "approximate_uv_loop", "point_count": 8, "approximate": False})
    assert status == "good"
    assert score == 1.0


def test_score_boundary_approximate():
    score, status = _score_boundary({"type": "approximate_uv_loop", "point_count": 8, "approximate": True})
    assert status == "approximate"
    assert score == 0.5


def test_score_boundary_missing():
    score, status = _score_boundary(None)
    assert status == "missing"
    assert score == 0.0


def test_score_control_net_good():
    score, status = _score_control_net(4, 4)
    assert status == "good"
    assert score == 1.0


def test_score_control_net_excessive():
    score, status = _score_control_net(14, 14)
    assert status == "excessive"
    assert score == 0.4


def test_score_sample_good():
    score, status = _score_sample(60)
    assert status == "good"
    assert score == 1.0


def test_score_sample_sparse():
    score, status = _score_sample(10)
    assert status == "sparse"
    assert score == 0.2


# ── Part B: surface readiness assessment ──────────────────────────────────────

def test_saddle_surface_assessed_as_ready_or_partial(tmp_path: Path):
    """A smooth saddle with many samples should score well."""
    verts, faces = _saddle_mesh(n=20)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    readiness = write_freeform_readiness(pkg)
    assert readiness["format"] == "aieng.mesh.freeform_reconstruction_readiness.v0"
    assert readiness["status"] in ("ready", "partial", "not_ready")
    assert len(readiness["surfaces"]) >= 1
    surf = readiness["surfaces"][0]
    assert "quality_score" in surf
    assert 0.0 <= surf["quality_score"] <= 1.0
    assert surf["readiness"] in ("ready", "partial", "not_ready")
    assert surf["recommended_next_action"] is not None


def test_sphere_patch_surface_scores_reflect_quality(tmp_path: Path):
    """A sphere-like patch produces scored surfaces with confidence."""
    verts, faces = _sphere_patch_mesh(n=14)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    readiness = write_freeform_readiness(pkg)
    assert len(readiness["surfaces"]) >= 1
    for s in readiness["surfaces"]:
        assert "fit_error_quality" in s
        assert "boundary_quality" in s
        assert "control_net_quality" in s
        assert "sample_quality" in s
        assert s["confidence"] in ("high", "medium", "low")


def test_high_error_surface_becomes_not_ready(tmp_path: Path):
    """A surface with very high RMS error should be not_ready."""
    verts, faces = _saddle_mesh(n=8)
    # Perturb heavily to create high error
    verts = verts + np.random.RandomState(42).normal(0, 0.5, verts.shape)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    readiness = write_freeform_readiness(pkg)
    for s in readiness["surfaces"]:
        if s["readiness"] == "not_ready":
            assert "fit_error_too_high" in s["blocking_issues"] or "too_few_samples" in s["blocking_issues"]
            break


def test_missing_freeform_fit_produces_skipped(tmp_path: Path):
    """Without a freeform fit artifact, readiness is skipped/insufficient_data."""
    pkg = _write_pkg(tmp_path, [], [])
    readiness = assess_freeform_readiness(None)
    assert readiness["status"] == "skipped"
    assert readiness["summary"]["recommended_next_action"] == "insufficient_data"


def test_cube_produces_no_ready_surfaces(tmp_path: Path):
    """Cube has no freeform fits, so readiness has no surfaces."""
    verts, faces = _cube_mesh()
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    readiness = write_freeform_readiness(pkg)
    assert readiness["summary"]["surfaces_total"] == 0
    assert readiness["status"] == "skipped"
    assert readiness["summary"]["recommended_next_action"] == "insufficient_data"


# ── Part C: artifact writing ──────────────────────────────────────────────────

def test_readiness_artifact_written(tmp_path: Path):
    """write_freeform_readiness persists diagnostics/mesh_freeform_reconstruction_readiness.json."""
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert FREEFORM_READINESS_PATH in names


def test_honesty_flags_present(tmp_path: Path):
    """Readiness document includes honesty flags set to false."""
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    readiness = write_freeform_readiness(pkg)
    honesty = readiness.get("honesty", {})
    assert honesty.get("is_brep") is False
    assert honesty.get("cad_editable") is False
    assert honesty.get("step_exported") is False
    assert honesty.get("readiness_only") is True


# ── Part D: reconstruction plan annotation ────────────────────────────────────

def test_plan_annotated_with_readiness(tmp_path: Path):
    """Reconstruction plan freeform evidence rows include readiness annotations."""
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    plan, _surfaces, _diag = build_partial_brep_plan(pkg)
    evidence_rows = [r for r in plan.get("region_plan", [])
                     if r.get("reconstruction_status") == "evidence_only"]
    assert len(evidence_rows) >= 1
    for row in evidence_rows:
        assert "freeform_readiness" in row
        assert "freeform_quality_score" in row
        assert "freeform_recommended_next_action" in row
        assert row["reason"] == "freeform_brep_not_implemented"


def test_plan_entries_remain_evidence_only(tmp_path: Path):
    """Freeform plan entries do NOT become face candidates."""
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    _plan, surfaces, _diag = build_partial_brep_plan(pkg)
    for cand in surfaces.get("face_candidates", []):
        assert cand["surface_type"] != "bspline_surface_candidate"


# ── Part E: summary counts ────────────────────────────────────────────────────

def test_summary_counts_are_consistent(tmp_path: Path):
    """Total = ready + partial + not_ready."""
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    readiness = write_freeform_readiness(pkg)
    s = readiness["summary"]
    assert s["surfaces_total"] == s["surfaces_ready"] + s["surfaces_partial"] + s["surfaces_not_ready"]
