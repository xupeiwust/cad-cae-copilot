"""REST integration coverage for Issue #40 batch candidate evaluation."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.main import create_app, default_project, project_dir, save_project
from starlette.testclient import TestClient
from test_api import _make_patch_settings


def _seed_executed_package(settings, project_id: str) -> Path:
    """Package with a problem + two executed candidate workspaces (static metrics).

    One candidate has the stress metric (complete/feasible), one is missing it
    (partial/unknown) — exercising the honest missing-metric path end-to-end.
    """
    package_path = project_dir(settings, project_id) / "study.aieng"
    package_path.parent.mkdir(parents=True, exist_ok=True)

    baseline = {"representation": "brep_build123d",
                "parts": [{"id": "base", "params": {"WALL_THICKNESS": 3.0}}]}
    problem = {
        "format": "aieng.design_study_problem",
        "schema_version": "0.1",
        "id": "source_001",
        "variables": [
            {"id": "wall_t", "path": "parts/0/params/WALL_THICKNESS", "type": "continuous",
             "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "unit": "mm",
             "safe_to_modify": True},
        ],
        "constraints": [{"id": "stress_limit", "type": "max_stress", "limit": 200.0, "unit": "MPa"}],
        "objective": {"metric": "mass", "sense": "minimize"},
        "settings": {"max_variables_per_candidate": 1, "require_reasoning": True},
    }
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", "{}")
        package.writestr("geometry/shape_ir.json", json.dumps(baseline))
        package.writestr("analysis/design_study_problem.json", json.dumps(problem))
        # executed workspaces
        package.writestr("candidates/cand_full/patch.json", json.dumps({"candidate_id": "cand_full"}))
        package.writestr("candidates/cand_full/geometry/shape_ir.json", json.dumps(baseline))
        package.writestr("candidates/cand_full/analysis/static_metrics.json",
                         json.dumps({"mass_kg": 1.0, "max_stress": 150.0}))
        package.writestr("candidates/cand_partial/patch.json", json.dumps({"candidate_id": "cand_partial"}))
        package.writestr("candidates/cand_partial/geometry/shape_ir.json", json.dumps(baseline))
        package.writestr("candidates/cand_partial/analysis/static_metrics.json",
                         json.dumps({"mass_kg": 1.0}))  # no stress -> unknown
    return package_path


def test_evaluate_candidates_batch_endpoint(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("batch-eval"))
    project_id = project["id"]
    package_path = _seed_executed_package(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    with zipfile.ZipFile(package_path) as package:
        baseline_before = json.loads(package.read("geometry/shape_ir.json"))

    response = client.post(f"/api/projects/{project_id}/design-study/evaluate-candidates", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["evaluated"] == 2
    assert body["complete"] == 1          # cand_full
    assert body["partial"] == 1           # cand_partial (missing stress)
    assert body["feasibility"].get("feasible") == 1
    assert body["feasibility"].get("unknown") == 1
    assert body["baseline_modified"] is False

    with zipfile.ZipFile(package_path) as package:
        # evaluation artifacts written per candidate; baseline untouched
        assert "candidates/cand_full/analysis/evaluation.json" in package.namelist()
        assert "candidates/cand_partial/analysis/evaluation.json" in package.namelist()
        ev_partial = json.loads(package.read("candidates/cand_partial/analysis/evaluation.json"))
        assert json.loads(package.read("geometry/shape_ir.json")) == baseline_before
    stress = [c for c in ev_partial["constraint_evidence"] if c.get("type") == "max_stress"][0]
    assert stress["status"] == "unknown"


def test_evaluate_candidates_batch_empty_is_ok(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("batch-eval-empty"))
    project_id = project["id"]
    package_path = project_dir(settings, project_id) / "study.aieng"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", "{}")
        package.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
        package.writestr("analysis/design_study_problem.json",
                         json.dumps({"format": "aieng.design_study_problem", "variables": []}))
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    response = client.post(f"/api/projects/{project_id}/design-study/evaluate-candidates", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["evaluated"] == 0
    assert body["warnings"]
