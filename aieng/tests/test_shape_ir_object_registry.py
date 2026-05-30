"""Tests for the Shape IR object registry (registry/object_registry.json)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng.converters.shape_ir_object_registry import (
    SHAPE_IR_OBJECT_REGISTRY_PATH,
    build_shape_ir_object_registry,
    write_shape_ir_object_registry,
)


def _pkg(tmp_path: Path, members: dict[str, Any]) -> Path:
    p = tmp_path / "m.aieng"
    with zipfile.ZipFile(p, "w") as zf:
        for member, content in members.items():
            zf.writestr(member, content if isinstance(content, (bytes, str)) else json.dumps(content))
    return p


def _manifest(representation: str, *, executed: bool = True, backend: str = "build123d",
              geometry_kind: str = "brep") -> dict[str, Any]:
    m: dict[str, Any] = {
        "source": {"source_document_metadata": {
            "representation": representation, "requested_representation": representation,
            "compile_runtime": backend, "representation_fallback": False,
        }},
        "achieved_capability_levels": [{"level": n} for n in (0, 1, 2, 3)],
    }
    if executed:
        m["geometry_execution"] = {"executed": True, "backend": backend, "geometry_kind": geometry_kind}
    return m


def _obj(reg: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(o for o in reg["objects"] if o["node_id"] == node_id)


def test_registry_links_executed_brep_by_name_match(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"parts": [
            {"id": "plate", "type": "box", "parameters": {"LENGTH": 10}},
            {"id": "rib", "type": "box"},
        ]},
        "geometry/source.py": "# Shape IR node: plate\n# Shape IR node: rib\n",
        "geometry/generated.step": "ISO-10303-21;\n",
        "geometry/preview.glb": b"glTF",
        "geometry/topology_map.json": {"metadata": {"extractor": "build123d"}, "entities": [
            {"id": "body_001", "type": "solid", "name": "plate", "face_ids": ["face_001", "face_002"]},
            {"id": "body_002", "type": "solid", "name": "rib", "face_ids": ["face_003"]},
            {"id": "face_001", "type": "face", "body_id": "body_001", "surface_type": "plane"},
            {"id": "face_002", "type": "face", "body_id": "body_001", "surface_type": "plane"},
            {"id": "face_003", "type": "face", "body_id": "body_002", "surface_type": "plane"},
        ]},
        "provenance/conversion_manifest.json": _manifest("brep_build123d"),
    })
    reg = build_shape_ir_object_registry(pkg)
    assert reg["resolved_count"] == 2
    plate = _obj(reg, "plate")
    assert plate["linkage"] == "name_match"
    assert plate["source_pointer"] == "/parts/0"
    assert "body_001" in plate["topology_entities"]
    assert set(plate["viewer_selectable_ids"]) == {"face_001", "face_002"}
    assert plate["editable_parameters"] == {"LENGTH": 10}
    assert plate["cad_editable"] is True and plate["representation_kind"] == "brep"
    assert plate["verification_status_ref"].endswith("#/nodes/0")
    rib = _obj(reg, "rib")
    assert rib["viewer_selectable_ids"] == ["face_003"]


def test_registry_links_projected_by_source_ir_node(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"parts": [{"id": "plate", "type": "box"}]},
        "geometry/source.py": "# Shape IR node: plate\n",
        "geometry/topology_map.json": {"metadata": {}, "entities": [
            {"id": "body_plate", "type": "solid", "name": "plate", "source_ir_node": "plate", "face_ids": ["face_plate"]},
            {"id": "face_plate", "type": "face", "body_id": "body_plate", "source_ir_node": "plate"},
        ]},
        "provenance/conversion_manifest.json": _manifest("brep_build123d", executed=False),
    })
    reg = build_shape_ir_object_registry(pkg)
    plate = _obj(reg, "plate")
    assert plate["linkage"] == "source_ir_node"
    assert "body_plate" in plate["topology_entities"]
    assert "face_plate" in plate["viewer_selectable_ids"]


def test_registry_fused_mesh_maps_all_nodes_to_one_body(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"representation": "implicit_sdf", "parts": [
            {"id": "a", "type": "sphere"}, {"id": "b", "type": "sphere"},
        ]},
        "geometry/sdf_source.py": "# Shape IR node: a\n# Shape IR node: b\n",
        "geometry/preview.glb": b"glTF",
        "geometry/topology_map.json": {"metadata": {
            "extractor": "SDFRunner", "extraction_mode": "marching_cubes_mesh", "real_step_parsing": False,
        }, "entities": [
            {"id": "body_001", "type": "solid", "name": "sdf_body", "face_ids": ["face_001"]},
            {"id": "face_001", "type": "face", "body_id": "body_001", "surface_type": "freeform"},
        ]},
        "provenance/conversion_manifest.json": _manifest("implicit_sdf", backend="sdf", geometry_kind="mesh"),
    })
    reg = build_shape_ir_object_registry(pkg)
    assert reg["resolved_count"] == 2
    for nid in ("a", "b"):
        o = _obj(reg, nid)
        assert o["linkage"] == "fused_mesh"
        assert o["representation_kind"] == "implicit_field" and o["cad_editable"] is False
        assert o["viewer_selectable_ids"] == ["face_001"]


def test_registry_manifold_mesh_without_manifest_is_fused_mesh(tmp_path: Path) -> None:
    # A manifold mesh recompiled without a conversion manifest (so no executed
    # geometry_kind) must still resolve to fused_mesh from its mesh representation +
    # extracted topology — not fall through to linkage "none".
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"representation": "manifold_mesh", "parts": [
            {"id": "optimized_blk", "type": "density_voxels", "dimension": 3},
        ]},
        "geometry/manifold_source.py": "# Shape IR node: optimized_blk\n",
        "geometry/preview.glb": b"glTF",
        "geometry/topology_map.json": {"metadata": {
            "extractor": "ManifoldRunner", "extraction_mode": "mesh_region", "real_step_parsing": False,
        }, "entities": [
            {"id": "body_001", "type": "solid", "name": "manifold_body", "face_ids": ["face_001"]},
            {"id": "face_001", "type": "face", "body_id": "body_001", "surface_type": "mesh_region"},
        ]},
        # NOTE: no provenance/conversion_manifest.json on purpose
    })
    reg = build_shape_ir_object_registry(pkg)
    o = _obj(reg, "optimized_blk")
    assert o["linkage"] == "fused_mesh"
    assert o["topology_entities"] == ["body_001", "face_001"]
    assert o["cad_editable"] is False


def test_registry_nurbs_bspline_resolves(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"representation": "nurbs_brep", "parts": [
            {"id": "patch", "type": "nurbs_surface"},
        ]},
        "geometry/source.py": "# Shape IR NURBS node: patch\n",
        "geometry/generated.step": "ISO-10303-21;\n",
        "geometry/topology_map.json": {"metadata": {"extractor": "build123d"}, "entities": [
            {"id": "body_001", "type": "solid", "name": "patch", "face_ids": ["face_001"]},
            {"id": "face_001", "type": "face", "body_id": "body_001", "surface_type": "bspline"},
        ]},
        "provenance/conversion_manifest.json": _manifest("nurbs_brep"),
    })
    reg = build_shape_ir_object_registry(pkg)
    patch = _obj(reg, "patch")
    assert patch["representation_kind"] == "nurbs_brep"
    assert patch["linkage"] == "name_match"
    assert patch["viewer_selectable_ids"] == ["face_001"]


def test_write_object_registry_into_package(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"parts": [{"id": "plate", "type": "box"}]},
        "geometry/source.py": "# Shape IR node: plate\n",
        "geometry/topology_map.json": {"metadata": {}, "entities": [
            {"id": "body_001", "type": "solid", "name": "plate", "face_ids": ["face_001"]},
            {"id": "face_001", "type": "face", "body_id": "body_001"},
        ]},
        "provenance/conversion_manifest.json": _manifest("brep_build123d"),
    })
    reg = write_shape_ir_object_registry(pkg)
    assert reg["node_count"] == 1
    with zipfile.ZipFile(pkg) as zf:
        assert SHAPE_IR_OBJECT_REGISTRY_PATH in zf.namelist()
        written = json.loads(zf.read(SHAPE_IR_OBJECT_REGISTRY_PATH))
    assert written["objects"][0]["node_id"] == "plate"
    assert "face_001" in written["objects"][0]["viewer_selectable_ids"]
