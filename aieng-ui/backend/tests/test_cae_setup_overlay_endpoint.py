"""Tests for the CAE setup overlay endpoint."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app, default_project, project_dir, project_relpath, save_project

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


def _make_package(path: Path, setup: dict[str, object], topo: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"version": "0.1.0"}))
        zf.writestr("simulation/setup.yaml", yaml.safe_dump(setup))
        zf.writestr("geometry/topology_map.json", json.dumps(topo))


def test_cae_setup_overlay_returns_loads_and_constraints(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    project = save_project(settings, default_project("cae-overlay"))
    project_id = project["id"]
    pkg = project_dir(settings, project_id) / "packages" / "part.aieng"

    setup = {
        "schema_version": "0.1",
        "analysis_type": "static_structural",
        "boundary_conditions": [
            {
                "id": "bc_001",
                "type": "fixed",
                "target_feature": "feat_hole",
                "target_pointers": ["@face:face_003"],
                "target_face_ids": ["face_003"],
            },
        ],
        "loads": [
            {
                "id": "load_001",
                "type": "force",
                "target_feature": "feat_base",
                "target_pointers": ["@face:face_002"],
                "target_face_ids": ["face_002"],
                "value_n": 500.0,
                "direction": [0.0, 0.0, -1.0],
            },
        ],
    }
    topo = {
        "entities": [
            {"id": "face_002", "type": "face", "center": [10.0, 20.0, 30.0], "normal": [0.0, 0.0, 1.0], "surface_type": "plane"},
            {"id": "face_003", "type": "face", "center": [0.0, 0.0, 0.0], "normal": [0.0, 1.0, 0.0], "surface_type": "plane"},
        ]
    }
    _make_package(pkg, setup, topo)
    project["aieng_file"] = project_relpath(settings, project_id, pkg)
    save_project(settings, project)

    response = client.get(f"/api/projects/{project_id}/cae-setup-overlay")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert len(data["loads"]) == 1
    assert data["loads"][0]["value_n"] == 500.0
    assert data["loads"][0]["faces"][0]["face_id"] == "face_002"
    assert len(data["constraints"]) == 1
    assert data["constraints"][0]["faces"][0]["face_id"] == "face_003"


def test_cae_setup_overlay_missing_setup(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    project = save_project(settings, default_project("no-setup"))
    project_id = project["id"]
    pkg = project_dir(settings, project_id) / "packages" / "part.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"version": "0.1.0"}))
    project["aieng_file"] = project_relpath(settings, project_id, pkg)
    save_project(settings, project)

    response = client.get(f"/api/projects/{project_id}/cae-setup-overlay")
    assert response.status_code == 200
    assert response.json()["available"] is False


def test_cae_setup_overlay_flags_stale_face(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    project = save_project(settings, default_project("stale-face"))
    project_id = project["id"]
    pkg = project_dir(settings, project_id) / "packages" / "part.aieng"

    setup = {
        "schema_version": "0.1",
        "loads": [
            {
                "id": "load_001",
                "type": "force",
                "target_pointers": ["@face:face_missing"],
                "target_face_ids": ["face_missing"],
                "value_n": 100.0,
                "direction": [0.0, 0.0, -1.0],
            },
        ],
    }
    topo = {"entities": []}
    _make_package(pkg, setup, topo)
    project["aieng_file"] = project_relpath(settings, project_id, pkg)
    save_project(settings, project)

    response = client.get(f"/api/projects/{project_id}/cae-setup-overlay")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["loads"][0]["faces"] == []
    assert any(ref.get("face_id") == "face_missing" for ref in data["stale_references"])
