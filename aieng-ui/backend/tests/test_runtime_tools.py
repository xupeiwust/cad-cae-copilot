"""Tests for extracted runtime tool registrations.

Verifies that engineering_template.* and freecad.* wrapper tools are still
registered with the same approval semantics after the move from app_factory.py
to runtime_tools.py.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.config import Settings

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


def _make_project(settings: Settings, name: str, package: str) -> tuple[str, Path]:
    from app.main import default_project, project_dir, save_project

    project = save_project(settings, default_project(name))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / package
    project["aieng_file"] = package
    save_project(settings, project)
    return project_id, pkg_path


def _make_minimal_package(pkg: Path, *, extra_members: dict[str, bytes] | None = None) -> None:
    pkg.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "rt-test", "resources": {}}))
        for path, payload in (extra_members or {}).items():
            zf.writestr(path, payload)


_DEFAULT_SNAPSHOT: dict[str, Any] = {
    "source": "freecad_mcp",
    "captured_at": "2026-05-20T12:00:00Z",
    "document_name": "test",
    "generator": "test-suite",
    "object_count": 1,
    "objects": [],
    "named_regions": [],
    "topology_references": {},
    "warnings": [],
}


# ── registration smoke tests ────────────────────────────────────────────────


def test_engineering_template_tools_are_registered(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    tools = {t["name"]: t for t in client.get("/api/runtime/tools").json()}

    assert "engineering_template.preview" in tools
    assert tools["engineering_template.preview"]["requires_approval"] is False

    assert "engineering_template.save_draft" in tools
    assert tools["engineering_template.save_draft"]["requires_approval"] is True

    assert "engineering_template.adopt_targets" in tools
    assert tools["engineering_template.adopt_targets"]["requires_approval"] is True

    assert "engineering_template.generate_cad_fixture" in tools
    assert tools["engineering_template.generate_cad_fixture"]["requires_approval"] is True


def test_engineering_template_preview_is_read_only(tmp_path: Path) -> None:
    """Read-only engineering template tool should execute without approval."""
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "rt-preview", "p.aieng")
    _make_minimal_package(pkg)

    run = client.post(
        "/api/runtime/runs",
        json={
            "project_id": project_id,
            "steps": [
                {
                    "id": "preview1",
                    "tool_name": "engineering_template.preview",
                    "name": "engineering_template.preview",
                    "input": {"project_id": project_id, "template_id": "cantilever_beam"},
                    "approval_required": False,
                    "status": "pending",
                }
            ],
        },
    )
    assert run.status_code == 200, run.text
    run_dict = run.json()
    assert run_dict["status"] == "completed"
