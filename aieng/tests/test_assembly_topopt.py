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
    ASSEMBLY_DESIGN_RECOMMENDATIONS_PATH,
    ASSEMBLY_NEXT_ACTIONS_PATH,
    ASSEMBLY_OPTIMIZATION_SUMMARY_PATH,
    ASSEMBLY_POST_OPTIMIZATION_VERIFICATION_PATH,
    ASSEMBLY_POSTPROCESS_REPORT_PATH,
    ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH,
    ASSEMBLY_TOPOPT_EXECUTION_PATH,
    ASSEMBLY_TOPOPT_DERIVATION_PATH,
    ASSEMBLY_TOPOPT_PROBLEM_PATH,
    PART_OPTIMIZED_SHAPE_IR_TEMPLATE,
    PART_TOPOLOGY_OPTIMIZATION_TEMPLATE,
    STANDARD_TOPOPT_PROBLEM_PATH,
    derive_assembly_topopt_problem,
    run_assembly_topology_optimization,
    verify_assembly_post_optimization,
    write_assembly_design_recommendations,
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


def test_run_assembly_topology_optimization_executes_existing_optimizer_and_writes_part_artifacts(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly(), result_map=_result_map())
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6, use_result_guidance=True)
    result = run_assembly_topology_optimization(pkg, method="voxels", representation="manifold_mesh")
    assert result["status"] == "derived_part_artifact_written"
    assert result["selected_part_id"] == "bracket"
    assert result["bcs_source"] == "explicit"
    assert result["preserve_constraints"]["preserve_regions_total"] >= 3
    assert result["preserve_constraints"]["preserve_regions_mapped"] >= 3
    assert result["preserve_constraints"]["cells_preserved"] > 0
    part_result = PART_TOPOLOGY_OPTIMIZATION_TEMPLATE.format(part_id="bracket")
    part_shape = PART_OPTIMIZED_SHAPE_IR_TEMPLATE.format(part_id="bracket")
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH in names
        assert ASSEMBLY_TOPOPT_EXECUTION_PATH in names
        assert ASSEMBLY_POST_OPTIMIZATION_VERIFICATION_PATH in names
        assert ASSEMBLY_OPTIMIZATION_SUMMARY_PATH in names
        assert ASSEMBLY_DESIGN_RECOMMENDATIONS_PATH in names
        assert ASSEMBLY_POSTPROCESS_REPORT_PATH in names
        assert ASSEMBLY_NEXT_ACTIONS_PATH in names
        assert part_result in names
        assert part_shape in names
        assert PART_OPTIMIZED_SHAPE_IR_TEMPLATE.format(part_id="wall") not in names
        execution = json.loads(zf.read(ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH))
        topo = json.loads(zf.read(part_result))
        shape = json.loads(zf.read(part_shape))
        verification = json.loads(zf.read(ASSEMBLY_POST_OPTIMIZATION_VERIFICATION_PATH))
        recommendations = json.loads(zf.read(ASSEMBLY_DESIGN_RECOMMENDATIONS_PATH))
        report = json.loads(zf.read(ASSEMBLY_POSTPROCESS_REPORT_PATH))
    assert execution["topology_optimization"]["provenance"]["selected_part_id"] == "bracket"
    assert topo["problem"]["bcs_source"] == "explicit"
    assert topo["result"]["guidance_field_summary"]["cells_preserved"] > 0
    assert shape["assembly_writeback"]["selected_part_id"] == "bracket"
    assert shape["assembly_writeback"]["original_geometry_ref_preserved"] == "geometry/bracket.step"
    assert verification["status"] == "passed"
    assert verification["selected_part"]["optimized_artifact_found"] is True
    assert verification["provenance"]["proxy_limitations_preserved"] is True
    assert recommendations["status"] == "accept"
    assert {item["type"] for item in recommendations["recommendations"]} >= {
        "accept_candidate",
        "proceed_to_dimension_optimization",
        "proceed_to_mesh_to_cad_reconstruction",
    }
    assert report["status"] == "accept"
    assert report["recommendation_count"] >= 3


def test_run_without_runnable_standard_problem_returns_needs_user_input(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly(no_load=True))
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6)
    result = run_assembly_topology_optimization(pkg)
    assert result["status"] == "needs_user_input"
    assert "missing_topology_optimization_problem" in result["diagnostics"]
    with zipfile.ZipFile(pkg) as zf:
        assert ASSEMBLY_TOPOPT_EXECUTION_PATH in zf.namelist()
        assert ASSEMBLY_POST_OPTIMIZATION_VERIFICATION_PATH in zf.namelist()
        assert ASSEMBLY_DESIGN_RECOMMENDATIONS_PATH in zf.namelist()
        assert ASSEMBLY_POSTPROCESS_REPORT_PATH in zf.namelist()
        assert PART_TOPOLOGY_OPTIMIZATION_TEMPLATE.format(part_id="bracket") not in zf.namelist()
        verification = json.loads(zf.read(ASSEMBLY_POST_OPTIMIZATION_VERIFICATION_PATH))
        recommendations = json.loads(zf.read(ASSEMBLY_DESIGN_RECOMMENDATIONS_PATH))
    assert verification["status"] == "insufficient_data"
    assert recommendations["status"] == "insufficient_data"
    assert recommendations["recommendations"][0]["type"] == "request_user_input"


def test_recommendations_request_rerun_when_high_confidence_stress_guidance_was_not_consumed(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly(), result_map=_result_map())
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6, use_result_guidance=True)
    run_assembly_topology_optimization(pkg, method="voxels", representation="manifold_mesh")
    with zipfile.ZipFile(pkg) as zf:
        execution = json.loads(zf.read(ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH))
    execution["topology_optimization"]["result"]["result_guidance_consumed"] = False
    tmp = pkg.with_suffix(".tmp.aieng")
    with zipfile.ZipFile(pkg) as src, zipfile.ZipFile(tmp, "w") as dst:
        for item in src.infolist():
            if item.filename != ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH:
                dst.writestr(item, src.read(item.filename))
        dst.writestr(ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH, json.dumps(execution))
    tmp.replace(pkg)
    rec_result = write_assembly_design_recommendations(pkg)
    assert rec_result["status"] == "rerun_recommended"
    rec_types = {item["type"] for item in rec_result["recommendations"]["recommendations"]}
    assert "rerun_topopt" in rec_types
    assert "increase_stiffness_weight" in rec_types


def test_recommendations_request_user_input_for_low_confidence_result_mapping(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly(), result_map=_result_map(confidence="low"))
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6, use_result_guidance=True)
    run_assembly_topology_optimization(pkg, method="voxels", representation="manifold_mesh")
    rec_result = write_assembly_design_recommendations(pkg)
    assert rec_result["status"] == "needs_user_input"
    rec_types = {item["type"] for item in rec_result["recommendations"]["recommendations"]}
    assert "request_user_input" in rec_types
    assert "rerun_topopt" not in rec_types


def test_recommendation_writer_leaves_non_assembly_package_unchanged(tmp_path: Path) -> None:
    pkg = tmp_path / "plain_recommendations.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", "{}")
    before = set(zipfile.ZipFile(pkg).namelist())
    result = write_assembly_design_recommendations(pkg)
    after = set(zipfile.ZipFile(pkg).namelist())
    assert result["assembly_present"] is False
    assert before == after


def test_preserve_regions_without_grid_cells_are_warned_not_silent(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly())
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6)
    # Corrupt one preserve region cell map in the setup artifact to mimic an unresolved mapping.
    with zipfile.ZipFile(pkg) as zf:
        problem = json.loads(zf.read(ASSEMBLY_TOPOPT_PROBLEM_PATH))
    problem["preserve_regions"][0]["cells"] = []
    tmp = pkg.with_suffix(".tmp.aieng")
    with zipfile.ZipFile(pkg) as src, zipfile.ZipFile(tmp, "w") as dst:
        for item in src.infolist():
            if item.filename != ASSEMBLY_TOPOPT_PROBLEM_PATH:
                dst.writestr(item, src.read(item.filename))
        dst.writestr(ASSEMBLY_TOPOPT_PROBLEM_PATH, json.dumps(problem))
    tmp.replace(pkg)
    result = run_assembly_topology_optimization(pkg, method="voxels")
    assert result["preserve_constraints"]["preserve_regions_unmapped"] == 1
    assert any(w.startswith("preserve_region_unmapped:") for w in result["warnings"])


def test_assembly_result_map_guidance_is_preserved_in_execution_output(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly(), result_map=_result_map())
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6, use_result_guidance=True)
    result = run_assembly_topology_optimization(pkg, method="voxels")
    rg = result["execution"]["assembly_result_guidance"]
    assert rg["available"] is True
    assert rg["preserve_or_reinforce_regions"][0]["region_id"] == "hot_stress"
    assert result["execution"]["topology_optimization"]["result"]["result_guidance_consumed"] is True


def test_safe_writeback_target_missing_does_not_write_shape_artifact(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly())
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6)
    with zipfile.ZipFile(pkg) as zf:
        problem = json.loads(zf.read(ASSEMBLY_TOPOPT_PROBLEM_PATH))
    problem["target_part"].pop("geometry_ref", None)
    problem["target_part"].pop("source_ir_node", None)
    problem["target_part"].pop("design_space_node", None)
    tmp = pkg.with_suffix(".tmp.aieng")
    with zipfile.ZipFile(pkg) as src, zipfile.ZipFile(tmp, "w") as dst:
        for item in src.infolist():
            if item.filename != ASSEMBLY_TOPOPT_PROBLEM_PATH:
                dst.writestr(item, src.read(item.filename))
        dst.writestr(ASSEMBLY_TOPOPT_PROBLEM_PATH, json.dumps(problem))
    tmp.replace(pkg)
    result = run_assembly_topology_optimization(pkg, method="voxels")
    assert result["status"] == "needs_user_input"
    assert "safe_writeback_target_missing" in result["diagnostics"]
    with zipfile.ZipFile(pkg) as zf:
        assert PART_OPTIMIZED_SHAPE_IR_TEMPLATE.format(part_id="bracket") not in zf.namelist()


def test_post_optimization_verification_fails_when_selected_artifact_is_missing(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly(), result_map=_result_map())
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6, use_result_guidance=True)
    run_assembly_topology_optimization(pkg, method="voxels", representation="manifold_mesh")
    missing_path = PART_OPTIMIZED_SHAPE_IR_TEMPLATE.format(part_id="bracket")
    tmp = pkg.with_suffix(".tmp.aieng")
    with zipfile.ZipFile(pkg) as src, zipfile.ZipFile(tmp, "w") as dst:
        for item in src.infolist():
            if item.filename != missing_path:
                dst.writestr(item, src.read(item.filename))
    tmp.replace(pkg)
    verification = verify_assembly_post_optimization(pkg)
    assert verification["status"] == "failed"
    assert "selected_optimized_artifact_missing" in verification["verification"]["selected_part"]["errors"]


def test_post_optimization_verification_flags_non_selected_frozen_part_modification(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly(), result_map=_result_map())
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6, use_result_guidance=True)
    run_assembly_topology_optimization(pkg, method="voxels", representation="manifold_mesh")
    wall_shape = PART_OPTIMIZED_SHAPE_IR_TEMPLATE.format(part_id="wall")
    wall_topopt = PART_TOPOLOGY_OPTIMIZATION_TEMPLATE.format(part_id="wall")
    tmp = pkg.with_suffix(".tmp.aieng")
    with zipfile.ZipFile(pkg) as src, zipfile.ZipFile(tmp, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        dst.writestr(wall_shape, json.dumps({"assembly_writeback": {"selected_part_id": "wall"}}))
        dst.writestr(wall_topopt, json.dumps({"problem": {"bcs_source": "explicit"}}))
    tmp.replace(pkg)
    verification = verify_assembly_post_optimization(pkg)
    assert verification["status"] == "failed"
    frozen = verification["verification"]["non_selected_parts"]["frozen_parts_modified"]
    assert any(item["part_id"] == "wall" for item in frozen)


def test_post_optimization_verification_warns_when_preserve_region_is_unmapped(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly(), result_map=_result_map())
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6)
    with zipfile.ZipFile(pkg) as zf:
        problem = json.loads(zf.read(ASSEMBLY_TOPOPT_PROBLEM_PATH))
    problem["preserve_regions"][0]["cells"] = []
    tmp = pkg.with_suffix(".tmp.aieng")
    with zipfile.ZipFile(pkg) as src, zipfile.ZipFile(tmp, "w") as dst:
        for item in src.infolist():
            if item.filename != ASSEMBLY_TOPOPT_PROBLEM_PATH:
                dst.writestr(item, src.read(item.filename))
        dst.writestr(ASSEMBLY_TOPOPT_PROBLEM_PATH, json.dumps(problem))
    tmp.replace(pkg)
    run_assembly_topology_optimization(pkg, method="voxels")
    verification = verify_assembly_post_optimization(pkg)
    assert verification["status"] == "warning"
    preserve = verification["verification"]["preserve_interfaces"]
    assert preserve["preserve_regions_unmapped"] == 1
    assert any(w.startswith("preserve_region_unmapped:") for w in preserve["warnings"])


def test_post_optimization_verification_fails_on_unsupported_claims(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly(), result_map=_result_map())
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6, use_result_guidance=True)
    run_assembly_topology_optimization(pkg, method="voxels")
    with zipfile.ZipFile(pkg) as zf:
        execution = json.loads(zf.read(ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH))
    execution.setdefault("provenance", {})["bolt_preload_modelled"] = True
    execution["provenance"]["contact_physics_modeled"] = True
    tmp = pkg.with_suffix(".tmp.aieng")
    with zipfile.ZipFile(pkg) as src, zipfile.ZipFile(tmp, "w") as dst:
        for item in src.infolist():
            if item.filename != ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH:
                dst.writestr(item, src.read(item.filename))
        dst.writestr(ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH, json.dumps(execution))
    tmp.replace(pkg)
    verification = verify_assembly_post_optimization(pkg)
    assert verification["status"] == "failed"
    claims = verification["verification"]["provenance"]["unsupported_claims_detected"]
    assert any("contact_physics_modeled" in item for item in claims)
    assert any("bolt_preload_modelled" in item for item in claims)


def test_post_optimization_verification_is_insufficient_without_execution_artifacts(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly(), result_map=_result_map())
    write_assembly_topopt_problem(pkg, resolution=12, max_iters=6)
    verification = verify_assembly_post_optimization(pkg)
    assert verification["status"] == "insufficient_data"
    assert any(err.startswith("missing_input:analysis/assembly_topology_optimization.json") for err in verification["verification"]["errors"])


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
        assert ASSEMBLY_DESIGN_RECOMMENDATIONS_PATH not in names
        assert ASSEMBLY_POSTPROCESS_REPORT_PATH not in names


def test_package_without_assembly_is_unchanged(tmp_path: Path) -> None:
    pkg = tmp_path / "plain.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", "{}")
    before = set(zipfile.ZipFile(pkg).namelist())
    result = write_assembly_topopt_problem(pkg)
    after = set(zipfile.ZipFile(pkg).namelist())
    assert result["assembly_present"] is False
    assert before == after
