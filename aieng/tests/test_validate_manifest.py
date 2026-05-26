from __future__ import annotations

import json
import zipfile

from aieng.cli import main
from aieng.package import create_package
from aieng.validate import validate_package


def test_validate_fresh_phase0_package_reports_passes_and_warnings(tmp_path):
    package_path = tmp_path / "bracket_001.aieng"
    create_package("bracket_001", package_path)

    report = validate_package(package_path)
    rendered = report.render()

    assert report.ok
    assert "PASS manifest.json exists" in rendered
    assert "PASS format_version = 0.1.0" in rendered
    assert "PASS units are present" in rendered
    assert "WARN geometry/source.step missing" in rendered


def test_validate_missing_manifest_fails(tmp_path):
    package_path = tmp_path / "broken.aieng"
    with zipfile.ZipFile(package_path, "w") as package:
        package.writestr("geometry/", b"")

    report = validate_package(package_path)

    assert not report.ok
    assert "FAIL manifest.json missing" in report.render()


def test_validate_invalid_manifest_schema_fails(tmp_path):
    package_path = tmp_path / "broken.aieng"
    manifest = {
        "model_id": "bracket_001",
        "format_version": "9.9.9",
        "units": {"length": "mm"},
        "resources": {},
        "created_by": {"tool": "test", "created_at": "2026-01-01T00:00:00Z"},
    }
    with zipfile.ZipFile(package_path, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))

    report = validate_package(package_path)
    rendered = report.render()

    assert not report.ok
    assert "unsupported format_version" in rendered
    assert "units are missing or incomplete" in rendered


def test_validate_manifest_resource_paths_must_exist(tmp_path):
    package_path = tmp_path / "broken.aieng"
    manifest = {
        "model_id": "bracket_001",
        "format_version": "0.1.0",
        "units": {"length": "mm", "mass": "kg", "force": "N", "stress": "MPa"},
        "resources": {"geometry": {"source": "geometry/source.step"}},
        "created_by": {"tool": "test", "created_at": "2026-01-01T00:00:00Z"},
    }
    with zipfile.ZipFile(package_path, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))

    report = validate_package(package_path)

    assert not report.ok
    assert "FAIL required resource geometry/source.step missing" in report.render()


def test_cli_init_and_validate(tmp_path, capsys):
    package_path = tmp_path / "bracket_001.aieng"

    assert main(["init", "--model-id", "bracket_001", "--out", str(package_path)]) == 0
    init_output = capsys.readouterr().out
    assert "PASS created" in init_output

    assert main(["validate", str(package_path)]) == 0
    validate_output = capsys.readouterr().out
    assert "PASS manifest.json exists" in validate_output
    assert "WARN geometry/source.step missing" in validate_output


def test_cli_validate_missing_package_returns_failure(tmp_path, capsys):
    missing_path = tmp_path / "missing.aieng"

    assert main(["validate", str(missing_path)]) == 1
    output = capsys.readouterr().out
    assert "FAIL package does not exist" in output
