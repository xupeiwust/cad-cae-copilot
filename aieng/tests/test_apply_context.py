from __future__ import annotations

import json
import zipfile

import yaml

from aieng.cli import main
from aieng.context.apply_context import CONSTRAINTS_PATH, PROTECTED_REGIONS_PATH, SIMULATION_SETUP_PATH, apply_context_package
from aieng.geometry.step_importer import import_step_package
from aieng.geometry.topology_extractor import extract_topology_package
from aieng.graph.feature_graph import recognize_features_package
from aieng.package import read_manifest
from aieng.validate import validate_package

FAKE_STEP_CONTENT = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"

VALID_CONTEXT = {
    "material": "Al6061-T6",
    "protected_features": ["feat_hole_pattern_001"],
    "simulation": {
        "type": "static_structural",
        "fixed": ["feat_hole_pattern_001"],
        "loads": [
            {"target": "feat_base_plate_001", "type": "force", "value_n": 500, "direction": [1, 0, 0]}
        ],
    },
    "targets": {"max_von_mises_stress_mpa": 120},
    "assumptions": [
        "Mounting hole pattern is treated as fixed support.",
        "Load target is provided by user context.",
    ],
}


def write_fake_step(path):
    path.write_bytes(FAKE_STEP_CONTENT)
    return path


def write_context(path, data=None):
    path.write_text(yaml.safe_dump(data or VALID_CONTEXT, sort_keys=False), encoding="utf-8")
    return path


def phase3_package(tmp_path):
    step_path = write_fake_step(tmp_path / "bracket.step")
    package_path = tmp_path / "bracket_001.aieng"
    import_step_package(step_path, package_path)
    extract_topology_package(package_path)
    recognize_features_package(package_path)
    return package_path


def read_json_member(package_path, member):
    with zipfile.ZipFile(package_path) as package:
        return json.loads(package.read(member))


def read_yaml_member(package_path, member):
    with zipfile.ZipFile(package_path) as package:
        return yaml.safe_load(package.read(member))


def test_apply_context_happy_path_after_phase3(tmp_path):
    package_path = phase3_package(tmp_path)
    context_path = write_context(tmp_path / "context.yaml")

    apply_context_package(package_path, context_path)

    constraints = read_json_member(package_path, CONSTRAINTS_PATH)
    setup = read_yaml_member(package_path, SIMULATION_SETUP_PATH)
    protected = read_json_member(package_path, PROTECTED_REGIONS_PATH)
    assert constraints["constraints"]
    assert setup["simulation_id"] == "sim_static_001"
    assert protected["protected_regions"][0]["feature_id"] == "feat_hole_pattern_001"


def test_apply_context_fails_if_package_does_not_exist(tmp_path):
    context_path = write_context(tmp_path / "context.yaml")
    try:
        apply_context_package(tmp_path / "missing.aieng", context_path)
    except FileNotFoundError as exc:
        assert "package does not exist" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_apply_context_fails_if_context_file_does_not_exist(tmp_path):
    package_path = phase3_package(tmp_path)
    try:
        apply_context_package(package_path, tmp_path / "missing.yaml")
    except FileNotFoundError as exc:
        assert "context file does not exist" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_apply_context_fails_if_feature_graph_missing(tmp_path):
    step_path = write_fake_step(tmp_path / "bracket.step")
    package_path = tmp_path / "bracket_001.aieng"
    import_step_package(step_path, package_path)
    extract_topology_package(package_path)
    context_path = write_context(tmp_path / "context.yaml")

    try:
        apply_context_package(package_path, context_path)
    except FileNotFoundError as exc:
        assert "graph/feature_graph.json missing" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_apply_context_fails_for_unknown_material(tmp_path):
    package_path = phase3_package(tmp_path)
    data = dict(VALID_CONTEXT)
    data["material"] = "Unobtainium"
    context_path = write_context(tmp_path / "context.yaml", data)

    try:
        apply_context_package(package_path, context_path)
    except ValueError as exc:
        assert "unknown material" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_apply_context_fails_when_protected_feature_unknown(tmp_path):
    package_path = phase3_package(tmp_path)
    data = dict(VALID_CONTEXT)
    data["protected_features"] = ["feat_missing"]
    context_path = write_context(tmp_path / "context.yaml", data)

    try:
        apply_context_package(package_path, context_path)
    except ValueError as exc:
        assert "protected_features references unknown feature IDs" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_apply_context_fails_when_fixed_feature_unknown(tmp_path):
    package_path = phase3_package(tmp_path)
    data = dict(VALID_CONTEXT)
    data["simulation"] = dict(VALID_CONTEXT["simulation"])
    data["simulation"]["fixed"] = ["feat_missing"]
    context_path = write_context(tmp_path / "context.yaml", data)

    try:
        apply_context_package(package_path, context_path)
    except ValueError as exc:
        assert "simulation.fixed references unknown feature IDs" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_apply_context_fails_when_load_target_unknown(tmp_path):
    package_path = phase3_package(tmp_path)
    data = dict(VALID_CONTEXT)
    data["simulation"] = dict(VALID_CONTEXT["simulation"])
    data["simulation"]["loads"] = [{"target": "feat_missing", "type": "force", "value_n": 1, "direction": [1, 0, 0]}]
    context_path = write_context(tmp_path / "context.yaml", data)

    try:
        apply_context_package(package_path, context_path)
    except ValueError as exc:
        assert "references unknown target feature ID" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_apply_context_outputs_exist_and_manifest_references_them(tmp_path):
    package_path = phase3_package(tmp_path)
    context_path = write_context(tmp_path / "context.yaml")

    apply_context_package(package_path, context_path)

    with zipfile.ZipFile(package_path) as package:
        names = set(package.namelist())
    assert CONSTRAINTS_PATH in names
    assert SIMULATION_SETUP_PATH in names
    assert PROTECTED_REGIONS_PATH in names
    manifest = read_manifest(package_path)
    assert manifest["resources"]["graph"]["constraints"] == CONSTRAINTS_PATH
    assert manifest["resources"]["simulation"]["setup"] == SIMULATION_SETUP_PATH
    assert manifest["resources"]["ai"]["protected_regions"] == PROTECTED_REGIONS_PATH


def test_constraints_reference_valid_features(tmp_path):
    package_path = phase3_package(tmp_path)
    context_path = write_context(tmp_path / "context.yaml")
    apply_context_package(package_path, context_path)

    constraints = read_json_member(package_path, CONSTRAINTS_PATH)
    feature_ids = {feature["id"] for feature in read_json_member(package_path, "graph/feature_graph.json")["features"]}

    for constraint in constraints["constraints"]:
        if constraint["type"] != "simulation_target":
            assert constraint["target"] in feature_ids


def test_simulation_setup_references_valid_features_and_material(tmp_path):
    package_path = phase3_package(tmp_path)
    context_path = write_context(tmp_path / "context.yaml")
    apply_context_package(package_path, context_path)

    setup = read_yaml_member(package_path, SIMULATION_SETUP_PATH)
    feature_ids = {feature["id"] for feature in read_json_member(package_path, "graph/feature_graph.json")["features"]}

    assert "Al6061-T6" in setup["materials"]
    assert setup["materials"]["Al6061-T6"]["youngs_modulus_mpa"] == 69000
    assert setup["assignments"][0]["target_body"] == "body_001"
    assert setup["boundary_conditions"][0]["target_feature"] in feature_ids
    assert setup["loads"][0]["target_feature"] in feature_ids
    assert setup["loads"][0]["direction"] == [1.0, 0.0, 0.0]


def test_protected_regions_reference_valid_features(tmp_path):
    package_path = phase3_package(tmp_path)
    context_path = write_context(tmp_path / "context.yaml")
    apply_context_package(package_path, context_path)

    protected = read_json_member(package_path, PROTECTED_REGIONS_PATH)
    feature_ids = {feature["id"] for feature in read_json_member(package_path, "graph/feature_graph.json")["features"]}
    region = protected["protected_regions"][0]
    assert region["feature_id"] in feature_ids
    assert "read" in region["allowed_operations"]
    assert "delete" in region["forbidden_operations"]


def test_apply_context_does_not_overwrite_by_default(tmp_path):
    package_path = phase3_package(tmp_path)
    context_path = write_context(tmp_path / "context.yaml")
    apply_context_package(package_path, context_path)
    with zipfile.ZipFile(package_path) as package:
        original = package.read(CONSTRAINTS_PATH)

    try:
        apply_context_package(package_path, context_path)
    except FileExistsError as exc:
        assert "use --overwrite" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")
    with zipfile.ZipFile(package_path) as package:
        assert package.read(CONSTRAINTS_PATH) == original


def test_apply_context_overwrites_with_overwrite(tmp_path):
    package_path = phase3_package(tmp_path)
    context_path = write_context(tmp_path / "context.yaml")
    apply_context_package(package_path, context_path)

    apply_context_package(package_path, context_path, overwrite=True)

    assert read_yaml_member(package_path, SIMULATION_SETUP_PATH)["simulation_id"] == "sim_static_001"


def test_cli_apply_context_happy_path_and_validate(tmp_path, capsys):
    package_path = phase3_package(tmp_path)
    context_path = write_context(tmp_path / "context.yaml")

    assert main(["apply-context", str(package_path), "--context", str(context_path)]) == 0
    output = capsys.readouterr().out
    assert "PASS applied engineering context" in output
    assert "PASS graph/constraints.json written" in output
    assert "PASS simulation/setup.yaml written" in output
    assert "PASS ai/protected_regions.json written" in output

    assert main(["validate", str(package_path)]) == 0
    validate_output = capsys.readouterr().out
    assert "PASS graph/constraints.json exists" in validate_output
    assert "PASS simulation/setup.yaml exists" in validate_output
    assert "PASS ai/protected_regions.json exists" in validate_output


def test_validate_passes_after_apply_context(tmp_path):
    package_path = phase3_package(tmp_path)
    context_path = write_context(tmp_path / "context.yaml")
    apply_context_package(package_path, context_path)

    report = validate_package(package_path)
    rendered = report.render()

    assert report.ok
    assert "PASS constraints reference known features" in rendered
    assert "PASS simulation setup references known features and material properties" in rendered
    assert "PASS protected regions reference known features" in rendered
