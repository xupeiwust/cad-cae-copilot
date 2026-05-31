"""Tests for partial B-Rep reconstruction PLANNING from accepted mesh surface fits.

Produces analytic FACE CANDIDATES only — no stitching, no watertight solid, no STEP,
no NURBS, no production-CAD claim.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from aieng.converters.mesh_brep_reconstruction import (  # noqa: E402
    MESH_BREP_PLAN_PATH,
    PARTIAL_BREP_DIAG_PATH,
    PARTIAL_BREP_SURFACES_PATH,
    build_partial_brep_plan,
    plan_partial_brep,
    write_partial_brep_plan,
)

_PROV = {"source_mesh_artifact": "geometry/shape_ir.json#opt", "source_ir_node": "blk",
         "design_space_node": "blk", "runtime": "manifold"}


def _graph(regions, prov=None):
    return {"regions": regions, "adjacency": [], "provenance": prov or _PROV}


def _plane_region(i, area=10.0):
    return {"region_id": f"region_{i:03d}", "area": area, "bbox": [0, 0, 0, 5, 5, 0],
            "surface_class_candidate": "planar_candidate"}


def _plane_surf(i, conf="high", boundary=True):
    s = {"surface_id": f"surface_{i:03d}", "source_region_id": f"region_{i:03d}",
         "surface_type": "plane", "fit_confidence": conf, "origin": [0, 0, 0],
         "normal": [0, 0, 1], "basis_u": [1, 0, 0], "basis_v": [0, 1, 0],
         "rms_distance": 0.0, "max_distance": 0.0}
    if boundary:
        s["boundary"] = {"method": "convex_hull_2d", "approximate": True,
                         "loop_uv": [[0, 0], [5, 0], [5, 5]], "loop_world": [[0, 0, 0], [5, 0, 0], [5, 5, 0]]}
    return s


def _readiness(action="partial_brep_reconstruction", partial=True, full=False):
    return {"readiness": {"partial_brep_candidate": partial, "full_brep_candidate": full,
                          "recommended_next_action": action}, "provenance": _PROV}


# ── candidate generation (pure) ──────────────────────────────────────────────

def test_cube_six_planes_produce_six_face_candidates():
    regions = [_plane_region(i) for i in range(6)]
    surfaces = [_plane_surf(i) for i in range(6)]
    plan, surfaces_doc, diag = plan_partial_brep(
        _graph(regions), {"surfaces": surfaces, "provenance": _PROV},
        _readiness(full=True))
    s = surfaces_doc["summary"]
    assert s["candidate_face_count"] == 6 and s["plane_candidate_count"] == 6
    assert s["can_attempt_partial_brep"] is True
    fc = surfaces_doc["face_candidates"][0]
    assert fc["surface_type"] == "plane" and fc["reconstruction_status"] == "candidate"
    assert fc["analytic"]["normal"] == [0, 0, 1] and fc["boundary"]["loop_world"]
    assert fc["boundary"]["boundary_source"] == "convex_hull_2d"
    # honesty
    assert surfaces_doc["provenance"]["full_solid"] is False
    assert surfaces_doc["provenance"]["watertight"] is False
    assert surfaces_doc["provenance"]["step_exported"] is False
    assert surfaces_doc["provenance"]["reconstructed_faces_are_candidates"] is True


def test_cylinder_produces_one_cylinder_face_candidate():
    regions = [{"region_id": "region_000", "area": 50.0, "bbox": [0, 0, 0, 6, 6, 10],
                "surface_class_candidate": "freeform_candidate"}]
    surfaces = [{"surface_id": "surface_000", "source_region_id": "region_000",
                 "surface_type": "cylinder", "fit_confidence": "high",
                 "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": 3.0,
                 "axial_range": [0, 10], "rms_radial": 0.0, "max_radial": 0.0,
                 "normal_consistency": 1.0}]
    _plan, surfaces_doc, _diag = plan_partial_brep(
        _graph(regions), {"surfaces": surfaces, "provenance": _PROV}, _readiness())
    assert surfaces_doc["summary"]["cylinder_candidate_count"] == 1
    fc = surfaces_doc["face_candidates"][0]
    assert fc["surface_type"] == "cylinder"
    assert fc["analytic"]["radius"] == 3.0 and fc["analytic"]["axis_direction"] == [0, 0, 1]
    assert fc["boundary"]["boundary_source"] == "axial_range"
    assert surfaces_doc["summary"]["can_attempt_full_brep"] is False   # one face is not a solid


def test_low_confidence_or_no_boundary_skipped():
    regions = [_plane_region(0), _plane_region(1)]
    surfaces = [_plane_surf(0, conf="low"),            # low confidence -> skip
                _plane_surf(1, boundary=False)]        # no boundary -> skip
    _plan, surfaces_doc, diag = plan_partial_brep(
        _graph(regions), {"surfaces": surfaces, "provenance": _PROV}, _readiness())
    assert surfaces_doc["summary"]["candidate_face_count"] == 0
    reasons = " ".join(s["reason"] for s in diag["skipped"])
    assert "low-confidence" in reasons and "boundary" in reasons


def test_freeform_region_skipped():
    regions = [_plane_region(0), {"region_id": "region_001", "area": 30.0,
                                  "surface_class_candidate": "freeform_candidate", "bbox": [0, 0, 0, 5, 5, 5]}]
    surfaces = [_plane_surf(0)]                        # only region_000 fitted
    _plan, surfaces_doc, diag = plan_partial_brep(
        _graph(regions), {"surfaces": surfaces, "provenance": _PROV}, _readiness())
    assert surfaces_doc["summary"]["candidate_face_count"] == 1
    assert any("freeform" in s["reason"] for s in diag["skipped"])


def test_readiness_insufficient_produces_no_candidates():
    regions = [_plane_region(i) for i in range(6)]
    surfaces = [_plane_surf(i) for i in range(6)]
    _plan, surfaces_doc, diag = plan_partial_brep(
        _graph(regions), {"surfaces": surfaces, "provenance": _PROV},
        _readiness(action="insufficient_data"))
    assert surfaces_doc["summary"]["candidate_face_count"] == 0
    assert diag["gated"] is True and diag["warnings"]


def test_mesh_cleanup_gates_out_candidates():
    regions = [_plane_region(i) for i in range(6)]
    surfaces = [_plane_surf(i) for i in range(6)]
    _plan, surfaces_doc, _diag = plan_partial_brep(
        _graph(regions), {"surfaces": surfaces, "provenance": _PROV},
        _readiness(action="mesh_cleanup"))
    assert surfaces_doc["summary"]["candidate_face_count"] == 0
    assert surfaces_doc["summary"]["can_attempt_partial_brep"] is False


def test_provenance_and_honesty_preserved():
    regions = [_plane_region(i) for i in range(6)]
    surfaces = [_plane_surf(i) for i in range(6)]
    plan, surfaces_doc, diag = plan_partial_brep(
        _graph(regions), {"surfaces": surfaces, "provenance": _PROV}, _readiness(full=True))
    for doc in (plan, surfaces_doc, diag):
        p = doc["provenance"]
        assert p["source_ir_node"] == "blk" and p["design_space_node"] == "blk"
        assert p["is_brep"] is False and p["cad_editable"] == "candidate_only"
        assert p["step_exported"] is False
    assert "not a watertight solid" in surfaces_doc["claim_boundary"].lower() \
        or "watertight" in surfaces_doc["claim_boundary"].lower()


def test_missing_inputs_degrade():
    plan, surfaces_doc, diag = plan_partial_brep(None, None, None)
    assert surfaces_doc["summary"]["candidate_face_count"] == 0
    assert diag["available"] is False and diag["warnings"]


# ── package integration (real pipeline) ──────────────────────────────────────

def _cube_pkg(tmp_path: Path) -> Path:
    from aieng.converters.mesh_region_segmentation import write_mesh_region_graph
    from aieng.converters.mesh_surface_fitting import write_mesh_surface_fit
    from aieng.converters.mesh_reconstruction_readiness import write_mesh_reconstruction_readiness
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
    return pkg


def test_package_cube_produces_face_candidate_artifacts(tmp_path: Path):
    pkg = _cube_pkg(tmp_path)
    plan = write_partial_brep_plan(pkg)
    assert plan["summary"]["candidate_face_count"] == 6
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert MESH_BREP_PLAN_PATH in names
        assert PARTIAL_BREP_SURFACES_PATH in names
        assert PARTIAL_BREP_DIAG_PATH in names
        surfaces = json.loads(zf.read(PARTIAL_BREP_SURFACES_PATH))
        # no STEP exported by default
        assert not any(n.lower().endswith(".step") or n.lower().endswith(".stp") for n in names)
    assert len(surfaces["face_candidates"]) == 6
    assert surfaces["provenance"]["source_ir_node"] == "blk"
    assert surfaces["provenance"]["step_exported"] is False
