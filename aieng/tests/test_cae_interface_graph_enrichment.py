"""Tests for Phase 10C: CAE mappings enrich objects/interface_graph.json."""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from aieng.cli import main
from aieng.validate import validate_package

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
STEP_PATH = EXAMPLES_DIR / "bracket.step"
CONTEXT_PATH = EXAMPLES_DIR / "bracket_user_context.yaml"
DECK_FIXTURE_PATH = EXAMPLES_DIR / "bracket_loadcase.inp"
MAPPING_FIXTURE_PATH = EXAMPLES_DIR / "bracket_cae_mapping.yaml"

INTERFACE_GRAPH_PATH = "objects/interface_graph.json"
CAE_MAPPING_PATH = "simulation/cae_mapping.json"


def _read_member_json(pkg: Path, member: str) -> dict[str, Any]:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


def _read_member_text(pkg: Path, member: str) -> str:
    with zipfile.ZipFile(pkg) as zf:
        return zf.read(member).decode("utf-8")


def _tamper_member(pkg: Path, member: str, data: dict[str, Any]) -> None:
    with zipfile.ZipFile(pkg, mode="r") as zf:
        members = [
            (info, b"" if info.is_dir() else zf.read(info.filename))
            for info in zf.infolist()
            if info.filename != member
        ]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=pkg.parent) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with zipfile.ZipFile(tmp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for info, blob in members:
                zf.writestr(info, blob)
            zf.writestr(member, json.dumps(data, indent=2).encode())
        shutil.move(str(tmp_path), pkg)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _make_phase10c_package(tmp_path: Path) -> Path:
    pkg = tmp_path / "bracket_001.aieng"
    assert main(["import-step", str(STEP_PATH), "--out", str(pkg)]) == 0
    assert main(["extract-topology", str(pkg), "--overwrite", "--backend", "mock"]) == 0
    assert main(["recognize-features", str(pkg), "--overwrite"]) == 0
    assert main(["apply-context", str(pkg), "--context", str(CONTEXT_PATH), "--overwrite"]) == 0
    assert main(["build-interface-graph", str(pkg), "--overwrite"]) == 0
    assert main(
        [
            "import-cae-deck",
            str(pkg),
            "--deck",
            str(DECK_FIXTURE_PATH),
            "--format",
            "calculix",
            "--overwrite",
        ]
    ) == 0
    assert main(["apply-cae-mapping", str(pkg), "--mapping", str(MAPPING_FIXTURE_PATH), "--overwrite"]) == 0
    assert main(["build-interface-graph", str(pkg), "--overwrite"]) == 0
    return pkg


def _interface_by_feature(interface_graph: dict[str, Any], feature_id: str) -> dict[str, Any]:
    for interface in interface_graph["interfaces"]:
        if feature_id in interface.get("feature_ids", []):
            return interface
    raise AssertionError(f"missing interface containing {feature_id}")


def _cae_ref_by_entity(interface: dict[str, Any], cae_entity: str) -> dict[str, Any]:
    for ref in interface.get("cae_refs", []):
        if ref.get("cae_entity") == cae_entity:
            return ref
    raise AssertionError(f"missing CAE ref {cae_entity} on interface {interface.get('id')}")


def test_build_interface_graph_includes_cae_refs_after_explicit_mapping(tmp_path):
    pkg = _make_phase10c_package(tmp_path)
    graph = _read_member_json(pkg, INTERFACE_GRAPH_PATH)

    assert any(interface.get("cae_refs") for interface in graph["interfaces"])
    assert CAE_MAPPING_PATH in graph["source_files"]


def test_fixed_holes_cae_ref_on_expected_interface(tmp_path):
    pkg = _make_phase10c_package(tmp_path)
    graph = _read_member_json(pkg, INTERFACE_GRAPH_PATH)
    interface = _interface_by_feature(graph, "feat_hole_pattern_001")
    ref = _cae_ref_by_entity(interface, "FIXED_HOLES")

    assert interface["id"] == "iface_feat_hole_pattern_001"
    assert ref["maps_to"]["feature_id"] == "feat_hole_pattern_001"
    assert ref["maps_to"]["interface_id"] == "iface_feat_hole_pattern_001"
    assert ref["mapping_method"] == "user_provided"
    assert ref["confidence"] == "high"


def test_load_face_cae_ref_on_base_plate_interface(tmp_path):
    pkg = _make_phase10c_package(tmp_path)
    graph = _read_member_json(pkg, INTERFACE_GRAPH_PATH)
    interface = _interface_by_feature(graph, "feat_base_plate_001")
    ref = _cae_ref_by_entity(interface, "LOAD_FACE")

    assert ref["maps_to"]["feature_id"] == "feat_base_plate_001"
    assert "interface_id" not in ref["maps_to"]
    assert ref["mapping_method"] == "user_provided"
    assert ref["confidence"] == "high"


def test_cae_roles_are_added_to_interfaces(tmp_path):
    pkg = _make_phase10c_package(tmp_path)
    graph = _read_member_json(pkg, INTERFACE_GRAPH_PATH)

    fixed_interface = _interface_by_feature(graph, "feat_hole_pattern_001")
    load_interface = _interface_by_feature(graph, "feat_base_plate_001")
    assert "cae_mapped_interface" in fixed_interface["roles"]
    assert "cae_boundary_condition_target" in fixed_interface["roles"]
    assert "cae_mapped_interface" in load_interface["roles"]
    assert "cae_load_target" in load_interface["roles"]


def test_unmapped_cae_entities_are_not_added_as_cae_refs(tmp_path):
    pkg = tmp_path / "bracket_001.aieng"
    assert main(["import-step", str(STEP_PATH), "--out", str(pkg)]) == 0
    assert main(["extract-topology", str(pkg), "--overwrite", "--backend", "mock"]) == 0
    assert main(["recognize-features", str(pkg), "--overwrite"]) == 0
    assert main(["apply-context", str(pkg), "--context", str(CONTEXT_PATH), "--overwrite"]) == 0
    assert main(["build-interface-graph", str(pkg), "--overwrite"]) == 0

    deck = tmp_path / "extra_entity.inp"
    deck.write_text(
        "*BOUNDARY\nFIXED_HOLES,1,6,0\n*CLOAD\nLOAD_FACE,1,500\n*CLOAD\nEXTRA_FACE,2,25\n",
        encoding="utf-8",
    )
    assert main(["import-cae-deck", str(pkg), "--deck", str(deck), "--format", "calculix", "--overwrite"]) == 0

    mapping = tmp_path / "partial_mapping.yaml"
    mapping.write_text(
        yaml.safe_dump(
            {
                "mappings": [
                    {
                        "cae_entity": "FIXED_HOLES",
                        "maps_to": {
                            "feature_id": "feat_hole_pattern_001",
                            "interface_id": "iface_feat_hole_pattern_001",
                        },
                        "mapping_method": "user_provided",
                        "confidence": "high",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert main(["apply-cae-mapping", str(pkg), "--mapping", str(mapping), "--overwrite"]) == 0
    assert main(["build-interface-graph", str(pkg), "--overwrite"]) == 0

    graph = _read_member_json(pkg, INTERFACE_GRAPH_PATH)
    cae_entities = {
        ref["cae_entity"]
        for interface in graph["interfaces"]
        for ref in interface.get("cae_refs", [])
    }
    assert "FIXED_HOLES" in cae_entities
    assert "EXTRA_FACE" not in cae_entities


def test_validator_passes_for_valid_interface_cae_refs(tmp_path):
    pkg = _make_phase10c_package(tmp_path)
    report = validate_package(pkg)
    assert report.ok, report.render()


def test_validator_fails_if_cae_ref_references_unknown_cae_entity(tmp_path):
    pkg = _make_phase10c_package(tmp_path)
    graph = _read_member_json(pkg, INTERFACE_GRAPH_PATH)
    interface = _interface_by_feature(graph, "feat_hole_pattern_001")
    _cae_ref_by_entity(interface, "FIXED_HOLES")["cae_entity"] = "UNKNOWN_CAE_ENTITY"
    _tamper_member(pkg, INTERFACE_GRAPH_PATH, graph)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("unknown CAE entity" in text for text in fails)


def test_validator_fails_if_cae_ref_maps_to_unknown_feature(tmp_path):
    pkg = _make_phase10c_package(tmp_path)
    graph = _read_member_json(pkg, INTERFACE_GRAPH_PATH)
    interface = _interface_by_feature(graph, "feat_hole_pattern_001")
    _cae_ref_by_entity(interface, "FIXED_HOLES")["maps_to"]["feature_id"] = "feat_unknown_999"
    _tamper_member(pkg, INTERFACE_GRAPH_PATH, graph)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("unknown feature_id feat_unknown_999" in text for text in fails)


def test_validator_fails_if_cae_ref_interface_id_mismatches_container(tmp_path):
    pkg = _make_phase10c_package(tmp_path)
    graph = _read_member_json(pkg, INTERFACE_GRAPH_PATH)
    interface = _interface_by_feature(graph, "feat_hole_pattern_001")
    _cae_ref_by_entity(interface, "FIXED_HOLES")["maps_to"]["interface_id"] = "iface_other_001"
    _tamper_member(pkg, INTERFACE_GRAPH_PATH, graph)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("does not match containing interface" in text for text in fails)


def test_summary_mentions_explicit_cae_interface_mapping(tmp_path):
    pkg = _make_phase10c_package(tmp_path)
    assert main(["summarize", str(pkg), "--overwrite"]) == 0

    readme = _read_member_text(pkg, "README_FOR_AI.md")
    summary = _read_member_text(pkg, "ai/summary.md")
    assert "explicit cae interface mappings" in readme.lower()
    assert "FIXED_HOLES" in summary
    assert "LOAD_FACE" in summary


def test_validation_status_mentions_interface_graph_has_cae_refs(tmp_path):
    pkg = _make_phase10c_package(tmp_path)
    assert main(["update-validation-status", str(pkg), "--overwrite"]) == 0
    status = yaml.safe_load(_read_member_text(pkg, "validation/status.yaml"))

    assert status["interface_graph_status"]["interface_graph_has_cae_refs"] is True
    assert status["interface_graph_status"]["cae_interface_mapping_status"] == "mapped"


def test_object_registry_includes_cae_to_interface_relationships_from_enriched_graph(tmp_path):
    pkg = _make_phase10c_package(tmp_path)
    assert main(["build-object-registry", str(pkg), "--overwrite"]) == 0
    registry = _read_member_json(pkg, "objects/object_registry.json")

    relationships = registry["relationships"]
    assert any(
        rel["type"] == "cae_entity_to_interface"
        and rel["to"] == "iface_feat_hole_pattern_001"
        and rel["source_file"] == INTERFACE_GRAPH_PATH
        for rel in relationships
    )
    assert any(
        rel["type"] == "cae_entity_to_interface"
        and rel["to"] == "iface_feat_base_plate_001"
        and rel["source_file"] == INTERFACE_GRAPH_PATH
        for rel in relationships
    )
