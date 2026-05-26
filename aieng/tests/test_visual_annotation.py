"""Tests for Phase 8A: visual/annotation_layers.json generation and validation."""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

from aieng.cli import main
from aieng.package import create_package
from aieng.validate import validate_package
from aieng.visual.annotation_writer import (
    ANNOTATION_LAYERS_PATH,
    VISUAL_DIR,
    build_visual_index_package,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
STEP_PATH = EXAMPLES_DIR / "bracket.step"
CONTEXT_PATH = EXAMPLES_DIR / "bracket_user_context.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_full_package(tmp_path: Path) -> Path:
    pkg = tmp_path / "bracket_001.aieng"
    assert main(["import-step", str(STEP_PATH), "--out", str(pkg)]) == 0
    assert main(["extract-topology", str(pkg), "--overwrite", "--backend", "mock"]) == 0
    assert main(["recognize-features", str(pkg), "--overwrite"]) == 0
    assert main(["apply-context", str(pkg), "--context", str(CONTEXT_PATH), "--overwrite"]) == 0
    return pkg


def _read_annotation_layers(pkg: Path) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(ANNOTATION_LAYERS_PATH))


def _read_manifest(pkg: Path) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read("manifest.json"))


def _tamper_annotation_layers(pkg: Path, bad_layers: dict[str, Any]) -> None:
    """Replace annotation_layers.json in an existing package with tampered data."""
    with zipfile.ZipFile(pkg, mode="r") as zf:
        members = [
            (info, b"" if info.is_dir() else zf.read(info.filename))
            for info in zf.infolist()
            if info.filename != ANNOTATION_LAYERS_PATH
        ]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=pkg.parent) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with zipfile.ZipFile(tmp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for info, data in members:
                zf.writestr(info, data)
            zf.writestr(ANNOTATION_LAYERS_PATH, json.dumps(bad_layers).encode())
        shutil.move(str(tmp_path), pkg)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# Basic contract
# ---------------------------------------------------------------------------

def test_build_visual_index_returns_package_path(tmp_path):
    pkg = _make_full_package(tmp_path)
    result = build_visual_index_package(pkg)
    assert result == pkg


def test_build_visual_index_writes_annotation_layers(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    with zipfile.ZipFile(pkg) as zf:
        assert ANNOTATION_LAYERS_PATH in set(zf.namelist())


def test_build_visual_index_creates_visual_directory(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    with zipfile.ZipFile(pkg) as zf:
        assert VISUAL_DIR in set(zf.namelist())


def test_build_visual_index_manifest_references_annotation(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    manifest = _read_manifest(pkg)
    assert manifest["resources"]["visual"]["annotation_layers"] == ANNOTATION_LAYERS_PATH


def test_annotation_layers_is_valid_json(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    data = _read_annotation_layers(pkg)
    assert isinstance(data, dict)


def test_annotation_layers_format_field(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    data = _read_annotation_layers(pkg)
    assert data["format"] == "aieng.visual_annotation_layers"
    assert data["format_version"] == "0.1.0"


def test_annotation_layers_has_source_files(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    data = _read_annotation_layers(pkg)
    assert "graph/feature_graph.json" in data["source_files"]


# ---------------------------------------------------------------------------
# Layer existence
# ---------------------------------------------------------------------------

def test_features_layer_exists(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    layers = _read_annotation_layers(pkg)["layers"]
    assert any(layer["id"] == "features" for layer in layers)


def test_features_layer_has_items(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    layers = _read_annotation_layers(pkg)["layers"]
    features_layer = next(l for l in layers if l["id"] == "features")
    assert len(features_layer["items"]) > 0


def test_protected_regions_layer_exists(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    layers = _read_annotation_layers(pkg)["layers"]
    assert any(layer["id"] == "protected_regions" for layer in layers)


def test_protected_regions_layer_has_items(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    layers = _read_annotation_layers(pkg)["layers"]
    prot_layer = next(l for l in layers if l["id"] == "protected_regions")
    assert len(prot_layer["items"]) > 0


def test_simulation_targets_layer_exists(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    layers = _read_annotation_layers(pkg)["layers"]
    assert any(layer["id"] == "simulation_targets" for layer in layers)


def test_simulation_targets_layer_has_items(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    layers = _read_annotation_layers(pkg)["layers"]
    sim_layer = next(l for l in layers if l["id"] == "simulation_targets")
    assert len(sim_layer["items"]) > 0


def test_unknown_or_unclassified_layer_exists(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    layers = _read_annotation_layers(pkg)["layers"]
    assert any(layer["id"] == "unknown_or_unclassified" for layer in layers)


# ---------------------------------------------------------------------------
# Annotation content
# ---------------------------------------------------------------------------

def test_annotations_reference_valid_feature_ids(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    annotation_layers = _read_annotation_layers(pkg)
    with zipfile.ZipFile(pkg) as zf:
        feature_graph = json.loads(zf.read("graph/feature_graph.json"))
    known_feature_ids = {f["id"] for f in feature_graph["features"] if isinstance(f, dict)}
    for layer in annotation_layers["layers"]:
        for item in layer["items"]:
            assert item["feature_id"] in known_feature_ids, (
                f"Unknown feature_id {item['feature_id']!r} in layer {layer['id']!r}"
            )


def test_annotations_reference_valid_topology_face_ids(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    annotation_layers = _read_annotation_layers(pkg)
    with zipfile.ZipFile(pkg) as zf:
        topology_map = json.loads(zf.read("geometry/topology_map.json"))
    known_face_ids = {
        e["id"] for e in topology_map["entities"]
        if isinstance(e, dict) and e.get("type") == "face"
    }
    for layer in annotation_layers["layers"]:
        for item in layer["items"]:
            for face_id in item.get("topology_refs", {}).get("faces", []):
                assert face_id in known_face_ids, (
                    f"Unknown face ref {face_id!r} in layer {layer['id']!r}"
                )


def test_protected_annotation_includes_forbidden_operations(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    annotation_layers = _read_annotation_layers(pkg)
    prot_layer = next(l for l in annotation_layers["layers"] if l["id"] == "protected_regions")
    for item in prot_layer["items"]:
        assert "forbidden_operations" in item
        assert isinstance(item["forbidden_operations"], list)


def test_protected_annotation_visual_role(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    annotation_layers = _read_annotation_layers(pkg)
    prot_layer = next(l for l in annotation_layers["layers"] if l["id"] == "protected_regions")
    for item in prot_layer["items"]:
        assert item["visual_role"] == "protected_region"
        assert item["status"] == "protected"


def test_unknown_annotation_visual_role(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    annotation_layers = _read_annotation_layers(pkg)
    unk_layer = next(l for l in annotation_layers["layers"] if l["id"] == "unknown_or_unclassified")
    for item in unk_layer["items"]:
        assert item["visual_role"] == "unclassified_geometry"
        assert item["status"] == "unknown"


def test_simulation_annotation_visual_role(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    annotation_layers = _read_annotation_layers(pkg)
    sim_layer = next(l for l in annotation_layers["layers"] if l["id"] == "simulation_targets")
    for item in sim_layer["items"]:
        assert item["visual_role"] == "simulation_context"


def test_annotation_item_ids_unique_across_layers(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    annotation_layers = _read_annotation_layers(pkg)
    all_ids = [item["id"] for layer in annotation_layers["layers"] for item in layer["items"]]
    assert len(all_ids) == len(set(all_ids)), f"Duplicate annotation IDs: {[i for i in all_ids if all_ids.count(i) > 1]}"


def test_layer_ids_unique(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    annotation_layers = _read_annotation_layers(pkg)
    layer_ids = [l["id"] for l in annotation_layers["layers"]]
    assert len(layer_ids) == len(set(layer_ids))


def test_feature_items_have_topology_refs(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    annotation_layers = _read_annotation_layers(pkg)
    features_layer = next(l for l in annotation_layers["layers"] if l["id"] == "features")
    for item in features_layer["items"]:
        assert "topology_refs" in item
        assert "faces" in item["topology_refs"]
        assert "edges" in item["topology_refs"]


# ---------------------------------------------------------------------------
# Overwrite behavior
# ---------------------------------------------------------------------------

def test_build_visual_index_does_not_overwrite_by_default(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    with pytest.raises(FileExistsError):
        build_visual_index_package(pkg)


def test_build_visual_index_overwrites_with_flag(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    result = build_visual_index_package(pkg, overwrite=True)
    assert result == pkg


def test_build_visual_index_cli_no_overwrite_returns_2(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-visual-index", str(pkg)]) == 0
    assert main(["build-visual-index", str(pkg)]) == 2


def test_build_visual_index_cli_overwrite_returns_0(tmp_path):
    pkg = _make_full_package(tmp_path)
    assert main(["build-visual-index", str(pkg)]) == 0
    assert main(["build-visual-index", str(pkg), "--overwrite"]) == 0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_build_visual_index_fails_package_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_visual_index_package(tmp_path / "nonexistent.aieng")


def test_build_visual_index_fails_feature_graph_missing(tmp_path):
    pkg = tmp_path / "test.aieng"
    create_package("test_model", pkg)
    with pytest.raises(FileNotFoundError, match="feature_graph"):
        build_visual_index_package(pkg)


def test_build_visual_index_cli_fails_feature_graph_missing(tmp_path):
    pkg = tmp_path / "test.aieng"
    create_package("test_model", pkg)
    assert main(["build-visual-index", str(pkg)]) == 2


def test_build_visual_index_cli_fails_package_not_found(tmp_path):
    assert main(["build-visual-index", str(tmp_path / "nonexistent.aieng")]) == 2


# ---------------------------------------------------------------------------
# Validator integration
# ---------------------------------------------------------------------------

def test_validator_passes_after_build_visual_index(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert not fails, f"Validation failures: {fails}"


def test_validator_checks_annotation_layers_schema(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    report = validate_package(pkg)
    texts = [m.text for m in report.messages]
    assert any("annotation_layers" in t for t in texts)


def test_validator_checks_layer_ids_unique(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    report = validate_package(pkg)
    texts = [m.text for m in report.messages]
    assert any("annotation layer IDs are unique" in t for t in texts)


def test_validator_checks_item_ids_unique(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    report = validate_package(pkg)
    texts = [m.text for m in report.messages]
    assert any("annotation item IDs are unique" in t for t in texts)


def test_validator_fails_annotation_references_unknown_feature_id(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    bad_layers = {
        "format": "aieng.visual_annotation_layers",
        "format_version": "0.1.0",
        "source_files": ["graph/feature_graph.json"],
        "layers": [
            {
                "id": "features",
                "name": "Feature annotations",
                "items": [
                    {
                        "id": "ann_feat_nonexistent",
                        "feature_id": "feat_nonexistent_999",
                        "label": "Bad feature",
                        "visual_role": "candidate_feature",
                        "status": "candidate",
                        "topology_refs": {"faces": [], "edges": []},
                    }
                ],
            }
        ],
    }
    _tamper_annotation_layers(pkg, bad_layers)
    report = validate_package(pkg)
    fail_texts = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("feat_nonexistent_999" in t for t in fail_texts), (
        f"Expected unknown feature_id failure, got: {fail_texts}"
    )


def test_validator_fails_annotation_references_unknown_topology_id(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    bad_layers = {
        "format": "aieng.visual_annotation_layers",
        "format_version": "0.1.0",
        "source_files": ["graph/feature_graph.json"],
        "layers": [
            {
                "id": "features",
                "name": "Feature annotations",
                "items": [
                    {
                        "id": "ann_feat_base_plate_001",
                        "feature_id": "feat_base_plate_001",
                        "label": "Base plate candidate",
                        "visual_role": "candidate_feature",
                        "status": "candidate",
                        "topology_refs": {"faces": ["face_nonexistent_999"], "edges": []},
                    }
                ],
            }
        ],
    }
    _tamper_annotation_layers(pkg, bad_layers)
    report = validate_package(pkg)
    fail_texts = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("face_nonexistent_999" in t for t in fail_texts), (
        f"Expected unknown topology ref failure, got: {fail_texts}"
    )


# ---------------------------------------------------------------------------
# Summary mentions visual index
# ---------------------------------------------------------------------------

def test_readme_for_ai_mentions_visual_index_when_present(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    assert main(["summarize", str(pkg), "--overwrite"]) == 0
    with zipfile.ZipFile(pkg) as zf:
        readme = zf.read("README_FOR_AI.md").decode("utf-8")
    assert "visual/annotation_layers.json" in readme


def test_ai_summary_mentions_visual_index_when_present(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    assert main(["summarize", str(pkg), "--overwrite"]) == 0
    with zipfile.ZipFile(pkg) as zf:
        summary = zf.read("ai/summary.md").decode("utf-8")
    assert "visual/annotation_layers.json" in summary


def test_readme_for_ai_mentions_not_rendered_geometry(tmp_path):
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    assert main(["summarize", str(pkg), "--overwrite"]) == 0
    with zipfile.ZipFile(pkg) as zf:
        readme = zf.read("README_FOR_AI.md").decode("utf-8")
    assert "not rendered geometry" in readme.lower() or "not rendered" in readme.lower() or "annotation scaffold" in readme.lower()


# ---------------------------------------------------------------------------
# Validation status reflects visual index
# ---------------------------------------------------------------------------

def test_validation_status_records_visual_index_present(tmp_path):
    import yaml
    pkg = _make_full_package(tmp_path)
    build_visual_index_package(pkg)
    assert main(["update-validation-status", str(pkg), "--overwrite"]) == 0
    with zipfile.ZipFile(pkg) as zf:
        status = yaml.safe_load(zf.read("validation/status.yaml"))
    assert status["visual_status"]["visual_index_present"] is True
    assert status["visual_status"]["visual_rendering"] == "not_generated"


def test_validation_status_records_visual_index_absent(tmp_path):
    import yaml
    pkg = _make_full_package(tmp_path)
    assert main(["update-validation-status", str(pkg), "--overwrite"]) == 0
    with zipfile.ZipFile(pkg) as zf:
        status = yaml.safe_load(zf.read("validation/status.yaml"))
    assert status["visual_status"]["visual_index_present"] is False
