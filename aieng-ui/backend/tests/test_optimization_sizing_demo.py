"""Canonical open-loop sizing-optimization demo — full Phase-1 flow (#44).

Exercises the whole agent-guided optimization loop end-to-end through the REST
layer on a deterministic plate-with-hole bracket, with NO external solver:

  sample -> run (execute into derived workspaces) -> inject deterministic
  static metrics (stand-in for CAE results) -> evaluate -> rank -> recommend
  -> report.

The metric model is a real sizing trade-off: a thinner wall is lighter but more
highly stressed/deflected, so minimizing mass subject to max_stress +
max_displacement has a genuine feasible frontier — the thinnest wall that still
passes both constraints wins. Baseline geometry is never overwritten.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.main import create_app, default_project, project_dir, save_project
from starlette.testclient import TestClient
from test_api import _make_patch_settings

# ── deterministic sizing metric model (stand-in for a solver) ─────────────────
# wall thickness (mm) drives the trade-off; fillet radius is a secondary var.
#   mass        = 0.5 + 0.15 * wall          (thicker -> heavier)
#   max_stress  = 600 / wall                 (thinner -> higher stress)
#   max_disp    = 3.0 / wall                 (thinner -> more deflection)
# Constraints: max_stress <= 200, max_displacement <= 1.0  =>  feasible wall >= 3.
WALL_VAR_PATH = "parts/0/params/WALL_THICKNESS"


def _metrics_for_wall(wall: float) -> dict[str, float]:
    return {
        "mass_kg": round(0.5 + 0.15 * wall, 4),
        "max_stress": round(600.0 / wall, 4),
        "max_displacement": round(3.0 / wall, 4),
    }


def _baseline():
    return {
        "representation": "brep_build123d",
        "parts": [{"id": "plate", "type": "box",
                   "params": {"WALL_THICKNESS": 5.0, "FILLET_RADIUS": 2.0}}],
    }


def _problem():
    return {
        "format": "aieng.design_study_problem", "schema_version": "0.1", "id": "bracket_sizing_001",
        "variables": [
            {"id": "wall_t", "path": WALL_VAR_PATH, "type": "continuous",
             "current_value": 5.0, "min_value": 2.0, "max_value": 6.0, "unit": "mm",
             "safe_to_modify": True, "semantic_role": "wall_thickness"},
            {"id": "fillet_r", "path": "parts/0/params/FILLET_RADIUS", "type": "continuous",
             "current_value": 2.0, "min_value": 1.0, "max_value": 4.0, "unit": "mm",
             "safe_to_modify": True, "semantic_role": "fillet_radius"},
        ],
        "constraints": [
            {"id": "stress_limit", "type": "max_stress", "limit": 200.0, "unit": "MPa"},
            {"id": "disp_limit", "type": "max_deflection", "limit": 1.0, "unit": "mm"},
        ],
        "objective": {"sense": "minimize", "metric": "mass"},
        # baseline metrics at the current wall (5.0) so ranking computes objective deltas
        "baseline_metrics": _metrics_for_wall(5.0),
        "settings": {"max_variables_per_candidate": 2, "require_reasoning": True},
    }


def _variables_doc(problem):
    def _v(v):
        return {**v, "featureId": f"feat_{v['id']}", "parameterName": v["id"],
                "cad_parameter_name": v["path"].split("/")[-1], "binding_status": "bound",
                "allowed_values": None, "scope": "local", "candidate_ids": []}
    return {
        "format": "aieng.optimization_variables", "schema_version": "0.2",
        "study_id": "opt_bracket_001",
        "design_study_problem_ref": "analysis/design_study_problem.json",
        "design_study_problem_id": problem["id"],
        "variables": [_v(v) for v in problem["variables"]],
        "candidate_ids": [],
        "provenance": {"created_at": "2026-06-10T00:00:00Z", "created_by": "demo",
                       "claim_advancement": "none"},
        "claim_policy": {"advisory_only": True, "baseline_unchanged": True,
                         "human_approval_required_for_acceptance": True, "claim_advancement": "none"},
    }


def _seed(settings, project_id: str) -> Path:
    package_path = project_dir(settings, project_id) / "study.aieng"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    problem = _problem()
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", "{}")
        package.writestr("geometry/shape_ir.json", json.dumps(_baseline()))
        package.writestr("analysis/design_study_problem.json", json.dumps(problem))
        package.writestr("analysis/optimization_variables.json", json.dumps(_variables_doc(problem)))
        # baseline metrics so the ranking can compute objective deltas
        package.writestr("analysis/static_metrics.json", json.dumps(_metrics_for_wall(5.0)))
    return package_path


def _wall_of_candidate(package_path: Path, cid: str) -> float:
    """Read the candidate patch and return its WALL_THICKNESS new_value."""
    with zipfile.ZipFile(package_path) as zf:
        patch = json.loads(zf.read(f"patches/design_candidates/{cid}.json"))
    for ch in patch.get("variable_changes") or []:
        if ch.get("variable_id") == "wall_t":
            return float(ch["new_value"])
    return 5.0


def _inject_static_metrics(package_path: Path, candidate_ids: list[str]) -> None:
    """Write deterministic per-candidate static metrics into each workspace.

    Stand-in for CAE results — keyed on the candidate's actual wall thickness so
    the ranking reflects a real mass/stress trade-off.
    """
    members: dict[str, bytes] = {}
    for cid in candidate_ids:
        wall = _wall_of_candidate(package_path, cid)
        metrics = _metrics_for_wall(wall)
        members[f"candidates/{cid}/analysis/static_metrics.json"] = (
            json.dumps(metrics).encode("utf-8")
        )
    tmp = package_path.with_suffix(".inject.tmp.aieng")
    with (
        zipfile.ZipFile(package_path, "r") as src,
        zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for item in src.infolist():
            if item.filename not in members:
                dst.writestr(item, src.read(item.filename))
        for name, data in members.items():
            dst.writestr(name, data)
    tmp.replace(package_path)


def test_open_loop_sizing_demo_end_to_end(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("sizing-demo"))
    project_id = project["id"]
    package_path = _seed(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)
    base = f"/api/projects/{project_id}/design-study"

    with zipfile.ZipFile(package_path) as package:
        baseline_before = json.loads(package.read("geometry/shape_ir.json"))

    # 1) sample — grid over 2 vars (3 levels each = 9) capped to ensure >= 5 candidates
    sample = client.post(f"{base}/sample", json={"algorithm": "grid", "max_candidates": 9})
    assert sample.status_code == 200
    sbody = sample.json()
    assert sbody["status"] == "ok"
    candidate_ids = [c["candidate_id"] for c in sbody["candidates"]]
    assert len(candidate_ids) >= 5

    # 2) execute into derived workspaces (no recompiler — deterministic, no build123d)
    run = client.post(f"{base}/run-candidates", json={"compile": False})
    assert run.status_code == 200
    rbody = run.json()
    assert rbody["status"] == "ok"
    assert rbody["executed"] == len(candidate_ids)
    assert rbody["failed"] == 0

    # 3) inject deterministic static metrics (stand-in for CAE results)
    _inject_static_metrics(package_path, candidate_ids)

    # 4) evaluate
    ev = client.post(f"{base}/evaluate-candidates", json={})
    assert ev.status_code == 200
    ebody = ev.json()
    assert ebody["status"] == "ok"
    assert ebody["evaluated"] >= 5
    # mix of feasible (wall>=3) and infeasible (wall<3) candidates
    assert ebody["feasibility"].get("feasible", 0) >= 1
    assert ebody["feasibility"].get("infeasible", 0) >= 1

    # 5) rank
    rank = client.post(f"{base}/rank", json={})
    assert rank.status_code == 200
    assert rank.json()["status"] == "ok"

    # 6) recommendation
    reco = client.post(f"{base}/recommendation", json={})
    assert reco.status_code == 200
    rebody = reco.json()
    assert rebody["status"] == "ok"
    assert rebody["advisory_only"] is True
    assert "advisory_recommendation" in rebody["reason_codes"]

    # a genuine improving, high-confidence winner emerges from the trade-off
    assert rebody["recommended_candidate_id"] is not None
    assert rebody["safe_to_accept"] is True

    # 7) accept — the approval-gated close of the loop (best candidate)
    accept = client.post(
        f"{base}/candidates/{rebody['recommended_candidate_id']}/accept", json={}
    )
    assert accept.status_code == 200
    assert accept.json()["accepted"] is True

    # 8) report — aggregates the whole study
    report = client.post(f"{base}/report", json={})
    assert report.status_code == 200
    rpbody = report.json()
    assert rpbody["status"] == "ok"
    assert rpbody["candidate_count"] >= 5
    assert rpbody["accepted_candidate_id"] == rebody["recommended_candidate_id"]

    # ── assertions on the persisted artifacts ────────────────────────────────
    with zipfile.ZipFile(package_path) as package:
        names = set(package.namelist())
        assert "analysis/design_study_candidate_ranking.json" in names
        assert "analysis/optimization_recommendation.json" in names
        assert "analysis/design_study_acceptance.json" in names
        assert "diagnostics/optimization_report.json" in names
        ranking = json.loads(package.read("analysis/design_study_candidate_ranking.json"))
        report_doc = json.loads(package.read("diagnostics/optimization_report.json"))
        acceptance = json.loads(package.read("analysis/design_study_acceptance.json"))
        # baseline geometry untouched throughout the whole loop
        assert json.loads(package.read("geometry/shape_ir.json")) == baseline_before

    # the recommended/best candidate is feasible, improving, and the thinnest
    # wall that still passes both constraints (wall == 3 mm)
    best_id = ranking.get("best_candidate_id")
    assert best_id is not None
    assert ranking.get("safe_to_accept") is True
    best = [c for c in ranking["candidates"] if c["candidate_id"] == best_id][0]
    assert best["feasibility"] == "feasible"
    assert best["score"] > 0          # genuinely lighter than baseline
    assert best["confidence"] == "high"
    assert _wall_of_candidate(package_path, best_id) == 3.0

    # acceptance closed the loop on the best candidate; baseline still derived-only
    assert acceptance["accepted_candidate_id"] == best_id
    assert acceptance["baseline_modified"] is False
    assert acceptance["promotion_mode"] == "derived_only"
    assert f"accepted/{best_id}/geometry/shape_ir.json" in names

    # report aggregates candidates + feasibility summary + recommendation + acceptance
    assert report_doc["candidate_count"] >= 5
    assert report_doc["feasibility_summary"].get("feasible", 0) >= 1
    assert report_doc["feasibility_summary"].get("infeasible", 0) >= 1
    assert report_doc["honesty"]["baseline_modified"] is False
    assert report_doc["honesty"]["report_is_reconstructable_from_artifacts"] is True
