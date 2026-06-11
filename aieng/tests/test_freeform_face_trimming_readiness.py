"""Focused tests for freeform face trimming readiness v0.

Tests the mesh_freeform_face_trimming_readiness converter:
- boundary quality assessment (existence, closure, self-intersection)
- adjacency/neighbor compatibility assessment
- trimming readiness scoring and classification
- degraded paths (missing faces, no generated faces, missing region graph)
- plan annotation with trimming readiness
- honesty flags
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
    write_freeform_brep_faces,
)
from aieng.converters.mesh_freeform_face_trimming_readiness import (
    TRIMMING_READINESS_PATH,
    assess_freeform_trimming_readiness,
    write_freeform_trimming_readiness,
    _boundary_closed,
    _self_intersection_risk,
    _score_boundary,
)
from aieng.converters.mesh_region_segmentation import write_mesh_region_graph
from aieng.converters.mesh_surface_fitting import write_mesh_surface_fit
from aieng.converters.mesh_brep_reconstruction import build_partial_brep_plan


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


# ── Part A: unit tests for boundary helpers ───────────────────────────────────

def test_boundary_closed_true():
    loop = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    assert _boundary_closed(loop) is True


def test_boundary_closed_false():
    loop = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    assert _boundary_closed(loop) is False


def test_self_intersection_risk_low():
    loop = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    assert _self_intersection_risk(loop) == "low"


def test_self_intersection_risk_high():
    # Bow-tie shape self-intersects
    loop = [[0.0, 0.0], [1.0, 1.0], [1.0, 0.0], [0.0, 1.0], [0.0, 0.0]]
    assert _self_intersection_risk(loop) == "high"


def test_score_boundary_missing():
    score, status, details = _score_boundary(None)
    assert status == "missing"
    assert score == 0.0


def test_score_boundary_good():
    score, status, details = _score_boundary({
        "type": "approximate_uv_loop", "point_count": 8,
        "loop_uv": [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]], "approximate": True,
    })
    assert status == "good"
    assert score == 0.8
    assert details["closed"] is True


# ── Part B: trimming readiness assessment ─────────────────────────────────────

def test_ready_saddle_assessed(tmp_path: Path):
    pytest.importorskip("OCP", reason="OCP/CadQuery not installed")
    verts, faces = _saddle_mesh(n=20)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    write_freeform_brep_faces(pkg)
    readiness = write_freeform_trimming_readiness(pkg)
    assert readiness["format"] == "aieng.mesh.freeform_face_trimming_readiness.v0"
    assert readiness["status"] in ("ready", "partial", "not_ready")
    assert len(readiness["faces"]) >= 1
    face = readiness["faces"][0]
    assert "trimming_readiness" in face
    assert "boundary" in face
    assert "adjacency" in face
    assert 0.0 <= face["quality_score"] <= 1.0


def test_missing_face_candidates_skipped(tmp_path: Path):
    pkg = _write_pkg(tmp_path, [], [])
    readiness = assess_freeform_trimming_readiness(None, None, None, None)
    assert readiness["status"] == "skipped"
    assert readiness["summary"]["recommended_next_action"] == "insufficient_data"


def test_no_generated_faces_skipped(tmp_path: Path):
    faces_doc = {"faces": [{"status": "skipped", "source_region_id": "r1"}], "provenance": {}}
    readiness = assess_freeform_trimming_readiness(faces_doc, None, None, None)
    assert readiness["status"] == "skipped"


def test_honesty_flags_present(tmp_path: Path):
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    write_freeform_brep_faces(pkg)
    readiness = write_freeform_trimming_readiness(pkg)
    honesty = readiness.get("honesty", {})
    assert honesty.get("trimmed_faces_generated") is False
    assert honesty.get("faces_stitched") is False
    assert honesty.get("step_exported") is False
    assert honesty.get("readiness_only") is True


# ── Part C: artifact writing ──────────────────────────────────────────────────

def test_artifact_written_into_package(tmp_path: Path):
    verts, faces = _saddle_mesh(n=16)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    write_freeform_brep_faces(pkg)
    write_freeform_trimming_readiness(pkg)
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert TRIMMING_READINESS_PATH in names


# ── Part D: reconstruction plan annotation ────────────────────────────────────

def test_plan_annotated_with_trimming_readiness(tmp_path: Path):
    pytest.importorskip("OCP", reason="OCP/CadQuery not installed")
    verts, faces = _saddle_mesh(n=20)
    pkg = _write_pkg(tmp_path, verts, faces)
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    write_freeform_brep_faces(pkg)
    write_freeform_trimming_readiness(pkg)
    plan, _surfaces, _diag = build_partial_brep_plan(pkg)
    evidence_rows = [r for r in plan.get("region_plan", [])
                     if r.get("reconstruction_status") == "evidence_only"]
    for row in evidence_rows:
        assert "freeform_trimming_readiness" in row
        assert "freeform_trimming_quality_score" in row
        assert "freeform_trimming_next_action" in row
        assert "can_attempt_future_trimming" in row


# ── Part E: existing analytic path unchanged ──────────────────────────────────

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
    write_freeform_surface_fit(pkg)
    write_freeform_readiness(pkg)
    write_freeform_brep_faces(pkg)
    write_freeform_trimming_readiness(pkg)
    plan, surfaces, diag = build_partial_brep_plan(pkg)
    # Cube should have analytic plane candidates
    assert surfaces["summary"]["plane_candidate_count"] >= 1
    for cand in surfaces.get("face_candidates", []):
        assert cand["surface_type"] in ("plane", "cylinder")
