"""REST integration coverage for Issue #41 ranking + recommendation."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.main import create_app, default_project, project_dir, save_project
from starlette.testclient import TestClient
from test_api import _make_patch_settings


def _seed_evaluated_package(settings, project_id: str) -> Path:
    """Package with a problem, baseline metrics, and two executed+evaluated candidates."""
    package_path = project_dir(settings, project_id) / "study.aieng"
    package_path.parent.mkdir(parents=True, exist_ok=True)

    baseline = {"representation": "brep_build123d",
                "parts": [{"id": "base", "params": {"WALL_THICKNESS": 3.0}}]}
    problem = {
        "format": "aieng.design_study_problem", "schema_version": "0.1", "id": "source_001",
        "variables": [
            {"id": "wall_t", "path": "parts/0/params/WALL_THICKNESS", "type": "continuous",
             "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "unit": "mm",
             "safe_to_modify": True},
        ],
        "constraints": [{"id": "stress_limit", "type": "max_stress", "limit": 200.0, "unit": "MPa"}],
        "objective": {"metric": "mass", "sense": "minimize"},
        "settings": {"max_variables_per_candidate": 1, "require_reasoning": True},
    }
    # iterations record so ranking discovers the candidates
    iterations = {
        "format": "aieng.design_study_iterations", "schema_version": "0.1",
        "iterations": [
            {"iteration_id": "iter_001", "candidate_id": "cand_light",
             "execution_status": "evaluation_complete", "recommendation": "refine_candidate",
             "candidate_workspace": "candidates/cand_light/"},
            {"iteration_id": "iter_002", "candidate_id": "cand_heavy",
             "execution_status": "evaluation_complete", "recommendation": "refine_candidate",
             "candidate_workspace": "candidates/cand_heavy/"},
        ],
    }

    def _evaluation(cid, mass, stress):
        return {
            "format": "aieng.design_study_candidate_evaluation", "schema_version": "0.1",
            "candidate_id": cid, "evaluation_status": "complete", "feasibility": "feasible",
            "confidence": "high",
            "metrics": {"mass_kg": mass, "max_stress": stress},
            "constraint_evidence": [
                {"id": "stress_limit", "type": "max_stress", "actual": stress,
                 "limit": 200.0, "status": "satisfied" if stress <= 200 else "violated"}
            ],
            "baseline_modified": False,
        }

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", "{}")
        package.writestr("geometry/shape_ir.json", json.dumps(baseline))
        package.writestr("analysis/design_study_problem.json", json.dumps(problem))
        package.writestr("analysis/design_study_iterations.json", json.dumps(iterations))
        # baseline metrics so objective_delta is computable
        package.writestr("analysis/static_metrics.json", json.dumps({"mass_kg": 1.0, "max_stress": 160.0}))
        for cid, mass, stress in (("cand_light", 0.82, 150.0), ("cand_heavy", 0.97, 180.0)):
            package.writestr(f"candidates/{cid}/patch.json", json.dumps({"candidate_id": cid}))
            package.writestr(f"candidates/{cid}/analysis/evaluation.json",
                             json.dumps(_evaluation(cid, mass, stress)))
    return package_path


def test_rank_then_recommendation_endpoints(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("reco"))
    project_id = project["id"]
    package_path = _seed_evaluated_package(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    with zipfile.ZipFile(package_path) as package:
        baseline_before = json.loads(package.read("geometry/shape_ir.json"))

    # 1) rank
    rank = client.post(f"/api/projects/{project_id}/design-study/rank", json={})
    assert rank.status_code == 200
    rbody = rank.json()
    assert rbody["status"] == "ok"

    # 2) explain recommendation
    reco = client.post(f"/api/projects/{project_id}/design-study/recommendation", json={})
    assert reco.status_code == 200
    body = reco.json()
    assert body["status"] == "ok"
    assert body["advisory_only"] is True
    assert body["requires_human_review"] is True
    assert body["baseline_modified"] is False
    assert "advisory_recommendation" in body["reason_codes"]

    with zipfile.ZipFile(package_path) as package:
        assert "analysis/optimization_recommendation.json" in package.namelist()
        doc = json.loads(package.read("analysis/optimization_recommendation.json"))
        # baseline untouched
        assert json.loads(package.read("geometry/shape_ir.json")) == baseline_before
    assert doc["honesty"]["production_sign_off"] is False
    assert doc["advisory_only"] is True


def test_recommendation_without_ranking_asks_to_rank_first(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("reco-norank"))
    project_id = project["id"]
    package_path = project_dir(settings, project_id) / "study.aieng"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", "{}")
        package.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    reco = client.post(f"/api/projects/{project_id}/design-study/recommendation", json={})
    assert reco.status_code == 200
    body = reco.json()
    assert body["status"] == "needs_user_input"
    assert body["code"] == "no_ranking"
