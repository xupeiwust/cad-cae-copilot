from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from app import action_selector
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


def _make_project(settings: Settings, name: str, package: str | None) -> tuple[str, Path | None]:
    from app.main import default_project, project_dir, save_project

    project = save_project(settings, default_project(name))
    project_id = project["id"]
    pkg_path = None
    if package:
        pkg_path = project_dir(settings, project_id) / package
        project["aieng_file"] = package
        save_project(settings, project)
    return project_id, pkg_path


def _write_context_package(pkg: Path) -> None:
    fixture: dict[str, Any] = {
        "template_id": "cantilever_beam",
        "parameters": {
            "length_mm": 200.0,
            "width_mm": 20.0,
            "height_mm": 10.0,
            "material": "aluminum_6061_t6",
            "tip_load_N": 1200.0,
        },
        "geometry": {
            "geometry_kind": "cantilever_beam",
            "primitive": "rectangular_prism",
            "dimensions": {"length_mm": 200.0, "width_mm": 20.0, "height_mm": 10.0},
            "named_regions": [
                {"id": "fixed_root", "role": "fixed_support"},
                {"id": "tip_face", "role": "tip_load"},
            ],
            "material": {"id": "aluminum_6061_t6", "name": "Aluminum 6061-T6"},
        },
    }
    fea_setup = {
        "analysis_type": "linear_static",
        "material": {"name": "Aluminum 6061-T6"},
        "loads": [{"id": "tip_load", "region": "tip_face", "force_N": 1200.0}],
        "boundary_conditions": [{"id": "fixed_root", "region": "fixed_root", "type": "fixed"}],
    }
    targets = {
        "targets": [
            {
                "target_id": "stress_limit",
                "label": "Max stress",
                "metric": "max_von_mises_stress",
                "operator": "<=",
                "value": 150.0,
                "unit": "MPa",
            }
        ]
    }
    metrics = {
        "global_metrics": {
            "max_von_mises_stress": {"value": 172.5, "unit": "MPa", "source": "test"}
        },
        "load_cases": [],
    }

    pkg.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "agent-context-test"}))
        zf.writestr("geometry/template_cad_fixture.json", json.dumps(fixture))
        zf.writestr("task/fea_setup_draft.json", json.dumps(fea_setup))
        zf.writestr("task/design_targets.yaml", yaml.safe_dump(targets, sort_keys=False))
        zf.writestr("results/computed_metrics.json", json.dumps(metrics))


def test_agent_context_endpoint_returns_cad_cae_understanding_package(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "agent-context", "p.aieng")
    assert pkg is not None
    _write_context_package(pkg)

    resp = client.get(f"/api/projects/{project_id}/agent-context")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["schema_version"] == "0.1"
    assert body["project_id"] == project_id
    assert body["claim_advancement"] == "none"
    assert body["package"]["exists"] is True
    assert body["cad"]["geometry_evidence_level"] == "metadata"
    assert body["cad"]["known_geometry"]["geometry_kind"] == "cantilever_beam"
    assert body["cae"]["fea_setup_draft"]["analysis_type"] == "linear_static"
    assert body["design_targets"]["count"] == 1
    assert body["computed_metrics"]["metrics_count"] == 1
    assert body["agent_brief"]["next_decision_focus"]
    assert any(action["id"] for action in body["available_actions"])
    assert all(action["execution_policy"]["candidate_only"] for action in body["available_actions"])


def test_agent_context_endpoint_handles_project_without_package(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, _pkg = _make_project(settings, "no-package", None)

    resp = client.get(f"/api/projects/{project_id}/agent-context")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["package"]["exists"] is False
    assert body["cad"]["status"] == "missing"
    assert body["design_targets"]["count"] == 0
    assert body["computed_metrics"]["metrics_count"] == 0
    assert "obtain real CAD geometry or live CAD snapshot" in body["agent_brief"]["next_decision_focus"]


def test_agent_context_is_registered_as_runtime_tool_and_executes(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "rt-context", "p.aieng")
    assert pkg is not None
    _write_context_package(pkg)

    tools_resp = client.get("/api/runtime/tools")
    assert tools_resp.status_code == 200
    tools = {tool["name"]: tool for tool in tools_resp.json()}
    assert "aieng.agent_context" in tools
    assert tools["aieng.agent_context"]["requires_approval"] is False

    run_resp = client.post(
        "/api/runtime/runs",
        json={"message": "read the agent context", "project_id": project_id},
    )
    assert run_resp.status_code == 200, run_resp.text
    run = run_resp.json()
    assert any(call["name"] == "aieng.agent_context" for call in run["tool_calls"])
    context_call = next(call for call in run["tool_calls"] if call["name"] == "aieng.agent_context")
    context_result = next(result for result in run["tool_results"] if result["id"] == context_call["id"])
    assert context_result["status"] == "success"
    assert context_result["output"]["agent_brief"]["next_decision_focus"]

