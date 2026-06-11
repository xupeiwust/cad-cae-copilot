"""REST integration coverage for Issue #38 candidate generation."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.main import create_app, default_project, project_dir, save_project
from starlette.testclient import TestClient
from test_api import _make_patch_settings


def test_design_study_sample_endpoint_writes_candidates_without_touching_baseline(
    tmp_path: Path,
) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("optimization-sampler"))
    project_id = project["id"]
    package_path = project_dir(settings, project_id) / "study.aieng"
    package_path.parent.mkdir(parents=True, exist_ok=True)

    baseline = {"representation": "brep_build123d", "parts": [{"id": "base"}]}
    problem = {
        "format": "aieng.design_study_problem",
        "schema_version": "0.1",
        "id": "source_001",
        "variables": [
            {
                "id": "wall_t",
                "path": "parts/0/params/WALL_THICKNESS",
                "type": "continuous",
                "current_value": 3.0,
                "min_value": 2.0,
                "max_value": 8.0,
                "unit": "mm",
                "safe_to_modify": True,
            }
        ],
        "settings": {"max_variables_per_candidate": 1, "require_reasoning": True},
    }
    variables = {
        "format": "aieng.optimization_variables",
        "schema_version": "0.2",
        "study_id": "opt_001",
        "design_study_problem_ref": "analysis/design_study_problem.json",
        "design_study_problem_id": "source_001",
        "variables": [
            {
                **problem["variables"][0],
                "featureId": "feat_wall",
                "parameterName": "thickness",
                "cad_parameter_name": "WALL_THICKNESS",
                "binding_status": "bound",
                "allowed_values": None,
                "scope": "local",
                "candidate_ids": [],
            }
        ],
        "candidate_ids": [],
        "provenance": {
            "created_at": "2026-06-10T00:00:00Z",
            "created_by": "test",
            "claim_advancement": "none",
        },
        "claim_policy": {
            "advisory_only": True,
            "baseline_unchanged": True,
            "human_approval_required_for_acceptance": True,
            "claim_advancement": "none",
        },
    }
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", "{}")
        package.writestr("geometry/shape_ir.json", json.dumps(baseline))
        package.writestr("analysis/design_study_problem.json", json.dumps(problem))
        package.writestr("analysis/optimization_variables.json", json.dumps(variables))
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    response = client.post(
        f"/api/projects/{project_id}/design-study/sample",
        json={"algorithm": "random", "count": 3, "seed": 7},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["candidate_count"] == 3
    assert body["baseline_modified"] is False

    with zipfile.ZipFile(package_path) as package:
        assert json.loads(package.read("geometry/shape_ir.json")) == baseline
        assert len(
            [
                name
                for name in package.namelist()
                if name.startswith("patches/design_candidates/")
            ]
        ) == 3
        audit = package.read("audit/events.jsonl").decode()
    assert '"tool":"opt.propose_candidates"' in audit
