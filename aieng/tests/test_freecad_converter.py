"""Tests for the FreeCAD reference converter and end-to-end conversion (Phase 20)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from aieng.converters.cli_runners import convert_source
from aieng.converters.freecad import FreeCADConverter
from aieng.validate import validate_package


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "sample_bracket.FCStd"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_sample_fcstd.py"


@pytest.fixture(scope="module")
def fixture_fcstd() -> Path:
    if not FIXTURE.exists():
        # Generate on demand using the script's pure-Python helper.
        import importlib.util

        spec = importlib.util.spec_from_file_location("generate_sample_fcstd", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.generate(FIXTURE)
    assert FIXTURE.exists()
    return FIXTURE


def test_freecad_converter_runs_offline_on_fixture(fixture_fcstd: Path):
    converter = FreeCADConverter()
    result = converter.convert(fixture_fcstd, model_id="sample_bracket")
    assert result.converter_id == "freecad_reference"
    assert result.source_system == "FreeCAD"
    assert result.source_filename == fixture_fcstd.name
    assert result.source_byte_size > 0
    assert result.source_content_sha256 is not None
    assert result.runtime_mode in {"offline", "runtime"}
    # All 4 fixture objects -> 4 features
    feature_graph = json.loads(result.package_files["graph/feature_graph.json"])
    assert len(feature_graph["features"]) == 4
    types = {feature["type"] for feature in feature_graph["features"]}
    assert "base_plate" in types
    assert "mounting_hole" in types
    # Parameters lifted for at least one feature
    assert any(
        isinstance(feature.get("parameters"), dict) and feature["parameters"]
        for feature in feature_graph["features"]
    )
    # Every feature must have a parameter_source the validator recognizes
    for feature in feature_graph["features"]:
        assert feature["parameter_source"] == "converter_extracted"
    # Achieved level set should include L0, L2, L3, L4 (heuristics + parameters)
    achieved_levels = {level.level for level in result.achieved_levels}
    assert {0, 2, 3, 4}.issubset(achieved_levels)
    # Adaptive coverage categories must be populated
    coverage = {cat.category: cat.status for cat in result.coverage_categories}
    assert coverage.get("topology") == "missing"
    assert coverage.get("object_registry") == "complete"
    assert coverage.get("features") == "partial"
    assert coverage.get("geometry") == "missing"
    assert coverage.get("writeback_metadata") == "unsupported"


def test_convert_source_produces_valid_aieng_package(fixture_fcstd: Path, tmp_path: Path):
    out_path = tmp_path / "bracket_from_freecad.aieng"
    convert_source(
        source_path=fixture_fcstd,
        out=out_path,
        model_id="bracket_from_freecad",
        converter_id="freecad_reference",
        overwrite=True,
        runtime_mode="offline",
    )
    assert out_path.exists()

    with zipfile.ZipFile(out_path) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "provenance/conversion_manifest.json" in names
        assert "provenance/converter_capabilities.json" in names
        assert "validation/completeness_report.json" in names
        assert "graph/feature_graph.json" in names
        assert "objects/object_registry.json" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["source_mode"] == "converter"
        assert manifest["created_by"]["converter_id"] == "freecad_reference"
        conversion_manifest = json.loads(archive.read("provenance/conversion_manifest.json"))
        assert conversion_manifest["converter"]["converter_id"] == "freecad_reference"
        assert conversion_manifest["claim_policy"]["aieng_core_performs_cad_edits"] is False
        # Adaptive coverage categories must be present and non-empty
        coverage = {c["category"]: c["status"] for c in conversion_manifest["coverage_categories"]}
        assert coverage.get("topology") == "missing"
        assert coverage.get("object_registry") == "complete"
        assert coverage.get("writeback_metadata") == "unsupported"
        completeness = json.loads(archive.read("validation/completeness_report.json"))
        assert completeness["source_mode"] == "converter"
        # Verify the source_conversion category was emitted
        source_conv = next(
            cat for cat in completeness["categories"] if cat["category"] == "source_conversion"
        )
        assert source_conv["status"] in {"available", "partial"}
        assert "provenance/conversion_manifest.json" in source_conv["resources"]

    report = validate_package(out_path)
    fails = [m for m in report.messages if m.level.value == "FAIL"]
    assert not fails, f"converter-produced package should be valid; fails: {[m.text for m in fails]}"


def test_converter_does_not_run_solver_or_modify_cad(fixture_fcstd: Path, tmp_path: Path):
    out_path = tmp_path / "no_execution.aieng"
    convert_source(
        source_path=fixture_fcstd,
        out=out_path,
        model_id="no_execution",
        converter_id="freecad_reference",
        overwrite=True,
        runtime_mode="offline",
    )
    with zipfile.ZipFile(out_path) as archive:
        names = set(archive.namelist())
        # No solver evidence, no mesh evidence, no modified geometry artifact
        assert "results/evidence_index.json" not in names
        assert not any(name.startswith("geometry/modified_") for name in names)
        assert "simulation/solver_deck.inp" not in names
        # The package retains the original FCStd, unmodified, under provenance/.
        assert "provenance/source.fcstd" in names
        assert archive.read("provenance/source.fcstd") == fixture_fcstd.read_bytes()


def test_invalid_fcstd_source_raises_converter_error(tmp_path: Path):
    from aieng.converters.base import ConverterError

    fake = tmp_path / "fake.FCStd"
    fake.write_bytes(b"not a real archive")
    converter = FreeCADConverter()
    with pytest.raises(ConverterError):
        converter.convert(fake, model_id="m")


def test_missing_source_raises_converter_error(tmp_path: Path):
    from aieng.converters.base import ConverterError

    converter = FreeCADConverter()
    with pytest.raises(ConverterError):
        converter.convert(tmp_path / "absent.FCStd", model_id="m")
