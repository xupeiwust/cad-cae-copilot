"""Backend integration demo: 2D topology → sizing → CAE end-to-end (#110).

Exercises the full chain through the REST layer on a deterministic plate-with-
loads 2D case, with NO external solver:

  topology_to_sizing → sample → run (compile=False) → inject analytical metrics
  → evaluate → rank → recommendation → acceptance → report.

Also asserts honest refusal of 3D / non-extruded inputs and verifies the chain
is reconstructable from the package.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from app.main import create_app, default_project, project_dir, save_project
from starlette.testclient import TestClient
from test_api import _make_patch_settings


# ── deterministic metric model (stand-in for a solver) ───────────────────────
# Thicker extrusion is heavier; stress/displacement are absent (honest no-solver).
DENSITY_KG_MM3 = 2.7e-6


def _metrics_for_thickness(thickness: float) -> dict[str, Any]:
    area = 100.0  # 10 x 10 square plate
    volume = area * float(thickness)
    return {
        "volume_mm3": round(volume, 4),
        "mass_kg": round(volume * DENSITY_KG_MM3, 8),
    }


def _shape_ir() -> dict[str, Any]:
    return {
        "format": "aieng.shape_ir",
        "representation": "manifold_mesh",
        "model_id": "optimized_plate",
        "parts": [
            {
                "id": "optimized_plate",
                "label": "optimized_plate",
                "type": "extruded_region",
                "polygons": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
                "boundary": "polygon",
                "thickness": 5.0,
                "origin": [0, 0, 0],
                "u_axis": "x",
                "v_axis": "y",
                "placed_in_frame": True,
                "source_optimization": {"optimizer": "simp_2d"},
            }
        ],
    }


def _topology_optimization(dimension: str = "2d") -> dict[str, Any]:
    return {
        "format": "aieng.topology_optimization",
        "schema_version": "0.1",
        "contract_version": "0.1",
        "dimension": dimension,
        "optimizer": {"name": "simp_2d", "method": "SIMP", "dimension": 2 if dimension == "2d" else 3},
        "objective": "compliance_minimization",
        "problem": {"design_space_node": "plate", "volfrac": 0.5},
        "result": {},
    }


def _seed_package(settings: Any, project_id: str, *, dimension: str = "2d") -> Path:
    package_path = project_dir(settings, project_id) / "study.aieng"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", json.dumps({"format": "aieng.package", "format_version": "0.1.0", "resources": {}}))
        package.writestr("metadata.json", json.dumps({"name": "topology sizing backend demo"}))
        package.writestr("geometry/shape_ir.json", json.dumps(_shape_ir()))
        package.writestr("analysis/topology_optimization.json", json.dumps(_topology_optimization(dimension)))
    return package_path


def _thickness_of_candidate(package_path: Path, cid: str) -> float:
    with zipfile.ZipFile(package_path) as zf:
        patch = json.loads(zf.read(f"patches/design_candidates/{cid}.json"))
    for ch in patch.get("variable_changes") or []:
        if ch.get("variable_id") == "extrusion_thickness":
            return float(ch["new_value"])
    return 5.0


def _inject_baseline_metrics(package_path: Path) -> None:
    """Add baseline metrics to the design-study problem for high-confidence ranking."""
    with zipfile.ZipFile(package_path, "r") as zf:
        problem = json.loads(zf.read("analysis/design_study_problem.json"))
    problem["baseline_metrics"] = _metrics_for_thickness(5.0)
    _rewrite_member(package_path, "analysis/design_study_problem.json", json.dumps(problem).encode())


def _inject_static_metrics(package_path: Path, candidate_ids: list[str]) -> None:
    members: dict[str, bytes] = {}
    for cid in candidate_ids:
        thickness = _thickness_of_candidate(package_path, cid)
        metrics = _metrics_for_thickness(thickness)
        members[f"candidates/{cid}/analysis/static_metrics.json"] = json.dumps(metrics).encode("utf-8")
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


def test_topology_sizing_backend_demo_end_to_end(tmp_path: Path) -> None:
    """Full chain through REST: topology result → sizing → candidates → acceptance."""
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("topology-sizing-demo"))
    project_id = project["id"]
    package_path = _seed_package(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    with zipfile.ZipFile(package_path) as package:
        baseline_before = json.loads(package.read("geometry/shape_ir.json"))

    # 1) Bridge topology writeback → sizing study.
    t2s = client.post(f"/api/projects/{project_id}/topology-optimization/sizing", json={})
    assert t2s.status_code == 200
    t2s_body = t2s.json()
    assert t2s_body["status"] == "ok"
    assert t2s_body["baseline_modified"] is False

    # 1b) Inject baseline metrics so ranking can compute high-confidence deltas.
    _inject_baseline_metrics(package_path)

    # 2) Sample candidates from the recovered thickness variable.
    sample = client.post(f"/api/projects/{project_id}/design-study/sample", json={"algorithm": "grid", "max_candidates": 5})
    assert sample.status_code == 200
    sbody = sample.json()
    assert sbody["status"] == "ok"
    candidate_ids = [c["candidate_id"] for c in sbody["candidates"]]
    assert len(candidate_ids) >= 1

    # 3) Execute candidates without recompilation (no external CAD).
    run = client.post(f"/api/projects/{project_id}/design-study/run-candidates", json={"compile": False})
    assert run.status_code == 200
    rbody = run.json()
    assert rbody["status"] == "ok"
    assert rbody["executed"] == len(candidate_ids)

    # 4) Inject deterministic analytical metrics (stand-in for CAE).
    _inject_static_metrics(package_path, candidate_ids)

    # 5) Evaluate candidates.
    ev = client.post(f"/api/projects/{project_id}/design-study/evaluate-candidates", json={})
    assert ev.status_code == 200
    ebody = ev.json()
    assert ebody["status"] == "ok"
    assert ebody["evaluated"] >= 1

    # 6) Rank by volume objective.
    rank = client.post(f"/api/projects/{project_id}/design-study/rank", json={})
    assert rank.status_code == 200
    rank_body = rank.json()
    assert rank_body["status"] == "ok"
    assert rank_body["candidate_count"] >= 1

    # 7) Advisory recommendation.
    reco = client.post(f"/api/projects/{project_id}/design-study/recommendation", json={})
    assert reco.status_code == 200
    rebody = reco.json()
    assert rebody["status"] == "ok"
    assert rebody["advisory_only"] is True
    recommended_id = rebody["recommended_candidate_id"]
    assert recommended_id is not None

    # 8) Acceptance — approval-gated close of the loop (best candidate).
    accept = client.post(f"/api/projects/{project_id}/design-study/candidates/{recommended_id}/accept", json={})
    assert accept.status_code == 200
    abody = accept.json()
    assert abody["accepted"] is True

    # 9) Aggregate report.
    report = client.post(f"/api/projects/{project_id}/design-study/report", json={})
    assert report.status_code == 200
    rpbody = report.json()
    assert rpbody["status"] == "ok"
    assert rpbody["candidate_count"] >= 1
    assert rpbody["accepted_candidate_id"] == recommended_id

    # ── assertions on persisted artifacts ─────────────────────────────────────
    with zipfile.ZipFile(package_path) as package:
        names = set(package.namelist())
        assert "analysis/design_study_problem.json" in names
        assert "analysis/optimization_variables.json" in names
        assert "analysis/optimization_study.json" in names
        assert "analysis/optimization_decision_log.json" in names
        assert "analysis/design_study_candidate_ranking.json" in names
        assert "analysis/optimization_recommendation.json" in names
        assert "analysis/design_study_acceptance.json" in names
        assert "diagnostics/optimization_report.json" in names
        assert "provenance/tool_trace.json" in names

        study = json.loads(package.read("analysis/optimization_study.json"))
        decision_log = json.loads(package.read("analysis/optimization_decision_log.json"))
        report_doc = json.loads(package.read("diagnostics/optimization_report.json"))
        acceptance = json.loads(package.read("analysis/design_study_acceptance.json"))
        tool_trace = json.loads(package.read("provenance/tool_trace.json"))

        # Chain metadata present and marked experimental.
        chain = study.get("topology_to_sizing_chain")
        assert chain is not None
        assert chain["production_ready"] is False
        assert "analysis/topology_optimization.json" in chain.get("source_artifacts", [])
        assert "geometry/shape_ir.json" in chain.get("source_artifacts", [])

        # Decision log records the linkage and approval requirement.
        entries = decision_log.get("entries", [])
        assert any(e.get("decision") == "topology_to_sizing_linkage" for e in entries)
        assert any("production_ready=false" in e.get("note", "") for e in entries)

        # Report surfaces the chain.
        assert report_doc.get("topology_to_sizing_chain") is not None
        assert report_doc["topology_to_sizing_chain"]["production_ready"] is False

        # Acceptance is approval-gated and derived-only.
        assert acceptance["accepted_candidate_id"] == recommended_id
        assert acceptance["baseline_modified"] is False
        assert acceptance["promotion_mode"] == "derived_only"
        assert f"accepted/{recommended_id}/geometry/shape_ir.json" in names

        # Tool trace preserves parameterization + sizing steps.
        entries = tool_trace.get("entries", [])
        step_names = [e.get("step", {}).get("name") for e in entries]
        assert "parameterize_topology_writeback" in step_names
        assert "topology_to_sizing" in step_names

        # Baseline geometry untouched.
        assert json.loads(package.read("geometry/shape_ir.json")) == baseline_before

        # Honest CAE absence: volume present; stress/displacement not fabricated.
        for row in report_doc.get("candidates", []):
            assert row["metrics"].get("volume_mm3") is not None
            assert row["metrics"].get("max_stress") is None


def test_topology_sizing_refuses_3d_honestly(tmp_path: Path) -> None:
    """3D topology results are refused with needs_user_input, no artifacts written."""
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("topology-sizing-3d"))
    project_id = project["id"]
    package_path = _seed_package(settings, project_id, dimension="3d")
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    response = client.post(f"/api/projects/{project_id}/topology-optimization/sizing", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_user_input"
    assert body["code"] == "3d_or_non_2d_not_supported"

    with zipfile.ZipFile(package_path) as package:
        names = set(package.namelist())
        assert "analysis/design_study_problem.json" not in names
        assert "analysis/optimization_study.json" not in names


def test_topology_sizing_refuses_non_extruded_body_honestly(tmp_path: Path) -> None:
    """A non-extruded topology writeback is refused with needs_user_input."""
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("topology-sizing-no-param"))
    project_id = project["id"]
    package_path = _seed_package(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)

    # Replace shape_ir with a voxel node (no stable thickness parameter).
    shape_ir = _shape_ir()
    shape_ir["parts"][0]["type"] = "density_voxels"
    shape_ir["parts"][0].pop("thickness", None)
    _rewrite_member(package_path, "geometry/shape_ir.json", json.dumps(shape_ir).encode())

    response = client.post(f"/api/projects/{project_id}/topology-optimization/sizing", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_user_input"
    assert body["code"] == "no_stable_parameter"


def _rewrite_member(package_path: Path, name: str, data: bytes) -> None:
    tmp = package_path.with_suffix(".rewrite.tmp.aieng")
    with (
        zipfile.ZipFile(package_path, "r") as src,
        zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for item in src.infolist():
            if item.filename != name:
                dst.writestr(item, src.read(item.filename))
        dst.writestr(name, data)
    tmp.replace(package_path)
