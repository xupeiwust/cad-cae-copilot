"""Tests for the Shape IR reference converter."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from aieng.converters.base import ConverterError
from aieng.converters.cli_runners import convert_source
from aieng.converters.registry import available_converters
from aieng.converters.shape_ir import ShapeIRConverter
from aieng.validate import validate_package


def _write_shape_ir(path: Path) -> Path:
    payload = {
        "format_version": "0.1.0",
        "model_id": "organic_shell_demo",
        "model_kind": "organic",
        "parts": [
            {
                "id": "helmet_shell",
                "name": "Helmet shell",
                "kind": "freeform",
                "feature_type": "unknown_feature",
                "surface_type": "bspline",
                "freeform": True,
                "bbox": [-50, -35, 0, 50, 35, 80],
                "proxy_normal": [0, 0, 1],
                "uv_bounds": [0, 1, 0, 1],
                "curvature_sample": {"status": "not_computed"},
                "parameters": {
                    "section_count": 5,
                    "shell_offset_mm": 2.5,
                },
            },
            {
                "id": "visor_interface",
                "name": "Visor interface",
                "kind": "trim_patch",
                "feature_type": "interface_face",
                "surface_type": "plane",
                "bbox": [-30, -36, 35, 30, -34, 55],
                "normal": [0, -1, 0],
            },
        ],
        "adjacency": [
            {"source": "helmet_shell", "target": "visor_interface", "type": "trimmed_by"},
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_shape_ir_converter_is_registered():
    assert "shape_ir_reference" in available_converters()


def test_shape_ir_converter_projects_topology_and_features(tmp_path: Path):
    source = _write_shape_ir(tmp_path / "organic_shell.shape.json")
    converter = ShapeIRConverter()

    result = converter.convert(source, model_id="organic_shell")

    assert result.converter_id == "shape_ir_reference"
    assert result.source_system == "AIENG Shape IR"
    assert result.runtime_mode == "offline"
    assert result.source_content_sha256 is not None
    assert {level.level for level in result.achieved_levels} == {0, 1, 2, 3, 4}
    assert "geometry/source.py" in result.package_files
    source_py = result.package_files["geometry/source.py"].decode()
    compile(source_py, "geometry/source.py", "exec")
    assert "part_helmet_shell" in source_py
    assert "result = Compound(children=parts)" in source_py

    topology = json.loads(result.package_files["geometry/topology_map.json"])
    assert topology["metadata"]["extraction_mode"] == "projected_from_shape_ir"
    assert topology["metadata"]["real_step_parsing"] is False
    assert any(entity["id"] == "face_helmet_shell" and entity.get("freeform") is True for entity in topology["entities"])
    face = next(entity for entity in topology["entities"] if entity["id"] == "face_helmet_shell")
    assert face["adjacent_entity_ids"] == ["face_visor_interface"]
    assert face["surface_type"] == "bspline"
    assert face["proxy_normal"] == [0, 0, 1]
    assert face["uv_bounds"] == [0, 1, 0, 1]
    assert face["curvature_sample"] == {"status": "not_computed"}

    feature_graph = json.loads(result.package_files["graph/feature_graph.json"])
    features = {feature["id"]: feature for feature in feature_graph["features"]}
    assert features["feat_helmet_shell"]["editability"] == "proposal_allowed"
    assert features["feat_helmet_shell"]["writeback_strategy"] == "semantic_parameter_update_only"
    assert features["feat_visor_interface"]["type"] == "interface_face"


def test_convert_source_produces_valid_shape_ir_package(tmp_path: Path):
    source = _write_shape_ir(tmp_path / "organic_shell.shape_ir.json")
    out_path = tmp_path / "organic_shell.aieng"

    convert_source(
        source_path=source,
        out=out_path,
        model_id="organic_shell",
        converter_id=None,
        overwrite=True,
        runtime_mode="offline",
    )

    with zipfile.ZipFile(out_path) as archive:
        names = set(archive.namelist())
        assert "geometry/shape_ir.json" in names
        assert "geometry/source.py" in names
        assert "geometry/topology_map.json" in names
        assert "graph/feature_graph.json" in names
        assert "objects/object_registry.json" in names
        assert "provenance/conversion_manifest.json" in names
        assert "provenance/converter_capabilities.json" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["source_mode"] == "converter"
        assert manifest["created_by"]["converter_id"] == "shape_ir_reference"
        conversion_manifest = json.loads(archive.read("provenance/conversion_manifest.json"))
        emitted_paths = {item["path"] for item in conversion_manifest["emitted_resources"]}
        assert "geometry/source.py" in emitted_paths
        coverage = {item["category"]: item["status"] for item in conversion_manifest["coverage_categories"]}
        assert coverage["geometry"] == "inferred"
        assert coverage["topology"] == "inferred"
        assert coverage["writeback_metadata"] == "unsupported"

    report = validate_package(out_path)
    fails = [message for message in report.messages if message.level.value == "FAIL"]
    assert not fails, f"Shape IR package should validate; fails: {[m.text for m in fails]}"


def test_shape_ir_converter_rejects_invalid_source(tmp_path: Path):
    source = tmp_path / "broken.shape.json"
    source.write_text("[]", encoding="utf-8")
    with pytest.raises(ConverterError):
        ShapeIRConverter().convert(source, model_id="broken")


def test_shape_ir_compiler_supports_type_key_and_organic_blend():
    from aieng.converters.shape_ir import compile_shape_ir_to_build123d_source

    payload = {
        "parts": [
            {
                "id": "torso",
                "type": "lofted_stack",
                "sections": [[0, 120, 80], [200, 150, 90], [392, 60]],
            },
            {
                "id": "head",
                "type": "sphere",
                "radius": 45,
                "location": [0, 0, 440],
            },
            {
                "id": "body",
                "type": "organic_blend",
                "children": ["torso", "head"],
                "radius": 12,
            },
        ],
    }

    source = compile_shape_ir_to_build123d_source(payload)
    compile(source, "geometry/source.py", "exec")
    assert "lofted_stack([[0, 120, 80], [200, 150, 90], [392, 60]], label='torso')" in source
    assert "organic_blend([part_torso, part_head], 12.0, label='body')" in source
    # Referenced children are compiled as intermediate solids but not duplicated
    # into the final Compound unless emit=true is explicitly requested.
    assert "parts.append(part_torso)" not in source
    assert "parts.append(part_head)" not in source
    assert "parts.append(part_body)" in source
