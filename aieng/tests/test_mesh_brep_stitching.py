"""Tests for B-Rep stitching readiness + edge matching (plan only).

No sewing, no shell/solid, no STEP. Edge matching is approximate, toward a future shell.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from aieng.converters.mesh_brep_stitching import (  # noqa: E402
    MESH_BREP_STITCHING_PLAN_PATH,
    MESH_BREP_STITCHING_READINESS_PATH,
    build_brep_stitching_plan,
    plan_brep_stitching,
    write_brep_stitching_plan,
)

_PROV = {"source_mesh_artifact": "geometry/shape_ir.json#opt", "source_ir_node": "blk",
         "design_space_node": "blk", "runtime": "manifold"}

# unit-cube vertices + 6 quad faces (shared edges have identical endpoints)
_CV = {0: [0, 0, 0], 1: [1, 0, 0], 2: [1, 1, 0], 3: [0, 1, 0],
       4: [0, 0, 1], 5: [1, 0, 1], 6: [1, 1, 1], 7: [0, 1, 1]}
_CUBE_FACES = {  # region index -> quad vertex ids
    0: [0, 1, 2, 3], 1: [4, 5, 6, 7], 2: [0, 1, 5, 4],
    3: [3, 2, 6, 7], 4: [1, 2, 6, 5], 5: [0, 3, 7, 4]}
# region adjacency = face pairs sharing a cube edge
_CUBE_ADJ_PAIRS = [(0, 2), (0, 3), (0, 4), (0, 5), (1, 2), (1, 3), (1, 4), (1, 5),
                   (2, 4), (2, 5), (3, 4), (3, 5)]


def _loop(ids):
    return [list(_CV[i]) for i in ids]


def _faces_doc(region_ids):
    return {"faces": [{"face_id": f"face_cand_{i:03d}", "source_region_id": f"region_{i:03d}",
                       "source_surface_id": f"surface_{i:03d}", "face_type": "plane",
                       "status": "generated", "fit_confidence": "high"} for i in region_ids],
            "provenance": _PROV}


def _surfaces_doc(region_ids):
    return {"face_candidates": [{"face_candidate_id": f"face_cand_{i:03d}",
                                 "source_region_id": f"region_{i:03d}", "surface_type": "plane",
                                 "boundary": {"loop_world": _loop(_CUBE_FACES[i])}} for i in region_ids],
            "provenance": _PROV}


def _region_graph(region_ids, pairs):
    return {"regions": [{"region_id": f"region_{i:03d}", "area": 1.0,
                         "surface_class_candidate": "planar_candidate"} for i in region_ids],
            "adjacency": [{"region_a": f"region_{a:03d}", "region_b": f"region_{b:03d}",
                           "shared_boundary_edges": 1} for a, b in pairs],
            "provenance": _PROV}


# ── readiness ────────────────────────────────────────────────────────────────

def test_cube_six_faces_closed_shell_ready():
    ids = list(range(6))
    plan, readiness = plan_brep_stitching(_faces_doc(ids), _surfaces_doc(ids),
                                          _region_graph(ids, _CUBE_ADJ_PAIRS))
    s = plan["summary"]
    assert s["generated_face_count"] == 6 and s["boundary_edge_count"] == 24
    assert s["matched_edge_pair_count"] == 12 and s["unmatched_edge_count"] == 0
    assert s["adjacency_covered_fraction"] == 1.0
    assert s["can_attempt_partial_shell"] is True and s["can_attempt_closed_shell"] is True
    assert s["confidence"] == "high"
    # honesty
    p = plan["provenance"]
    assert p["shell_created"] is False and p["solid_created"] is False
    assert p["step_exported"] is False and p["stitching_plan_only"] is True


def test_missing_one_face_partial_not_closed():
    ids = list(range(5))   # drop face/region 5
    plan, readiness = plan_brep_stitching(_faces_doc(ids), _surfaces_doc(ids),
                                          _region_graph(list(range(6)), _CUBE_ADJ_PAIRS))
    s = plan["summary"]
    assert s["can_attempt_partial_shell"] is True
    assert s["can_attempt_closed_shell"] is False     # open boundary remains
    assert s["unmatched_edge_count"] > 0
    assert any(b["issue"] == "unreconstructed_neighbor_regions" for b in readiness["blocking_issues"])


def test_gapped_edges_block_and_flag():
    # two coplanar quads that SHOULD share an edge but are offset by ~1.8*tol -> near-miss
    # face A: x in [0,1]; face B: x in [1.03, 2.03] (gap 0.03; bbox diag ~2.4 -> tol ~0.024)
    fa = {"faces": [{"face_id": "face_cand_000", "source_region_id": "region_000",
                     "source_surface_id": "s0", "face_type": "plane", "status": "generated",
                     "fit_confidence": "high"},
                    {"face_id": "face_cand_001", "source_region_id": "region_001",
                     "source_surface_id": "s1", "face_type": "plane", "status": "generated",
                     "fit_confidence": "high"}],
          "provenance": _PROV}
    sd = {"face_candidates": [
        {"face_candidate_id": "face_cand_000", "source_region_id": "region_000", "surface_type": "plane",
         "boundary": {"loop_world": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]}},
        {"face_candidate_id": "face_cand_001", "source_region_id": "region_001", "surface_type": "plane",
         "boundary": {"loop_world": [[1.03, 0, 0], [2.03, 0, 0], [2.03, 1, 0], [1.03, 1, 0]]}}],
        "provenance": _PROV}
    rg = _region_graph([0, 1], [(0, 1)])
    plan, readiness = plan_brep_stitching(fa, sd, rg)
    assert plan["summary"]["matched_edge_pair_count"] == 0
    assert plan["summary"]["unmatched_edge_count"] > 0
    issues = {b["issue"] for b in readiness["blocking_issues"]}
    assert "large_edge_gaps" in issues
    assert readiness["edge_gap_statistics"]["near_miss_pairs"] >= 1


def test_cylinder_insufficient_boundary_no_false_matches():
    fa = {"faces": [{"face_id": "face_cand_000", "source_region_id": "region_000",
                     "source_surface_id": "s0", "face_type": "cylinder", "status": "generated",
                     "fit_confidence": "high"}], "provenance": _PROV}
    sd = {"face_candidates": [{"face_candidate_id": "face_cand_000", "source_region_id": "region_000",
                               "surface_type": "cylinder",
                               "analytic": {"axis_origin": [0, 0, 0], "axis_direction": [0, 0, 1],
                                            "radius": 3.0, "axial_range": [0, 10]},
                               "boundary": {"boundary_source": "axial_range", "axial_range": [0, 10]}}],
          "provenance": _PROV}   # no angular_range -> no edges
    plan, readiness = plan_brep_stitching(fa, sd, _region_graph([0], []))
    assert plan["summary"]["boundary_edge_count"] == 0
    assert plan["summary"]["matched_edge_pair_count"] == 0
    assert "face_cand_000" in readiness["faces_without_boundary"]
    assert any(b["issue"] == "missing_boundaries" for b in readiness["blocking_issues"])


def test_non_adjacent_faces_not_high_confidence():
    # two quads that coincide on an edge but whose regions are NOT adjacent in the graph
    fa = _faces_doc([0, 2])
    sd = _surfaces_doc([0, 2])     # regions 0 & 2 share cube edge (0,1)
    rg = _region_graph([0, 2], [])  # adjacency intentionally empty
    plan, readiness = plan_brep_stitching(fa, sd, rg)
    matches = plan["edge_matches"]
    assert matches and all(m["confidence"] == "low" and m["region_adjacent"] is False for m in matches)
    assert readiness["adjacency_prior"]["high_confidence_matches"] == 0


def test_provenance_preserved_and_missing_degrades():
    plan, readiness = plan_brep_stitching(None, None, None)
    assert plan["summary"]["matched_edge_pair_count"] == 0
    assert readiness["available"] is False and readiness["warnings"]
    ids = list(range(6))
    plan2, _ = plan_brep_stitching(_faces_doc(ids), _surfaces_doc(ids), _region_graph(ids, _CUBE_ADJ_PAIRS))
    assert plan2["provenance"]["source_ir_node"] == "blk" and plan2["provenance"]["design_space_node"] == "blk"


# ── package integration ──────────────────────────────────────────────────────

def test_package_cube_writes_plan_no_step(tmp_path: Path):
    from aieng.converters.mesh_region_segmentation import write_mesh_region_graph
    from aieng.converters.mesh_surface_fitting import write_mesh_surface_fit
    from aieng.converters.mesh_reconstruction_readiness import write_mesh_reconstruction_readiness
    from aieng.converters.mesh_brep_reconstruction import write_partial_brep_plan
    pytest.importorskip("OCP")
    from aieng.converters.mesh_brep_face_generation import write_brep_faces
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
    write_brep_faces(pkg)
    plan = write_brep_stitching_plan(pkg)
    assert plan["summary"]["matched_edge_pair_count"] >= 1
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert MESH_BREP_STITCHING_PLAN_PATH in names and MESH_BREP_STITCHING_READINESS_PATH in names
        assert not any(n.lower().endswith((".step", ".stp")) for n in names)
    assert plan["provenance"]["step_exported"] is False and plan["provenance"]["shell_created"] is False
