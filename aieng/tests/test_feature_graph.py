from __future__ import annotations

import json
import zipfile

from jsonschema import Draft202012Validator

from aieng.cli import main
from aieng.geometry.step_importer import import_step_package
from aieng.geometry.topology_extractor import extract_topology_package
from aieng.graph.feature_graph import FEATURE_GRAPH_PATH, recognize_features_package
from aieng.graph.feature_recognition import RuleBasedFeatureRecognizer
from aieng.package import read_manifest
from aieng.validate import validate_package


FAKE_STEP_CONTENT = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


def write_fake_step(path):
    path.write_bytes(FAKE_STEP_CONTENT)
    return path


def imported_and_topologized_package(tmp_path):
    step_path = write_fake_step(tmp_path / "bracket.step")
    package_path = tmp_path / "bracket_001.aieng"
    import_step_package(step_path, package_path)
    extract_topology_package(package_path)
    return package_path


def read_feature_graph(package_path):
    with zipfile.ZipFile(package_path) as package:
        return json.loads(package.read(FEATURE_GRAPH_PATH))


def read_topology_map(package_path):
    with zipfile.ZipFile(package_path) as package:
        return json.loads(package.read("geometry/topology_map.json"))


def test_recognize_features_happy_path_after_import_and_topology(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)

    recognize_features_package(package_path)

    feature_graph = read_feature_graph(package_path)
    feature_ids = {feature["id"] for feature in feature_graph["features"]}
    assert "feat_base_plate_001" in feature_ids
    assert "feat_hole_001" in feature_ids
    assert "feat_hole_pattern_001" in feature_ids
    assert "feat_unknown_001" in feature_ids


def test_recognize_features_fails_if_package_does_not_exist(tmp_path):
    try:
        recognize_features_package(tmp_path / "missing.aieng")
    except FileNotFoundError as exc:
        assert "package does not exist" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_recognize_features_fails_if_topology_map_missing(tmp_path):
    step_path = write_fake_step(tmp_path / "bracket.step")
    package_path = tmp_path / "bracket_001.aieng"
    import_step_package(step_path, package_path)

    try:
        recognize_features_package(package_path)
    except FileNotFoundError as exc:
        assert "geometry/topology_map.json missing" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_recognize_features_writes_feature_graph(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)

    recognize_features_package(package_path)

    with zipfile.ZipFile(package_path) as package:
        assert FEATURE_GRAPH_PATH in set(package.namelist())


def test_recognize_features_manifest_references_feature_graph(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)

    recognize_features_package(package_path)

    manifest = read_manifest(package_path)
    assert manifest["resources"]["graph"]["feature_graph"] == FEATURE_GRAPH_PATH
    assert manifest["resources"]["geometry"]["topology_map"] == "geometry/topology_map.json"


def test_feature_graph_conforms_to_schema(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    feature_graph = read_feature_graph(package_path)
    schema = json.loads((__import__("pathlib").Path("schemas") / "feature_graph.schema.json").read_text())

    errors = list(Draft202012Validator(schema).iter_errors(feature_graph))

    assert errors == []


def test_base_plate_candidate_exists(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    base = next(feature for feature in features if feature["id"] == "feat_base_plate_001")

    assert base["type"] == "base_plate"
    assert base["name"] == "Base plate candidate"
    assert base["geometry_refs"]["faces"] == ["face_base_bottom"]
    assert base["intent"]["role"] == "structural_base_candidate"
    assert base["recognition"]["method"] == "rule_based_largest_planar_face"
    assert base["recognition"]["confidence"] in {"low", "medium"}


def test_mounting_hole_candidates_exist(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    holes = [feature for feature in features if feature["type"] == "mounting_hole"]

    assert len(holes) == 4
    assert holes[0]["id"] == "feat_hole_001"
    assert holes[0]["geometry_refs"]["faces"] == ["face_hole_001_cyl"]
    assert holes[0]["parameters"]["radius_mm"] == 5.0
    assert holes[0]["parameters"]["diameter_mm"] == 10.0
    assert holes[0]["intent"]["role"] == "mounting_or_passage_candidate"


def test_mounting_hole_pattern_exists_when_multiple_cylindrical_faces_present(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    pattern = next(feature for feature in features if feature["id"] == "feat_hole_pattern_001")

    assert pattern["type"] == "mounting_hole_pattern"
    assert pattern["children"] == ["feat_hole_001", "feat_hole_002", "feat_hole_003", "feat_hole_004"]
    assert pattern["parameters"]["count"] == 4
    assert pattern["parameters"]["diameter_mm"] == 10.0
    assert pattern["intent"]["role"] == "mounting_interface_candidate"


def test_unknown_feature_exists_for_unclassified_topology(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    unknown = next(feature for feature in features if feature["id"] == "feat_unknown_001")

    assert unknown["type"] == "unknown_feature"
    assert unknown["intent"]["role"] == "unclassified_geometry"
    assert "face_base_top" in unknown["geometry_refs"]["faces"]
    assert "edge_base_front_top" in unknown["geometry_refs"]["edges"]


def test_feature_geometry_refs_point_to_known_topology_ids(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    feature_graph = read_feature_graph(package_path)
    topology_map = read_topology_map(package_path)
    face_ids = {entity["id"] for entity in topology_map["entities"] if entity["type"] == "face"}
    edge_ids = {entity["id"] for entity in topology_map["entities"] if entity["type"] == "edge"}

    for feature in feature_graph["features"]:
        refs = feature["geometry_refs"]
        assert set(refs.get("faces", [])).issubset(face_ids)
        assert set(refs.get("edges", [])).issubset(edge_ids)


def test_feature_ids_are_unique(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    feature_graph = read_feature_graph(package_path)

    ids = [feature["id"] for feature in feature_graph["features"]]

    assert len(ids) == len(set(ids))


def test_children_references_point_to_known_feature_ids(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    feature_graph = read_feature_graph(package_path)
    feature_ids = {feature["id"] for feature in feature_graph["features"]}

    for feature in feature_graph["features"]:
        assert set(feature.get("children", [])).issubset(feature_ids)


def test_recognize_features_does_not_overwrite_by_default(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    with zipfile.ZipFile(package_path) as package:
        original = package.read(FEATURE_GRAPH_PATH)

    try:
        recognize_features_package(package_path)
    except FileExistsError as exc:
        assert "use --overwrite" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")

    with zipfile.ZipFile(package_path) as package:
        assert package.read(FEATURE_GRAPH_PATH) == original


def test_recognize_features_overwrites_with_overwrite(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)

    recognize_features_package(package_path, overwrite=True)

    feature_graph = read_feature_graph(package_path)
    assert feature_graph["metadata"]["recognizer"] == "RuleBasedFeatureRecognizer"


def test_cli_recognize_features_happy_path_and_validate(tmp_path, capsys):
    package_path = imported_and_topologized_package(tmp_path)

    assert main(["recognize-features", str(package_path)]) == 0
    output = capsys.readouterr().out
    assert "PASS recognized rule-based feature candidates" in output
    assert "PASS graph/feature_graph.json written" in output

    assert main(["validate", str(package_path)]) == 0
    validate_output = capsys.readouterr().out
    assert "PASS graph/feature_graph.json exists" in validate_output
    assert "PASS graph/feature_graph.json conforms to feature_graph.schema.json" in validate_output
    assert "PASS feature IDs are unique" in validate_output
    assert "PASS feature geometry references resolve to topology IDs" in validate_output


def test_cli_recognize_features_does_not_overwrite_by_default(tmp_path, capsys):
    package_path = imported_and_topologized_package(tmp_path)
    assert main(["recognize-features", str(package_path)]) == 0
    capsys.readouterr()

    assert main(["recognize-features", str(package_path)]) == 2
    captured = capsys.readouterr()
    assert "FAIL graph/feature_graph.json already exists" in captured.err


def test_cli_recognize_features_overwrites_with_overwrite(tmp_path, capsys):
    package_path = imported_and_topologized_package(tmp_path)
    assert main(["recognize-features", str(package_path)]) == 0
    capsys.readouterr()

    assert main(["recognize-features", str(package_path), "--overwrite"]) == 0
    output = capsys.readouterr().out
    assert "PASS graph/feature_graph.json written" in output


def test_validate_passes_after_feature_recognition(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)

    report = validate_package(package_path)
    rendered = report.render()

    assert report.ok
    assert "PASS graph/feature_graph.json exists" in rendered
    assert "PASS feature child and relationship references resolve" in rendered


# --- Phase 13A: parametric feature definition tests ---

def test_all_features_have_parameter_source(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    valid_sources = {"mock", "ocp_extracted", "user_provided", "agent_defined"}
    for feature in features:
        assert "parameter_source" in feature, f"{feature['id']} missing parameter_source"
        assert feature["parameter_source"] in valid_sources, (
            f"{feature['id']} has invalid parameter_source '{feature['parameter_source']}'"
        )


def test_all_features_have_editable_flag(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    for feature in features:
        assert "editable" in feature, f"{feature['id']} missing editable field"
        assert isinstance(feature["editable"], bool), f"{feature['id']} editable must be bool"


def test_all_features_have_parameter_confidence(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    valid_confidences = {"high", "medium", "low"}
    for feature in features:
        assert "parameter_confidence" in feature, f"{feature['id']} missing parameter_confidence"
        assert feature["parameter_confidence"] in valid_confidences


def test_editable_features_have_non_empty_parameters(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    for feature in features:
        if feature.get("editable"):
            params = feature.get("parameters", {})
            assert isinstance(params, dict) and params, (
                f"{feature['id']} is editable but has empty or missing parameters"
            )


def test_unknown_feature_is_not_editable(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    unknown = next(f for f in features if f["id"] == "feat_unknown_001")
    assert unknown["editable"] is False


def test_mock_features_have_parameter_source_mock(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    for feature in features:
        assert feature["parameter_source"] == "mock", (
            f"{feature['id']} expected parameter_source 'mock', got '{feature['parameter_source']}'"
        )


def test_recognition_contains_uncertainty_notes_for_all_generated_features(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    for feature in features:
        recognition = feature.get("recognition")
        assert isinstance(recognition, dict)
        notes = recognition.get("uncertainty_notes")
        assert isinstance(notes, list) and notes


def test_real_topology_pattern_confidence_upgrades_to_high_with_strong_signals():
    recognizer = RuleBasedFeatureRecognizer()
    topology_map = {
        "format_version": "0.1.0",
        "metadata": {
            "extraction_backend": "occ",
            "real_step_parsing": True,
        },
        "entities": [
            {"id": "face_base_bottom", "type": "face", "surface_type": "plane", "area": 100.0},
            {"id": "face_hole_001_cyl", "type": "face", "surface_type": "cylinder", "radius": 5.0, "axis": [0.0, 0.0, 1.0]},
            {"id": "face_hole_002_cyl", "type": "face", "surface_type": "cylinder", "radius": 5.0, "axis": [0.0, 0.0, 1.0]},
            {"id": "face_hole_003_cyl", "type": "face", "surface_type": "cylinder", "radius": 5.0, "axis": [0.0, 0.0, 1.0]},
            {"id": "face_hole_004_cyl", "type": "face", "surface_type": "cylinder", "radius": 5.0, "axis": [0.0, 0.0, 1.0]},
            {"id": "face_other_001", "type": "face", "surface_type": "plane", "area": 10.0},
            {"id": "edge_other_001", "type": "edge"},
        ],
    }

    result = recognizer.recognize(topology_map)
    pattern = next(feature for feature in result["features"] if feature["id"] == "feat_hole_pattern_001")

    assert pattern["recognition"]["confidence"] == "high"
    assert pattern["recognition"]["signals"]["real_topology"] is True
    assert pattern["recognition"]["signals"]["single_diameter_group"] is True
    assert pattern["recognition"]["signals"]["axis_available_for_all_holes"] is True


def test_real_topology_pattern_confidence_is_higher_than_mock_baseline_for_same_geometry():
    recognizer = RuleBasedFeatureRecognizer()
    entities = [
        {"id": "face_base_bottom", "type": "face", "surface_type": "plane", "area": 100.0},
        {"id": "face_hole_001_cyl", "type": "face", "surface_type": "cylinder", "radius": 5.0, "axis": [0.0, 0.0, 1.0]},
        {"id": "face_hole_002_cyl", "type": "face", "surface_type": "cylinder", "radius": 5.0, "axis": [0.0, 0.0, 1.0]},
        {"id": "face_hole_003_cyl", "type": "face", "surface_type": "cylinder", "radius": 5.0, "axis": [0.0, 0.0, 1.0]},
        {"id": "face_hole_004_cyl", "type": "face", "surface_type": "cylinder", "radius": 5.0, "axis": [0.0, 0.0, 1.0]},
        {"id": "face_other_001", "type": "face", "surface_type": "plane", "area": 10.0},
        {"id": "edge_other_001", "type": "edge"},
    ]

    baseline_result = recognizer.recognize(
        {
            "format_version": "0.1.0",
            "metadata": {"extraction_backend": "mock", "real_step_parsing": False},
            "entities": entities,
        }
    )
    real_result = recognizer.recognize(
        {
            "format_version": "0.1.0",
            "metadata": {"extraction_backend": "occ", "real_step_parsing": True},
            "entities": entities,
        }
    )

    baseline_pattern = next(feature for feature in baseline_result["features"] if feature["id"] == "feat_hole_pattern_001")
    real_pattern = next(feature for feature in real_result["features"] if feature["id"] == "feat_hole_pattern_001")

    assert baseline_pattern["recognition"]["confidence"] == "medium"
    assert real_pattern["recognition"]["confidence"] == "high"


def test_mock_features_are_semantic_only_not_cad_writeback(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)
    features = read_feature_graph(package_path)["features"]

    for feature in features:
        if feature["parameter_source"] == "mock":
            assert feature["writeback_strategy"] in {"semantic_parameter_update_only", "none"}
            assert feature["editability"] in {"semantic_only", "not_editable"}


def test_validator_rejects_invalid_parameter_source(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)

    with zipfile.ZipFile(package_path, "a") as zf:
        fg = json.loads(zf.read(FEATURE_GRAPH_PATH))
        fg["features"][0]["parameter_source"] = "invented_source"
        zf.writestr(FEATURE_GRAPH_PATH, json.dumps(fg))

    report = validate_package(package_path)
    assert not report.ok
    assert any("parameter_source" in msg.text for msg in report.messages)


def test_validator_rejects_mock_cad_writeback_claim(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)

    with zipfile.ZipFile(package_path, "a") as zf:
        fg = json.loads(zf.read(FEATURE_GRAPH_PATH))
        fg["features"][0]["writeback_strategy"] = "cadquery_regeneration"
        zf.writestr(FEATURE_GRAPH_PATH, json.dumps(fg))

    report = validate_package(package_path)
    assert not report.ok
    assert any("cannot declare CAD write-back strategy" in msg.text for msg in report.messages)


def test_validator_rejects_executable_editability_without_parametric_source(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)

    with zipfile.ZipFile(package_path, "a") as zf:
        fg = json.loads(zf.read(FEATURE_GRAPH_PATH))
        fg["features"][0]["editability"] = "executable_by_regeneration"
        fg["features"][0]["writeback_strategy"] = "cadquery_regeneration"
        zf.writestr(FEATURE_GRAPH_PATH, json.dumps(fg))

    report = validate_package(package_path)
    assert not report.ok
    assert any("executable editability requires" in msg.text for msg in report.messages)


def test_validator_rejects_editable_true_with_empty_parameters(tmp_path):
    package_path = imported_and_topologized_package(tmp_path)
    recognize_features_package(package_path)

    with zipfile.ZipFile(package_path, "a") as zf:
        fg = json.loads(zf.read(FEATURE_GRAPH_PATH))
        fg["features"][0]["editable"] = True
        fg["features"][0]["parameters"] = {}
        zf.writestr(FEATURE_GRAPH_PATH, json.dumps(fg))

    report = validate_package(package_path)
    assert not report.ok
    assert any("editable=true requires" in msg.text for msg in report.messages)
