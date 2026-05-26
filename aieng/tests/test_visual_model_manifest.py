"""Tests for Phase 8B: visual/model_manifest.json generation and validation."""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

from aieng.cli import main
from aieng.validate import validate_package
from aieng.visual.model_manifest_writer import (
    ANNOTATION_LAYERS_PATH,
    MODEL_MANIFEST_PATH,
    build_visual_manifest_package,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
STEP_PATH = EXAMPLES_DIR / "bracket.step"
CONTEXT_PATH = EXAMPLES_DIR / "bracket_user_context.yaml"


def _make_package_for_visual_manifest(tmp_path: Path, *, with_visual_index: bool = True) -> Path:
    pkg = tmp_path / "bracket_001.aieng"
    assert main(["import-step", str(STEP_PATH), "--out", str(pkg)]) == 0
    assert main(["extract-topology", str(pkg), "--overwrite", "--backend", "mock"]) == 0
    assert main(["recognize-features", str(pkg), "--overwrite"]) == 0
    assert main(["apply-context", str(pkg), "--context", str(CONTEXT_PATH), "--overwrite"]) == 0
    if with_visual_index:
        assert main(["build-visual-index", str(pkg), "--overwrite"]) == 0
    return pkg


def _read_json_member(pkg: Path, member: str) -> dict[str, Any]:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


def _tamper_model_manifest(pkg: Path, manifest_data: dict[str, Any]) -> None:
    with zipfile.ZipFile(pkg, mode="r") as zf:
        members = [
            (info, b"" if info.is_dir() else zf.read(info.filename))
            for info in zf.infolist()
            if info.filename != MODEL_MANIFEST_PATH
        ]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=pkg.parent) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with zipfile.ZipFile(tmp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for info, data in members:
                zf.writestr(info, data)
            zf.writestr(MODEL_MANIFEST_PATH, json.dumps(manifest_data, indent=2).encode())
        shutil.move(str(tmp_path), pkg)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_build_visual_manifest_happy_path_after_visual_index(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path, with_visual_index=True)
    result = build_visual_manifest_package(pkg)
    assert result == pkg

    data = _read_json_member(pkg, MODEL_MANIFEST_PATH)
    assert data["format"] == "aieng.visual_model_manifest"
    assert data["visual_resources"]["annotation_layers"]["status"] == "present"


def test_build_visual_manifest_works_without_annotation_layers(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path, with_visual_index=False)
    build_visual_manifest_package(pkg)
    data = _read_json_member(pkg, MODEL_MANIFEST_PATH)
    assert data["visual_resources"]["annotation_layers"]["status"] in {"missing", "not_generated"}


def test_build_visual_manifest_writes_model_manifest(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path)
    build_visual_manifest_package(pkg)
    with zipfile.ZipFile(pkg) as zf:
        assert MODEL_MANIFEST_PATH in zf.namelist()


def test_build_visual_manifest_updates_manifest_resources(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path)
    build_visual_manifest_package(pkg)
    manifest = _read_json_member(pkg, "manifest.json")
    assert manifest["resources"]["visual"]["model_manifest"] == MODEL_MANIFEST_PATH


def test_annotation_layers_status_present_when_file_exists(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path, with_visual_index=True)
    build_visual_manifest_package(pkg)
    data = _read_json_member(pkg, MODEL_MANIFEST_PATH)
    with zipfile.ZipFile(pkg) as zf:
        assert ANNOTATION_LAYERS_PATH in zf.namelist()
    assert data["visual_resources"]["annotation_layers"]["status"] == "present"


def test_model_gltf_status_not_generated(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path)
    build_visual_manifest_package(pkg)
    data = _read_json_member(pkg, MODEL_MANIFEST_PATH)
    assert data["visual_resources"]["model_gltf"]["status"] == "not_generated"


def test_rendering_status_flags_are_false(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path)
    build_visual_manifest_package(pkg)
    data = _read_json_member(pkg, MODEL_MANIFEST_PATH)
    assert data["rendering_status"]["rendered_geometry_present"] is False
    assert data["rendering_status"]["viewer_ready"] is False


def test_claim_policy_forbids_rendered_model_claims(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path)
    build_visual_manifest_package(pkg)
    data = _read_json_member(pkg, MODEL_MANIFEST_PATH)
    forbidden = [item.lower() for item in data["claim_policy"]["forbidden_claims"]]
    assert any("rendered 3d model" in claim for claim in forbidden)
    assert any("model.glb" in claim for claim in forbidden)


def test_validator_passes_after_visual_manifest_generation(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path)
    build_visual_manifest_package(pkg)
    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert not fails, f"Validation failures: {fails}"


def test_validator_fails_if_status_present_but_path_missing(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path, with_visual_index=False)
    build_visual_manifest_package(pkg)
    data = _read_json_member(pkg, MODEL_MANIFEST_PATH)
    data["visual_resources"]["annotation_layers"]["status"] = "present"
    _tamper_model_manifest(pkg, data)

    report = validate_package(pkg)
    fails = [m.text for m in report.messages if m.level.value == "FAIL"]
    assert any("marks annotation_layers as present" in t for t in fails)


def test_build_visual_manifest_does_not_overwrite_by_default(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path)
    build_visual_manifest_package(pkg)
    with pytest.raises(FileExistsError):
        build_visual_manifest_package(pkg)


def test_build_visual_manifest_overwrites_with_flag(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path)
    build_visual_manifest_package(pkg)
    result = build_visual_manifest_package(pkg, overwrite=True)
    assert result == pkg


def test_build_visual_manifest_cli_no_overwrite_returns_2(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path)
    assert main(["build-visual-manifest", str(pkg)]) == 0
    assert main(["build-visual-manifest", str(pkg)]) == 2


def test_build_visual_manifest_cli_overwrite_returns_0(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path)
    assert main(["build-visual-manifest", str(pkg)]) == 0
    assert main(["build-visual-manifest", str(pkg), "--overwrite"]) == 0


def test_summary_mentions_visual_model_manifest_when_present(tmp_path):
    pkg = _make_package_for_visual_manifest(tmp_path)
    assert main(["build-visual-manifest", str(pkg)]) == 0
    assert main(["summarize", str(pkg), "--overwrite"]) == 0

    with zipfile.ZipFile(pkg) as zf:
        readme = zf.read("README_FOR_AI.md").decode("utf-8")
        summary = zf.read("ai/summary.md").decode("utf-8")

    assert "visual/model_manifest.json" in readme
    assert "visual/model_manifest.json" in summary


def test_validation_status_records_visual_manifest_fields(tmp_path):
    import yaml

    pkg = _make_package_for_visual_manifest(tmp_path)
    assert main(["build-visual-manifest", str(pkg)]) == 0
    assert main(["update-validation-status", str(pkg), "--overwrite"]) == 0

    with zipfile.ZipFile(pkg) as zf:
        status = yaml.safe_load(zf.read("validation/status.yaml"))

    assert status["visual_status"]["visual_manifest_present"] is True
    assert status["visual_status"]["rendered_geometry_present"] is False
    assert status["visual_status"]["visual_rendering"] == "not_generated"
