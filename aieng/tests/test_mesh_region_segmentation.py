"""Tests for solver-neutral mesh region segmentation of smooth topo-opt mesh outputs.

Mesh analysis only — region clusters are *_candidate guesses toward future mesh-to-CAD,
never B-Rep faces. No STEP export, no CAD-editability claim.
"""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")
import numpy as np  # noqa: E402

from aieng.converters.mesh_region_segmentation import (  # noqa: E402
    MESH_REGION_GRAPH_PATH,
    MESH_REGION_SEGMENTATION_DIAG_PATH,
    build_mesh_region_graph,
    segment_mesh_regions,
    write_mesh_region_graph,
)


def _cube():
    """Unit cube: 8 vertices, 12 triangles (2 per face), axis-aligned face normals."""
    V = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
         [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]
    F = [
        [0, 2, 1], [0, 3, 2],   # z- (bottom)
        [4, 5, 6], [4, 6, 7],   # z+ (top)
        [0, 1, 5], [0, 5, 4],   # y-
        [2, 3, 7], [2, 7, 6],   # y+
        [1, 2, 6], [1, 6, 5],   # x+
        [0, 4, 7], [0, 7, 3],   # x-
    ]
    return V, F


def _ico_sphere(subdiv=2):
    """A smooth-ish sphere via icosphere subdivision (varying normals)."""
    t = (1 + 5 ** 0.5) / 2
    verts = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0],
             [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
             [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]]
    faces = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
             [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
             [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
             [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]]
    V = [list(np.array(v) / np.linalg.norm(v)) for v in verts]
    for _ in range(subdiv):
        mid: dict = {}
        newF = []

        def midpoint(a, b):
            key = (min(a, b), max(a, b))
            if key in mid:
                return mid[key]
            p = (np.array(V[a]) + np.array(V[b])) / 2
            p = p / np.linalg.norm(p)
            V.append(list(p))
            mid[key] = len(V) - 1
            return mid[key]

        for a, b, c in faces:
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            newF += [[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]]
        faces = newF
    return V, faces


# ── pure segmentation ────────────────────────────────────────────────────────

def test_cube_yields_six_planar_candidate_regions():
    V, F = _cube()
    seg = segment_mesh_regions(V, F, normal_angle_deg=20.0)
    assert seg["diagnostics"]["total_regions"] == 6
    classes = [r["surface_class_candidate"] for r in seg["regions"]]
    assert classes.count("planar_candidate") == 6
    assert all(r["planarity_score"] >= 0.99 for r in seg["regions"])
    # each cube face region neighbors the 4 side faces
    assert all(len(r["neighbors"]) == 4 for r in seg["regions"])


def test_cube_region_adjacency_populated():
    V, F = _cube()
    seg = segment_mesh_regions(V, F)
    assert seg["adjacency"]                       # non-empty
    assert all(e["shared_boundary_edges"] >= 1 for e in seg["adjacency"])
    # a cube has 12 edges -> 12 region-adjacency pairs
    assert len(seg["adjacency"]) == 12


def test_smooth_blob_is_freeform_or_low_planarity():
    V, F = _ico_sphere(subdiv=2)
    seg = segment_mesh_regions(V, F, normal_angle_deg=20.0)
    classes = [r["surface_class_candidate"] for r in seg["regions"]]
    # a sphere is not 6 crisp planes; expect freeform candidates or clearly non-planar regions
    assert "freeform_candidate" in classes or all(
        r["planarity_score"] < 0.98 for r in seg["regions"] if r["surface_class_candidate"] != "noisy_small_region")
    assert seg["diagnostics"]["total_faces"] == len(F)


def test_tiny_noisy_island_is_flagged():
    V, F = _cube()
    base = len(V)
    # a far-away tiny disconnected triangle -> its own small region
    V = V + [[100.0, 100.0, 100.0], [100.05, 100.0, 100.0], [100.0, 100.05, 100.0]]
    F = F + [[base, base + 1, base + 2]]
    seg = segment_mesh_regions(V, F)
    assert seg["diagnostics"]["small_regions"] >= 1
    assert any(r["surface_class_candidate"] == "noisy_small_region" for r in seg["regions"])


def test_empty_mesh_degrades():
    seg = segment_mesh_regions([], [])
    assert seg["regions"] == [] and seg["diagnostics"]["total_regions"] == 0
    assert seg["diagnostics"]["warnings"]


# ── package integration ──────────────────────────────────────────────────────

def _pkg_with_mesh_node(tmp_path: Path) -> Path:
    V, F = _cube()
    shape_ir = {"representation": "manifold_mesh", "parts": [{
        "id": "optimized_blk", "type": "smooth_mesh_proxy", "dimension": 3,
        "vertices": V, "faces": F,
        "source_optimization": {"design_space_node": "blk", "source_ir_node": "blk",
                                "limitations": ["experimental 3D SIMP"]},
    }]}
    manifest = {"format": "aieng.conversion_manifest",
                "geometry_execution": {"executed": True, "geometry_kind": "mesh",
                                       "representation_kind": "mesh", "actual_runtime": "manifold"}}
    pkg = tmp_path / "m.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", json.dumps(shape_ir))
        zf.writestr("provenance/conversion_manifest.json", json.dumps(manifest))
    return pkg


def test_build_graph_from_shape_ir_node_preserves_provenance(tmp_path: Path):
    pkg = _pkg_with_mesh_node(tmp_path)
    graph, diag = build_mesh_region_graph(pkg)
    assert len(graph["regions"]) == 6
    p = graph["provenance"]
    assert p["source_ir_node"] == "blk" and p["design_space_node"] == "blk"
    assert p["representation_kind"] == "mesh" and p["geometry_kind"] == "mesh"
    assert p["cad_editable"] is False and p["is_brep"] is False
    assert p["runtime"] == "manifold"
    assert p["source_mesh_artifact"].startswith("geometry/shape_ir.json#")
    assert any("not B-Rep" in lim for lim in p["limitations"])


def test_write_graph_artifacts(tmp_path: Path):
    pkg = _pkg_with_mesh_node(tmp_path)
    write_mesh_region_graph(pkg)
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert MESH_REGION_GRAPH_PATH in names and MESH_REGION_SEGMENTATION_DIAG_PATH in names
        graph = json.loads(zf.read(MESH_REGION_GRAPH_PATH))
        diag = json.loads(zf.read(MESH_REGION_SEGMENTATION_DIAG_PATH))
    assert graph["format"] == "aieng.mesh_region_graph" and len(graph["regions"]) == 6
    assert diag["total_regions"] == 6 and diag["total_faces"] == 12
    assert "B-Rep" in graph["claim_boundary"]


def test_missing_mesh_degrades_honestly(tmp_path: Path):
    pkg = tmp_path / "bare.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:   # no mesh node, no preview.stl
        zf.writestr("geometry/shape_ir.json", json.dumps(
            {"representation": "manifold_mesh", "parts": [{"id": "x", "type": "density_voxels"}]}))
    graph, diag = build_mesh_region_graph(pkg)
    assert graph["regions"] == [] and graph["provenance"]["available"] is False
    assert diag["available"] is False and diag["warnings"]
    # writing still produces honest (empty) artifacts
    write_mesh_region_graph(pkg)
    with zipfile.ZipFile(pkg) as zf:
        assert MESH_REGION_GRAPH_PATH in zf.namelist()
