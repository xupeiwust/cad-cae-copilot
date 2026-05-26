from __future__ import annotations

import zipfile

from aieng.cli import main
from aieng.geometry.step_importer import NORMALIZED_STEP_PATH, SOURCE_STEP_PATH, import_step_package
from aieng.package import PACKAGE_DIRECTORIES, read_manifest
from aieng.validate import validate_package


FAKE_STEP_CONTENT = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


def write_fake_step(path):
    path.write_bytes(FAKE_STEP_CONTENT)
    return path


def test_import_step_happy_path_copies_source_and_normalized(tmp_path):
    step_path = write_fake_step(tmp_path / "bracket.step")
    package_path = tmp_path / "bracket_001.aieng"

    import_step_package(step_path, package_path)

    with zipfile.ZipFile(package_path) as package:
        names = set(package.namelist())
        assert SOURCE_STEP_PATH in names
        assert NORMALIZED_STEP_PATH in names
        assert set(PACKAGE_DIRECTORIES).issubset(names)
        assert package.read(SOURCE_STEP_PATH) == FAKE_STEP_CONTENT
        assert package.read(NORMALIZED_STEP_PATH) == FAKE_STEP_CONTENT


def test_import_step_accepts_stp_extension(tmp_path):
    step_path = write_fake_step(tmp_path / "bracket.stp")
    package_path = tmp_path / "bracket_001.aieng"

    import_step_package(step_path, package_path)

    with zipfile.ZipFile(package_path) as package:
        assert package.read(SOURCE_STEP_PATH) == FAKE_STEP_CONTENT
        assert package.read(NORMALIZED_STEP_PATH) == FAKE_STEP_CONTENT


def test_import_step_missing_file_fails(tmp_path):
    missing_step = tmp_path / "missing.step"
    package_path = tmp_path / "bracket_001.aieng"

    try:
        import_step_package(missing_step, package_path)
    except FileNotFoundError as exc:
        assert "STEP file does not exist" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_import_step_invalid_extension_fails(tmp_path):
    bad_path = write_fake_step(tmp_path / "bracket.txt")
    package_path = tmp_path / "bracket_001.aieng"

    try:
        import_step_package(bad_path, package_path)
    except ValueError as exc:
        assert ".step or .stp" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_import_step_existing_output_fails_without_overwrite(tmp_path):
    step_path = write_fake_step(tmp_path / "bracket.step")
    package_path = tmp_path / "bracket_001.aieng"
    package_path.write_bytes(b"existing")

    try:
        import_step_package(step_path, package_path)
    except FileExistsError as exc:
        assert "package already exists" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")


def test_import_step_manifest_references_geometry_resources(tmp_path):
    step_path = write_fake_step(tmp_path / "bracket.step")
    package_path = tmp_path / "bracket_001.aieng"

    import_step_package(step_path, package_path)

    manifest = read_manifest(package_path)
    assert manifest["model_id"] == "bracket_001"
    assert manifest["resources"]["geometry"] == {
        "source": SOURCE_STEP_PATH,
        "normalized": NORMALIZED_STEP_PATH,
    }


def test_validate_passes_after_import_step(tmp_path):
    step_path = write_fake_step(tmp_path / "bracket.step")
    package_path = tmp_path / "bracket_001.aieng"

    import_step_package(step_path, package_path)
    report = validate_package(package_path)
    rendered = report.render()

    assert report.ok
    assert "PASS geometry/source.step exists" in rendered
    assert "PASS geometry/normalized.step exists" in rendered


def test_cli_import_step_happy_path_and_validate(tmp_path, capsys):
    step_path = write_fake_step(tmp_path / "bracket.step")
    package_path = tmp_path / "bracket_001.aieng"

    assert main(["import-step", str(step_path), "--out", str(package_path)]) == 0
    import_output = capsys.readouterr().out
    assert "PASS imported" in import_output
    assert "PASS geometry/source.step written" in import_output
    assert "PASS geometry/normalized.step written" in import_output
    assert "PASS import is evidence-only; no automatic claim status update performed" in import_output

    assert main(["validate", str(package_path)]) == 0
    validate_output = capsys.readouterr().out
    assert "PASS geometry/source.step exists" in validate_output
    assert "PASS geometry/normalized.step exists" in validate_output


def test_cli_import_step_missing_file_returns_failure(tmp_path, capsys):
    package_path = tmp_path / "bracket_001.aieng"

    assert main(["import-step", str(tmp_path / "missing.step"), "--out", str(package_path)]) == 2
    captured = capsys.readouterr()
    assert "FAIL STEP file does not exist" in captured.err


def test_cli_import_step_invalid_extension_returns_failure(tmp_path, capsys):
    bad_path = write_fake_step(tmp_path / "bracket.txt")
    package_path = tmp_path / "bracket_001.aieng"

    assert main(["import-step", str(bad_path), "--out", str(package_path)]) == 2
    captured = capsys.readouterr()
    assert "FAIL STEP file must have .step or .stp extension" in captured.err
