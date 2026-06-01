"""Focused tests for freeform/NURBS surface fitting evidence v0.

Tests the mesh_freeform_surface_fitting converter:
- freeform_candidate regions produce approximate BSpline surface evidence
- planar/cylinder regions are skipped (already analytic-fit)
- noisy/tiny regions are skipped
- artifacts include control_net, fit_error, confidence, approximate boundary
- honesty flags (is_brep=false, cad_editable=false, etc.)
- integration with pipeline: artifacts written, no STEP export triggered
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
    FREEFORM_SURFACE_FITTING_DIAG_PATH,
    fit_freeform_surfaces,
    write_freeform_surface_fit,
    _fit_bspline_surface,
    _parameterize_region,
)
from aieng.converters.mesh_region_segmentation import (
    MESH_REGION_GRAPH_PATH,
    segment_mesh_regions,
    write_mesh_region_graph,
)
from aieng.converters.mesh_surface_fitting import (
    MESH_SURFACE_FIT_PATH,
    write_mesh_surface_fit,
)
from aieng.converters.mesh_brep_reconstruction import (
    MESH_BREP_PLAN_PATH,
    build_partial_brep_plan,
)


# ── synthetic mesh helpers ────────────────────────────────────────────────────

def _saddle_mesh(n: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """A smooth saddle patch z = x^2 - y^2 over [-1,1]^2."""
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
    """A sphere-like patch (octant) for freeform fitting."""
    theta = np.linspace(0, np.pi / 2, n)
    phi = np.linspace(0, np.pi / 2, n)
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
    """Simple cube mesh with 8 vertices, 12 faces."""
    verts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=float)
    faces = np.array([
        [0, 1, 2], [0, 2, 3],  # bottom
        [4, 6, 5], [4, 7, 6],  # top
        [0, 4, 5], [0, 5, 1],  # front
        [2, 6, 7], [2, 7, 3],  # back
        [0, 3, 7], [0, 7, 4],  # left
        [1, 5, 6], [1, 6, 2],  # right
    ], dtype=int)
    return verts, faces


def _write_pkg(tmp_path: Path, vertices, faces, extra: dict | None = None) -> Path:
    """Create a minimal .aieng package with a mesh node for testing."""
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


# ── Part A: unit tests for core fitting ───────────────────────────────────────

def test_parameterize_region_produces_uv_in_01():
    """PCA parameterization maps vertices into [0,1] x [0,1]."""
    verts = np.array([[0, 0, 0], [1, 0, 0.1], [1, 1, 0.2], [0, 1, 0.1]], dtype=float)
    uv, centroid, basis = _parameterize_region(verts)
    assert uv.shape == (4, 2)
    assert uv.min() >= -1e-9
    assert uv.max() <= 1 + 1e-9


def test_fit_bspline_surface_produces_control_net():
    """Least-squares fit returns control net and error metrics."""
    verts, faces = _saddle_mesh(n=12)
    uv, _centroid, _basis = _parameterize_region(verts)
    fit = _fit_bspline_surface(verts, uv)
    assert fit is not None
    assert "control_net" in fit
    assert "fit_error" in fit
    assert fit["fit_error"]["rms"] >= 0
    assert fit["degree_u"] == 3
    assert fit["degree_v"] == 3


def test_fit_bspline_surface_fails_on_too_few_points():
    """Fit returns None when there are too few vertices."""
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    uv = np.array([[0, 0], [1, 0], [0, 1]], dtype=float)
    fit = _fit_bspline_surface(verts, uv)
    assert fit is None


# ── Part B: freeform region selection and fitting ─────────────────────────────

def test_saddle_mesh_produces_freeform_surface_candidate(tmp_path: Path):
    """A smooth saddle produces a freeform_candidate region with BSpline evidence."""
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    fit_doc, diag = fit_freeform_surfaces(pkg)
    assert len(fit_doc["surfaces"]) >= 1
    surf = fit_doc["surfaces"][0]
    assert surf["surface_type"] == "bspline_surface_candidate"
    assert surf["status"] == "fitted"
    assert surf["is_brep"] is False
    assert surf["cad_editable"] is False
    assert surf["reconstructed_face"] is False
    assert surf["step_exported"] is False
    assert surf["approximate"] is True
    assert "control_net" in surf
    assert "fit_error" in surf
    assert surf["fit_error"]["rms"] >= 0


def test_sphere_patch_produces_freeform_candidate_with_confidence(tmp_path: Path):
    """A sphere-like patch is classified freeform and fitted with confidence."""
    verts, faces = _sphere_patch_mesh(n=14)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    fit_doc, diag = fit_freeform_surfaces(pkg)
    assert len(fit_doc["surfaces"]) >= 1
    surf = fit_doc["surfaces"][0]
    assert surf["surface_type"] == "bspline_surface_candidate"
    assert surf["confidence"] in ("high", "medium", "low")
    assert "fit_error" in surf


def test_cube_planar_regions_do_not_produce_freeform_fits(tmp_path: Path):
    """Cube planar regions are skipped by freeform fitting (already analytic)."""
    verts, faces = _cube_mesh()
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    fit_doc, diag = fit_freeform_surfaces(pkg)
    # All 6 cube faces are planar; none should be freeform-fitted
    assert len(fit_doc["surfaces"]) == 0
    assert diag["regions_skipped"] > 0


def test_noisy_tiny_region_is_skipped(tmp_path: Path):
    """A tiny region (single triangle) is noisy_small_region and skipped."""
    verts = np.array([[0, 0, 0], [1, 0, 0], [0.5, 0.5, 0.1]], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=int)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    fit_doc, diag = fit_freeform_surfaces(pkg)
    assert len(fit_doc["surfaces"]) == 0
    assert diag["regions_skipped"] >= 1


# ── Part C: artifact writing and package integration ──────────────────────────

def test_artifacts_written_into_package(tmp_path: Path):
    """write_freeform_surface_fit persists both artifact and diagnostics."""
    verts, faces = _saddle_mesh(n=14)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert FREEFORM_SURFACE_FIT_PATH in names
        assert FREEFORM_SURFACE_FITTING_DIAG_PATH in names


def test_diagnostics_include_counts_and_skipped_reasons(tmp_path: Path):
    """Diagnostics report considered, fitted, skipped, and reasons."""
    verts, faces = _saddle_mesh(n=14)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    diag = _read(pkg, FREEFORM_SURFACE_FITTING_DIAG_PATH)
    assert "regions_considered" in diag
    assert "regions_fitted" in diag
    assert "regions_skipped" in diag
    assert "skipped_detail" in diag
    assert "confidence_distribution" in diag


# ── Part D: boundary extraction ───────────────────────────────────────────────

def test_fitted_patch_includes_approximate_boundary(tmp_path: Path):
    """Fitted freeform surface includes an approximate UV boundary."""
    verts, faces = _saddle_mesh(n=14)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    fit_doc, _ = fit_freeform_surfaces(pkg)
    assert len(fit_doc["surfaces"]) >= 1
    surf = fit_doc["surfaces"][0]
    boundary = surf.get("boundary") or {}
    assert boundary.get("approximate") is True
    assert boundary.get("type") in ("approximate_uv_loop", "none")
    assert boundary.get("boundary_source") is not None


# ── Part E: reconstruction plan integration ───────────────────────────────────

def test_freeform_evidence_appears_in_reconstruction_plan(tmp_path: Path):
    """Reconstruction plan includes freeform evidence-only entries."""
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_freeform_surface_fit(pkg)
    plan, surfaces, diag = build_partial_brep_plan(pkg)
    # freeform regions should appear as evidence_only in the plan
    evidence_rows = [r for r in plan.get("region_plan", [])
                     if r.get("reconstruction_status") == "evidence_only"]
    assert len(evidence_rows) >= 1
    assert evidence_rows[0].get("reason") == "freeform_brep_not_implemented"
    assert "source_freeform_surface_id" in evidence_rows[0]
    assert surfaces["summary"].get("freeform_evidence_count", 0) >= 1


def test_freeform_evidence_does_not_create_face_candidates(tmp_path: Path):
    """Freeform evidence does NOT generate B-Rep face candidates."""
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_freeform_surface_fit(pkg)
    _plan, surfaces, _diag = build_partial_brep_plan(pkg)
    # No face candidates from freeform surfaces
    for cand in surfaces.get("face_candidates", []):
        assert cand["surface_type"] != "bspline_surface_candidate"


# ── Part F: degraded paths ────────────────────────────────────────────────────

def test_missing_region_graph_degrades_honestly(tmp_path: Path):
    """Without a region graph, freeform fitting returns empty + reason."""
    pkg = _write_pkg(tmp_path, [], [])
    fit_doc, diag = fit_freeform_surfaces(pkg)
    assert len(fit_doc["surfaces"]) == 0
    assert diag.get("available") is False
    assert diag.get("status") == "skipped"


def test_no_freeform_regions_skips_gracefully(tmp_path: Path):
    """A mesh with only planar regions produces no freeform fits but does not fail."""
    verts, faces = _cube_mesh()
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    fit_doc, diag = fit_freeform_surfaces(pkg)
    assert len(fit_doc["surfaces"]) == 0
    assert diag["regions_skipped"] >= 1


# ── Part G: honesty boundary checks ───────────────────────────────────────────

def test_all_honesty_flags_are_false(tmp_path: Path):
    """Every freeform surface entry has honesty flags set to false."""
    verts, faces = _saddle_mesh(n=14)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    fit_doc, _ = fit_freeform_surfaces(pkg)
    for surf in fit_doc["surfaces"]:
        assert surf["is_brep"] is False
        assert surf["cad_editable"] is False
        assert surf["reconstructed_face"] is False
        assert surf["step_exported"] is False
        assert surf["stitching_ready"] is False
        assert surf["candidate_only"] is True
        assert surf["approximate"] is True
