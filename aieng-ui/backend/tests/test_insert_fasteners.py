"""Tests for cad.insert_fasteners MCP/runtime integration."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.app_factory import create_app
from app.cad_generation import insert_fasteners
from app.config import Settings
from app.main import default_project, save_project
from app.project_io import get_project, project_dir, resolve_project_path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def _make_settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=_WORKSPACE_ROOT / "aieng",
        sample_step=workspace / "sample.step",
    )


def _make_project(settings: Settings, name: str) -> str:
    project = save_project(settings, default_project(name))
    return project["id"]


def _attach_package(settings: Settings, project_id: str, package_path: Path) -> None:
    """Create the packages folder and point project metadata at the .aieng file."""
    from app.project_io import metadata_path, write_json

    project = get_project(settings, project_id)
    rel = str(package_path.relative_to(project_dir(settings, project_id))).replace("\\", "/")
    project["aieng_file"] = rel
    project["status"] = "viewer_ready_glb"
    write_json(metadata_path(settings, project_id), project)


def _build_test_package(package_path: Path, hole_diameter: float = 6.5) -> dict[str, Any]:
    """Create a minimal .aieng package with one mounting_hole feature."""
    manifest = {
        "format_version": "0.1.0",
        "resources": {
            "graph": {"feature_graph": "graph/feature_graph.json"},
        },
    }
    feature_graph = {
        "format_version": "0.1.0",
        "features": [
            {
                "id": "feat_hole_001",
                "type": "mounting_hole",
                "name": "mounting hole 1",
                "geometry_refs": ["face_001"],
                "hole_metadata": {
                    "diameter_mm": hole_diameter,
                    "through": True,
                    "axis": {
                        "origin_mm": [10.0, 10.0, 0.0],
                        "direction": [0.0, 0.0, 1.0],
                    },
                    "mating_stack": {"status": "known", "thickness_mm": 20.0},
                },
            }
        ],
    }
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("graph/feature_graph.json", json.dumps(feature_graph, indent=2))
    return feature_graph


def _load_package_json(package_path: Path, name: str) -> Any:
    with zipfile.ZipFile(package_path, "r") as zf:
        return json.loads(zf.read(name).decode("utf-8"))


@pytest.fixture
def client():
    # create_app registers runtime tools; TestClient lets us exercise the API if needed.
    return create_app()


def test_insert_fasteners_explicit_hole(tmp_path: Path):
    settings = _make_settings(tmp_path)
    project_id = _make_project(settings, "fastener-test")
    package_path = project_dir(settings, project_id) / "packages" / "test.aieng"
    _build_test_package(package_path)
    _attach_package(settings, project_id, package_path)

    result = insert_fasteners(
        settings,
        project_id,
        {"hole_feature_ids": ["feat_hole_001"]},
    )

    assert result["status"] == "ok"
    assert result["project_id"] == project_id
    assert result["inserted_count"] == 2  # screw + nut
    assert len(result["blockers"]) == 0

    fg = _load_package_json(package_path, "graph/feature_graph.json")
    feature_types = {f.get("type") for f in fg.get("features", [])}
    assert "standard_part" in feature_types

    report = _load_package_json(package_path, "graph/fastener_insertion_report.json")
    assert report["status"] == "ok"
    assert report["inserted_count"] == 2


def test_insert_fasteners_auto_select(tmp_path: Path):
    settings = _make_settings(tmp_path)
    project_id = _make_project(settings, "fastener-auto")
    package_path = project_dir(settings, project_id) / "packages" / "test.aieng"
    _build_test_package(package_path)
    _attach_package(settings, project_id, package_path)

    result = insert_fasteners(
        settings,
        project_id,
        {"auto_select_holes": True},
    )

    assert result["status"] == "ok"
    assert result["inserted_count"] == 2


def test_insert_fasteners_missing_hole_ids(tmp_path: Path):
    settings = _make_settings(tmp_path)
    project_id = _make_project(settings, "fastener-missing")
    package_path = project_dir(settings, project_id) / "packages" / "test.aieng"
    _build_test_package(package_path)
    _attach_package(settings, project_id, package_path)

    result = insert_fasteners(settings, project_id, {})
    assert result["status"] == "error"
    assert result["code"] == "missing_hole_feature_ids"


def test_insert_fasteners_unknown_feature(tmp_path: Path):
    settings = _make_settings(tmp_path)
    project_id = _make_project(settings, "fastener-unknown")
    package_path = project_dir(settings, project_id) / "packages" / "test.aieng"
    _build_test_package(package_path)
    _attach_package(settings, project_id, package_path)

    result = insert_fasteners(
        settings,
        project_id,
        {"hole_feature_ids": ["feat_missing"]},
    )
    assert result["status"] == "blocked"
    assert result["inserted_count"] == 0
    assert any(b.get("code") == "feature_not_found" for b in result["blockers"])
