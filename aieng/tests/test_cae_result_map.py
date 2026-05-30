"""Tests for the solver-neutral CAE result contract + Shape IR mapping."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng.converters import cae_result_map as crm
from aieng.converters.cae_result_map import (
    CAE_RESULT_MAP_PATH,
    build_cae_result_map_for_package,
    map_cae_results,
    write_cae_result_map,
)
from aieng.converters.cae_result_contract import (
    NEUTRAL_COMPUTED_METRICS_PATH,
    NEUTRAL_FIELD_REGIONS_PATH,
    normalize_calculix_computed_metrics,
    normalize_calculix_field_regions,
)

# A simple bracket: base_plate (body_001) + post (body_002).
_TOPOLOGY = {"entities": [
    {"id": "body_001", "type": "solid", "name": "plate", "bounding_box": [-20, -15, 0, 20, 15, 6], "face_ids": ["face_001", "face_002"]},
    {"id": "body_002", "type": "solid", "name": "post", "bounding_box": [10, -3, 6, 16, 3, 26], "face_ids": ["face_010", "face_011"]},
]}
_REGISTRY = {"objects": [
    {"node_id": "plate", "topology_entities": ["body_001", "face_001", "face_002"], "linkage": "name_match"},
    {"node_id": "post", "topology_entities": ["body_002", "face_010", "face_011"], "linkage": "name_match"},
]}

# ── neutral artifacts (what ANY solver adapter must emit) ──
_NEUTRAL_CM = {
    "format": "aieng.cae.computed_metrics", "schema_version": "0.1",
    "solver": {"name": "generic_fake", "version": "1.0", "adapter": "fake_adapter"},
    "load_cases": [{"id": "lc1", "results": [
        {"result_type": "stress", "metric": "peak_vm", "max": 245.0, "min": None, "average": None, "unit": "MPa"},
        {"result_type": "displacement", "metric": "peak_disp", "max": 0.82, "unit": "mm"},
    ]}],
}
_NEUTRAL_FR = {
    "format": "aieng.cae.field_regions", "schema_version": "0.1",
    "solver": {"name": "generic_fake", "version": "1.0", "adapter": "fake_adapter"},
    "regions": [
        {"id": "region_001", "result_type": "stress", "load_case_id": "lc1",
         "center": {"x": 13, "y": 0, "z": 18}, "value": {"peak": 245.0, "unit": "MPa"}, "node_count": 40},
        {"id": "region_002", "result_type": "displacement", "load_case_id": "lc1",
         "center": {"x": -18, "y": 0, "z": 6}, "value": {"peak": 0.82, "unit": "mm"}, "node_count": 12},
    ],
}

# ── legacy CalculiX-native artifacts (adapter input) ──
_CALCULIX_CM = {"load_cases": [{"id": "lc1", "metrics": {
    "max_von_mises_stress": {"value": 245.0, "unit": "MPa"},
    "max_displacement": {"value": 0.82, "unit": "mm"}}}]}
_CALCULIX_FR = {"field": "S", "metric": "von_mises", "clusters": [
    {"id": "cluster_001", "location": {"x": 13, "y": 0, "z": 18}, "magnitude": {"value": 245.0, "unit": "MPa"}, "node_count": 40, "feature_ref": None}]}


def _mapped(res, rtype, node=None):
    return next(m for m in res["mapped_results"] if m["result_type"] == rtype and (node is None or m["source_ir_node"] == node))


# ── normalizer (CalculiX adapter) ──

def test_normalize_calculix_to_neutral():
    cm = normalize_calculix_computed_metrics(_CALCULIX_CM, solver_version="2.20")
    assert cm["solver"] == {"name": "calculix", "version": "2.20", "adapter": "calculix_frd_v1"}
    by = {r["result_type"]: r for r in cm["load_cases"][0]["results"]}
    assert by["stress"]["max"] == 245.0 and by["stress"]["unit"] == "MPa"
    assert by["displacement"]["unit"] == "mm"

    fr = normalize_calculix_field_regions(_CALCULIX_FR)
    r = fr["regions"][0]
    assert r["result_type"] == "stress"          # "S" -> stress happens in the ADAPTER
    assert r["center"] == {"x": 13.0, "y": 0.0, "z": 18.0}
    assert r["value"]["peak"] == 245.0 and r["value"]["unit"] == "MPa"


# ── neutral mapping ──

def test_map_neutral_stress_and_deflection():
    res = map_cae_results(computed_metrics=_NEUTRAL_CM, field_regions=_NEUTRAL_FR,
                          topology_map=_TOPOLOGY, object_registry=_REGISTRY)
    s = _mapped(res, "stress")
    assert s["source_ir_node"] == "post" and s["confidence"] == "high" and s["value"] == 245.0 and s["unit"] == "MPa"
    d = _mapped(res, "displacement")
    assert d["source_ir_node"] == "plate" and d["unit"] == "mm"
    # units + load case preserved end to end
    assert res["units"]["stress"] == "MPa" and res["units"]["displacement"] == "mm"
    assert res["load_cases"] == ["lc1"]
    assert res["summary"]["unmapped_count"] == 0


def test_generic_fake_solver_maps_and_records_provenance():
    res = map_cae_results(computed_metrics=_NEUTRAL_CM, field_regions=_NEUTRAL_FR,
                          topology_map=_TOPOLOGY, object_registry=_REGISTRY)
    # proves the mapper is solver-neutral: a non-CalculiX solver flows through
    assert res["solver"]["name"] == "generic_fake"
    assert res["provenance"]["solver_name"] == "generic_fake"
    assert res["provenance"]["adapter"] == "fake_adapter"
    assert "bbox_contains" in res["provenance"]["mapping_methods"]


def test_overall_extrema_units_and_load_case_preserved():
    res = map_cae_results(computed_metrics=_NEUTRAL_CM, field_regions={"regions": []},
                          topology_map=_TOPOLOGY, object_registry=_REGISTRY)
    by = {o["result_type"]: o for o in res["overall"]}
    assert by["stress"]["max"] == 245.0 and by["stress"]["unit"] == "MPa"
    assert by["stress"]["load_case_id"] == "lc1"
    assert by["stress"]["min"] is None and by["stress"]["average"] is None


def test_unmapped_region_reported_honestly():
    topo_no_solids = {"entities": [{"id": "face_001", "type": "face"}]}
    res = map_cae_results(computed_metrics=_NEUTRAL_CM, field_regions=_NEUTRAL_FR,
                          topology_map=topo_no_solids, object_registry=_REGISTRY)
    assert res["mapped_results"] == [] and res["summary"]["unmapped_count"] == 2
    assert all("no topology solid" in u["reason"] for u in res["unmapped_regions"])
    assert res["provenance"]["unsupported_or_uncertain"]


def test_fused_mesh_low_confidence_preserved():
    fused_topo = {"entities": [
        {"id": "body_001", "type": "solid", "name": "sdf_body", "bounding_box": [-20, -20, 0, 20, 20, 30], "face_ids": ["face_001"]}]}
    fused_reg = {"objects": [
        {"node_id": "a", "topology_entities": ["body_001", "face_001"], "linkage": "fused_mesh"},
        {"node_id": "b", "topology_entities": ["body_001", "face_001"], "linkage": "fused_mesh"}]}
    res = map_cae_results(computed_metrics=_NEUTRAL_CM, field_regions=_NEUTRAL_FR,
                          topology_map=fused_topo, object_registry=fused_reg)
    s = _mapped(res, "stress")
    assert s["source_ir_node"] is None and s["confidence"] == "low" and "note" in s
    assert res["summary"]["resolved_to_node"] == 0


def test_core_ignores_calculix_native_shapes():
    """The neutral mapper must NOT understand solver-native shapes — passing
    CalculiX-native computed_metrics/field_regions yields nothing mapped."""
    res = map_cae_results(computed_metrics=_CALCULIX_CM, field_regions=_CALCULIX_FR,
                          topology_map=_TOPOLOGY, object_registry=_REGISTRY)
    assert res["overall"] == [] and res["mapped_results"] == []


def test_no_calculix_tokens_leak_into_mapper_source():
    import re
    raw = Path(crm.__file__).read_text(encoding="utf-8")
    # strip triple-quoted docstrings (prose explaining neutrality), keep code + literals
    code = re.sub(r'""".*?"""', "", raw, flags=re.S)
    code = re.sub(r"'''.*?'''", "", code, flags=re.S).lower()
    # solver-native logic signals must not appear in the neutral mapper
    for token in (".frd", ".inp", ".dat", "von_mises", "results/computed_metrics", "results/field_regions"):
        assert token not in code, f"CalculiX-specific token '{token}' leaked into the neutral mapper"


# ── package paths (neutral vs legacy CalculiX) ──

def _pkg(tmp_path: Path, members: dict[str, Any]) -> Path:
    p = tmp_path / "m.aieng"
    with zipfile.ZipFile(p, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content if isinstance(content, (bytes, str)) else json.dumps(content))
    return p


def test_package_neutral_artifacts_map(tmp_path: Path):
    pkg = _pkg(tmp_path, {
        "geometry/topology_map.json": _TOPOLOGY,
        "registry/object_registry.json": _REGISTRY,
        NEUTRAL_COMPUTED_METRICS_PATH: _NEUTRAL_CM,
        NEUTRAL_FIELD_REGIONS_PATH: _NEUTRAL_FR,
    })
    res = build_cae_result_map_for_package(pkg)
    assert _mapped(res, "stress")["source_ir_node"] == "post"
    assert res["provenance"]["artifact_source"] == "neutral"


def test_package_legacy_calculix_is_normalized_then_mapped(tmp_path: Path):
    pkg = _pkg(tmp_path, {
        "geometry/topology_map.json": _TOPOLOGY,
        "registry/object_registry.json": _REGISTRY,
        "results/computed_metrics.json": _CALCULIX_CM,
        "results/field_regions.json": _CALCULIX_FR,
    })
    res = build_cae_result_map_for_package(pkg)
    assert _mapped(res, "stress")["source_ir_node"] == "post"   # CalculiX still works
    assert res["provenance"]["artifact_source"] == "calculix_normalized"
    assert res["provenance"]["solver_name"] == "calculix"

    written = write_cae_result_map(pkg)
    assert written["summary"]["resolved_to_node"] >= 1
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
    # neutral artifacts + result map persisted
    assert NEUTRAL_COMPUTED_METRICS_PATH in names and NEUTRAL_FIELD_REGIONS_PATH in names
    assert CAE_RESULT_MAP_PATH in names
