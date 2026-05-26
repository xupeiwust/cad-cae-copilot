"""Tests for Phase 9A: objects/object_registry.json generation and validation."""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

from aieng.cli import main
from aieng.objects.registry_writer import OBJECT_REGISTRY_PATH, build_object_registry_package
from aieng.validate import validate_package

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
STEP_PATH = EXAMPLES_DIR / "bracket.step"
CONTEXT_PATH = EXAMPLES_DIR / "bracket_user_context.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_topology_feature_package(tmp_path: Path) -> Path:
    pkg = tmp_path / "bracket_001.aieng"
    assert main(["import-step", str(STEP_PATH), "--out", str(pkg)]) == 0
    assert main(["extract-topology", str(pkg), "--overwrite", "--backend", "mock"]) == 0
    assert main(["recognize-features", str(pkg), "--overwrite"]) == 0
    return pkg


def _make_full_package(tmp_path: Path) -> Path:
    pkg = _make_topology_feature_package(tmp_path)
    assert main(["apply-context", str(pkg), "--context", str(CONTEXT_PATH), "--overwrite"]) == 0
    assert main(["summarize", str(pkg), "--overwrite"]) == 0
    assert main(["propose-patch", str(pkg), "--intent", "Reduce mass by 15% while keeping mounting holes unchanged."]) == 0
    assert main(["build-visual-index", str(pkg), "--overwrite"]) == 0
    assert main(["build-visual-manifest", str(pkg), "--overwrite"]) == 0
    assert main(["update-validation-status", str(pkg), "--overwrite"]) == 0
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


# ---------------------------------------------------------------------------
# Build command behavior
# ---------------------------------------------------------------------------

def test_build_object_registry_happy_path_after_full_chain(tmp_path):
    pkg = _make_full_package(tmp_path)
    result = build_object_registry_package(pkg)
    assert result == pkg


def test_build_object_registry_works_with_topology_and_feature_only(tmp_path):
    pkg = _make_topology_feature_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert isinstance(data, dict)


def test_build_object_registry_writes_registry_file(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    with zipfile.ZipFile(pkg) as zf:
        assert OBJECT_REGISTRY_PATH in zf.namelist()


def test_build_object_registry_updates_manifest_resources(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    manifest = _read_json_member(pkg, "manifest.json")
    assert manifest["resources"]["objects"]["object_registry"] == OBJECT_REGISTRY_PATH


# ---------------------------------------------------------------------------
# Registry content
# ---------------------------------------------------------------------------

def test_registry_contains_topology_entities(tmp_path):
    pkg = _make_topology_feature_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert any(obj["kind"] == "topology_entity" for obj in data["objects"])


def test_registry_contains_feature_objects(tmp_path):
    pkg = _make_topology_feature_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert any(obj["kind"] == "feature" for obj in data["objects"])


def test_registry_contains_constraint_objects_when_constraints_exist(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert any(obj["kind"] == "constraint" for obj in data["objects"])


def test_registry_contains_simulation_bc_load_material_objects(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    kinds = {obj["kind"] for obj in data["objects"]}
    assert "simulation" in kinds
    assert "boundary_condition" in kinds
    assert "load" in kinds
    assert "material" in kinds


def test_registry_contains_protected_region_objects(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert any(obj["kind"] == "protected_region" for obj in data["objects"])


def test_registry_contains_patch_and_patch_operation_objects(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    kinds = {obj["kind"] for obj in data["objects"]}
    assert "patch" in kinds
    assert "patch_operation" in kinds


def test_registry_contains_visual_annotation_objects(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert any(obj["kind"] == "visual_annotation" for obj in data["objects"])


def test_registry_contains_visual_resource_objects(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert any(obj["kind"] == "visual_resource" for obj in data["objects"])


def test_registry_contains_validation_status_object_when_status_exists(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert any(obj["kind"] == "validation_status" for obj in data["objects"])


def test_registry_relationships_include_feature_to_topology(tmp_path):
    pkg = _make_topology_feature_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert any(rel["type"] == "feature_to_topology" for rel in data["relationships"])


def test_registry_relationships_include_parent_child(tmp_path):
    pkg = _make_topology_feature_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert any(rel["type"] == "parent_child" for rel in data["relationships"])


def test_registry_relationships_include_constraint_target(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert any(rel["type"] == "constraint_target" for rel in data["relationships"])


def test_registry_relationships_include_patch_targets_feature(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    assert any(rel["type"] == "patch_targets_feature" for rel in data["relationships"])


def test_registry_unresolved_references_are_represented(tmp_path):
    pkg = _make_full_package(tmp_path)
    layers = _read_json_member(pkg, "visual/annotation_layers.json")
    layers["layers"][0]["items"][0]["feature_id"] = "feat_missing_999"
    _tamper_member(pkg, "visual/annotation_layers.json", layers)

    assert main(["build-object-registry", str(pkg), "--overwrite"]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)

    unresolved = [obj for obj in data["objects"] if obj["kind"] == "unresolved_reference"]
    assert any(obj["id"] == "feat_missing_999" for obj in unresolved)
    assert any(obj["status"] == "unresolved" for obj in unresolved)


def test_registry_object_ids_are_unique(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    ids = [obj["id"] for obj in data["objects"]]
    assert len(ids) == len(set(ids))


def test_registry_relationship_endpoints_resolve_to_known_or_unresolved(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)

    ids = {obj["id"] for obj in data["objects"]}
    for rel in data["relationships"]:
        assert rel["from"] in ids
        assert rel["to"] in ids


def test_registry_notes_say_not_source_of_truth(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    data = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    notes = [note.lower() for note in data["notes"]]
    assert any("source of truth" in note and "not" in note for note in notes)


# ---------------------------------------------------------------------------
# Validator integration
# ---------------------------------------------------------------------------

def test_validator_passes_after_object_registry_generation(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert not fails, f"Validation failures: {fails}"


def test_validator_fails_if_duplicate_object_ids_exist(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    registry = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    registry["objects"].append(dict(registry["objects"][0]))
    _tamper_member(pkg, OBJECT_REGISTRY_PATH, registry)

    report = validate_package(pkg)
    fail_texts = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("object IDs are not unique" in text for text in fail_texts)


def test_validator_fails_if_relationship_endpoint_unknown_and_not_unresolved(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    registry = _read_json_member(pkg, OBJECT_REGISTRY_PATH)
    registry["relationships"][0]["to"] = "unknown_endpoint_999"
    _tamper_member(pkg, OBJECT_REGISTRY_PATH, registry)

    report = validate_package(pkg)
    fail_texts = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("relationship endpoint 'to' unknown" in text for text in fail_texts)


# ---------------------------------------------------------------------------
# Overwrite behavior + summary/status integration
# ---------------------------------------------------------------------------

def test_build_object_registry_does_not_overwrite_by_default(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_object_registry_package(pkg)
    with pytest.raises(FileExistsError):
        build_object_registry_package(pkg)


def test_build_object_registry_overwrites_with_flag(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_object_registry_package(pkg)
    result = build_object_registry_package(pkg, overwrite=True)
    assert result == pkg


def test_build_object_registry_cli_no_overwrite_returns_2(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    assert main(["build-object-registry", str(pkg)]) == 2


def test_build_object_registry_cli_overwrite_returns_0(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    assert main(["build-object-registry", str(pkg), "--overwrite"]) == 0


def test_summary_mentions_object_registry_when_present(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    assert main(["summarize", str(pkg), "--overwrite"]) == 0
    with zipfile.ZipFile(pkg) as zf:
        readme = zf.read("README_FOR_AI.md").decode("utf-8")
        summary = zf.read("ai/summary.md").decode("utf-8")
    assert "objects/object_registry.json" in readme
    assert "objects/object_registry.json" in summary


def test_validation_status_mentions_object_registry_when_present(tmp_path):
    import yaml

    pkg = _make_full_package(tmp_path)
    assert main(["build-object-registry", str(pkg)]) == 0
    assert main(["update-validation-status", str(pkg), "--overwrite"]) == 0

    with zipfile.ZipFile(pkg) as zf:
        status = yaml.safe_load(zf.read("validation/status.yaml"))

    assert status["object_registry_status"]["object_registry_present"] is True
    assert status["object_registry_status"]["registry_is_source_of_truth"] is False
