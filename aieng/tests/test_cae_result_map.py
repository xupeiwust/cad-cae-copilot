"""Tests for CAE result -> Shape IR mapping (analysis/cae_result_map.json)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng.converters.cae_result_map import (
    CAE_RESULT_MAP_PATH,
    build_cae_result_map_for_package,
    map_cae_results,
    write_cae_result_map,
)


# A simple bracket: base_plate (body_001) + post (body_002).
_TOPOLOGY = {"entities": [
    {"id": "body_001", "type": "solid", "name": "plate", "bounding_box": [-20, -15, 0, 20, 15, 6], "face_ids": ["face_001", "face_002"]},
    {"id": "body_002", "type": "solid", "name": "post", "bounding_box": [10, -3, 6, 16, 3, 26], "face_ids": ["face_010", "face_011"]},
    {"id": "face_001", "type": "face", "body_id": "body_001"},
    {"id": "face_010", "type": "face", "body_id": "body_002"},
]}
_REGISTRY = {"objects": [
    {"node_id": "plate", "topology_entities": ["body_001", "face_001", "face_002"], "linkage": "name_match"},
    {"node_id": "post", "topology_entities": ["body_002", "face_010", "face_011"], "linkage": "name_match"},
]}
_METRICS = {"load_cases": [{"id": "lc1", "metrics": {
    "max_von_mises_stress": {"value": 245.0, "unit": "MPa"},
    "max_displacement": {"value": 0.82, "unit": "mm"},
}}]}
_STRESS = {"field": "S", "clusters": [
    {"id": "cluster_001", "location": {"x": 13, "y": 0, "z": 18}, "magnitude": {"value": 245.0, "unit": "MPa"}, "node_count": 40},
]}
_DISP = {"field": "U", "clusters": [
    {"id": "cluster_001", "location": {"x": -18, "y": 0, "z": 6}, "magnitude": {"value": 0.82, "unit": "mm"}, "node_count": 12},
]}


def _stress(res, node):
    return next(m for m in res["mapped_results"] if m["result_type"] == "stress" and m["source_ir_node"] == node)


def test_map_stress_hotspot_to_node():
    res = map_cae_results(computed_metrics=_METRICS, field_regions_docs=[_STRESS],
                          topology_map=_TOPOLOGY, object_registry=_REGISTRY)
    m = _stress(res, "post")
    assert m["result_type"] == "stress" and m["value"] == 245.0 and m["unit"] == "MPa"
    assert "body_002" in m["affected_topology_entities"]
    assert m["mapping_method"] == "bbox_contains" and m["confidence"] == "high"
    assert res["summary"]["unmapped_count"] == 0


def test_map_deflection_max_to_node():
    res = map_cae_results(computed_metrics=_METRICS, field_regions_docs=[_DISP],
                          topology_map=_TOPOLOGY, object_registry=_REGISTRY)
    m = res["mapped_results"][0]
    assert m["result_type"] == "displacement" and m["source_ir_node"] == "plate"
    assert m["unit"] == "mm" and m["confidence"] == "high"


def test_overall_extrema_from_computed_metrics():
    res = map_cae_results(computed_metrics=_METRICS, field_regions_docs=[],
                          topology_map=_TOPOLOGY, object_registry=_REGISTRY)
    by_type = {o["result_type"]: o for o in res["overall"]}
    assert by_type["stress"]["max"] == 245.0 and by_type["stress"]["unit"] == "MPa"
    assert by_type["displacement"]["max"] == 0.82 and by_type["displacement"]["unit"] == "mm"
    assert res["units"]["stress"] == "MPa" and res["units"]["displacement"] == "mm"
    # extrema-only source -> min/average honestly null
    assert by_type["stress"]["min"] is None and by_type["stress"]["average"] is None


def test_unmapped_region_reported_honestly():
    # topology with no solids -> the region cannot be tied to geometry
    topo_no_solids = {"entities": [{"id": "face_001", "type": "face"}]}
    res = map_cae_results(computed_metrics=_METRICS, field_regions_docs=[_STRESS],
                          topology_map=topo_no_solids, object_registry=_REGISTRY)
    assert res["mapped_results"] == []
    assert res["summary"]["unmapped_count"] == 1
    assert "no topology solid" in res["unmapped_regions"][0]["reason"]


def test_fused_mesh_region_low_confidence_without_node():
    # both nodes share the single fused body -> region maps to the body but not a unique node
    fused_topo = {"entities": [
        {"id": "body_001", "type": "solid", "name": "sdf_body", "bounding_box": [-20, -20, 0, 20, 20, 30], "face_ids": ["face_001"]},
        {"id": "face_001", "type": "face", "body_id": "body_001"},
    ]}
    fused_registry = {"objects": [
        {"node_id": "a", "topology_entities": ["body_001", "face_001"], "linkage": "fused_mesh"},
        {"node_id": "b", "topology_entities": ["body_001", "face_001"], "linkage": "fused_mesh"},
    ]}
    res = map_cae_results(computed_metrics=_METRICS, field_regions_docs=[_STRESS],
                          topology_map=fused_topo, object_registry=fused_registry)
    m = res["mapped_results"][0]
    assert m["source_ir_node"] is None and m["confidence"] == "low"
    assert "body_001" in m["affected_topology_entities"]
    assert "note" in m
    assert res["summary"]["resolved_to_node"] == 0


def test_package_read_and_write(tmp_path: Path):
    pkg = tmp_path / "m.aieng"
    members: dict[str, Any] = {
        "geometry/topology_map.json": _TOPOLOGY,
        "registry/object_registry.json": _REGISTRY,
        "results/computed_metrics.json": _METRICS,
        "results/field_regions.json": _STRESS,
    }
    with zipfile.ZipFile(pkg, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, json.dumps(content))
    res = build_cae_result_map_for_package(pkg)
    assert _stress(res, "post")["confidence"] == "high"

    written = write_cae_result_map(pkg)
    assert written["summary"]["resolved_to_node"] == 1
    with zipfile.ZipFile(pkg) as zf:
        assert CAE_RESULT_MAP_PATH in zf.namelist()
        loaded = json.loads(zf.read(CAE_RESULT_MAP_PATH))
    assert loaded["mapped_results"][0]["result_type"] == "stress"
