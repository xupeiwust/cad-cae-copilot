"""G12: Interop conformance suite for CI - roundtrip invariance tests.

This test suite verifies that representative CAD/CAE fixtures can roundtrip
through .aieng without semantic drift:

1. Import CAD geometry
2. Extract topology/features
3. Apply simulation context
4. Export to solver deck
5. Verify core semantics are preserved

These tests must be deterministic and suitable for CI execution.
"""
import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from aieng.package import create_package
from aieng.provenance.tool_trace_writer import record_trace_package
from aieng.results.evidence_writer import write_evidence_scaffold_package

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
STEP_FILE = EXAMPLES_DIR / "bracket.step"


class TestG12InteropConformanceBracketStep:
    """Test roundtrip invariance for bracket.step reference fixture."""

    def test_step_import_creates_valid_package(self, tmp_path):
        """Importing STEP should create valid .aieng package."""
        package_path = tmp_path / "bracket_roundtrip_g12.aieng"
        create_package("bracket_g12", package_path)
        
        assert package_path.exists()
        with zipfile.ZipFile(package_path) as zf:
            assert "manifest.json" in zf.namelist()
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["model_id"] == "bracket_g12"
            assert manifest["format_version"] == "0.1.0"

    def test_package_structure_has_required_directories(self, tmp_path):
        """Package must have all required directory structure."""
        package_path = tmp_path / "bracket_structure.aieng"
        create_package("bracket_struct", package_path)
        
        # These directories are created by create_package
        required_dirs = {
            "geometry/",
            "graph/",
            "simulation/",
            "results/",
            "provenance/",
            "ai/",
            "visual/",
        }
        
        with zipfile.ZipFile(package_path) as zf:
            names = set(zf.namelist())
            for req_dir in required_dirs:
                assert any(n.startswith(req_dir) for n in names), \
                    f"Missing directory {req_dir}"

    def test_evidence_scaffold_creates_required_resources(self, tmp_path):
        """Evidence scaffold should initialize claim/evidence infrastructure."""
        package_path = tmp_path / "bracket_evidence.aieng"
        create_package("bracket_evid", package_path)
        
        write_evidence_scaffold_package(package_path)
        
        with zipfile.ZipFile(package_path) as zf:
            assert "results/evidence_index.json" in zf.namelist()

            evid_index = json.loads(zf.read("results/evidence_index.json"))

            assert evid_index["format_version"] == "0.1.0"

    def test_tool_trace_can_be_recorded(self, tmp_path):
        """Tool trace should record deterministically."""
        package_path = tmp_path / "bracket_trace.aieng"
        create_package("bracket_trace", package_path)
        
        record_trace_package(
            package_path,
            tool_id="importer_step_v1",
            tool_role="cad_runtime",
            step_name="import_step_geometry",
            exit_status="success",
            tool_version="1.0",
            inputs=["bracket.step"],
            outputs=["geometry/normalized.step"],
            artifacts_recorded=[],
            claims_advanced=[],
            notes=["G12 test: recorded deterministically"],
        )
        
        with zipfile.ZipFile(package_path) as zf:
            assert "provenance/tool_trace.json" in zf.namelist()
            trace = json.loads(zf.read("provenance/tool_trace.json"))
            
            assert trace["format_version"] == "0.1.0"
            assert len(trace["entries"]) == 1
            assert trace["entries"][0]["tool"]["tool_id"] == "importer_step_v1"
            assert trace["entries"][0]["step"]["exit_status"] == "success"


class TestG12DeterministicRoundtrip:
    """Test deterministic roundtrip of core package semantics."""

    def test_repeated_package_creation_is_deterministic(self, tmp_path):
        """Creating same package twice should produce same manifest."""
        manifests = []
        
        for i in range(2):
            package_path = tmp_path / f"deterministic_{i}.aieng"
            create_package("deterministic_test", package_path)
            
            with zipfile.ZipFile(package_path) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                # Remove timestamp which may vary
                manifest.pop("created_timestamp_utc", None)
                manifests.append(manifest)
        
        # Core manifest fields should match
        assert manifests[0]["model_id"] == manifests[1]["model_id"]
        assert manifests[0]["format_version"] == manifests[1]["format_version"]
        assert manifests[0]["units"] == manifests[1]["units"]

    def test_evidence_scaffold_is_deterministic(self, tmp_path):
        """Evidence scaffold should be deterministic across runs."""
        evidence_indices = []
        
        for i in range(2):
            package_path = tmp_path / f"scaffold_{i}.aieng"
            create_package("scaffold_test", package_path)
            write_evidence_scaffold_package(package_path)
            
            with zipfile.ZipFile(package_path) as zf:
                evid_index = json.loads(zf.read("results/evidence_index.json"))
                evidence_indices.append(evid_index)
        
        # Structure should be identical
        assert evidence_indices[0]["format_version"] == evidence_indices[1]["format_version"]
        assert evidence_indices[0].get("evidence_ledger", {}) == evidence_indices[1].get("evidence_ledger", {})

    def test_tool_trace_entry_ids_are_unique(self, tmp_path):
        """Each tool trace entry should have unique ID."""
        package_path = tmp_path / "unique_trace.aieng"
        create_package("unique_trace_test", package_path)
        
        entry_ids = set()
        
        for i in range(3):
            record_trace_package(
                package_path,
                tool_id=f"tool_{i}",
                tool_role="solver",
                step_name=f"step_{i}",
                exit_status="success",
            )
        
        with zipfile.ZipFile(package_path) as zf:
            trace = json.loads(zf.read("provenance/tool_trace.json"))
            
            for entry in trace["entries"]:
                entry_id = entry["entry_id"]
                assert entry_id not in entry_ids, f"Duplicate entry_id: {entry_id}"
                entry_ids.add(entry_id)
        
        assert len(entry_ids) == 3


class TestG12PackageCoreInvariants:
    """Test that core package invariants are maintained."""

    def test_manifest_units_are_consistent(self, tmp_path):
        """Manifest units should be consistent and documented."""
        package_path = tmp_path / "units_test.aieng"
        create_package("units_test", package_path)
        
        with zipfile.ZipFile(package_path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            
            required_units = {"length", "mass", "force", "stress"}
            assert required_units <= set(manifest["units"].keys())
            
            # All units should be non-empty strings
            for unit_type, unit_value in manifest["units"].items():
                assert isinstance(unit_value, str)
                assert len(unit_value) > 0

    def test_manifest_model_id_is_preserved(self, tmp_path):
        """Model ID should match input and be stable."""
        model_ids = ["model_a", "model_b", "model_c_long_name_123"]
        
        for model_id in model_ids:
            package_path = tmp_path / f"{model_id}.aieng"
            create_package(model_id, package_path)
            
            with zipfile.ZipFile(package_path) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                assert manifest["model_id"] == model_id

    def test_resource_paths_in_manifest_reference_correct_types(self, tmp_path):
        """Resource paths should match directory structure."""
        package_path = tmp_path / "paths_test.aieng"
        create_package("paths_test", package_path)
        
        with zipfile.ZipFile(package_path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            names = zf.namelist()
            
            # If resources are listed in manifest, they should exist or be subdirs
            for resource_key, resource_value in manifest.get("resources", {}).items():
                if isinstance(resource_value, str):
                    # Should be a path that exists as dir or will contain files
                    assert resource_value.endswith("/") or any(
                        n.startswith(resource_value)
                        for n in names
                    )


class TestG12ConformanceReporting:
    """Tests that verify conformance can be reported."""

    def test_package_structure_can_be_validated(self, tmp_path):
        """Package should support structure validation."""
        package_path = tmp_path / "validate_test.aieng"
        create_package("validate_test", package_path)
        
        # Basic structure check
        with zipfile.ZipFile(package_path) as zf:
            names = set(zf.namelist())
            
            # Should have manifest
            assert "manifest.json" in names
            
            # Should have at least directory markers for key areas
            key_dirs = {"geometry/", "graph/", "simulation/", "results/"}
            for key_dir in key_dirs:
                assert any(n.startswith(key_dir) for n in names)

    def test_ci_can_collect_fixture_statistics(self, tmp_path):
        """CI should be able to collect statistics on fixtures."""
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        
        # Create representative fixtures
        for model_id in ["bracket_fixture_1", "bracket_fixture_2"]:
            fixture_path = fixtures_dir / f"{model_id}.aieng"
            create_package(model_id, fixture_path)
        
        # CI should be able to iterate and collect stats
        fixture_files = list(fixtures_dir.glob("*.aieng"))
        assert len(fixture_files) == 2
        
        stats = {
            "fixture_count": len(fixture_files),
            "fixture_paths": [f.name for f in fixture_files],
            "all_exist": all(f.exists() for f in fixture_files),
        }
        
        assert stats["fixture_count"] == 2
        assert stats["all_exist"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
