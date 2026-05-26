"""Tests for Phase 10A: import-cae-deck scaffold."""
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
from aieng.objects.registry_writer import build_object_registry_package
from aieng.validate import validate_package

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
STEP_PATH = EXAMPLES_DIR / "bracket.step"
CONTEXT_PATH = EXAMPLES_DIR / "bracket_user_context.yaml"
DECK_FIXTURE_PATH = EXAMPLES_DIR / "bracket_loadcase.inp"

CAE_SOURCE_DECK_PATH = "simulation/cae_imports/source_solver_deck.inp"
CAE_PARSED_MATERIALS_PATH = "simulation/cae_imports/parsed_materials.json"
CAE_PARSED_BCS_PATH = "simulation/cae_imports/parsed_boundary_conditions.json"
CAE_PARSED_LOADS_PATH = "simulation/cae_imports/parsed_loads.json"
CAE_MAPPING_PATH = "simulation/cae_mapping.json"


def _make_context_package(tmp_path: Path, *, with_interface_graph: bool = False) -> Path:
    pkg = tmp_path / "bracket_001.aieng"
    assert main(["import-step", str(STEP_PATH), "--out", str(pkg)]) == 0
    assert main(["extract-topology", str(pkg), "--overwrite", "--backend", "mock"]) == 0
    assert main(["recognize-features", str(pkg), "--overwrite"]) == 0
    assert main(["apply-context", str(pkg), "--context", str(CONTEXT_PATH), "--overwrite"]) == 0
    if with_interface_graph:
        assert main(["build-interface-graph", str(pkg), "--overwrite"]) == 0
    return pkg


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


def _import_deck(pkg: Path, deck_path: Path, *, overwrite: bool = False) -> int:
    cmd = [
        "import-cae-deck",
        str(pkg),
        "--deck",
        str(deck_path),
        "--format",
        "calculix",
    ]
    if overwrite:
        cmd.append("--overwrite")
    return main(cmd)


def test_import_cae_deck_happy_path(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert _import_deck(pkg, DECK_FIXTURE_PATH) == 0


def test_cli_import_cae_deck_prints_no_auto_claim_policy(tmp_path, capsys):
    pkg = _make_context_package(tmp_path)
    assert _import_deck(pkg, DECK_FIXTURE_PATH) == 0
    output = capsys.readouterr().out
    assert "PASS import is evidence-only; no automatic claim status update performed" in output


def test_import_cae_deck_writes_required_resources(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
    assert CAE_SOURCE_DECK_PATH in names
    assert CAE_PARSED_MATERIALS_PATH in names
    assert CAE_PARSED_BCS_PATH in names
    assert CAE_PARSED_LOADS_PATH in names
    assert CAE_MAPPING_PATH in names


def test_import_cae_deck_updates_manifest_simulation_resources(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    manifest = _read_member_json(pkg, "manifest.json")
    sim = manifest["resources"]["simulation"]
    assert sim["cae_import_source_solver_deck"] == CAE_SOURCE_DECK_PATH
    assert sim["cae_import_parsed_materials"] == CAE_PARSED_MATERIALS_PATH
    assert sim["cae_import_parsed_boundary_conditions"] == CAE_PARSED_BCS_PATH
    assert sim["cae_import_parsed_loads"] == CAE_PARSED_LOADS_PATH
    assert sim["cae_mapping"] == CAE_MAPPING_PATH


def test_source_solver_deck_matches_input_file(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    original = DECK_FIXTURE_PATH.read_text(encoding="utf-8")
    imported = _read_member_text(pkg, CAE_SOURCE_DECK_PATH)
    assert imported == original


def test_parsed_materials_contains_expected_material_fields(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    materials = _read_member_json(pkg, CAE_PARSED_MATERIALS_PATH)
    assert materials["format"] == "aieng.parsed_cae_materials"
    assert materials["parser"]["format"] == "calculix"
    assert materials["parser"]["scope"] == "phase_10a_minimal_cards"
    assert materials["materials"][0]["name"] == "Al6061-T6"
    assert materials["materials"][0]["elastic"]["youngs_modulus"] == 69000
    assert materials["materials"][0]["elastic"]["poisson_ratio"] == 0.33
    assert materials["materials"][0]["density"] == 2700


def test_parsed_boundary_conditions_contains_expected_fields(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    bcs = _read_member_json(pkg, CAE_PARSED_BCS_PATH)
    assert bcs["format"] == "aieng.parsed_cae_boundary_conditions"
    assert bcs["boundary_conditions"][0]["id"] == "cae_bc_001"
    assert bcs["boundary_conditions"][0]["target"] == "FIXED_HOLES"
    assert bcs["boundary_conditions"][0]["dof_start"] == 1
    assert bcs["boundary_conditions"][0]["dof_end"] == 6
    assert bcs["boundary_conditions"][0]["value"] == 0


def test_parsed_loads_contains_expected_fields(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    loads = _read_member_json(pkg, CAE_PARSED_LOADS_PATH)
    assert loads["format"] == "aieng.parsed_cae_loads"
    assert loads["loads"][0]["id"] == "cae_load_001"
    assert loads["loads"][0]["target"] == "LOAD_FACE"
    assert loads["loads"][0]["dof"] == 1
    assert loads["loads"][0]["value"] == 500


def test_cae_mapping_default_unmapped_for_fixture_targets(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    assert mapping["format"] == "aieng.cae_mapping"
    assert mapping["mapping_summary"]["mapped_count"] == 0
    assert mapping["mapping_summary"]["unmapped_count"] >= 1
    assert all(item["mapping_status"] == "unmapped" for item in mapping["mappings"])
    by_entity = {item["cae_entity"]: item for item in mapping["mappings"]}
    assert by_entity["FIXED_HOLES"]["mapping_status"] == "unmapped"
    assert by_entity["FIXED_HOLES"]["maps_to"] is None
    assert by_entity["LOAD_FACE"]["mapping_status"] == "unmapped"
    assert by_entity["LOAD_FACE"]["maps_to"] is None


def test_cae_mapping_notes_include_phase_10a_non_auto_mapping_policy(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    notes_text = " ".join(mapping["notes"]).lower()
    assert "phase 10a" in notes_text
    assert "does not automatically map" in notes_text


def test_import_cae_deck_does_not_overwrite_by_default(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert _import_deck(pkg, DECK_FIXTURE_PATH) == 0
    assert _import_deck(pkg, DECK_FIXTURE_PATH) == 2


def test_import_cae_deck_overwrites_with_flag(tmp_path):
    pkg = _make_context_package(tmp_path)
    assert _import_deck(pkg, DECK_FIXTURE_PATH) == 0

    overwrite_deck = tmp_path / "overwrite.inp"
    overwrite_deck.write_text("*MATERIAL, NAME=Steel\n*ELASTIC\n210000,0.3\n", encoding="utf-8")
    assert _import_deck(pkg, overwrite_deck, overwrite=True) == 0

    materials = _read_member_json(pkg, CAE_PARSED_MATERIALS_PATH)
    assert materials["materials"][0]["name"] == "Steel"


def test_import_cae_deck_fails_for_unsupported_format(tmp_path):
    pkg = _make_context_package(tmp_path)
    rc = main([
        "import-cae-deck",
        str(pkg),
        "--deck",
        str(DECK_FIXTURE_PATH),
        "--format",
        "nastran",
    ])
    assert rc == 2


def test_import_cae_deck_fails_if_deck_file_missing(tmp_path):
    pkg = _make_context_package(tmp_path)
    rc = main([
        "import-cae-deck",
        str(pkg),
        "--deck",
        str(tmp_path / "missing.inp"),
        "--format",
        "calculix",
    ])
    assert rc == 2


def test_import_cae_deck_fails_if_package_missing(tmp_path):
    rc = main([
        "import-cae-deck",
        str(tmp_path / "missing.aieng"),
        "--deck",
        str(DECK_FIXTURE_PATH),
        "--format",
        "calculix",
    ])
    assert rc == 2


def test_validate_passes_after_import_cae_deck(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    report = validate_package(pkg)
    assert report.ok


def test_validator_fails_for_duplicate_material_names(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    materials = _read_member_json(pkg, CAE_PARSED_MATERIALS_PATH)
    materials["materials"].append(dict(materials["materials"][0]))
    _tamper_member(pkg, CAE_PARSED_MATERIALS_PATH, materials)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("material names are not unique" in msg for msg in fails)


def test_validator_fails_for_duplicate_boundary_condition_ids(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    bcs = _read_member_json(pkg, CAE_PARSED_BCS_PATH)
    bcs["boundary_conditions"].append(dict(bcs["boundary_conditions"][0]))
    _tamper_member(pkg, CAE_PARSED_BCS_PATH, bcs)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("boundary condition IDs are not unique" in msg for msg in fails)


def test_validator_fails_for_duplicate_load_ids(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    loads = _read_member_json(pkg, CAE_PARSED_LOADS_PATH)
    loads["loads"].append(dict(loads["loads"][0]))
    _tamper_member(pkg, CAE_PARSED_LOADS_PATH, loads)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("load IDs are not unique" in msg for msg in fails)


def test_validator_fails_if_mapping_references_unknown_feature_id(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    mapping["mappings"][0]["mapping_status"] = "mapped"
    mapping["mappings"][0]["maps_to"] = {"feature_id": "feat_unknown_999"}
    mapping["mapping_summary"] = {"mapped_count": 1, "unmapped_count": max(0, len(mapping["mappings"]) - 1)}
    _tamper_member(pkg, CAE_MAPPING_PATH, mapping)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("unknown feature_id" in msg for msg in fails)


def test_validator_fails_if_mapping_references_unknown_interface_id(tmp_path):
    pkg = _make_context_package(tmp_path, with_interface_graph=True)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    mapping["mappings"][0]["mapping_status"] = "mapped"
    mapping["mappings"][0]["maps_to"] = {"interface_id": "iface_unknown_999"}
    mapping["mapping_summary"] = {"mapped_count": 1, "unmapped_count": max(0, len(mapping["mappings"]) - 1)}
    _tamper_member(pkg, CAE_MAPPING_PATH, mapping)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("unknown interface_id" in msg for msg in fails)


def test_validator_fails_if_mapping_notes_remove_phase_10a_policy(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    mapping["notes"] = ["Mapping imported."]
    _tamper_member(pkg, CAE_MAPPING_PATH, mapping)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("does not automatically infer mappings" in msg for msg in fails)


def test_summary_mentions_cae_import_resources_without_solver_claims(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    assert main(["summarize", str(pkg)]) == 0
    summary = _read_member_text(pkg, "ai/summary.md")
    readme = _read_member_text(pkg, "README_FOR_AI.md")

    assert "simulation/cae_imports/source_solver_deck.inp" in summary
    assert "simulation/cae_mapping.json" in summary
    assert "do not indicate mesh generation or solver execution" in summary
    assert "simulation/cae_imports/source_solver_deck.inp" in readme


def test_validation_status_has_cae_import_section_and_not_run_values(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    assert main(["update-validation-status", str(pkg)]) == 0
    status = yaml.safe_load(_read_member_text(pkg, "validation/status.yaml"))

    assert status["cae_import_status"]["cae_import_present"] is True
    assert status["cae_import_status"]["cae_mapping_status"] == "imported_unmapped"
    assert status["cae_import_status"]["cae_solver_execution"] == "not_run"
    assert status["cae_import_status"]["cae_results_imported"] is False


def test_object_registry_includes_cae_objects_after_import(tmp_path):
    pkg = _make_context_package(tmp_path)
    _import_deck(pkg, DECK_FIXTURE_PATH)

    build_object_registry_package(pkg)
    registry = _read_member_json(pkg, "objects/object_registry.json")
    kinds = {obj["kind"] for obj in registry["objects"]}
    assert "cae_material" in kinds
    assert "cae_boundary_condition" in kinds
    assert "cae_load" in kinds
    assert "cae_mapping" in kinds


def test_mapping_does_not_auto_match_feature_names(tmp_path):
    pkg = _make_context_package(tmp_path)
    exact_deck = tmp_path / "exact_feature.inp"
    exact_deck.write_text(
        "*BOUNDARY\nfeat_hole_pattern_001,1,6,0\n*CLOAD\nfeat_base_plate_001,1,500\n",
        encoding="utf-8",
    )
    _import_deck(pkg, exact_deck)

    mapping = _read_member_json(pkg, CAE_MAPPING_PATH)
    assert mapping["mapping_summary"]["mapped_count"] == 0
    assert all(item.get("maps_to") is None for item in mapping["mappings"])
