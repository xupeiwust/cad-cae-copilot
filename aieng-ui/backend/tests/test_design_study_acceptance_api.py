"""REST integration coverage for Issue #42 approval-gated candidate acceptance.

The eligibility logic is unit-tested in aieng/tests/test_design_study_acceptance.py;
this exercises the REST/tool path and the approval-gate wiring.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.main import create_app, default_project, project_dir, save_project
from starlette.testclient import TestClient
from test_api import _make_patch_settings


def _seed_ranked_package(settings, project_id: str, *, best="cand_good", safe=True) -> Path:
    """Package with a ranking that has a feasible best candidate + its workspace."""
    package_path = project_dir(settings, project_id) / "study.aieng"
    package_path.parent.mkdir(parents=True, exist_ok=True)

    baseline = {"representation": "brep_build123d", "parts": [{"id": "base"}]}
    problem = {
        "format": "aieng.design_study_problem", "schema_version": "0.1", "id": "study_001",
        "variables": [
            {"id": "wall_t", "path": "parts/0/params/WALL_THICKNESS", "type": "continuous",
             "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "unit": "mm",
             "safe_to_modify": True},
        ],
        "objective": {"sense": "minimize", "metric": "mass"},
    }
    ranking = {
        "format": "aieng.design_study.candidate_ranking.v0", "status": "ranked",
        "best_candidate_id": best, "safe_to_accept": safe,
        "candidates": [
            {"rank": 1, "candidate_id": "cand_good", "feasibility": "feasible",
             "confidence": "high", "score": 0.2, "recommendation": "accept_candidate",
             "metrics_used": {"mass_kg": 0.8}, "constraint_violations": [], "objective_delta": {},
             "reasons": []},
            {"rank": 2, "candidate_id": "cand_alt", "feasibility": "feasible",
             "confidence": "medium", "score": 0.05, "recommendation": "refine_candidate",
             "metrics_used": {"mass_kg": 0.95}, "constraint_violations": [], "objective_delta": {},
             "reasons": []},
        ],
    }
    iterations = {
        "format": "aieng.design_study_iterations", "schema_version": "0.1",
        "iterations": [
            {"candidate_id": "cand_good", "execution_status": "evaluation_complete",
             "metrics": {"mass_kg": 0.8}, "baseline_modified": False},
            {"candidate_id": "cand_alt", "execution_status": "evaluation_complete",
             "metrics": {"mass_kg": 0.95}, "baseline_modified": False},
        ],
    }

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", "{}")
        package.writestr("geometry/shape_ir.json", json.dumps(baseline))
        package.writestr("analysis/design_study_problem.json", json.dumps(problem))
        package.writestr("analysis/design_study_candidate_ranking.json", json.dumps(ranking))
        package.writestr("analysis/design_study_iterations.json", json.dumps(iterations))
        for cid in ("cand_good", "cand_alt"):
            package.writestr(f"candidates/{cid}/patch.json", json.dumps({"candidate_id": cid}))
            package.writestr(f"candidates/{cid}/geometry/shape_ir.json", json.dumps(baseline))
            package.writestr(f"candidates/{cid}/analysis/evaluation.json",
                             json.dumps({"candidate_id": cid, "feasibility": "feasible",
                                         "metrics": {"mass_kg": 0.8}}))
    return package_path


def test_accept_best_candidate_via_rest(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("accept"))
    project_id = project["id"]
    package_path = _seed_ranked_package(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    with zipfile.ZipFile(package_path) as package:
        baseline_before = json.loads(package.read("geometry/shape_ir.json"))

    response = client.post(
        f"/api/projects/{project_id}/design-study/candidates/cand_good/accept", json={}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["accepted"] is True
    assert body["baseline_modified"] is False

    with zipfile.ZipFile(package_path) as package:
        names = package.namelist()
        assert "accepted/cand_good/patch.json" in names
        assert "accepted/cand_good/geometry/shape_ir.json" in names
        assert "accepted/cand_good/provenance/acceptance.json" in names
        assert "analysis/design_study_acceptance.json" in names
        acc = json.loads(package.read("analysis/design_study_acceptance.json"))
        # baseline untouched
        assert json.loads(package.read("geometry/shape_ir.json")) == baseline_before
    assert acc["accepted_candidate_id"] == "cand_good"
    assert acc["baseline_modified"] is False
    assert acc["promotion_mode"] == "derived_only"


def test_accept_non_best_requires_override_via_rest(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("accept-nonbest"))
    project_id = project["id"]
    _seed_ranked_package(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    # cand_alt is not the best candidate -> needs_user_input without override
    blocked = client.post(
        f"/api/projects/{project_id}/design-study/candidates/cand_alt/accept", json={}
    )
    assert blocked.status_code == 200
    assert blocked.json()["accepted"] is False
    assert blocked.json()["status"] == "needs_user_input"

    # with override_unsafe it is accepted (and the override is recorded in the report)
    forced = client.post(
        f"/api/projects/{project_id}/design-study/candidates/cand_alt/accept",
        json={"override_unsafe": True},
    )
    assert forced.status_code == 200
    body = forced.json()
    assert body["accepted"] is True

    package_path = project_dir(settings, project_id) / "study.aieng"
    with zipfile.ZipFile(package_path) as package:
        report = json.loads(package.read("diagnostics/design_study_acceptance_report.json"))
        acc = json.loads(package.read("analysis/design_study_acceptance.json"))
    assert acc["accepted_candidate_id"] == "cand_alt"
    assert any("override_unsafe" in w for w in report.get("warnings", []))
