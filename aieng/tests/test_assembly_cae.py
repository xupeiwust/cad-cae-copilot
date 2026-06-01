"""Tests for Assembly CAE v0 simplified proxy execution contract."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.assembly_cae import (
    ASSEMBLY_CAE_MODEL_DIAGNOSTICS_PATH,
    ASSEMBLY_CAE_MODEL_PATH,
    ASSEMBLY_COMPUTED_METRICS_PATH,
    ASSEMBLY_FIELD_REGIONS_PATH,
    ASSEMBLY_RESULT_MAP_PATH,
    ASSEMBLY_RESULT_MAPPING_DIAGNOSTICS_PATH,
    ASSEMBLY_SOLVER_DECK_DIAGNOSTICS_PATH,
    ASSEMBLY_SOLVER_DECK_PATH,
    ASSEMBLY_SOLVER_EXECUTION_DIAGNOSTICS_PATH,
    build_assembly_cae_model,
    generate_assembly_solver_deck,
    map_assembly_results,
    normalize_assembly_solver_result,
    process_assembly_cae_package,
)
from aieng.converters.assembly_interface_resolution import (
    ASSEMBLY_CONNECTION_GEOMETRY_PATH,
    INTERFACE_RESOLUTION_PATH,
    resolve_assembly_interfaces,
    resolve_and_validate_assembly_geometry,
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


def _face(fid: str, bbox: list[float], normal: list[float], *, area=25.0, body=None) -> dict:
    out = {"id": fid, "type": "face", "bounding_box": bbox, "normal": normal, "area": area}
    if body:
        out["body_id"] = body
    return out


def _topology() -> dict:
    return {
        "a": {"a_top": _face("a_top", [0, 0, 10, 5, 5, 10], [0, 0, 1.0], body="a")},
        "b": {"b_bot": _face("b_bot", [0, 0, 0, 5, 5, 0], [0, 0, -1.0], body="b")},
    }


def _assembly(conn_type="rigid_tie", *, missing_interface=False, far=False, mesh=False) -> dict:
    parts = [
        {
            "id": "a",
            "role": "design_part",
            "geometry_ref": "geometry/a.step",
            "transform": {"translation": [0, 0, 0], "unit": "mm"},
            "material": "steel",
            "source_ir_node": "node_a",
        },
        {
            "id": "b",
            "role": "reference_part",
            "geometry_ref": "geometry/b.step",
            "transform": {"translation": [0, 0, 10 if not far else 1000], "unit": "mm"},
            "material": "steel",
            "source_ir_node": "node_b",
        },
    ]
    if mesh:
        parts[0]["mesh_ref"] = "simulation/mesh/a.inp"
        parts[1]["mesh_ref"] = "simulation/mesh/b.inp"
    conn = {"id": "c1", "type": conn_type, "part_a": "a", "part_b": "b", "behavior": ["load_transfer"]}
    if not missing_interface:
        conn.update({"interface_a": "if_a", "interface_b": "if_b"})
    if conn_type == "bolted_proxy":
        conn["limitations"] = ["no preload"]
    if conn_type == "spring_proxy":
        conn["limitations"] = ["linear spring only"]
    if conn_type == "contact_proxy":
        conn["limitations"] = ["draft only"]
    return {
        "format": "aieng.assembly_ir",
        "schema_version": "0.1",
        "unit": "mm",
        "parts": parts,
        "interfaces": [
            {
                "id": "if_a",
                "part_id": "a",
                "semantic_role": "mounting_face",
                "topology_refs": {"face_ids": ["a_top"]},
            },
            {
                "id": "if_b",
                "part_id": "b",
                "semantic_role": "support_face",
                "topology_refs": {"face_ids": ["b_bot"]},
            },
        ],
        "connections": [conn],
        "analysis_intent": {"design_parts": ["a"], "frozen_parts": ["b"]},
        "provenance": {"fixture": "test"},
    }


def _docs(asm: dict) -> tuple[dict, dict, dict, dict, dict]:
    resolution = resolve_assembly_interfaces(asm, _topology())
    geometry = validate_connection_geometry(asm, resolution)
    return (
        build_part_registry(asm),
        build_connection_graph(asm),
        resolution,
        geometry,
        build_assembly_cae_setup_draft(asm),
    )


def _write_pkg(tmp_path: Path, asm: dict, *, generic_result: dict | None = None) -> Path:
    pkg = tmp_path / "asm.aieng"
    reg, graph, resolution, geometry, draft = _docs(asm)
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr(ASSEMBLY_IR_PATH, json.dumps(asm))
        zf.writestr(PART_REGISTRY_PATH, json.dumps(reg))
        zf.writestr(CONNECTION_GRAPH_PATH, json.dumps(graph))
        zf.writestr(INTERFACE_RESOLUTION_PATH, json.dumps(resolution))
        zf.writestr(ASSEMBLY_CONNECTION_GEOMETRY_PATH, json.dumps(geometry))
        zf.writestr(ASSEMBLY_CAE_DRAFT_PATH, json.dumps(draft))
        zf.writestr(CONVERSION_MANIFEST_PATH, json.dumps({"format": "aieng.conversion_manifest"}))
        if generic_result:
            zf.writestr("simulation/assembly_solver_result.json", json.dumps(generic_result))
    return pkg


def test_valid_two_part_rigid_tie_creates_enabled_tie_proxy() -> None:
    asm = _assembly("rigid_tie")
    reg, graph, resolution, geometry, draft = _docs(asm)
    model, diag = build_assembly_cae_model(
        assembly=asm,
        part_registry=reg,
        connection_graph=graph,
        interface_resolution=resolution,
        connection_geometry=geometry,
        setup_draft=draft,
    )
    conn = model["connections"][0]
    assert conn["proxy_model_type"] == "tie_proxy"
    assert conn["enabled_for_solver"] is True
    assert conn["load_transfer"] is True
    assert diag["summary"]["enabled_connection_count"] == 1
    assert model["provenance"]["production_ready"] is False


def test_bolted_proxy_is_connector_proxy_with_no_preload_limitation() -> None:
    asm = _assembly("bolted_proxy")
    reg, graph, resolution, geometry, draft = _docs(asm)
    model, _diag = build_assembly_cae_model(
        assembly=asm, part_registry=reg, connection_graph=graph,
        interface_resolution=resolution, connection_geometry=geometry, setup_draft=draft)
    conn = model["connections"][0]
    assert conn["proxy_model_type"] == "bolted_connector_proxy"
    assert conn["enabled_for_solver"] is True
    assert any("preload" in item.lower() for item in conn["limitations"])


def test_contact_proxy_is_unsupported_and_not_solver_enabled() -> None:
    asm = _assembly("contact_proxy")
    reg, graph, resolution, geometry, draft = _docs(asm)
    model, diag = build_assembly_cae_model(
        assembly=asm, part_registry=reg, connection_graph=graph,
        interface_resolution=resolution, connection_geometry=geometry, setup_draft=draft)
    conn = model["connections"][0]
    assert conn["proxy_model_type"] == "unsupported_contact_proxy"
    assert conn["enabled_for_solver"] is False
    assert "unsupported_proxy_type" in conn["disabled_reason"]
    assert diag["summary"]["disabled_connection_count"] == 1


def test_invalid_far_apart_connection_is_disabled() -> None:
    asm = _assembly("rigid_tie", far=True)
    reg, graph, resolution, geometry, draft = _docs(asm)
    model, diag = build_assembly_cae_model(
        assembly=asm, part_registry=reg, connection_graph=graph,
        interface_resolution=resolution, connection_geometry=geometry, setup_draft=draft)
    assert model["connections"][0]["geometry_status"] == "invalid"
    assert model["connections"][0]["enabled_for_solver"] is False
    assert model["status"] == "needs_user_input"
    assert diag["needs_user_input"]


def test_missing_interface_creates_needs_user_input() -> None:
    asm = _assembly("rigid_tie", missing_interface=True)
    reg, graph, resolution, geometry, draft = _docs(asm)
    model, diag = build_assembly_cae_model(
        assembly=asm, part_registry=reg, connection_graph=graph,
        interface_resolution=resolution, connection_geometry=geometry, setup_draft=draft)
    assert model["connections"][0]["enabled_for_solver"] is False
    assert "missing_interface" in model["connections"][0]["disabled_reason"]
    assert diag["status"] == "needs_user_input"


def test_solver_deck_generation_skips_without_mesh_and_can_generate_with_mesh() -> None:
    asm = _assembly("rigid_tie")
    reg, graph, resolution, geometry, draft = _docs(asm)
    model, _diag = build_assembly_cae_model(
        assembly=asm, part_registry=reg, connection_graph=graph,
        interface_resolution=resolution, connection_geometry=geometry, setup_draft=draft)
    deck, deck_diag = generate_assembly_solver_deck(model, available_members=set())
    assert deck is None
    assert deck_diag["status"] == "skipped"
    assert "mesh" in deck_diag["reason"]

    asm_mesh = _assembly("rigid_tie", mesh=True)
    reg, graph, resolution, geometry, draft = _docs(asm_mesh)
    model, _diag = build_assembly_cae_model(
        assembly=asm_mesh, part_registry=reg, connection_graph=graph,
        interface_resolution=resolution, connection_geometry=geometry, setup_draft=draft)
    deck, deck_diag = generate_assembly_solver_deck(model, available_members=set())
    assert deck is None
    assert deck_diag["reason"] == "mesh_ref members missing from package"

    deck, deck_diag = generate_assembly_solver_deck(
        model, available_members={"simulation/mesh/a.inp", "simulation/mesh/b.inp"})
    assert deck is not None and "*INCLUDE, INPUT=simulation/mesh/a.inp" in deck
    assert deck_diag["metadata"]["contact_physics_modeled"] is False
    assert deck_diag["metadata"]["bolt_preload_modeled"] is False


def test_generic_solver_result_normalizes_preserving_load_case_and_units() -> None:
    native = {
        "solver": {"name": "generic_fake", "version": "1", "adapter": "fake_asm"},
        "load_cases": [{"id": "lc_asm", "results": [
            {"result_type": "stress", "metric": "peak_vm", "max": 99.0, "unit": "MPa"}
        ]}],
        "regions": [{"id": "r1", "result_type": "stress", "load_case_id": "lc_asm",
                     "center": {"x": 2, "y": 2, "z": 10}, "value": {"peak": 99.0, "unit": "MPa"},
                     "connection_id": "c1"}],
    }
    cm, fr = normalize_assembly_solver_result(native)
    assert cm["solver"]["name"] == "generic_fake"
    assert cm["load_cases"][0]["id"] == "lc_asm"
    assert cm["load_cases"][0]["results"][0]["unit"] == "MPa"
    assert fr["regions"][0]["proxy_derived"] is True


def test_assembly_result_mapping_to_part_interface_connection_and_source_node() -> None:
    asm = _assembly("rigid_tie")
    reg, graph, resolution, geometry, draft = _docs(asm)
    model, _diag = build_assembly_cae_model(
        assembly=asm, part_registry=reg, connection_graph=graph,
        interface_resolution=resolution, connection_geometry=geometry, setup_draft=draft)
    cm, fr = normalize_assembly_solver_result({
        "load_cases": [{"id": "lc1", "results": [{"result_type": "stress", "max": 11, "unit": "MPa"}]}],
        "regions": [{"id": "r1", "result_type": "stress", "load_case_id": "lc1",
                     "center": {"x": 2, "y": 2, "z": 10}, "value": {"peak": 11, "unit": "MPa"},
                     "interface_id": "if_a", "connection_id": "c1"}],
    })
    res, diag = map_assembly_results(computed_metrics=cm, field_regions=fr, model=model)
    mapped = res["mapped_results"][0]
    assert mapped["part_id"] == "a"
    assert mapped["interface_id"] == "if_a"
    assert mapped["connection_id"] == "c1"
    assert mapped["source_ir_node"] == "node_a"
    assert mapped["confidence"] == "high"
    assert mapped["proxy_derived"] is True
    assert diag["status"] == "mapped"


def test_ambiguous_and_unmapped_regions_are_preserved() -> None:
    asm = _assembly("rigid_tie")
    reg, graph, resolution, geometry, draft = _docs(asm)
    model, _diag = build_assembly_cae_model(
        assembly=asm, part_registry=reg, connection_graph=graph,
        interface_resolution=resolution, connection_geometry=geometry, setup_draft=draft)
    # Duplicate the same bbox on another interface to force ambiguity.
    model["interfaces"].append({**model["interfaces"][0], "interface_id": "if_shadow"})
    cm, fr = normalize_assembly_solver_result({
        "regions": [
            {"id": "amb", "result_type": "stress", "center": {"x": 2, "y": 2, "z": 10},
             "value": {"peak": 1, "unit": "MPa"}},
            {"id": "far", "result_type": "stress", "center": {"x": 500, "y": 500, "z": 500},
             "value": {"peak": 2, "unit": "MPa"}},
        ],
    })
    res, _diag = map_assembly_results(computed_metrics=cm, field_regions=fr, model=model)
    amb = next(m for m in res["mapped_results"] if m["region_id"] == "amb")
    assert amb["confidence"] == "low"
    # Nearest part fallback is honest medium confidence, not a fabricated topology resolution.
    far = next(m for m in res["mapped_results"] if m["region_id"] == "far")
    assert far["mapping_method"] == "nearest_part_centroid" and far["confidence"] == "medium"


def test_package_processing_writes_model_skipped_diagnostics_and_manifest(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly("rigid_tie"))
    result = process_assembly_cae_package(pkg)
    assert result["assembly_present"] is True
    assert result["assembly_cae_model_status"] == "ready"
    assert result["solver_deck_status"] == "skipped"
    assert result["solver_execution_status"] == "skipped"
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        for art in (
            ASSEMBLY_CAE_MODEL_PATH,
            ASSEMBLY_CAE_MODEL_DIAGNOSTICS_PATH,
            ASSEMBLY_SOLVER_DECK_DIAGNOSTICS_PATH,
            ASSEMBLY_SOLVER_EXECUTION_DIAGNOSTICS_PATH,
            ASSEMBLY_RESULT_MAPPING_DIAGNOSTICS_PATH,
        ):
            assert art in names
        assert ASSEMBLY_SOLVER_DECK_PATH not in names
        manifest = json.loads(zf.read(CONVERSION_MANIFEST_PATH))
    assert manifest["assembly"]["assembly_cae_model_status"] == "ready"
    assert manifest["assembly"]["solver_executed"] is False


def test_package_processing_normalizes_fake_result_and_maps_back(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, _assembly("rigid_tie"), generic_result={
        "solver": {"name": "generic_fake", "version": "1", "adapter": "fake_asm"},
        "load_cases": [{"id": "lc1", "results": [{"result_type": "stress", "max": 12, "unit": "MPa"}]}],
        "regions": [{"id": "r1", "result_type": "stress", "load_case_id": "lc1",
                     "center": {"x": 2, "y": 2, "z": 10}, "value": {"peak": 12, "unit": "MPa"},
                     "connection_id": "c1"}],
    })
    result = process_assembly_cae_package(pkg)
    assert result["solver_execution_status"] == "normalized_external_result"
    assert result["assembly_result_mapping_status"] == "mapped"
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert ASSEMBLY_COMPUTED_METRICS_PATH in names
        assert ASSEMBLY_FIELD_REGIONS_PATH in names
        assert ASSEMBLY_RESULT_MAP_PATH in names
        amap = json.loads(zf.read(ASSEMBLY_RESULT_MAP_PATH))
    assert amap["mapped_results"][0]["connection_id"] == "c1"
    assert amap["mapped_results"][0]["source_ir_node"] == "node_a"


def test_resolve_and_validate_integration_writes_assembly_cae_artifacts(tmp_path: Path) -> None:
    pkg = tmp_path / "asm.aieng"
    asm = _assembly("rigid_tie")
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr(ASSEMBLY_IR_PATH, json.dumps(asm))
        topo = _topology()
        for pid, ents in topo.items():
            zf.writestr(f"parts/{pid}/topology_map.json", json.dumps({"entities": list(ents.values())}))
        zf.writestr(CONVERSION_MANIFEST_PATH, json.dumps({"format": "aieng.conversion_manifest"}))
    result = resolve_and_validate_assembly_geometry(pkg)
    assert result["assembly_cae_model_status"] == "ready"
    assert result["solver_deck_status"] == "skipped"
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert ASSEMBLY_CAE_MODEL_PATH in names
        assert ASSEMBLY_SOLVER_DECK_PATH not in names


def test_package_without_assembly_is_unchanged(tmp_path: Path) -> None:
    pkg = tmp_path / "plain.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", "{}")
    before = set(zipfile.ZipFile(pkg).namelist())
    result = process_assembly_cae_package(pkg)
    after = set(zipfile.ZipFile(pkg).namelist())
    assert result["assembly_present"] is False
    assert before == after
