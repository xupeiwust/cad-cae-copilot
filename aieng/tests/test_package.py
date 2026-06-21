from __future__ import annotations

import json
import zipfile

from aieng.package import PACKAGE_DIRECTORIES, build_manifest, create_package, read_manifest


def test_create_package_writes_manifest_and_empty_directories(tmp_path):
    package_path = tmp_path / "bracket_001.aieng"

    create_package("bracket_001", package_path)

    assert package_path.exists()
    with zipfile.ZipFile(package_path) as package:
        names = set(package.namelist())
    assert "manifest.json" in names
    assert set(PACKAGE_DIRECTORIES).issubset(names)

    manifest = read_manifest(package_path)
    assert manifest["model_id"] == "bracket_001"
    assert manifest["format_version"] == "0.1.0"
    assert manifest["units"] == {
        "length": "mm",
        "mass": "kg",
        "force": "N",
        "stress": "MPa",
    }


def test_create_package_rejects_non_aieng_extension(tmp_path):
    try:
        create_package("bracket_001", tmp_path / "bracket_001.zip")
    except ValueError as exc:
        assert "must end with .aieng" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_manifest_json_is_readable(tmp_path):
    package_path = tmp_path / "bracket_001.aieng"
    create_package("bracket_001", package_path)

    with zipfile.ZipFile(package_path) as package:
        manifest = json.loads(package.read("manifest.json"))

    assert manifest["resources"] == {
        "ai": {"patches": []},
        "geometry": {},
        "graph": {},
        "previews": {},
        "results": {},
        "simulation": {},
        "task": {},
    }


def test_build_manifest_resources_are_independent():
    first = build_manifest("first").to_dict()
    first["resources"]["ai"]["patches"].append("ai/patches/patch_0001.json")

    second = build_manifest("second").to_dict()

    assert second["resources"]["ai"]["patches"] == []
