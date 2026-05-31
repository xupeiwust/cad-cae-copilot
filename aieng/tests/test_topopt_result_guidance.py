"""Tests for CAE-result-guided topology-optimization problem derivation.

Guidance is ADVISORY annotation from neutral CAE result artifacts; it never replaces
the loads/supports/material/design-space taken from the CAE setup. Solver-agnostic:
no CalculiX-specific field names are read.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from aieng.converters.topology_optimization import (  # noqa: E402
    TOPOPT_RESULT_GUIDANCE_PATH,
    build_topopt_result_guidance,
    collect_topopt_result_guidance,
    derive_topopt_problem_from_package,
)

# A neutral cae_result_map: one stress hotspot + one displacement hotspot + one unmapped.
_CRM = {
    "format": "aieng.cae_result_map",
    "load_cases": ["lc1"],
    "units": {"stress": "MPa", "displacement": "mm"},
    "mapped_results": [
        {"load_case_id": "lc1", "result_type": "stress", "region_id": "r1",
         "value": 280.0, "value_range": {"min": 250.0, "max": 280.0}, "unit": "MPa",
         "location": {"x": 10, "y": 5, "z": 2}, "node_count": 12,
         "affected_topology_entities": ["body_plate", "face_002"], "source_ir_node": "plate",
         "node_linkage": "name_match", "mapping_method": "bbox_contains", "confidence": "high"},
        {"load_case_id": "lc1", "result_type": "displacement", "region_id": "r2",
         "value": 1.4, "value_range": {"min": 1.0, "max": 1.4}, "unit": "mm",
         "location": {"x": 110, "y": 40, "z": 5}, "node_count": 8,
         "affected_topology_entities": ["body_plate"], "source_ir_node": "plate",
         "node_linkage": "source_ir_node", "mapping_method": "bbox_contains", "confidence": "medium"},
    ],
    "unmapped_regions": [
        {"load_case_id": "lc1", "result_type": "stress", "region_id": "r3",
         "reason": "no topology solid near the result location"},
    ],
}
_CM = {"format": "aieng.cae.computed_metrics", "load_cases": [
    {"id": "lc1", "results": [{"result_type": "stress", "metric": "max_von_mises_stress",
                               "max": 280.0, "min": None, "unit": "MPa"}]}]}


# ── pure builder ─────────────────────────────────────────────────────────────

def test_stress_hotspot_adds_preserve_or_reinforce():
    g, diag, warns = build_topopt_result_guidance(_CRM, None, _CM, "plate",
                                                  present={"cae_result_map": True, "computed_metrics": True})
    assert g["available"] is True and g["advisory_only"] is True
    assert len(g["stress_hotspots"]) == 1
    s = g["stress_hotspots"][0]
    # all neutral fields preserved
    assert s["load_case_id"] == "lc1" and s["result_type"] == "stress" and s["quantity"] == "von_mises_stress"
    assert s["value"] == 280.0 and s["unit"] == "MPa" and s["value_range"]["max"] == 280.0
    assert s["affected_topology_entities"] == ["body_plate", "face_002"]
    assert s["source_ir_node"] == "plate" and s["mapping_method"] == "bbox_contains" and s["confidence"] == "high"
    assert s["within_design_space"] is True            # mapped back to design_space_node
    # stress -> preserve_or_reinforce guidance
    assert len(g["preserve_or_reinforce_regions"]) == 1
    assert g["preserve_or_reinforce_regions"][0]["guidance"] == "preserve_or_reinforce"
    assert g["global_extrema"] and g["global_extrema"][0]["metric"] == "max_von_mises_stress"


def test_deflection_adds_stiffness_sensitive():
    g, _d, _w = build_topopt_result_guidance(_CRM, None, None, "plate", present={"cae_result_map": True})
    assert len(g["deflection_hotspots"]) == 1
    d = g["deflection_hotspots"][0]
    assert d["result_type"] == "displacement" and d["quantity"] == "displacement_magnitude"
    assert d["unit"] == "mm" and d["confidence"] == "medium"
    assert len(g["stiffness_sensitive_regions"]) == 1
    assert g["stiffness_sensitive_regions"][0]["guidance"] == "increase_stiffness"


def test_unmapped_regions_recorded_honestly():
    g, diag, _w = build_topopt_result_guidance(_CRM, None, None, "plate", present={"cae_result_map": True})
    assert len(g["unmapped_result_regions"]) == 1
    u = g["unmapped_result_regions"][0]
    assert u["region_id"] == "r3" and u["result_type"] == "stress" and "no topology solid" in u["reason"]
    assert diag["counts"]["unmapped_result_regions"] == 1
    assert diag["confidence_distribution"].get("high") == 1


def test_no_calculix_specific_names_in_guidance():
    g, diag, _w = build_topopt_result_guidance(_CRM, None, _CM, "plate", present={"cae_result_map": True})
    blob = json.dumps([g, diag]).lower()
    for token in ("calculix", "ccx", "frd", ".inp", "abaqus"):
        assert token not in blob


def test_field_regions_fallback_when_no_result_map():
    fr = {"regions": [
        {"id": "fr1", "result_type": "stress", "load_case_id": "lc1",
         "center": {"x": 1, "y": 2, "z": 3}, "value": {"peak": 200.0, "min": 150.0, "max": 200.0, "unit": "MPa"}},
    ]}
    g, diag, warns = build_topopt_result_guidance(None, fr, None, "plate", present={"field_regions": True})
    assert g["available"] is True and diag["used_field_regions_fallback"] is True
    assert len(g["stress_hotspots"]) == 1
    assert g["stress_hotspots"][0]["confidence"] == "low"      # not mapped to topology
    assert g["unmapped_result_regions"]                        # also recorded as unmapped


def test_missing_artifacts_warns_not_errors():
    g, diag, warns = build_topopt_result_guidance(None, None, None, "plate", present={})
    assert g["available"] is False
    assert any("CAE setup only" in w for w in warns)           # warning, not error
    assert g["stress_hotspots"] == [] and g["preserve_or_reinforce_regions"] == []


# ── package integration ──────────────────────────────────────────────────────

def _plate_pkg(tmp_path: Path, *, with_results: bool) -> Path:
    pkg = tmp_path / "plate.aieng"
    topo = {"entities": [
        {"id": "body_plate", "type": "solid", "source_ir_node": "plate", "bounding_box": [0, 0, 0, 120, 80, 10]},
        {"id": "face_left", "type": "face", "bounding_box": [0, 0, 0, 0, 80, 10]},
        {"id": "face_right", "type": "face", "bounding_box": [120, 0, 0, 120, 80, 10]}]}
    cae_map = {"mappings": [
        {"maps_to": {"feature_id": "feat_fix"}, "face_ids": ["face_left"]},
        {"maps_to": {"feature_id": "feat_load"}, "face_ids": ["face_right"]}]}
    setup = ("boundary_conditions:\n  - {id: bc1, target_feature: feat_fix, type: fixed}\n"
             "loads:\n  - {id: ld1, target_feature: feat_load, type: force, value_n: 500.0, "
             "direction: [0.0, -1.0, 0.0]}\n")
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/topology_map.json", json.dumps(topo))
        zf.writestr("simulation/cae_mapping.json", json.dumps(cae_map))
        zf.writestr("simulation/setup.yaml", setup)
        if with_results:
            zf.writestr("analysis/cae_result_map.json", json.dumps(_CRM))
            zf.writestr("analysis/computed_metrics.json", json.dumps(_CM))
    return pkg


def test_derive_setup_only_still_works_and_warns(tmp_path: Path):
    pytest.importorskip("yaml")
    pkg = _plate_pkg(tmp_path, with_results=False)
    prob = derive_topopt_problem_from_package(pkg)
    # BCs still derived from the CAE setup (unchanged behavior)
    assert prob["bcs"]["supports"] and prob["bcs"]["loads"]
    assert prob["bcs"]["loads"][0]["fy"] == -500.0
    # guidance absent -> advisory warning, not an error
    assert prob["result_guidance"]["available"] is False
    assert any("CAE setup only" in w for w in prob["derivation"]["warnings"])


def test_derive_with_results_attaches_guidance_and_writes_diagnostics(tmp_path: Path):
    pytest.importorskip("yaml")
    pkg = _plate_pkg(tmp_path, with_results=True)
    prob = derive_topopt_problem_from_package(pkg)
    # BCs unchanged (setup is still the source of loads/supports)
    assert prob["bcs"]["loads"][0]["fy"] == -500.0
    g = prob["result_guidance"]
    assert g["available"] is True
    assert g["stress_hotspots"] and g["preserve_or_reinforce_regions"]
    assert g["stress_hotspots"][0]["source_ir_node"] == "plate"
    assert prob["derivation"]["bc_source"] == "cae_setup"
    assert prob["derivation"]["result_guidance_source"] == "cae_result_artifacts"
    # diagnostics file + manifest provenance written into the package
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert TOPOPT_RESULT_GUIDANCE_PATH in names
        diag = json.loads(zf.read(TOPOPT_RESULT_GUIDANCE_PATH))
        assert "analysis/cae_result_map.json" in diag["consumed_artifacts"]
        manifest = json.loads(zf.read("provenance/conversion_manifest.json"))
        ti = manifest["topopt_inputs"]
        assert ti["used"] == "cae_setup+cae_result_guidance" and ti["result_guidance_available"] is True


def test_collect_guidance_missing_results_warns(tmp_path: Path):
    pkg = _plate_pkg(tmp_path, with_results=False)
    g, warns = collect_topopt_result_guidance(pkg, "plate")
    assert g["available"] is False and warns
    # manifest still records cae_setup_only honestly
    with zipfile.ZipFile(pkg) as zf:
        manifest = json.loads(zf.read("provenance/conversion_manifest.json"))
    assert manifest["topopt_inputs"]["used"] == "cae_setup_only"
