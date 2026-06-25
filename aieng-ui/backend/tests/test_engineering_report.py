"""Tests for the self-contained engineering report export (#372)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app, default_project, project_dir, save_project

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


def _make_project(settings: Settings) -> tuple[str, Path]:
    project = save_project(settings, default_project("engineering-report"))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / "report.aieng"
    project["aieng_file"] = "report.aieng"
    save_project(settings, project)
    return project_id, pkg_path


def _write_report_package(pkg_path: Path) -> None:
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    feature_graph = {
        "format_version": "0.1.0",
        "features": [
            {
                "id": "feat_bracket",
                "type": "solid",
                "name": "machined_bracket",
                "canonical_type": "bracket",
                "material": "Aluminium 6061-T6",
                "parameters": {},
            },
            {
                "id": "feat_bolt_1",
                "type": "standard_part",
                "name": "mounting_bolt_M6",
                "canonical_type": "screw",
                "designation": "M6-1",
                "source_library": "bd_warehouse",
                "parameters": {},
            },
        ],
    }
    targets = {
        "schema_version": "0.1",
        "targets": [
            {
                "target_id": "stress_pass",
                "label": "Stress below yield",
                "metric": "max_von_mises_stress",
                "operator": "<=",
                "value": 200,
                "unit": "MPa",
            }
        ],
    }
    metrics = {
        "schema_version": "0.1",
        "load_cases": [
            {
                "load_case_id": "lc1",
                "metrics": {
                    "max_von_mises_stress": {"value": 87.4, "unit": "MPa"},
                    "max_displacement": {"value": 0.42, "unit": "mm"},
                },
            }
        ],
    }
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "report-test", "resources": {}}))
        zf.writestr("graph/feature_graph.json", json.dumps(feature_graph))
        zf.writestr(
            "geometry/topology_map.json",
            json.dumps({
                "format_version": "0.1",
                "entities": [
                    {"id": "body_001", "type": "solid", "name": "machined_bracket"},
                    {"id": "face_001", "type": "face"},
                ],
            }),
        )
        zf.writestr("geometry/generated.step", "")
        zf.writestr("task/design_targets.yaml", yaml.safe_dump(targets, sort_keys=False))
        zf.writestr("results/computed_metrics.json", json.dumps(metrics))
        zf.writestr("simulation/runs/run_001/solver_input.inp", "*HEADING\nreport fixture\n")
        zf.writestr("simulation/runs/run_001/solver_run.json", json.dumps({"status": "completed", "return_code": 0}))
        zf.writestr("simulation/runs/run_001/result.frd", "")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_engineering_report_endpoint_returns_self_contained_html_read_only(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg_path = _make_project(settings)
    _write_report_package(pkg_path)
    before = _digest(pkg_path)

    response = client.get(f"/api/projects/{project_id}/report")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert _digest(pkg_path) == before
    html = response.text
    assert "<!doctype html>" in html
    assert "Engineering Report" in html
    assert "Honesty Boundary" in html
    assert "does not certify design safety" in html
    assert "Credibility Stamp" in html
    assert "max_von_mises_stress" in html
    assert "87.4" in html
    assert "mounting_bolt_M6" in html
    assert "claim advancement" in html.lower()


def test_report_generate_runtime_tool_returns_html_without_claim_advancement(tmp_path: Path) -> None:
    from app import runtime as _rt

    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg_path = _make_project(settings)
    _write_report_package(pkg_path)

    original_build = _rt.build_plan
    _rt.build_plan = lambda _msg, pid: [
        {"name": "report.generate", "description": "engineering report", "input": {"project_id": pid}}
    ]
    try:
        response = client.post(
            "/api/runtime/runs",
            json={
                "message": "generate engineering report",
                "project_id": project_id,
                "tool_input": {"project_id": project_id},
            },
        )
    finally:
        _rt.build_plan = original_build

    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "completed"
    output = run["tool_results"][0]["output"]
    assert output["ok"] is True
    assert output["tool"] == "report.generate"
    assert output["claim_advancement"] == "none"
    assert output["credibility_summary"]["result_evidence"] == "present"
    assert "Engineering Report" in output["html"]


def test_report_generate_tool_is_registered() -> None:
    from app.runtime import registered_tools_info

    tools = {tool["name"]: tool for tool in registered_tools_info()}
    assert "report.generate" in tools
    assert "Read-only" in tools["report.generate"]["description"]
