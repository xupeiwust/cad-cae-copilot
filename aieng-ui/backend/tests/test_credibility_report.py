"""Tests for the project credibility report endpoint (#310)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from app.main import Settings, create_app, default_project, project_dir, save_project

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


def _make_solved_package(pkg_path: Path) -> None:
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    targets = [
        {
            "target_id": "stress_pass",
            "label": "Stress pass",
            "metric": "max_von_mises_stress",
            "operator": "<=",
            "value": 200,
            "unit": "MPa",
        }
    ]
    metrics = {
        "schema_version": "0.1",
        "load_cases": [
            {
                "load_case_id": "lc1",
                "metrics": {
                    "max_von_mises_stress": {"value": 187.4, "unit": "MPa"},
                    "max_displacement": {"value": 0.82, "unit": "mm"},
                },
            }
        ],
    }
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test", "resources": {}}))
        zf.writestr("geometry/generated.step", "")
        zf.writestr(
            "geometry/topology_map.json",
            json.dumps({
                "format_version": "0.1",
                "entities": [
                    {"id": "body_001", "type": "solid", "name": "bracket"},
                    {"id": "face_001", "type": "face"},
                    {"id": "edge_001", "type": "edge"},
                ],
            }),
        )
        zf.writestr("graph/feature_graph.json", json.dumps({"features": []}))
        zf.writestr(
            "task/design_targets.yaml",
            yaml.safe_dump({"schema_version": "0.1", "targets": targets}, sort_keys=False),
        )
        zf.writestr("results/computed_metrics.json", json.dumps(metrics))
        zf.writestr("simulation/runs/run_001/solver_input.inp", "*Solver input\n")
        zf.writestr("simulation/runs/run_001/solver_run.json", json.dumps({"status": "completed"}))
        zf.writestr("simulation/runs/run_001/result.frd", "")


def _make_cad_only_package(pkg_path: Path) -> None:
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test", "resources": {}}))
        zf.writestr("geometry/generated.step", "")
        zf.writestr(
            "geometry/topology_map.json",
            json.dumps({
                "format_version": "0.1",
                "entities": [
                    {"id": "body_001", "type": "solid", "name": "bracket"},
                    {"id": "face_001", "type": "face"},
                    {"id": "edge_001", "type": "edge"},
                ],
            }),
        )
        zf.writestr("graph/feature_graph.json", json.dumps({"features": []}))


def _make_partial_geometry_package(pkg_path: Path) -> None:
    """Geometry is partial (only topology map), but results and targets exist."""
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    targets = [
        {
            "target_id": "stress_pass",
            "label": "Stress pass",
            "metric": "max_von_mises_stress",
            "operator": "<=",
            "value": 200,
            "unit": "MPa",
        }
    ]
    metrics = {
        "schema_version": "0.1",
        "global_metrics": {
            "max_von_mises_stress": {"value": 150.0, "unit": "MPa"},
        },
    }
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test", "resources": {}}))
        zf.writestr(
            "geometry/topology_map.json",
            json.dumps({
                "format_version": "0.1",
                "entities": [
                    {"id": "body_001", "type": "solid", "name": "bracket"},
                    {"id": "face_001", "type": "face"},
                ],
            }),
        )
        zf.writestr(
            "task/design_targets.yaml",
            yaml.safe_dump({"schema_version": "0.1", "targets": targets}, sort_keys=False),
        )
        zf.writestr("results/computed_metrics.json", json.dumps(metrics))


def _client_with_package(
    tmp_path: Path,
    pkg_builder: Any,
    *,
    assumptions: list[str] | None = None,
) -> tuple[TestClient, str, Path]:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("credibility-report"))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / "test.aieng"
    pkg_builder(pkg_path)
    project["aieng_file"] = "test.aieng"
    save_project(settings, project)
    if assumptions is not None:
        brief_path = project_dir(settings, project_id) / "cad_brief.json"
        brief_path.write_text(json.dumps({"assumptions": assumptions}), encoding="utf-8")
    return client, project_id, pkg_path


def test_credibility_report_for_solved_design_study(tmp_path: Path) -> None:
    assumptions = ["Linear elastic material behavior assumed."]
    client, project_id, pkg = _client_with_package(
        tmp_path, _make_solved_package, assumptions=assumptions
    )

    before = hashlib.sha256(pkg.read_bytes()).hexdigest()
    resp = client.get(f"/api/projects/{project_id}/reports/credibility")
    after = hashlib.sha256(pkg.read_bytes()).hexdigest()

    assert resp.status_code == 200, resp.text
    assert before == after, "Credibility report must not mutate the package"
    body = resp.json()

    assert body["project_id"] == project_id
    assert body["claim_advancement"] == "none"
    assert body["summary"]["overall"] == "pass"
    assert body["summary"]["geometry_evidence"] == "present"
    assert body["summary"]["cae_evidence"] == "present"
    assert body["summary"]["result_evidence"] == "present"
    assert body["summary"]["design_targets"] == "pass"

    geometry = body["geometry_evidence"]
    assert geometry["has_geometry"] is True
    assert geometry["has_topology_map"] is True
    assert geometry["has_feature_graph"] is True
    assert geometry["part_count"] == 1
    assert geometry["named_parts"] == ["bracket"]

    cae = body["cae_evidence"]
    assert cae["has_solver_input"] is True
    assert cae["has_solver_run"] is True
    assert cae["has_frd_output"] is True

    result = body["result_evidence"]
    assert result["has_computed_metrics"] is True
    assert result["key_results"]["max_von_mises_stress"]["value"] == 187.4
    assert result["key_results"]["max_displacement"]["value"] == 0.82

    design = body["design_targets"]
    assert design["summary"]["total"] == 1
    assert design["summary"]["pass"] == 1
    assert design["items"][0]["status"] == "pass"

    assert body["assumptions"] == assumptions
    assert "No authored CAD brief assumptions." not in body["missing_evidence"]


def test_credibility_report_for_cad_only_project(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_with_package(tmp_path, _make_cad_only_package)

    resp = client.get(f"/api/projects/{project_id}/reports/credibility")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["summary"]["overall"] == "partial"
    assert body["summary"]["geometry_evidence"] == "present"
    assert body["summary"]["cae_evidence"] == "missing"
    assert body["summary"]["result_evidence"] == "missing"
    assert body["summary"]["design_targets"] == "not_evaluated"

    cae = body["cae_evidence"]
    assert cae["status"] == "missing"
    assert cae["has_solver_input"] is False
    assert cae["has_solver_run"] is False
    assert cae["has_frd_output"] is False

    result = body["result_evidence"]
    assert result["status"] == "missing"
    assert result["has_computed_metrics"] is False

    missing = body["missing_evidence"]
    assert any("CAE solver-run evidence" in m for m in missing)
    assert any("Computed result evidence" in m for m in missing)
    assert any("design targets" in m.lower() for m in missing)
    assert any("assumptions" in m.lower() for m in missing)


def test_partial_geometry_rolls_up_to_partial_overall(tmp_path: Path) -> None:
    """A partial geometry tier must roll up to overall 'partial', not 'unknown'."""
    client, project_id, _pkg = _client_with_package(
        tmp_path, _make_partial_geometry_package
    )

    resp = client.get(f"/api/projects/{project_id}/reports/credibility")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["summary"]["geometry_evidence"] == "partial"
    assert body["summary"]["result_evidence"] == "present"
    assert body["summary"]["design_targets"] == "pass"
    assert body["summary"]["overall"] == "partial"


def test_credibility_report_returns_404_for_missing_project(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))

    resp = client.get("/api/projects/nonexistent-project/reports/credibility")

    assert resp.status_code == 404
