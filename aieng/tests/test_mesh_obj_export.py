"""Tests for the neutral OBJ exporter for topology-optimization meshes (#149/#204)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.mesh_obj_export import (
    TOPOLOGY_RESULT_MESH_OBJ_PATH,
    find_surface_mesh_node,
    mesh_to_obj,
    topology_result_mesh_obj,
    write_topology_result_mesh_obj,
)


def test_mesh_to_obj_emits_1indexed_vertices_and_faces() -> None:
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)]
    faces = [(0, 1, 2), (1, 3, 2)]
    obj = mesh_to_obj(verts, faces, object_name="part")
    lines = obj.splitlines()
    assert "o part" in lines
    assert lines.count("v 0.000000 0.000000 0.000000") == 1
    assert "v 1.000000 1.000000 0.000000" in lines
    # OBJ faces are 1-based
    assert "f 1 2 3" in lines
    assert "f 2 4 3" in lines
    # 4 verts + 2 faces
    assert sum(1 for ln in lines if ln.startswith("v ")) == 4
    assert sum(1 for ln in lines if ln.startswith("f ")) == 2


def test_mesh_to_obj_skips_degenerate_faces_and_handles_empty() -> None:
    assert "f " not in mesh_to_obj([(0, 0, 0)], [])  # no faces
    obj = mesh_to_obj([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1)])  # 2-index face skipped
    assert "f " not in obj


def _shape_ir_with_mesh() -> dict:
    return {
        "format": "aieng.shape_ir",
        "parts": [
            {
                "id": "opt_body",
                "type": "smooth_mesh_proxy",
                "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "faces": [[0, 1, 2]],
            }
        ],
    }


def test_find_surface_mesh_node() -> None:
    node = find_surface_mesh_node(_shape_ir_with_mesh())
    assert node is not None and node["id"] == "opt_body"
    # a B-Rep-only payload has no surface-mesh node
    assert find_surface_mesh_node({"parts": [{"id": "b", "type": "extruded_region"}]}) is None
    # an empty mesh node is not usable
    assert find_surface_mesh_node({"parts": [{"type": "smooth_mesh_proxy", "vertices": [], "faces": []}]}) is None
    assert find_surface_mesh_node({}) is None


def test_topology_result_mesh_obj_names_object_after_node_id() -> None:
    obj = topology_result_mesh_obj(_shape_ir_with_mesh())
    assert obj is not None
    assert "o opt_body" in obj
    assert "f 1 2 3" in obj
    assert topology_result_mesh_obj({"parts": []}) is None


def test_write_topology_result_mesh_obj_into_package(tmp_path: Path) -> None:
    pkg = tmp_path / "p.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", "{}")
        zf.writestr("geometry/shape_ir.json", json.dumps(_shape_ir_with_mesh()))

    result = write_topology_result_mesh_obj(pkg)
    assert result["ok"] is True
    assert result["vertex_count"] == 3 and result["face_count"] == 1
    with zipfile.ZipFile(pkg, "r") as zf:
        assert TOPOLOGY_RESULT_MESH_OBJ_PATH in zf.namelist()
        obj = zf.read(TOPOLOGY_RESULT_MESH_OBJ_PATH).decode("utf-8")
    assert "v 0.000000 0.000000 0.000000" in obj and "f 1 2 3" in obj


def test_write_topology_result_mesh_obj_honest_failures(tmp_path: Path) -> None:
    # no shape_ir
    pkg1 = tmp_path / "noir.aieng"
    with zipfile.ZipFile(pkg1, "w") as zf:
        zf.writestr("metadata.json", "{}")
    assert write_topology_result_mesh_obj(pkg1) == {"ok": False, "reason": "no_shape_ir"}

    # shape_ir without a surface-mesh node
    pkg2 = tmp_path / "nomesh.aieng"
    with zipfile.ZipFile(pkg2, "w") as zf:
        zf.writestr("metadata.json", "{}")
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": [{"id": "b", "type": "extruded_region"}]}))
    assert write_topology_result_mesh_obj(pkg2)["reason"] == "no_surface_mesh_node"
