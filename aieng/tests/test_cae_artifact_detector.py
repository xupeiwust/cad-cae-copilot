"""Tests for cae_artifact_detector."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from aieng.cae_artifact_detector import CAE_ARTIFACT_PATHS, detect_cae_artifacts


def _build_package(tmp_path: Path, members: dict[str, bytes]) -> Path:
    pkg = tmp_path / "test.aieng"
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test"}))
        for name, data in members.items():
            zf.writestr(name, data)
    return pkg


class TestDetectCaeArtifacts:
    def test_empty_package_is_cad_only(self, tmp_path: Path) -> None:
        pkg = _build_package(tmp_path, {})
        result = detect_cae_artifacts(pkg)
        assert result["mode"] == "cad_only"
        assert result["detected_count"] == 0
        assert result["total_count"] == len(CAE_ARTIFACT_PATHS)
        assert all(v is False for v in result["artifacts"].values())

    def test_cae_setup_detected(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {
                "graph/constraints.json": b"{}",
                "simulation/cae_imports/parsed_materials.json": b"[]",
                "simulation/cae_imports/parsed_boundary_conditions.json": b"[]",
                "simulation/cae_imports/parsed_loads.json": b"[]",
                "simulation/cae_mapping.json": b"{}",
            },
        )
        result = detect_cae_artifacts(pkg)
        assert result["mode"] == "cae_setup"
        assert result["has_cae_setup"] is True
        assert result["has_mesh"] is False
        assert result["has_results"] is False
        assert result["has_validation"] is False
        assert result["detected_count"] == 5

    def test_mesh_promotes_to_cae_setup(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {"simulation/mesh/model.vtu": b"<xml/>"},
        )
        result = detect_cae_artifacts(pkg)
        assert result["mode"] == "cae_setup"
        assert result["has_mesh"] is True

    def test_result_fields_detected(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {
                "results/fields/von_mises_stress.vtu": b"<xml/>",
                "results/fields/displacement.vtu": b"<xml/>",
            },
        )
        result = detect_cae_artifacts(pkg)
        assert result["mode"] == "cae_result"
        assert result["has_fields"] is True
        assert result["has_results"] is False  # evidence_index missing

    def test_evidence_index_detected(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {"results/evidence_index.json": b"[]"},
        )
        result = detect_cae_artifacts(pkg)
        assert result["mode"] == "cae_result"
        assert result["has_results"] is True

    def test_validation_promotes_to_cae_validation(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {
                "results/fields/safety_factor.vtu": b"<xml/>",
                "validation/status.yaml": b"status: ok",
            },
        )
        result = detect_cae_artifacts(pkg)
        assert result["mode"] == "cae_validation"
        assert result["has_validation"] is True
        assert result["has_fields"] is True

    def test_validation_alone_is_cae_validation(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {"validation/status.yaml": b"status: ok"},
        )
        result = detect_cae_artifacts(pkg)
        assert result["mode"] == "cae_validation"

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            detect_cae_artifacts(tmp_path / "missing.aieng")

    def test_all_artifacts_present(self, tmp_path: Path) -> None:
        members = {path: b"{}" for path in CAE_ARTIFACT_PATHS}
        pkg = _build_package(tmp_path, members)
        result = detect_cae_artifacts(pkg)
        assert result["mode"] == "cae_validation"
        assert result["detected_count"] == len(CAE_ARTIFACT_PATHS)
        assert all(result["artifacts"].values())
