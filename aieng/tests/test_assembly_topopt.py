"""Tests for assembly-aware topology optimization setup v0."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from aieng.converters.assembly_cae import (
    ASSEMBLY_CAE_MODEL_PATH,
    ASSEMBLY_RESULT_MAP_PATH,
    build_assembly_cae_model,
    process_assembly_cae_package,
)
from aieng.converters.assembly_interface_resolution import (
    ASSEMBLY_CONNECTION_GEOMETRY_PATH,
    INTERFACE_RESOLUTION_PATH,
    resolve_assembly_interfaces,
    validate_connection_geometry,
)
from aieng.converters.assembly_ir import (
    ASSEMBLY_CAE_DRAFT_PATH,
    ASSEMBLY_IR_PATH,
    CONNECTION_GRAPH_PATH,
    CONVERSION_MANIFEST_PATH,
    PART_REGISTRY_PATH,
    build_assembly_cae_setup_draft,
    build_connection_graph,
    build_part_registry,
)
from aieng.converters.assembly_topopt import (
    ASSEMBLY_TOPOPT_DERIVATION_PATH,
    ASSEMBLY_TOPOPT_PROBLEM_PATH,
    STANDARD_TOPOPT_PROBLEM_PATH,
    derive_assembly_topopt_problem,
    write_assembly_topopt_problem,
)
from aieng.converters.topology_optimization import run_topology_optimization


def _face(fid: str, bbox: list[float], normal: list[float], *, body: str, area: float = 100.0) -> dict:
    return {"id": fid, "type": "face", "body_id": body, "bounding_box": bbox, "normal": normal, "area": area}


def _solid(sid: str, bbox: list[float]) -> dict:
    return {"id": sid, "type": "solid", "body_id": sid, "bounding_box": bbox}


def _topology() -> dict[str, dict[str, dict]]:
    return {
        "bracket": {
            "bracket_solid": _solid("bracket", [0, 0, 0, 120, 20, 10]),
            "face_mount": _face("face_mount", [0, 0, 0, 0, 20, 10], [-1, 0, 0], body="bracket"),
            "face_load": _face("face_load", [120, 5, 0, 120, 15, 10], [1, 0, 0], body="bracket"),
            "face_bolt": _face("face_bolt", [8, 8, 0, 12, 12, 10], [0, 0, 1], body="bracket", area=20),
        },
        "wall": {
            "wall_solid": _solid("wall", [-10, 0, 0, 0, 20, 10]),
            "face_wall": _face("face_wall", [0, 0, 0, 0, 20, 10], [1, 0, 0], body="wall"),
        },
        "load_jig": {
            "load_solid": _solid("load_jig", [120, 5, 0, 130, 15, 10]),
            "face_jig": _face("face_jig", [120, 5, 0, 120, 15, 10], [-1, 0, 0], body="load_jig"),
        },
        "bolt_fixture": {
            "bolt_fixture_solid": _solid("bolt_fixture", [8, 8, 10, 12, 12, 20]),
            "face_bolt_fixture": _face("face_bolt_fixture", [8, 8, 10, 12, 12, 10], [0, 0, -1], body="bolt_fixture", area=20),
        },
    }


def _assembly(*, second_design: bool = False, no_load: bool = False) -> dict:
    parts = [
        {
            "id": "bracket",
            "name": "Optimized bracket",
            "role": "design_part",
            "geometry_ref": "geometry/bracket.step",
            "topology_ref": "parts/bracket/topology_map.json",
            "material": "aluminum",
            "source_ir_node": "node_bracket",
        },
        {
            "id": "wall",
            "role": "reference_part",
            "geometry_ref": "geometry/wall.step",
            "topology_ref": "parts/wall/topology_map.json",
            "source_ir_node": "node_wall",
        },
        {
            "id": "load_jig",
            "role": "load_source",
            "geometry_ref": "geometry/load_jig.step",
            "topology_ref": "parts/load_jig/topology_map.json",
            "source_ir_node": "node_load_jig",
        },
        {
            "id": "bolt_fixture",
            "role": "fastener",
            "geometry_ref": "geometry/bolt_fixture.step",
            "topology_ref": "parts/bolt_fixture/topology_map.json",
            "source_ir_node": "node_bolt_fixture",
        },
    ]
    if second_design:
        parts.append({
            "id": "gusset",
            "role": "design_part",
            "geometry_ref": "geometry/gusset.step",
            "topology_ref": "parts/bracket/topology_map.json",
            "source_ir_node": "node_gusset",
        })
    interfaces = [
        {"id": "if_mount", "part_id": "bracket", "semantic_role": "mounting_face", "topology_refs": {"face_ids": ["face_mount"]}},
        {"id": "if_wall", "part_id": "wall", "semantic_role": "support_face", "topology_refs": {"face_ids": ["face_wall"]}},
        {"id": "if_load", "part_id": "bracket", "semantic_role": "load_face", "topology_refs": {"face_ids": ["face_load"]}},
        {"id": "if_jig", "part_id": "load_jig", "semantic_role": "load_face", "topology_refs": {"face_ids": ["face_jig"]}},
        {"id": "if_bolt", "part_id": "bracket", "semantic_role": "bolt_hole", "topology_refs": {"face_ids": ["face_bolt"]}},
        {"id": "if_bolt_fixture", "part_id": "bolt_fixture", "semantic_role": "support_face", "topology_refs": {"face_ids": ["face_bolt_fixture"]}},
    ]
    connections = [
        {"id": "c_mount", "type": "rigid_tie", "part_a": "bracket", "part_b": "wall", "interface_a": "if_mount", "interface_b": "if_wall", "behavior": ["load_transfer"]},
        {"id": "c_bolt", "type": "bolted_proxy", "part_a": "bracket", "part_b": "bolt_fixture", "interface_a": "if_bolt", "interface_b": "if_bolt_fixture", "behavior": ["load_transfer"], "limitations": ["no preload"]},
    ]
    if not no_load:
        connections.append({"id": "c_load", "type": "bolted_proxy", "part_a": "bracket", "part_b": "load_jig", "interface_a": "if_load", "interface_b": "if_jig", "behavior": ["load_transfer"], "limitations": ["load fixture proxy only"]})
    return {
        "format": "aieng.assembly_ir",
        "schema_version": "0.1",
        "unit": "mm",
        "parts": parts,
        "interfaces": interfaces,
        "connections": connections,
        "analysis_intent": {"design_parts": ["bracket"], "frozen_parts": ["wall", "load_jig", "bolt_fixture"]},
    }


def _docs(asm: dict) -> tuple[dict, dict, dict, dict, dict, dict]:
    topo = _topology()
    resolution = resolve_assembly_interfaces(asm, topo)
    geometry = validate_connection_geometry(asm, resolution)
    registry = build_part_registry(asm)
    graph = build_connection_graph(asm)
    draft = build_assembly_cae_setup_draft(asm)
    model, _diag = build_assembly_cae_model(
        assembly=asm,
        part_registry=registry,
        connection_graph=graph,
        interface_resolution=resolution,
        connection_geometry=geometry,
        setup_draft=draft,
    )
    # Make the default load an in-plane load for the 2D topopt projection.
    for load in model.get("boundary_conditions", {}).get("loads", []):
        if load.get("interface_id") == "if_load":
            load["direction"] = [0.0, -1.0, 0.0]
            load["value_n"] = 100.0
    return registry, graph, resolution, geometry, draft, model


def _derive(asm: dict | None = None, *, result_map: dict | None = None, selected_part_id: str | None = None, use_result_guidance: bool = False):
    asm = asm or _assembly()
    reg, graph, resolution, geometry, _draft, model = _docs(asm)
    return derive_assembly_topopt_problem(
        assembly=asm,
        part_registry=reg,
        connection_graph=graph,
        interface_resolution=resolution,
        connection_geometry=geometry,
        assembly_cae_model=model,
        assembly_result_map=result_map or {},
        topology_by_part=_topology(),
        selected_part_id=selected_part_id,
        resolution=12,
        max_iters=6,
        use_result_guidance=use_result_guidance,
    )


def _result_map(confidence: str = "high") -> dict:
    return {
        "format": "aieng.assembly_result_map",
        "mapped_results": [
            {
                "region_id": "hot_stress",
                "part_id": "bracket",
                "interface_id": "if_mount",
                "connection_id": "c_mount",
                "load_case_id": "assembly_lc",
                "result_type": "stress",
                "value": 180.0,
                "unit": "MPa",
                "confidence": confidence,
                "mapping_method": "interface_bbox",
                "location": [4.0, 10.0, 5.0],
                "source_ir_node": "node_bracket",
                "proxy_derived": True,
            },
            {
                "region_id": "tip_deflection",
                "part_id": "bracket",
                "interface_id": "if_load",
                "connection_id": "c_load",
                "load_case_id": "assembly_lc",
                "result_type": "displacement",
                "value": 0.7,
                "unit": "mm",
                "confidence": confidence,
                "mapping_method": "interface_bbox",
                "location": [116.0, 10.0, 5.0],
                "source_ir_node": "node_bracket",
                "proxy_derived": True,
            },
        ],
        "unmapped_regions": [{"region_id": "unmapped_far", "result_type": "stress", "reason": "outside assembly"}],
    }


def _write_pkg(tmp_path: Path, asm: dict, *, result_map: dict | None = None) -> Path:
    pkg = tmp_path / "asm_topopt.aieng"
    reg, graph, resolution, geometry, draft, model = _docs(asm)
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr(ASSEMBLY_IR_PATH, json.dumps(asm))
        zf.writestr(PART_REGISTRY_PATH, json.dumps(reg))
        zf.writestr(CONNECTION_GRAPH_PATH, json.dumps(graph))
        zf.writestr(INTERFACE_RESOLUTION_PATH, json.dumps(resolution))
        zf.writestr(ASSEMBLY_CONNECTION_GEOMETRY_PATH, json.dumps(geometry))
        zf.writestr(ASSEMBLY_CAE_DRAFT_PATH, json.dumps(draft))
        zf.writestr(ASSEMBLY_CAE_MODEL_PATH, json.dumps(model))
        zf.writestr(CONVERSION_MANIFEST_PATH, json.dumps({"format": "aieng.conversion_manifest"}))
        for pid, ents in _topology().items():
            zf.writestr(f"parts/{pid}/topology_map.json", json.dumps({"entities": list(ents.values())}))
        if result_map:
            zf.writestr(ASSEMBLY_RESULT_MAP_PATH, json.dumps(result_map))
    return pkg


def test_selected_design_part_derives_ready_problem_with_standard_problem() -> None:
    problem, diag, standard = _derive()
    assert problem["status"] == "ready"
    assert problem["selected_part_id"] == "bracket"
    assert problem["target_part"]["role"] == "design_part"
    assert problem["standard_problem_emitted"] is True
    assert standard is not None
    assert standard["grid"] == problem["grid"]
    assert standard["bcs"]["supports"] and standard["bcs"]["loads"]
    assert diag["summary"]["standard_problem_emitted"] is True
    assert standard["derivation"]["contact_physics_modeled"] is False
    assert standard["derivation"]["bolt_preload_modeled"] is False


def test_mounting_and_bolt_interfaces_become_preserve_regions() -> None:
    problem, _diag, standard = _derive()
    by_iface = {r["interface_id"]: r for r in problem["preserve_regions"]}
    assert {"if_mount", "if_bolt", "if_load"} <= set(by_iface)
    assert by_iface["if_mount"]["reason"] == "proxy_connection_preserve_reason"
    assert by_iface["if_bolt"]["semantic_role"] == "bolt_hole"
    assert by_iface["if_bolt"]["cells"]
    assert standard is not None
    preserve_ifaces = {r["interface_id"] for r in standard["constraints"]["preserve_regions"]}
    assert "if_bolt" in preserve_ifaces


def test_stress_and_deflection_hotspots_feed_result_guidance() -> None:
    problem, _diag, standard = _derive(result_map=_result_map(), use_result_guidance=True)
    rg = problem["result_guidance"]
    assert rg["available"] is True
    assert rg["advisory_only"] is False
    assert rg["preserve_or_reinforce_regions"][0]["region_id"] == "hot_stress"
    assert rg["preserve_or_reinforce_regions"][0]["enforced"] is True
    assert rg["stiffness_sensitive_regions"][0]["region_id"] == "tip_deflection"
    assert rg["stiffness_sensitive_regions"][0]["enforced"] is True
    assert any(w.startswith("unmapped_region_diagnostic:unmapped_far") for w in problem["warnings"])
    assert standard is not None and standard["result_guidance"]["available"] is True


def test_low_confidence_result_guidance_is_recorded_not_enforced() -> None:
    problem, _diag, standard = _derive(result_map=_result_map(confidence="low"), use_result_guidance=True)
    rg = problem["result_guidance"]
    assert rg["recorded_low_confidence_regions"]
    assert all(item["enforced"] is False for item in rg["preserve_or_reinforce_regions"])
    assert all(item["enforced"] is False for item in rg["stiffness_sensitive_regions"])
    assert any(w.startswith("low_confidence_result_guidance_recorded:") for w in problem["warnings"])
    assert standard is not None
    res = run_topology_optimization(standard)
    assert res["result"]["result_guidance_consumed"] is False


def test_reference_or_frozen_part_cannot_be_selected_for_optimization() -> None:
    problem, _diag, standard = _derive(selected_part_id="wall")
    assert problem["status"] == "needs_user_input"
    assert "selected_part_not_optimizable" in problem["diagnostics"]
    assert standard is None


def test_multiple_design_parts_requires_explicit_selection() -> None:
    problem, _diag, standard = _derive(_assembly(second_design=True))
    assert problem["status"] == "needs_user_input"
    assert "multiple_design_parts_needs_selection" in problem["diagnostics"]
    assert standard is None
    assert {c["part_id"] for c in problem["candidate_parts"]} == {"bracket", "gusset"}


def test_missing_loads_or_supports_blocks_standard_problem() -> None:
    problem, _diag, standard = _derive(_assembly(no_load=True))
    assert problem["status"] == "needs_user_input"
    assert "missing_loads_supports" in problem["diagnostics"]
    assert problem["standard_problem_emitted"] is False
    assert standard is None


def test_standard_problem_is_consumable_by_existing_optimizer() -> None:
    _problem, _diag, standard = _derive()
    assert standard is not None
    result = run_topology_optimization(standard)
    assert result["problem"]["bcs_source"] == "explicit"
    hist = result["result"]["compliance_history"]
    assert len(hist) >= 1 and all(v > 0 for v in hist)
    assert result["provenance"]["source_ir_node"] == "node_bracket"


def test_package_writer_emits_assembly_and_standard_artifacts(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly(), result_map=_result_map())
    result = write_assembly_topopt_problem(pkg, resolution=12, max_iters=6, use_result_guidance=True)
    assert result["assembly_present"] is True
    assert result["status"] == "ready"
    assert result["standard_problem_emitted"] is True
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert ASSEMBLY_TOPOPT_PROBLEM_PATH in names
        assert ASSEMBLY_TOPOPT_DERIVATION_PATH in names
        assert STANDARD_TOPOPT_PROBLEM_PATH in names
        assert ASSEMBLY_IR_PATH in names  # input assembly is preserved, not rewritten
        problem = json.loads(zf.read(ASSEMBLY_TOPOPT_PROBLEM_PATH))
        diag = json.loads(zf.read(ASSEMBLY_TOPOPT_DERIVATION_PATH))
        standard = json.loads(zf.read(STANDARD_TOPOPT_PROBLEM_PATH))
        manifest = json.loads(zf.read(CONVERSION_MANIFEST_PATH))
    assert problem["selected_part_id"] == "bracket"
    assert diag["summary"]["standard_problem_emitted"] is True
    assert standard["bcs"]["supports"] and standard["bcs"]["loads"]
    assert manifest["assembly"]["assembly_topopt_status"] == "ready"


def test_assembly_cae_processing_writes_topopt_setup_without_running_optimizer(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly())
    result = process_assembly_cae_package(pkg)
    assert result["assembly_topopt_status"] == "ready"
    assert result["assembly_topopt_standard_problem_emitted"] is True
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert ASSEMBLY_TOPOPT_PROBLEM_PATH in names
        assert ASSEMBLY_TOPOPT_DERIVATION_PATH in names
        assert STANDARD_TOPOPT_PROBLEM_PATH in names
        assert "analysis/topology_optimization.json" not in names


def test_package_without_assembly_is_unchanged(tmp_path: Path) -> None:
    pkg = tmp_path / "plain.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", "{}")
    before = set(zipfile.ZipFile(pkg).namelist())
    result = write_assembly_topopt_problem(pkg)
    after = set(zipfile.ZipFile(pkg).namelist())
    assert result["assembly_present"] is False
    assert before == after
