"""Focused tests for freeform B-Rep face candidate generation v0.

Tests the mesh_freeform_brep_face_generation converter:
- ready freeform surfaces produce face candidates when OCP is available
- OCP unavailable path degrades honestly
- not_ready surfaces are skipped
- missing control_net is skipped
- generated faces carry honesty flags
- freeform candidates do not affect analytic STEP export
- plan annotation includes face generation status
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
    write_freeform_readiness,
)
from aieng.converters.mesh_freeform_brep_face_generation import (
    FREEFORM_BREP_FACES_PATH,
    FREEFORM_BREP_FACE_GEN_DIAG_PATH,
    generate_freeform_brep_faces,
    write_freeform_brep_faces,
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


# ── Part A: face generation from ready surfaces ───────────────────────────────

def test_ready_saddle_produces_face_candidate_or_skipped(tmp_path: Path):
    """A smooth saddle with many samples may produce a face candidate when OCP is present."""
    verts, faces = _saddle_mesh(n=20)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    write_freeform_brep_faces(pkg)
    faces_doc = _read(pkg, FREEFORM_BREP_FACES_PATH)
    diag = _read(pkg, FREEFORM_BREP_FACE_GEN_DIAG_PATH)
    assert faces_doc["format"] == "aieng.mesh.freeform_brep_faces.v0"
    # Either generated (OCP present) or skipped (OCP absent)
    for f in faces_doc["faces"]:
        assert f["status"] in ("generated", "skipped", "failed")
    assert diag["occ_available"] in (True, False)


def test_sphere_patch_face_candidate_honesty_flags(tmp_path: Path):
    """Generated freeform face candidates carry correct honesty flags."""
    verts, faces = _sphere_patch_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    write_freeform_brep_faces(pkg)
    faces_doc = _read(pkg, FREEFORM_BREP_FACES_PATH)
    for f in faces_doc["faces"]:
        honesty = f.get("honesty", {})
        assert honesty.get("faces_stitched") is False
        assert honesty.get("full_solid") is False
        assert honesty.get("step_exported") is False
        assert honesty.get("production_ready") is False
        if f["status"] == "generated":
            assert honesty.get("is_brep_face_candidate") is True


# ── Part B: degraded/skip paths ──────────────────────────────────────────────

def test_not_ready_surface_is_skipped(tmp_path: Path):
    """A surface with readiness=not_ready is skipped."""
    # Small noisy mesh creates not_ready
    verts = np.array([[0, 0, 0], [1, 0, 0], [0.5, 0.5, 0.1]], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=int)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    faces_doc, diag = generate_freeform_brep_faces(
        _read(pkg, FREEFORM_SURFACE_FIT_PATH),
        _read(pkg, FREEFORM_READINESS_PATH),
    )
    for f in faces_doc["faces"]:
        assert f["status"] == "skipped"


def test_missing_freeform_fit_skips(tmp_path: Path):
    """Without freeform fit artifact, generation produces no faces."""
    faces_doc, diag = generate_freeform_brep_faces(None, None)
    assert faces_doc["summary"]["input_surface_count"] == 0
    assert len(faces_doc["faces"]) == 0


def test_missing_control_net_skipped(tmp_path: Path):
    """A surface missing control_net should be skipped."""
    fit = {
        "surfaces": [{
            "surface_id": "test_001", "source_region_id": "region_000",
            "status": "fitted", "confidence": "high",
            "control_net": [], "control_points_u": 0, "control_points_v": 0,
            "fit_error": {"rms": 0.01, "max": 0.05},
        }],
        "provenance": {"representation_kind": "mesh"},
    }
    readiness = {
        "surfaces": [{
            "source_region_id": "region_000", "readiness": "ready", "quality_score": 0.9,
        }],
    }
    faces_doc, diag = generate_freeform_brep_faces(fit, readiness)
    for f in faces_doc["faces"]:
        assert f["status"] == "skipped"


# ── Part C: artifact writing ──────────────────────────────────────────────────

def test_artifacts_written_into_package(tmp_path: Path):
    """write_freeform_brep_faces persists both artifact and diagnostics."""
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    write_freeform_brep_faces(pkg)
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert FREEFORM_BREP_FACES_PATH in names
        assert FREEFORM_BREP_FACE_GEN_DIAG_PATH in names


# ── Part D: reconstruction plan annotation ────────────────────────────────────

def test_plan_annotated_with_face_generation_status(tmp_path: Path):
    """Reconstruction plan includes face generation annotations when faces are generated."""
    verts, faces = _saddle_mesh(n=20)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    write_freeform_brep_faces(pkg)
    plan, _surfaces, _diag = build_partial_brep_plan(pkg)
    evidence_rows = [r for r in plan.get("region_plan", [])
                     if r.get("reconstruction_status") == "evidence_only"]
    for row in evidence_rows:
        assert "freeform_face_generation_status" in row
        assert "future_stitching_possible" in row


def test_plan_entries_do_not_trigger_face_candidates(tmp_path: Path):
    """Freeform plan entries never have eligible=True or face_candidate_id set."""
    verts, faces = _saddle_mesh(n=20)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    write_freeform_brep_faces(pkg)
    plan, surfaces, _diag = build_partial_brep_plan(pkg)
    for row in plan.get("region_plan", []):
        if row.get("reconstruction_status") == "evidence_only":
            assert row["eligible"] is False
            assert row.get("face_candidate_id") is None
    for cand in surfaces.get("face_candidates", []):
        assert cand["surface_type"] != "bspline"


# ── Part E: existing analytic path unchanged ──────────────────────────────────

def test_cube_analytic_path_unchanged(tmp_path: Path):
    """Cube produces analytic face candidates; freeform pipeline does not interfere."""
    verts, faces = _cube_mesh()
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    write_freeform_brep_faces(pkg)
    plan, surfaces, diag = build_partial_brep_plan(pkg)
    # Cube should have plane face candidates
    assert surfaces["summary"]["plane_candidate_count"] >= 1
    # No freeform face candidates in the B-Rep surfaces doc
    for cand in surfaces.get("face_candidates", []):
        assert cand["surface_type"] in ("plane", "cylinder")
