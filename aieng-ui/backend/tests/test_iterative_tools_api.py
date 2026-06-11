"""REST integration coverage for Issue #63 iterative-loop tools.

Exercises POST /design-study/propose-next and /check-convergence end-to-end,
plus the iteration-history section the report gains.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.main import create_app, default_project, project_dir, save_project
from starlette.testclient import TestClient
from test_api import _make_patch_settings


def _variables_doc():
    return {
        "format": "aieng.optimization_variables", "schema_version": "0.1",
        "study_id": "opt_study_001",
        "design_study_problem_ref": "analysis/design_study_problem.json",
        "design_study_problem_id": "study_source_001",
        "variables": [
            {"id": "wall_t", "type": "continuous", "path": "parts/0/params/WALL_THICKNESS",
             "featureId": "feat_wall", "parameterName": "thickness",
             "cad_parameter_name": "WALL_THICKNESS", "binding_status": "bound",
             "min_value": 2.0, "max_value": 8.0, "current_value": 5.0,
             "allowed_values": None, "unit": "mm", "scope": "local",
             "safe_to_modify": True, "candidate_ids": []},
        ],
        "candidate_ids": [],
        "provenance": {
            "created_at": "2026-06-10T00:00:00Z", "created_by": "test",
            "claim_advancement": "none",
        },
        "claim_policy": {
            "advisory_only": True, "baseline_unchanged": True,
            "human_approval_required_for_acceptance": True,
            "claim_advancement": "none",
        },
    }


def _ranking(best_id, obj):
    return {
        "format": "aieng.design_study.candidate_ranking.v0", "status": "ranked",
        "objective": {"sense": "minimize", "metric": "mass"},
        "best_candidate_id": best_id, "safe_to_accept": True,
        "candidates": [{"rank": 1, "candidate_id": best_id, "feasibility": "feasible",
                        "score": 0.2, "confidence": "high",
                        "objective_delta": {"metric": "mass", "candidate_value": obj}}],
    }


def _incumbent_patch(cid, wall):
    return {"format": "aieng.design_candidate_patch", "candidate_id": cid,
            "variable_changes": [{"variable_id": "wall_t", "new_value": wall}]}


def _seed(settings, project_id: str) -> Path:
    package_path = project_dir(settings, project_id) / "study.aieng"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as p:
        p.writestr("manifest.json", "{}")
        p.writestr("geometry/shape_ir.json", json.dumps({"parts": []}))
        p.writestr("analysis/optimization_variables.json", json.dumps(_variables_doc()))
        p.writestr("analysis/design_study_candidate_ranking.json",
                   json.dumps(_ranking("inc", 0.8)))
        p.writestr("patches/design_candidates/inc.json", json.dumps(_incumbent_patch("inc", 5.0)))
    return package_path


def test_propose_next_endpoint_writes_refined_candidates(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("propose"))
    project_id = project["id"]
    package_path = _seed(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    with zipfile.ZipFile(package_path) as p:
        baseline_before = json.loads(p.read("geometry/shape_ir.json"))

    resp = client.post(f"/api/projects/{project_id}/design-study/propose-next",
                       json={"count": 4, "seed": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["strategy"] == "trust_region"
    assert body["candidate_count"] == 4
    assert body["baseline_modified"] is False

    with zipfile.ZipFile(package_path) as p:
        names = p.namelist()
        new = [n for n in names if n.startswith("patches/design_candidates/cand_iter")]
        assert len(new) == 4
        assert json.loads(p.read("geometry/shape_ir.json")) == baseline_before


def test_check_convergence_endpoint_records_and_verdicts(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("converge"))
    project_id = project["id"]
    package_path = _seed(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    resp = client.post(f"/api/projects/{project_id}/design-study/check-convergence", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["iteration_index"] == 1
    assert body["incumbent_candidate_id"] == "inc"
    assert body["verdict"] == "continue"  # one iteration, no stagnation yet
    assert body["baseline_modified"] is False

    with zipfile.ZipFile(package_path) as p:
        assert "analysis/optimization_iterations.json" in p.namelist()
        doc = json.loads(p.read("analysis/optimization_iterations.json"))
        assert len(doc["iterations"]) == 1


def test_report_includes_iteration_history(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("iterreport"))
    project_id = project["id"]
    package_path = _seed(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    # add a problem so the report has enough to aggregate
    members = {"analysis/design_study_problem.json": json.dumps(
        {"format": "aieng.design_study_problem", "id": "s1",
         "objective": {"sense": "minimize", "metric": "mass"}}).encode()}
    tmp = package_path.with_suffix(".t.aieng")
    with zipfile.ZipFile(package_path) as src, zipfile.ZipFile(tmp, "w") as dst:
        for i in src.infolist():
            if i.filename not in members:
                dst.writestr(i, src.read(i.filename))
        for n, d in members.items():
            dst.writestr(n, d)
    tmp.replace(package_path)

    client.post(f"/api/projects/{project_id}/design-study/check-convergence", json={})
    rep = client.post(f"/api/projects/{project_id}/design-study/report", json={})
    assert rep.status_code == 200
    with zipfile.ZipFile(package_path) as p:
        doc = json.loads(p.read("diagnostics/optimization_report.json"))
    assert doc["iteration_history"]["iteration_count"] == 1
    assert doc["sources_present"]["optimization_iterations"] is True
    assert doc["iteration_history"]["iterations"][0]["incumbent_candidate_id"] == "inc"


def test_select_optimizer_endpoint_chooses_slsqp(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("select-opt"))
    project_id = project["id"]
    package_path = _seed(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    resp = client.post(f"/api/projects/{project_id}/design-study/select-optimizer", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["optimizer"] == "slsqp"
    assert body["baseline_modified"] is False

    with zipfile.ZipFile(package_path) as p:
        assert "analysis/optimization_decision_log.json" in p.namelist()
        doc = json.loads(p.read("analysis/optimization_decision_log.json"))
        assert len(doc["entries"]) == 1
        assert doc["entries"][0]["decision"] == "select_slsqp"
        assert "select_slsqp" in doc["entries"][0]["reason_codes"]


def test_select_optimizer_endpoint_honors_override(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("select-override"))
    project_id = project["id"]
    package_path = _seed(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    resp = client.post(
        f"/api/projects/{project_id}/design-study/select-optimizer",
        json={"optimizer": "genetic"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["optimizer"] == "genetic"
    assert "user_selected" in body["reason_codes"]


def test_select_optimizer_endpoint_appends_to_existing_log(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("select-append"))
    project_id = project["id"]
    package_path = _seed(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    client.post(f"/api/projects/{project_id}/design-study/select-optimizer", json={})
    resp = client.post(
        f"/api/projects/{project_id}/design-study/select-optimizer",
        json={"optimizer": "bayesian"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["optimizer"] == "bayesian"

    with zipfile.ZipFile(package_path) as p:
        doc = json.loads(p.read("analysis/optimization_decision_log.json"))
        assert len(doc["entries"]) == 2


def test_select_optimizer_endpoint_returns_404_without_package(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("select-nopkg"))
    project_id = project["id"]
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    resp = client.post(f"/api/projects/{project_id}/design-study/select-optimizer", json={})
    assert resp.status_code == 404
