"""Tests for Phase 9B: objects/interface_graph.json generation and validation."""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from aieng.cli import main
from aieng.objects.interface_graph_writer import INTERFACE_GRAPH_PATH, build_interface_graph_package
from aieng.validate import validate_package

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
STEP_PATH = EXAMPLES_DIR / "bracket.step"
CONTEXT_PATH = EXAMPLES_DIR / "bracket_user_context.yaml"


def _make_context_package(tmp_path: Path, *, with_visual_index: bool = True) -> Path:
    pkg = tmp_path / "bracket_001.aieng"
    assert main(["import-step", str(STEP_PATH), "--out", str(pkg)]) == 0
    assert main(["extract-topology", str(pkg), "--backend", "mock", "--overwrite"]) == 0
    assert main(["recognize-features", str(pkg), "--overwrite"]) == 0
    assert main(["apply-context", str(pkg), "--context", str(CONTEXT_PATH), "--overwrite"]) == 0
    if with_visual_index:
        assert main(["build-visual-index", str(pkg), "--overwrite"]) == 0
    return pkg


def _read_json_member(pkg: Path, member: str) -> dict[str, Any]:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


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


def test_build_interface_graph_happy_path_after_apply_context(tmp_path):
    pkg = _make_context_package(tmp_path)
    result = build_interface_graph_package(pkg)
    assert result == pkg


def test_build_interface_graph_writes_interface_graph_file(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0
    with zipfile.ZipFile(pkg) as zf:
        assert INTERFACE_GRAPH_PATH in zf.namelist()


def test_build_interface_graph_updates_manifest_resources(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0
    manifest = _read_json_member(pkg, "manifest.json")
    assert manifest["resources"]["objects"]["interface_graph"] == INTERFACE_GRAPH_PATH


def test_mounting_interface_created_for_feat_hole_pattern_001(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0
    data = _read_json_member(pkg, INTERFACE_GRAPH_PATH)

    assert any(
        iface["type"] == "mounting_interface" and "feat_hole_pattern_001" in iface["feature_ids"]
        for iface in data["interfaces"]
    )


def test_protected_feature_becomes_protected_interface(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0
    data = _read_json_member(pkg, INTERFACE_GRAPH_PATH)

    matching = [iface for iface in data["interfaces"] if "feat_hole_pattern_001" in iface["feature_ids"]]
    assert matching
    assert matching[0]["protected"] is True
    assert "protected_external_interface" in matching[0]["roles"]


def test_fixed_bc_target_becomes_fixed_support_interface_role(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0
    data = _read_json_member(pkg, INTERFACE_GRAPH_PATH)

    matching = [iface for iface in data["interfaces"] if "feat_hole_pattern_001" in iface["feature_ids"]]
    assert matching
    assert "fixed_support_interface" in matching[0]["roles"]
    assert "bc_fixed_001" in matching[0]["simulation_refs"]


def test_load_target_becomes_load_application_interface_role(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0
    data = _read_json_member(pkg, INTERFACE_GRAPH_PATH)

    matching = [iface for iface in data["interfaces"] if "feat_base_plate_001" in iface["feature_ids"]]
    assert matching
    assert "load_application_interface" in matching[0]["roles"]
    assert "load_001" in matching[0]["simulation_refs"]


def test_constraint_refs_are_included(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0
    data = _read_json_member(pkg, INTERFACE_GRAPH_PATH)

    matching = [iface for iface in data["interfaces"] if "feat_hole_pattern_001" in iface["feature_ids"]]
    assert matching
    assert "con_protect_001" in matching[0]["constraint_refs"]


def test_allowed_forbidden_operations_included_for_protected_interface(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0
    data = _read_json_member(pkg, INTERFACE_GRAPH_PATH)

    matching = [iface for iface in data["interfaces"] if "feat_hole_pattern_001" in iface["feature_ids"]]
    assert matching
    assert "read" in matching[0]["allowed_operations"]
    assert "delete" in matching[0]["forbidden_operations"]


def test_visual_refs_included_when_visual_annotations_exist(tmp_path):
    pkg = _make_context_package(tmp_path, with_visual_index=True)
    assert main(["build-interface-graph", str(pkg)]) == 0
    data = _read_json_member(pkg, INTERFACE_GRAPH_PATH)

    matching = [iface for iface in data["interfaces"] if "feat_hole_pattern_001" in iface["feature_ids"]]
    assert matching
    assert matching[0]["visual_refs"]


def test_interface_feature_ids_resolve_to_known_features(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0

    feature_graph = _read_json_member(pkg, "graph/feature_graph.json")
    known = {feature["id"] for feature in feature_graph["features"]}
    iface_graph = _read_json_member(pkg, INTERFACE_GRAPH_PATH)

    for iface in iface_graph["interfaces"]:
        for feature_id in iface["feature_ids"]:
            assert feature_id in known


def test_interface_topology_refs_resolve_to_known_topology_ids(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0

    topo = _read_json_member(pkg, "geometry/topology_map.json")
    face_ids = {entity["id"] for entity in topo["entities"] if entity.get("type") == "face"}
    edge_ids = {entity["id"] for entity in topo["entities"] if entity.get("type") == "edge"}

    iface_graph = _read_json_member(pkg, INTERFACE_GRAPH_PATH)
    for iface in iface_graph["interfaces"]:
        refs = iface.get("topology_refs", {})
        for face_id in refs.get("faces", []):
            assert face_id in face_ids
        for edge_id in refs.get("edges", []):
            assert edge_id in edge_ids


def test_validator_passes_after_interface_graph_generation(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert not fails, f"Validation failures: {fails}"


def test_validator_fails_if_interface_references_unknown_feature_id(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0

    iface_graph = _read_json_member(pkg, INTERFACE_GRAPH_PATH)
    iface_graph["interfaces"][0]["feature_ids"] = ["feat_unknown_999"]
    _tamper_member(pkg, INTERFACE_GRAPH_PATH, iface_graph)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("unknown feature IDs" in text for text in fails)


def test_validator_fails_if_interface_references_unknown_topology_id(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0

    iface_graph = _read_json_member(pkg, INTERFACE_GRAPH_PATH)
    iface_graph["interfaces"][0]["topology_refs"]["faces"] = ["face_unknown_999"]
    _tamper_member(pkg, INTERFACE_GRAPH_PATH, iface_graph)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("unknown topology faces" in text for text in fails)


def test_build_interface_graph_does_not_overwrite_by_default(tmp_path):
    pkg = _make_context_package(tmp_path)
    build_interface_graph_package(pkg)
    with pytest.raises(FileExistsError):
        build_interface_graph_package(pkg)


def test_build_interface_graph_overwrites_with_flag(tmp_path):
    pkg = _make_context_package(tmp_path)
    build_interface_graph_package(pkg)
    result = build_interface_graph_package(pkg, overwrite=True)
    assert result == pkg


def test_summary_mentions_interface_graph_when_present(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0
    assert main(["summarize", str(pkg), "--overwrite"]) == 0

    with zipfile.ZipFile(pkg) as zf:
        readme = zf.read("README_FOR_AI.md").decode("utf-8")
        summary = zf.read("ai/summary.md").decode("utf-8")

    assert "objects/interface_graph.json" in readme
    assert "objects/interface_graph.json" in summary


def test_validation_status_mentions_interface_graph_present(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0
    assert main(["update-validation-status", str(pkg), "--overwrite"]) == 0

    with zipfile.ZipFile(pkg) as zf:
        status = yaml.safe_load(zf.read("validation/status.yaml"))

    assert status["interface_graph_status"]["interface_graph_present"] is True
    assert status["interface_graph_status"]["interface_graph_source_of_truth"] is False


def test_object_registry_includes_interface_objects_when_interface_graph_exists(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert main(["build-interface-graph", str(pkg)]) == 0
    assert main(["build-object-registry", str(pkg)]) == 0

    registry = _read_json_member(pkg, "objects/object_registry.json")
    kinds = {obj["kind"] for obj in registry["objects"]}
    assert "interface" in kinds
