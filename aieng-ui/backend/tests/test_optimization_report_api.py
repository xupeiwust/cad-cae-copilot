"""REST integration coverage for Issue #43 optimization summary report."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.main import create_app, default_project, project_dir, save_project
from starlette.testclient import TestClient
from test_api import _make_patch_settings


def _seed_full_study_package(settings, project_id: str) -> Path:
    package_path = project_dir(settings, project_id) / "study.aieng"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    baseline = {"representation": "brep_build123d", "parts": [{"id": "base"}]}
    problem = {
        "format": "aieng.design_study_problem", "schema_version": "0.1", "id": "study_001",
        "objective": {"sense": "minimize", "metric": "mass"},
        "variables": [{"id": "wall_t", "type": "continuous", "current_value": 3.0,
                       "min_value": 2.0, "max_value": 8.0, "safe_to_modify": True}],
    }
    ranking = {
        "format": "aieng.design_study.candidate_ranking.v0", "status": "ranked",
        "objective": {"sense": "minimize", "metric": "mass"},
        "best_candidate_id": "cand_good", "safe_to_accept": True, "next_action": "accept_candidate",
        "candidates": [
            {"rank": 1, "candidate_id": "cand_good", "feasibility": "feasible", "confidence": "high",
             "score": 0.2, "recommendation": "accept_candidate", "metrics_used": {"mass_kg": 0.8},
             "constraint_violations": [], "objective_delta": {}, "reasons": []},
        ],
    }
    iterations = {
        "format": "aieng.design_study_iterations", "schema_version": "0.1",
        "iterations": [{"candidate_id": "cand_good", "execution_status": "evaluation_complete",
                        "metrics": {"mass_kg": 0.8}}],
    }
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", "{}")
        package.writestr("geometry/shape_ir.json", json.dumps(baseline))
        package.writestr("analysis/design_study_problem.json", json.dumps(problem))
        package.writestr("analysis/design_study_candidate_ranking.json", json.dumps(ranking))
        package.writestr("analysis/design_study_iterations.json", json.dumps(iterations))
        package.writestr("candidates/cand_good/patch.json", json.dumps({"candidate_id": "cand_good"}))
        package.writestr("candidates/cand_good/analysis/evaluation.json",
                         json.dumps({"candidate_id": "cand_good", "feasibility": "feasible",
                                     "metrics": {"mass_kg": 0.8, "max_stress": 150.0}}))
    return package_path


def test_report_endpoint_aggregates_study(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("report"))
    project_id = project["id"]
    package_path = _seed_full_study_package(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    with zipfile.ZipFile(package_path) as package:
        baseline_before = json.loads(package.read("geometry/shape_ir.json"))

    response = client.post(f"/api/projects/{project_id}/design-study/report", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["candidate_count"] == 1
    assert body["best_candidate_id"] == "cand_good"
    assert body["baseline_modified"] is False

    with zipfile.ZipFile(package_path) as package:
        assert "diagnostics/optimization_report.json" in package.namelist()
        doc = json.loads(package.read("diagnostics/optimization_report.json"))
        assert json.loads(package.read("geometry/shape_ir.json")) == baseline_before
    assert doc["problem"]["id"] == "study_001"
    assert doc["candidates"][0]["metrics"]["max_stress"] == 150.0
    assert doc["honesty"]["report_is_reconstructable_from_artifacts"] is True


def test_report_endpoint_no_study_insufficient(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("report-empty"))
    project_id = project["id"]
    package_path = project_dir(settings, project_id) / "study.aieng"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", "{}")
        package.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    response = client.post(f"/api/projects/{project_id}/design-study/report", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_data"
