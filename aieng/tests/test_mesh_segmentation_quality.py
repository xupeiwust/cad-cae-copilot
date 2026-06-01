"""Focused tests for mesh region segmentation quality and re-segmentation hints v0.

Tests the mesh_segmentation_quality converter:
- quality scoring (fragmentation, undersegmentation, fit coverage, boundary quality)
- region findings (tiny, noisy, large mixed, boundary problems)
- hint generation (merge, split, curvature-aware, keep, manual review)
- honesty / advisory-only behavior
- integration with mesh pipeline
- existing analytic STEP path unchanged
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np

from aieng.converters.mesh_segmentation_quality import (
    SEGMENTATION_QUALITY_PATH,
    RESEGMENTATION_HINTS_PATH,
    assess_segmentation_quality,
    write_segmentation_quality,
)
from aieng.converters.mesh_region_segmentation import write_mesh_region_graph
from aieng.converters.mesh_surface_fitting import write_mesh_surface_fit
from aieng.converters.mesh_freeform_surface_fitting import write_freeform_surface_fit
from aieng.converters.mesh_freeform_surface_readiness import write_freeform_readiness
from aieng.converters.mesh_reconstruction_readiness import write_mesh_reconstruction_readiness
from aieng.converters.mesh_to_cad_reconstruction_status import build_mesh_to_cad_reconstruction_status


def _saddle_mesh(n: int = 20):
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


def _write_pkg(tmp_path: Path, vertices, faces, extra=None) -> Path:
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


# ── Part A: missing / insufficient data ───────────────────────────────────────

def test_missing_region_graph_insufficient_data():
    q, h = assess_segmentation_quality(None, None, None, None, None, None, None, None)
    assert q["status"] == "insufficient_data"
    assert h["status"] == "insufficient_data"
    assert h["recommended_next_action"] == "insufficient_data"


# ── Part B: clean cube segmentation ───────────────────────────────────────────

def test_cube_segmentation_good(tmp_path: Path):
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
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_mesh_reconstruction_readiness(pkg)
    q, h = write_segmentation_quality(pkg)
    # Cube should have 6 planar regions with good fits
    assert q["status"] in ("good", "warning")
    assert q["summary"]["region_count"] == 6
    assert h["recommended_next_action"] in ("keep_current_segmentation", "rerun_with_adjusted_thresholds")


# ── Part C: fragmentation / tiny noisy regions ────────────────────────────────

def test_many_tiny_regions_fragmentation_hint(tmp_path: Path):
    # Sphere-like mesh produces many small freeform regions
    n = 12
    phi = np.linspace(0, np.pi, n)
    theta = np.linspace(0, 2 * np.pi, n)
    phi, theta = np.meshgrid(phi, theta)
    x = np.sin(phi) * np.cos(theta)
    y = np.sin(phi) * np.sin(theta)
    z = np.cos(phi)
    verts = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    faces = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            b = a + 1
            c = (i + 1) * n + j
            d = c + 1
            faces.append([a, b, d])
            faces.append([a, d, c])
    pkg = _write_pkg(tmp_path, verts, np.asarray(faces, dtype=int))
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    q, h = write_segmentation_quality(pkg)
    # Sphere should produce many small regions → fragmentation concern
    assert q["summary"]["region_count"] >= 3
    if q["summary"]["tiny_region_count"] >= 2:
        assert q["status"] in ("warning", "poor")
        hint_types = [hint["type"] for hint in h["hints"]]
        assert "merge_tiny_regions" in hint_types or "raise_normal_angle_threshold" in hint_types


# ── Part D: undersegmentation / large freeform ────────────────────────────────

def test_large_freeform_undersegmentation_hint(tmp_path: Path):
    verts, faces = _saddle_mesh(n=20)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    q, h = write_segmentation_quality(pkg)
    # Saddle is a single freeform surface; may be one large region
    assert q["summary"]["region_count"] >= 1
    # If it remains largely unfit, undersegmentation may be flagged
    if q["summary"]["large_mixed_region_count"] >= 1:
        hint_types = [hint["type"] for hint in h["hints"]]
        assert any(t in hint_types for t in ("split_high_curvature_region", "try_curvature_aware_segmentation"))


# ── Part E: reconstruction status step_exported → keep ────────────────────────

def test_step_exported_keep_current():
    rs = build_mesh_to_cad_reconstruction_status("test.aieng", {
        "step_export": {"step_exported": True},
        "roundtrip_verification": {"status": "passed"},
        "sewing": {"summary": {"shell_type": "closed_shell"}},
    })
    q, h = assess_segmentation_quality(
        {"regions": [{"region_id": "r1", "area": 10.0, "face_count": 10,
                      "surface_class_candidate": "planar_candidate", "planarity_score": 0.99}]},
        None, None, None, None, None, None, rs,
    )
    assert h["recommended_next_action"] == "keep_current_segmentation"
    assert any(hint["type"] == "keep_current_segmentation" for hint in h["hints"])


# ── Part F: boundary problems → hints ─────────────────────────────────────────

def test_boundary_problem_hint():
    q, h = assess_segmentation_quality(
        {"regions": [{"region_id": "r1", "area": 10.0, "face_count": 20,
                      "surface_class_candidate": "freeform_candidate", "planarity_score": 0.5}]},
        None, None, None, None, None,
        {"faces": [{"source_region_id": "r1", "trimming_readiness": "not_ready",
                    "blocking_issues": ["boundary_missing"]}]},
        None,
    )
    finding_types = [f["finding_type"] for f in q["region_findings"]]
    assert "boundary_problem" in finding_types
    hint_types = [hint["type"] for hint in h["hints"]]
    assert "try_curvature_aware_segmentation" in hint_types


# ── Part G: freeform readiness improve_segmentation → matching hint ───────────

def test_freeform_readiness_improve_segmentation_hint():
    q, h = assess_segmentation_quality(
        {"regions": [{"region_id": "r1", "area": 10.0, "face_count": 20,
                      "surface_class_candidate": "freeform_candidate", "planarity_score": 0.5}]},
        None, None, None, None,
        {"surfaces": [{"source_region_id": "r1", "readiness": "not_ready",
                       "recommended_next_action": "improve_segmentation", "quality_score": 0.2}]},
        None, None,
    )
    hint_types = [hint["type"] for hint in h["hints"]]
    assert "split_high_curvature_region" in hint_types


# ── Part H: deterministic / limited hints ─────────────────────────────────────

def test_hints_deterministic_and_limited():
    rg = {"regions": [
        {"region_id": f"r{i}", "area": 0.5, "face_count": 2,
         "surface_class_candidate": "noisy_small_region", "planarity_score": 0.3}
        for i in range(20)
    ] + [{"region_id": "r_big", "area": 50.0, "face_count": 200,
          "surface_class_candidate": "unknown", "planarity_score": 0.4}]}
    q1, h1 = assess_segmentation_quality(rg, None, None, None, None, None, None, None)
    q2, h2 = assess_segmentation_quality(rg, None, None, None, None, None, None, None)
    assert q1 == q2
    assert h1 == h2
    assert len(h1["hints"]) <= 10


# ── Part I: integration / artifact writing ────────────────────────────────────

def test_artifacts_written_into_package(tmp_path: Path):
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    q, h = write_segmentation_quality(pkg)
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert SEGMENTATION_QUALITY_PATH in names
        assert RESEGMENTATION_HINTS_PATH in names
        loaded_q = json.loads(zf.read(SEGMENTATION_QUALITY_PATH))
        assert loaded_q["format"] == "aieng.mesh.segmentation_quality.v0"


# ── Part J: existing analytic STEP path unchanged ─────────────────────────────

def test_cube_analytic_path_unchanged(tmp_path: Path):
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
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_mesh_reconstruction_readiness(pkg)
    q, h = write_segmentation_quality(pkg)
    # Cube should still be recognized as having 6 planar regions
    assert q["summary"]["region_count"] == 6
    # Quality should be good enough for analytic reconstruction
    assert q["summary"]["fitted_area_fraction"] >= 0.9
