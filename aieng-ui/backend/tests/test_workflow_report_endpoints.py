"""Tests for the sizing-sweep + mesh-convergence report endpoints."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

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


def _make_minimal_package(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"version": "0.1.0"}))
        zf.writestr("graph/feature_graph.json", json.dumps({"features": []}))


def test_sizing_sweep_report_endpoint_returns_available(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    project = save_project(settings, default_project("sweep-report"))
    project_id = project["id"]
    pkg = project_dir(settings, project_id) / "packages" / "part.aieng"
    _make_minimal_package(pkg)
    project["aieng_file"] = project_relpath(settings, project_id, pkg)
    save_project(settings, project)

    # Write a report directly into the package.
    report = {"tool": "opt.sizing_sweep", "variants": [], "variant_count": 0}
    with zipfile.ZipFile(pkg, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("analysis/sizing_sweep_report.json", json.dumps(report))

    response = client.get(f"/api/projects/{project_id}/sizing-sweep-report")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["report"]["tool"] == "opt.sizing_sweep"


def test_sizing_sweep_report_endpoint_missing(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    project = save_project(settings, default_project("no-sweep-report"))
    project_id = project["id"]
    pkg = project_dir(settings, project_id) / "packages" / "part.aieng"
    _make_minimal_package(pkg)
    project["aieng_file"] = project_relpath(settings, project_id, pkg)
    save_project(settings, project)

    response = client.get(f"/api/projects/{project_id}/sizing-sweep-report")
    assert response.status_code == 200
    assert response.json()["available"] is False


def test_mesh_convergence_report_endpoint_returns_available(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    project = save_project(settings, default_project("mesh-report"))
    project_id = project["id"]
    pkg = project_dir(settings, project_id) / "packages" / "part.aieng"
    _make_minimal_package(pkg)
    project["aieng_file"] = project_relpath(settings, project_id, pkg)
    save_project(settings, project)

    report = {"tool": "cae.mesh_convergence", "overall_verdict": "converged"}
    with zipfile.ZipFile(pkg, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("analysis/mesh_convergence_report.json", json.dumps(report))

    response = client.get(f"/api/projects/{project_id}/mesh-convergence-report")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["report"]["overall_verdict"] == "converged"


def test_mesh_convergence_report_endpoint_no_package(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    project = save_project(settings, default_project("no-pkg"))
    response = client.get(f"/api/projects/{project['id']}/mesh-convergence-report")
    assert response.status_code == 200
    assert response.json()["available"] is False
