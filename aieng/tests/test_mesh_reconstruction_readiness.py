"""Tests for mesh reconstruction readiness analysis.

Analysis only — judges analytic-fit coverage of a mesh; never reconstructs B-Rep,
exports STEP, or claims CAD editability.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from aieng.converters.mesh_reconstruction_readiness import (  # noqa: E402
    MESH_RECONSTRUCTION_PLAN_PATH,
    MESH_RECONSTRUCTION_READINESS_PATH,
    assess_reconstruction_readiness,
    build_mesh_reconstruction_readiness,
    write_mesh_reconstruction_readiness,
)


def _graph(regions, adjacency=None, prov=None):
    return {"regions": regions, "adjacency": adjacency or [],
            "provenance": prov or {"source_mesh_artifact": "geometry/shape_ir.json#opt",
                                   "source_ir_node": "blk", "design_space_node": "blk",
                                   "runtime": "manifold"}}


def _fit(surfaces):
    return {"surfaces": surfaces}


def _planar_region(i, area=10.0):
    return {"region_id": f"region_{i:03d}", "area": area, "surface_class_candidate": "planar_candidate"}


def _plane_surface(i, conf="high"):
    return {"source_region_id": f"region_{i:03d}", "surface_type": "plane",
            "fit_confidence": conf, "boundary": {"approximate": True}}


# ── classification (pure) ────────────────────────────────────────────────────

def test_cube_six_planes_is_full_and_partial_candidate():
    regions = [_planar_region(i) for i in range(6)]
    adj = [{"region_a": f"region_{a:03d}", "region_b": f"region_{b:03d}", "shared_boundary_edges": 1}
           for a in range(6) for b in range(a + 1, 6)]   # fully connected (>= cube's 12)
    surfaces = [_plane_surface(i) for i in range(6)]
    r, plan = assess_reconstruction_readiness(_graph(regions, adj), _fit(surfaces))
    assert r["readiness"]["partial_brep_candidate"] is True
    assert r["readiness"]["full_brep_candidate"] is True
    assert r["readiness"]["recommended_next_action"] == "partial_brep_reconstruction"
    assert r["coverage"]["fitted_area_fraction"] == 1.0 and r["coverage"]["plane_area_fraction"] == 1.0
    # plan marks every region as a reconstruct candidate
    assert all(p["action"] == "reconstruct_face_candidate" for p in plan["region_plan"])


def test_single_cylinder_is_partial_not_full():
    regions = [{"region_id": "region_000", "area": 50.0, "surface_class_candidate": "freeform_candidate"}]
    surfaces = [{"source_region_id": "region_000", "surface_type": "cylinder", "fit_confidence": "high"}]
    r, _ = assess_reconstruction_readiness(_graph(regions, []), _fit(surfaces))
    assert r["readiness"]["partial_brep_candidate"] is True
    assert r["readiness"]["full_brep_candidate"] is False     # one face is not a closed solid
    assert r["coverage"]["cylinder_area_fraction"] == 1.0


def test_freeform_blob_recommends_freeform_fitting():
    # large freeform region with no accepted fit
    regions = [{"region_id": "region_000", "area": 100.0, "surface_class_candidate": "freeform_candidate"}]
    r, _ = assess_reconstruction_readiness(_graph(regions, []), _fit([]))
    assert r["readiness"]["full_brep_candidate"] is False
    assert r["readiness"]["partial_brep_candidate"] is False
    assert r["readiness"]["recommended_next_action"] == "freeform_surface_fitting"
    assert any(b["issue"] == "large_unfit_regions" for b in r["blocking_issues"])


def test_noisy_mesh_recommends_cleanup():
    regions = [{"region_id": f"region_{i:03d}", "area": 1.0, "surface_class_candidate": "noisy_small_region"}
               for i in range(8)] + [_planar_region(99, area=2.0)]
    surfaces = [_plane_surface(99)]
    r, _ = assess_reconstruction_readiness(_graph(regions, []), _fit(surfaces))
    assert r["readiness"]["recommended_next_action"] == "mesh_cleanup"
    assert any(b["issue"] == "too_many_noisy_regions" for b in r["blocking_issues"])


def test_partial_fit_with_unfit_remainder_recommends_freeform():
    # 60% fitted plane + 40% unfit freeform -> partial candidate but freeform fitting next
    regions = [_planar_region(0, area=60.0),
               {"region_id": "region_001", "area": 40.0, "surface_class_candidate": "freeform_candidate"}]
    surfaces = [_plane_surface(0)]
    r, _ = assess_reconstruction_readiness(_graph(regions, []), _fit(surfaces))
    assert r["readiness"]["partial_brep_candidate"] is True
    assert r["readiness"]["full_brep_candidate"] is False
    assert r["readiness"]["recommended_next_action"] == "freeform_surface_fitting"


def test_missing_inputs_insufficient_data():
    r, plan = assess_reconstruction_readiness(None, None)
    assert r["available"] is False
    assert r["readiness"]["recommended_next_action"] == "insufficient_data"
    assert any(b["issue"] == "missing_inputs" for b in r["blocking_issues"])
    assert plan["region_plan"] == []


def test_provenance_and_honesty_flags():
    regions = [_planar_region(i) for i in range(6)]
    r, plan = assess_reconstruction_readiness(_graph(regions), _fit([_plane_surface(i) for i in range(6)]))
    for doc in (r, plan):
        p = doc["provenance"]
        assert p["source_ir_node"] == "blk" and p["design_space_node"] == "blk"
        assert p["representation_kind"] == "mesh" and p["geometry_kind"] == "mesh"
        assert p["is_brep"] is False and p["cad_editable"] is False
    assert "B-Rep" in r["claim_boundary"] and "STEP" in r["claim_boundary"]


# ── package integration (real pipeline) ──────────────────────────────────────

def _cube_pkg(tmp_path: Path) -> Path:
    from aieng.converters.mesh_region_segmentation import write_mesh_region_graph
    from aieng.converters.mesh_surface_fitting import write_mesh_surface_fit
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
    return pkg


def test_package_cube_readiness_and_artifacts(tmp_path: Path):
    pkg = _cube_pkg(tmp_path)
    readiness = write_mesh_reconstruction_readiness(pkg)
    assert readiness["readiness"]["full_brep_candidate"] is True
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert MESH_RECONSTRUCTION_READINESS_PATH in names and MESH_RECONSTRUCTION_PLAN_PATH in names
        doc = json.loads(zf.read(MESH_RECONSTRUCTION_READINESS_PATH))
        plan = json.loads(zf.read(MESH_RECONSTRUCTION_PLAN_PATH))
    assert doc["coverage"]["fitted_region_count"] == 6
    assert doc["provenance"]["runtime"] == "manifold" and doc["provenance"]["is_brep"] is False
    assert len(plan["region_plan"]) == 6


def test_package_missing_artifacts_degrades(tmp_path: Path):
    pkg = tmp_path / "bare.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
    readiness, plan = build_mesh_reconstruction_readiness(pkg)
    assert readiness["available"] is False
    assert readiness["readiness"]["recommended_next_action"] == "insufficient_data"
