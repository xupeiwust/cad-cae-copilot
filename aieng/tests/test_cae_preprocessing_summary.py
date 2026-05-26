"""Tests for cae_preprocessing_summary."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from aieng.cae_preprocessing_summary import (
    generate_preprocessing_summary,
    generate_preprocessing_markdown,
    write_preprocessing_summary_package,
)
from aieng.schema_versions import CAE_PREPROCESSING_SUMMARY_SCHEMA


def _build_package(tmp_path: Path, members: dict[str, bytes]) -> Path:
    pkg = tmp_path / "test.aieng"
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test", "resources": {}}))
        for name, data in members.items():
            zf.writestr(name, data)
    return pkg


class TestGeneratePreprocessingSummary:
    def test_cad_only_package(self, tmp_path: Path) -> None:
        pkg = _build_package(tmp_path, {})
        result = generate_preprocessing_summary(pkg)
        assert result["schema_version"] == CAE_PREPROCESSING_SUMMARY_SCHEMA
        assert result["summary_type"] == "cae_preprocessing"
        assert result["status"]["ready_for_solver"] is False
        assert result["status"]["has_cae_setup"] is False
        assert "materials" in result["status"]["missing_items"]
        assert result["llm_summary"]["one_line"].startswith("No CAE pre-processing")

    def test_complete_setup_package(self, tmp_path: Path) -> None:
        members = {
            "graph/constraints.json": json.dumps({"constraints": [{"id": "c1"}]}).encode(),
            "simulation/cae_imports/parsed_materials.json": json.dumps({"materials": [{"name": "Steel"}]}).encode(),
            "simulation/cae_imports/parsed_boundary_conditions.json": json.dumps({"boundary_conditions": [{"id": "bc1"}]}).encode(),
            "simulation/cae_imports/parsed_loads.json": json.dumps({"loads": [{"id": "l1"}]}).encode(),
            "simulation/cae_mapping.json": json.dumps({"mapping": {}}).encode(),
            "simulation/mesh/mesh_metadata.json": json.dumps({"elements": 1000}).encode(),
            "simulation/solver_settings.json": json.dumps({"solver_type": "CalculiX"}).encode(),
            "simulation/load_cases/load_case_001.json": json.dumps({"id": "lc1", "name": "Force", "type": "force"}).encode(),
        }
        pkg = _build_package(tmp_path, members)
        result = generate_preprocessing_summary(pkg)
        assert result["status"]["ready_for_solver"] is True
        assert result["status"]["has_materials"] is True
        assert result["status"]["has_loads"] is True
        assert result["status"]["has_boundary_conditions"] is True
        assert result["status"]["has_constraints"] is True
        assert result["status"]["has_mesh"] is True
        assert result["status"]["has_solver_settings"] is True
        assert result["status"]["has_load_cases"] is True
        assert result["status"]["has_cae_mapping"] is True
        assert result["status"]["missing_items"] == []
        assert "ready for external solver" in result["llm_summary"]["one_line"]

    def test_partial_setup_package(self, tmp_path: Path) -> None:
        members = {
            "simulation/cae_imports/parsed_materials.json": json.dumps({"materials": [{"name": "Steel"}]}).encode(),
            "simulation/cae_imports/parsed_loads.json": json.dumps({"loads": [{"id": "l1"}]}).encode(),
        }
        pkg = _build_package(tmp_path, members)
        result = generate_preprocessing_summary(pkg)
        assert result["status"]["ready_for_solver"] is False
        assert result["status"]["has_materials"] is True
        assert result["status"]["has_loads"] is True
        assert result["status"]["has_boundary_conditions"] is False
        assert "boundary_conditions" in result["status"]["missing_items"]
        assert "mesh" in result["status"]["missing_items"]

    def test_mesh_detection_vtu_and_vtk(self, tmp_path: Path) -> None:
        pkg = _build_package(tmp_path, {"simulation/mesh/model.vtu": b"<xml/>"})
        result = generate_preprocessing_summary(pkg)
        assert result["status"]["has_mesh"] is True

    def test_load_case_detection(self, tmp_path: Path) -> None:
        members = {
            "simulation/load_cases/load_case_001.json": json.dumps({"id": "lc1", "name": "Force"}).encode(),
            "simulation/load_cases/load_case_002.json": json.dumps({"id": "lc2", "name": "Pressure"}).encode(),
        }
        pkg = _build_package(tmp_path, members)
        result = generate_preprocessing_summary(pkg)
        assert result["status"]["has_load_cases"] is True
        assert len(result["artifacts"]["load_cases"]) == 2

    def test_malformed_json_adds_warning(self, tmp_path: Path) -> None:
        members = {
            "simulation/solver_settings.json": b"not json",
            "simulation/mesh/mesh_metadata.json": b"{bad",
        }
        pkg = _build_package(tmp_path, members)
        result = generate_preprocessing_summary(pkg)
        warnings = result["status"]["warnings"]
        assert any("solver_settings.json is malformed" in w for w in warnings)
        assert any("mesh_metadata.json is malformed" in w for w in warnings)
        assert result["artifacts"]["solver_settings"] is None
        assert result["artifacts"]["mesh_metadata"] is None

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            generate_preprocessing_summary(tmp_path / "missing.aieng")


class TestGeneratePreprocessingMarkdown:
    def test_includes_status_sections(self, tmp_path: Path) -> None:
        members = {
            "simulation/cae_imports/parsed_materials.json": json.dumps({"materials": [{"name": "Steel"}]}).encode(),
            "simulation/solver_settings.json": json.dumps({"solver_type": "CalculiX"}).encode(),
        }
        pkg = _build_package(tmp_path, members)
        summary = generate_preprocessing_summary(pkg)
        md = generate_preprocessing_markdown(summary)
        assert "# CAE Pre-processing Summary" in md
        assert "## Setup Status" in md
        assert "## Missing items" in md
        assert "## Limitations" in md
        assert "Materials:** present" in md
        assert "Solver settings:** present" in md
        assert "This summary is based on package artifact presence only." in md

    def test_ready_for_solver_shows_yes(self, tmp_path: Path) -> None:
        members = {
            "simulation/cae_imports/parsed_materials.json": json.dumps({"materials": [{"name": "Steel"}]}).encode(),
            "simulation/cae_imports/parsed_boundary_conditions.json": json.dumps({"boundary_conditions": [{"id": "bc1"}]}).encode(),
            "simulation/cae_imports/parsed_loads.json": json.dumps({"loads": [{"id": "l1"}]}).encode(),
            "simulation/mesh/mesh_metadata.json": json.dumps({"elements": 1000}).encode(),
            "simulation/solver_settings.json": json.dumps({"solver_type": "CalculiX"}).encode(),
        }
        pkg = _build_package(tmp_path, members)
        summary = generate_preprocessing_summary(pkg)
        md = generate_preprocessing_markdown(summary)
        assert "Ready for solver:** yes" in md


class TestWritePreprocessingSummaryPackage:
    def test_writes_both_files(self, tmp_path: Path) -> None:
        pkg = _build_package(tmp_path, {})
        write_preprocessing_summary_package(pkg, overwrite=True)
        with zipfile.ZipFile(pkg, "r") as zf:
            names = set(zf.namelist())
            assert "simulation/preprocessing_summary.json" in names
            assert "simulation/preprocessing_summary.md" in names
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["resources"]["simulation"]["preprocessing_summary"] == "simulation/preprocessing_summary.json"

    def test_preserves_unrelated_entries(self, tmp_path: Path) -> None:
        pkg = _build_package(tmp_path, {"other.txt": b"keep me"})
        write_preprocessing_summary_package(pkg, overwrite=True)
        with zipfile.ZipFile(pkg, "r") as zf:
            assert "other.txt" in zf.namelist()
            assert zf.read("other.txt") == b"keep me"

    def test_refuses_overwrite_by_default(self, tmp_path: Path) -> None:
        pkg = _build_package(tmp_path, {"simulation/preprocessing_summary.json": b"old"})
        with pytest.raises(FileExistsError):
            write_preprocessing_summary_package(pkg, overwrite=False)

    def test_allows_overwrite(self, tmp_path: Path) -> None:
        pkg = _build_package(tmp_path, {"simulation/preprocessing_summary.json": b"old"})
        write_preprocessing_summary_package(pkg, overwrite=True)
        with zipfile.ZipFile(pkg, "r") as zf:
            data = zf.read("simulation/preprocessing_summary.json").decode()
            assert "old" not in data
            assert "schema_version" in data

    def test_no_duplicate_zip_entries(self, tmp_path: Path) -> None:
        pkg = _build_package(tmp_path, {"simulation/preprocessing_summary.json": b"old"})
        write_preprocessing_summary_package(pkg, overwrite=True)
        with zipfile.ZipFile(pkg, "r") as zf:
            names = zf.namelist()
            assert names.count("simulation/preprocessing_summary.json") == 1
            assert names.count("simulation/preprocessing_summary.md") == 1
