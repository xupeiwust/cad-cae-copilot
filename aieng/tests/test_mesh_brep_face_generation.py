"""Tests for analytic B-Rep FACE generation from partial B-Rep face candidates.

Generates + validates real OCC faces as an intermediate artifact only — no stitching,
no watertight solid, no STEP export, no production-CAD claim.
"""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("OCP")   # OCC kernel (build123d) required to generate faces

from aieng.converters.mesh_brep_face_generation import (  # noqa: E402
    PARTIAL_BREP_FACES_PATH,
    PARTIAL_BREP_FACE_GEN_DIAG_PATH,
    build_brep_faces,
    generate_brep_faces,
    write_brep_faces,
)

_PROV = {"source_mesh_artifact": "geometry/shape_ir.json#opt", "source_ir_node": "blk",
         "design_space_node": "blk", "runtime": "manifold"}


def _plane_candidate(i, loop):
    return {"face_candidate_id": f"face_cand_{i:03d}", "source_region_id": f"region_{i:03d}",
            "source_surface_id": f"surface_{i:03d}", "surface_type": "plane", "fit_confidence": "high",
            "analytic": {"origin": [0, 0, 0], "normal": [0, 0, 1]},
            "boundary": {"boundary_source": "convex_hull_2d", "loop_world": loop}}


def _surfaces(cands):
    return {"face_candidates": cands, "provenance": _PROV}


# ── face generation ──────────────────────────────────────────────────────────

def test_six_plane_candidates_generate_six_faces():
    squares = [
        [[0, 0, 0], [5, 0, 0], [5, 5, 0], [0, 5, 0]],
        [[0, 0, 1], [5, 0, 1], [5, 5, 1], [0, 5, 1]],
        [[0, 0, 0], [5, 0, 0], [5, 0, 1], [0, 0, 1]],
        [[0, 5, 0], [5, 5, 0], [5, 5, 1], [0, 5, 1]],
        [[5, 0, 0], [5, 5, 0], [5, 5, 1], [5, 0, 1]],
        [[0, 0, 0], [0, 5, 0], [0, 5, 1], [0, 0, 1]],
    ]
    cands = [_plane_candidate(i, sq) for i, sq in enumerate(squares)]
    faces_doc, diag = generate_brep_faces(_surfaces(cands))
    assert faces_doc["summary"]["generated_face_count"] == 6
    assert faces_doc["summary"]["generated_plane_count"] == 6
    assert faces_doc["summary"]["can_attempt_stitching"] is True
    for f in faces_doc["faces"]:
        assert f["status"] == "generated" and f["face_type"] == "plane"
        assert f["geometry_validation"]["valid"] is True and f["geometry_validation"]["area"] > 0
    # honesty
    p = faces_doc["provenance"]
    assert p["full_solid"] is False and p["watertight"] is False and p["step_exported"] is False
    assert p["cad_editable"] == "candidate_faces_only" and p["faces_stitched"] is False


def test_degenerate_boundary_skipped():
    # 3 collinear points -> zero-area / invalid -> skipped (not generated)
    cand = _plane_candidate(0, [[0, 0, 0], [1, 0, 0], [2, 0, 0]])
    faces_doc, _ = generate_brep_faces(_surfaces([cand]))
    f = faces_doc["faces"][0]
    assert f["status"] in ("skipped", "failed") and f["status"] != "generated"
    assert faces_doc["summary"]["generated_face_count"] == 0


def test_cylinder_without_angular_is_skipped_insufficient():
    cand = {"face_candidate_id": "face_cand_000", "source_region_id": "region_000",
            "source_surface_id": "surface_000", "surface_type": "cylinder", "fit_confidence": "high",
            "analytic": {"axis_origin": [0, 0, 0], "axis_direction": [0, 0, 1], "radius": 3.0,
                         "axial_range": [0, 10]},
            "boundary": {"boundary_source": "axial_range", "axial_range": [0, 10]}}  # no angular_range
    faces_doc, _ = generate_brep_faces(_surfaces([cand]))
    f = faces_doc["faces"][0]
    assert f["status"] == "skipped" and "insufficient" in f["reason"]


def test_cylinder_with_angular_bounds_generates_face():
    cand = {"face_candidate_id": "face_cand_000", "source_region_id": "region_000",
            "source_surface_id": "surface_000", "surface_type": "cylinder", "fit_confidence": "high",
            "analytic": {"axis_origin": [0, 0, 0], "axis_direction": [0, 0, 1], "radius": 3.0,
                         "axial_range": [0, 10]},
            "boundary": {"boundary_source": "axial_range", "axial_range": [0, 10],
                         "angular_range": [0.0, math.pi / 2]}}
    faces_doc, _ = generate_brep_faces(_surfaces([cand]))
    f = faces_doc["faces"][0]
    assert f["status"] == "generated" and f["face_type"] == "cylinder"
    # area = r * angular_span * axial_span = 3 * (pi/2) * 10
    assert abs(f["geometry_validation"]["area"] - 3.0 * (math.pi / 2) * 10) < 1e-3
    assert faces_doc["summary"]["generated_cylinder_count"] == 1


def test_provenance_preserved():
    cand = _plane_candidate(0, [[0, 0, 0], [5, 0, 0], [5, 5, 0], [0, 5, 0]])
    faces_doc, diag = generate_brep_faces(_surfaces([cand]))
    for doc in (faces_doc, diag):
        p = doc["provenance"]
        assert p["source_ir_node"] == "blk" and p["design_space_node"] == "blk"
        assert p["is_brep"] is False and p["step_exported"] is False
    assert faces_doc["faces"][0]["source_region_id"] == "region_000"
    assert "STEP" in faces_doc["claim_boundary"]


# ── package integration (real pipeline) ──────────────────────────────────────

def test_package_cube_generates_faces_no_step(tmp_path: Path):
    from aieng.converters.mesh_region_segmentation import write_mesh_region_graph
    from aieng.converters.mesh_surface_fitting import write_mesh_surface_fit
    from aieng.converters.mesh_reconstruction_readiness import write_mesh_reconstruction_readiness
    from aieng.converters.mesh_brep_reconstruction import write_partial_brep_plan
    V = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]
    F = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
         [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [0, 4, 7], [0, 7, 3]]
    node = {"id": "optimized_blk", "type": "smooth_mesh_proxy", "dimension": 3, "vertices": V, "faces": F,
            "source_optimization": {"design_space_node": "blk", "source_ir_node": "blk"}}
    manifest = {"format": "aieng.conversion_manifest",
                "geometry_execution": {"executed": True, "geometry_kind": "mesh",
                                       "representation_kind": "mesh", "actual_runtime": "manifold"}}
    pkg = tmp_path / "c.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", json.dumps({"representation": "manifold_mesh", "parts": [node]}))
        zf.writestr("provenance/conversion_manifest.json", json.dumps(manifest))
    write_mesh_region_graph(pkg)
    write_mesh_surface_fit(pkg)
    write_mesh_reconstruction_readiness(pkg)
    write_partial_brep_plan(pkg)
    faces_doc = write_brep_faces(pkg)
    assert faces_doc["summary"]["generated_face_count"] == 6
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert PARTIAL_BREP_FACES_PATH in names and PARTIAL_BREP_FACE_GEN_DIAG_PATH in names
        assert not any(n.lower().endswith((".step", ".stp")) for n in names)   # no STEP
        doc = json.loads(zf.read(PARTIAL_BREP_FACES_PATH))
    assert doc["provenance"]["step_exported"] is False and doc["provenance"]["source_ir_node"] == "blk"


def test_missing_surfaces_input_degrades(tmp_path: Path):
    pkg = tmp_path / "bare.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
    faces_doc, diag = build_brep_faces(pkg)
    assert faces_doc["summary"]["generated_face_count"] == 0 and faces_doc["faces"] == []
