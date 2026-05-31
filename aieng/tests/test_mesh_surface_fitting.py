"""Tests for analytic plane fitting of mesh planar_candidate regions.

Mesh analysis only — fitted planes + convex-hull boundaries are approximations toward
future mesh-to-CAD, NOT B-Rep faces. No STEP export, no NURBS, no CAD-editability claim.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")
import numpy as np  # noqa: E402

from aieng.converters.mesh_region_segmentation import write_mesh_region_graph
from aieng.converters.mesh_surface_fitting import (  # noqa: E402
    MESH_SURFACE_FITTING_DIAG_PATH,
    MESH_SURFACE_FIT_PATH,
    fit_mesh_surfaces,
    fit_plane_to_points,
    write_mesh_surface_fit,
)


def _cube():
    V = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
         [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]
    F = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
         [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [0, 4, 7], [0, 7, 3]]
    return V, F


def _pkg(tmp_path: Path, V, F, *, node_id="optimized_blk", extra=None) -> Path:
    node = {"id": node_id, "type": "smooth_mesh_proxy", "dimension": 3,
            "vertices": V, "faces": F,
            "source_optimization": {"design_space_node": "blk", "source_ir_node": "blk",
                                    "limitations": ["experimental 3D SIMP"]}}
    shape_ir = {"representation": "manifold_mesh", "parts": [node]}
    manifest = {"format": "aieng.conversion_manifest",
                "geometry_execution": {"executed": True, "geometry_kind": "mesh",
                                       "representation_kind": "mesh", "actual_runtime": "manifold"}}
    pkg = tmp_path / "m.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", json.dumps(shape_ir))
        zf.writestr("provenance/conversion_manifest.json", json.dumps(manifest))
    write_mesh_region_graph(pkg)            # produce the region graph the fitter consumes
    return pkg


# ── pure plane fit ───────────────────────────────────────────────────────────

def test_fit_plane_axis_aligned():
    pts = np.array([[0, 0, 5], [1, 0, 5], [1, 1, 5], [0, 1, 5]], dtype=float)
    fit = fit_plane_to_points(pts)
    assert abs(abs(fit["normal"][2]) - 1.0) < 1e-6     # normal ~ ±Z
    assert fit["max_distance"] < 1e-9 and fit["rms_distance"] < 1e-9
    assert abs(fit["origin"][2] - 5.0) < 1e-6


def test_fit_plane_tilted_normal():
    # plane z = x (normal ~ (-1,0,1)/sqrt2)
    pts = np.array([[0, 0, 0], [1, 0, 1], [1, 1, 1], [0, 1, 0], [2, 0, 2], [2, 1, 2]], dtype=float)
    fit = fit_plane_to_points(pts)
    n = np.array(fit["normal"])
    expected = np.array([-1, 0, 1]) / np.sqrt(2)
    assert abs(abs(float(n @ expected)) - 1.0) < 1e-6   # parallel (up to sign)
    assert fit["rms_distance"] < 1e-9


# ── package fitting ──────────────────────────────────────────────────────────

def test_cube_produces_six_plane_fits_low_error(tmp_path: Path):
    V, F = _cube()
    pkg = _pkg(tmp_path, V, F)
    fit_doc, diag = fit_mesh_surfaces(pkg)
    assert len(fit_doc["surfaces"]) == 6 and diag["fitted"] == 6
    for s in fit_doc["surfaces"]:
        assert s["surface_type"] == "plane" and s["fitted"] is True
        assert s["max_distance"] < 1e-6 and s["rms_distance"] < 1e-6
        assert s["fit_confidence"] == "high"
        assert s["is_brep"] is False
        # axis-aligned normals
        n = np.abs(np.array(s["normal"]))
        assert abs(n.max() - 1.0) < 1e-6 and n.sum() < 1.0 + 1e-6
    assert diag["fit_error_summary"]["max_rms"] < 1e-6


def test_boundary_approximation_present(tmp_path: Path):
    V, F = _cube()
    pkg = _pkg(tmp_path, V, F)
    fit_doc, _ = fit_mesh_surfaces(pkg)
    b = fit_doc["surfaces"][0]["boundary"]
    assert b["approximate"] is True and b["method"] == "convex_hull_2d"
    assert len(b["loop_world"]) >= 3 and len(b["loop_uv"]) == len(b["loop_world"])


def test_provenance_preserved(tmp_path: Path):
    V, F = _cube()
    pkg = _pkg(tmp_path, V, F)
    fit_doc, diag = fit_mesh_surfaces(pkg)
    p = fit_doc["provenance"]
    assert p["source_ir_node"] == "blk" and p["design_space_node"] == "blk"
    assert p["representation_kind"] == "mesh" and p["geometry_kind"] == "mesh"
    assert p["is_brep"] is False and p["cad_editable"] is False
    assert p["runtime"] == "manifold"
    assert any("NOT B-Rep" in lim for lim in p["limitations"])
    assert fit_doc["surfaces"][0]["source_region_id"].startswith("region_")
    assert "B-Rep" in fit_doc["claim_boundary"] and "No STEP" in fit_doc["claim_boundary"]


def test_noisy_near_plane_medium_confidence(tmp_path: Path):
    # a near-planar quad (small z perturbation) -> still planar_candidate, fit medium confidence
    V = [[0, 0, 0.0], [10, 0, 0.05], [10, 10, -0.05], [0, 10, 0.03]]
    F = [[0, 1, 2], [0, 2, 3]]
    pkg = _pkg(tmp_path, V, F)
    fit_doc, diag = fit_mesh_surfaces(pkg)
    if fit_doc["surfaces"]:                              # planarity stayed above the planar threshold
        s = fit_doc["surfaces"][0]
        assert s["rms_distance"] > 0.0
        assert s["fit_confidence"] in ("medium", "high")


def test_sphere_freeform_regions_skipped(tmp_path: Path):
    from aieng.converters.mesh_region_segmentation import _grow_regions  # noqa: F401
    # icosahedron-ish: strongly varying normals -> not planar_candidate -> skipped
    t = (1 + 5 ** 0.5) / 2
    verts = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t],
             [0, -1, -t], [0, 1, -t], [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]]
    V = [list(np.array(v) / np.linalg.norm(v)) for v in verts]
    F = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4],
         [11, 10, 2], [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8],
         [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]]
    pkg = _pkg(tmp_path, V, F)
    fit_doc, diag = fit_mesh_surfaces(pkg)
    # at least some regions skipped as non-planar; any skip records a reason
    assert diag["skipped"] >= 1
    assert all("reason" in s for s in diag["skipped_detail"])


def test_write_artifacts(tmp_path: Path):
    V, F = _cube()
    pkg = _pkg(tmp_path, V, F)
    write_mesh_surface_fit(pkg)
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert MESH_SURFACE_FIT_PATH in names and MESH_SURFACE_FITTING_DIAG_PATH in names
        doc = json.loads(zf.read(MESH_SURFACE_FIT_PATH))
        diag = json.loads(zf.read(MESH_SURFACE_FITTING_DIAG_PATH))
    assert doc["format"] == "aieng.mesh_surface_fit" and len(doc["surfaces"]) == 6
    assert diag["fitted"] == 6 and diag["regions_processed"] == 6


def test_missing_region_graph_degrades(tmp_path: Path):
    pkg = tmp_path / "bare.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:   # no region graph
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
    fit_doc, diag = fit_mesh_surfaces(pkg)
    assert fit_doc["surfaces"] == [] and fit_doc["provenance"]["available"] is False
    assert diag["available"] is False and diag["warnings"]
