"""Tests for Phase 10B: apply-cae-mapping explicit user-provided mapping."""
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
from aieng.validate import validate_package

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
STEP_PATH = EXAMPLES_DIR / "bracket.step"
CONTEXT_PATH = EXAMPLES_DIR / "bracket_user_context.yaml"
DECK_FIXTURE_PATH = EXAMPLES_DIR / "bracket_loadcase.inp"
MAPPING_FIXTURE_PATH = EXAMPLES_DIR / "bracket_cae_mapping.yaml"

CAE_MAPPING_PATH = "simulation/cae_mapping.json"


def _read_member_text(pkg: Path, member: str) -> str:
    with zipfile.ZipFile(pkg) as zf:
        return zf.read(member).decode("utf-8")


def _read_member_json(pkg: Path, member: str) -> dict[str, Any]:
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


def _import_deck(pkg: Path, *, overwrite: bool = False) -> int:
    cmd = [
        "import-cae-deck",
        str(pkg),
        "--deck",
        str(DECK_FIXTURE_PATH),
        "--format",
        "calculix",
    ]
    if overwrite:
        cmd.append("--overwrite")
    return main(cmd)


def _apply_mapping(pkg: Path, mapping_path: Path, *, overwrite: bool = False) -> int:
    cmd = [
        "apply-cae-mapping",
        str(pkg),
        "--mapping",
        str(mapping_path),
    ]
    if overwrite:
        cmd.append("--overwrite")
    return main(cmd)


def _make_phase10a_package(
    tmp_path: Path,
    *,
    with_feature_graph: bool = True,
    with_interface_graph: bool = False,
    include_cae_import: bool = True,
) -> Path:
    pkg = tmp_path / "bracket_001.aieng"
    assert main(["import-step", str(STEP_PATH), "--out", str(pkg)]) == 0

    if with_feature_graph:
        assert main(["extract-topology", str(pkg), "--overwrite", "--backend", "mock"]) == 0
        assert main(["recognize-features", str(pkg), "--overwrite"]) == 0
        assert main(["apply-context", str(pkg), "--context", str(CONTEXT_PATH), "--overwrite"]) == 0

    if with_interface_graph:
        assert main(["build-interface-graph", str(pkg), "--overwrite"]) == 0

    if include_cae_import:
        assert _import_deck(pkg, overwrite=True) == 0

    return pkg


def _mounting_interface_id(pkg: Path) -> str:
    data = _read_member_json(pkg, "objects/interface_graph.json")
    for interface in data.get("interfaces", []):
        if "feat_hole_pattern_001" in interface.get("feature_ids", []):
            interface_id = interface.get("id")
            if isinstance(interface_id, str) and interface_id:
                return interface_id
    raise AssertionError("expected interface id for feat_hole_pattern_001")


def _mapping_yaml(
    path: Path,
    *,
    include_interface: bool,
    interface_id: str = "iface_feat_hole_pattern_001",
    method: str = "user_provided",
    confidence: str = "high",
    feature_id: str = "feat_hole_pattern_001",
) -> Path:
    maps_to: dict[str, str] = {"feature_id": feature_id}
    if include_interface:
        maps_to["interface_id"] = interface_id

    content = {
        "mappings": [
            {
                "cae_entity": "FIXED_HOLES",
                "maps_to": maps_to,
                "mapping_method": method,
                "confidence": confidence,
                "notes": ["User confirms explicit mapping."],
            },
            {
                "cae_entity": "LOAD_FACE",
                "maps_to": {"feature_id": "feat_base_plate_001"},
                "mapping_method": method,
                "confidence": confidence,
            },
        ]
    }
    path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    return path


def test_apply_cae_mapping_happy_path_after_import_cae_deck(tmp_path):
    pkg = _make_phase10a_package(tmp_path, with_interface_graph=True)
    assert _apply_mapping(pkg, MAPPING_FIXTURE_PATH) == 0


def test_apply_cae_mapping_fails_if_package_missing(tmp_path):
    rc = _apply_mapping(tmp_path / "missing.aieng", MAPPING_FIXTURE_PATH)
    assert rc == 2


def test_apply_cae_mapping_fails_if_mapping_yaml_missing(tmp_path):
    pkg = _make_phase10a_package(tmp_path)
    rc = _apply_mapping(pkg, tmp_path / "missing_mapping.yaml")
    assert rc == 2


def test_apply_cae_mapping_fails_if_cae_mapping_json_missing(tmp_path):
    pkg = _make_phase10a_package(tmp_path, include_cae_import=False)
    rc = _apply_mapping(pkg, MAPPING_FIXTURE_PATH)
    assert rc == 2


def test_apply_cae_mapping_fails_if_mapping_references_unknown_cae_entity(tmp_path):
    pkg = _make_phase10a_package(tmp_path)
    bad = tmp_path / "unknown_entity.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "mappings": [
                    {
                        "cae_entity": "UNKNOWN_SET",
                        "maps_to": {"feature_id": "feat_hole_pattern_001"},
                        "mapping_method": "user_provided",
                        "confidence": "high",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert _apply_mapping(pkg, bad) == 2


def test_apply_cae_mapping_fails_if_feature_id_missing(tmp_path):
    pkg = _make_phase10a_package(tmp_path)
    bad = _mapping_yaml(tmp_path / "bad_feature.yaml", include_interface=False, feature_id="feat_unknown_999")
    assert _apply_mapping(pkg, bad) == 2


def test_apply_cae_mapping_fails_if_interface_id_missing(tmp_path):
    pkg = _make_phase10a_package(tmp_path, with_interface_graph=True)
    bad = _mapping_yaml(tmp_path / "bad_interface.yaml", include_interface=True, interface_id="iface_unknown_999")
    assert _apply_mapping(pkg, bad) == 2


def test_apply_cae_mapping_fails_if_interface_graph_missing_with_interface_mapping(tmp_path):
    pkg = _make_phase10a_package(tmp_path, with_interface_graph=False)
    mapping = _mapping_yaml(tmp_path / "need_interface_graph.yaml", include_interface=True)
    assert _apply_mapping(pkg, mapping) == 2


def test_apply_cae_mapping_fails_if_feature_graph_missing_with_feature_mapping(tmp_path):
    pkg = _make_phase10a_package(tmp_path, with_feature_graph=False)
    # Import CAE deck without feature graph is valid; applying feature mapping must fail.
    assert _import_deck(pkg, overwrite=True) == 0

    mapping = _mapping_yaml(tmp_path / "need_feature_graph.yaml", include_interface=False)
    assert _apply_mapping(pkg, mapping) == 2


def test_apply_cae_mapping_fails_if_mapping_method_not_user_provided(tmp_path):
    pkg = _make_phase10a_package(tmp_path)
    bad = _mapping_yaml(tmp_path / "bad_method.yaml", include_interface=False, method="exact_name_match")
    assert _apply_mapping(pkg, bad) == 2


def test_apply_cae_mapping_fails_if_confidence_invalid(tmp_path):
    pkg = _make_phase10a_package(tmp_path)
    bad = _mapping_yaml(tmp_path / "bad_confidence.yaml", include_interface=False, confidence="certain")
    assert _apply_mapping(pkg, bad) == 2


def test_apply_cae_mapping_sets_fixed_holes_feature_id(tmp_path):
    pkg = _make_phase10a_package(tmp_path)
    mapping = _mapping_yaml(tmp_path / "feature_only.yaml", include_interface=False)
    assert _apply_mapping(pkg, mapping) == 0

    cae_mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    by_entity = {item["cae_entity"]: item for item in cae_mapping["mappings"]}
    assert by_entity["FIXED_HOLES"]["maps_to"]["feature_id"] == "feat_hole_pattern_001"
    assert by_entity["FIXED_HOLES"]["mapping_status"] == "mapped"
    assert by_entity["FIXED_HOLES"]["mapping_method"] == "user_provided"
    assert by_entity["FIXED_HOLES"]["confidence"] == "high"


def test_apply_cae_mapping_sets_fixed_holes_interface_id_actual_generated_id(tmp_path):
    pkg = _make_phase10a_package(tmp_path, with_interface_graph=True)
    interface_id = _mounting_interface_id(pkg)
    mapping = _mapping_yaml(tmp_path / "feature_and_interface.yaml", include_interface=True, interface_id=interface_id)
    assert _apply_mapping(pkg, mapping) == 0

    cae_mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    by_entity = {item["cae_entity"]: item for item in cae_mapping["mappings"]}
    assert by_entity["FIXED_HOLES"]["maps_to"]["interface_id"] == interface_id


def test_apply_cae_mapping_sets_load_face_feature_id(tmp_path):
    pkg = _make_phase10a_package(tmp_path)
    mapping = _mapping_yaml(tmp_path / "load_face.yaml", include_interface=False)
    assert _apply_mapping(pkg, mapping) == 0

    cae_mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    by_entity = {item["cae_entity"]: item for item in cae_mapping["mappings"]}
    assert by_entity["LOAD_FACE"]["maps_to"]["feature_id"] == "feat_base_plate_001"


def test_apply_cae_mapping_keeps_unmentioned_entities_unmapped(tmp_path):
    pkg = _make_phase10a_package(tmp_path)

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
                        "maps_to": {"feature_id": "feat_hole_pattern_001"},
                        "mapping_method": "user_provided",
                        "confidence": "high",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert _apply_mapping(pkg, mapping) == 0
    cae_mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    by_entity = {item["cae_entity"]: item for item in cae_mapping["mappings"]}
    assert by_entity["EXTRA_FACE"]["mapping_status"] == "unmapped"
    assert by_entity["EXTRA_FACE"]["maps_to"] is None


def test_apply_cae_mapping_does_not_overwrite_existing_mapping_by_default(tmp_path):
    pkg = _make_phase10a_package(tmp_path)
    mapping = _mapping_yaml(tmp_path / "initial.yaml", include_interface=False)
    assert _apply_mapping(pkg, mapping) == 0
    assert _apply_mapping(pkg, mapping) == 2


def test_apply_cae_mapping_overwrites_existing_mapping_with_flag(tmp_path):
    pkg = _make_phase10a_package(tmp_path)
    mapping = _mapping_yaml(tmp_path / "initial.yaml", include_interface=False)
    assert _apply_mapping(pkg, mapping) == 0

    overwrite_mapping = _mapping_yaml(
        tmp_path / "overwrite.yaml",
        include_interface=False,
        confidence="medium",
    )
    assert _apply_mapping(pkg, overwrite_mapping, overwrite=True) == 0

    cae_mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    by_entity = {item["cae_entity"]: item for item in cae_mapping["mappings"]}
    assert by_entity["FIXED_HOLES"]["confidence"] == "medium"


def test_validator_passes_after_explicit_mapping(tmp_path):
    pkg = _make_phase10a_package(tmp_path, with_interface_graph=True)
    assert _apply_mapping(pkg, MAPPING_FIXTURE_PATH) == 0

    report = validate_package(pkg)
    assert report.ok


def test_validator_fails_if_mapped_feature_id_unknown(tmp_path):
    pkg = _make_phase10a_package(tmp_path)
    mapping = _mapping_yaml(tmp_path / "feature_only.yaml", include_interface=False)
    assert _apply_mapping(pkg, mapping) == 0

    cae_mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    for item in cae_mapping["mappings"]:
        if item["cae_entity"] == "FIXED_HOLES":
            item["maps_to"]["feature_id"] = "feat_unknown_999"
            break
    _tamper_member(pkg, CAE_MAPPING_PATH, cae_mapping)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("unknown feature_id" in msg for msg in fails)


def test_validator_fails_if_mapped_interface_id_unknown(tmp_path):
    pkg = _make_phase10a_package(tmp_path, with_interface_graph=True)
    interface_id = _mounting_interface_id(pkg)
    mapping = _mapping_yaml(tmp_path / "feature_and_interface.yaml", include_interface=True, interface_id=interface_id)
    assert _apply_mapping(pkg, mapping) == 0

    cae_mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    for item in cae_mapping["mappings"]:
        if item["cae_entity"] == "FIXED_HOLES":
            item["maps_to"]["interface_id"] = "iface_unknown_999"
            break
    _tamper_member(pkg, CAE_MAPPING_PATH, cae_mapping)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("unknown interface_id" in msg for msg in fails)


def test_summary_mentions_user_provided_cae_mapping_when_present(tmp_path):
    pkg = _make_phase10a_package(tmp_path, with_interface_graph=True)
    assert _apply_mapping(pkg, MAPPING_FIXTURE_PATH) == 0

    assert main(["summarize", str(pkg)]) == 0
    summary = _read_member_text(pkg, "ai/summary.md")
    assert "user-provided" in summary.lower()


def test_validation_status_reports_mapped_or_partially_mapped(tmp_path):
    pkg = _make_phase10a_package(tmp_path, with_interface_graph=True)
    assert _apply_mapping(pkg, MAPPING_FIXTURE_PATH) == 0

    assert main(["update-validation-status", str(pkg)]) == 0
    status = yaml.safe_load(_read_member_text(pkg, "validation/status.yaml"))
    assert status["cae_import_status"]["cae_mapping_status"] in {"imported_mapped", "imported_partially_mapped"}


def test_object_registry_includes_cae_mapping_relationships(tmp_path):
    pkg = _make_phase10a_package(tmp_path, with_interface_graph=True)
    assert _apply_mapping(pkg, MAPPING_FIXTURE_PATH) == 0

    assert main(["build-object-registry", str(pkg)]) == 0
    registry = _read_member_json(pkg, "objects/object_registry.json")
    rel_types = {rel["type"] for rel in registry["relationships"]}
    assert "cae_entity_to_feature" in rel_types
    assert "cae_entity_to_interface" in rel_types
