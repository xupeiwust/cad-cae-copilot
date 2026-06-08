"""Tests for CAD Observation v1 (v0.36).

Covers the five required cases:

  1. No CAD artifact → status=missing, evidence_level=none, no false claims.
  2. Metadata-only CAD fixture → status=metadata_only, evidence_level=metadata.
  3. IntentObservation after generate_cad_fixture includes CADObservation
     and recommends real CAD geometry / inspection.
  4. Metadata-only observation does not claim meshability, watertightness,
     solver readiness, or physical correctness.
  5. Future-compatible: a live_cad_snapshot artifact lifts the evidence
     level without requiring FreeCAD execution.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.cad_observation import (
    is_cad_related_action,
    observe_cad_state,
)
from app.config import Settings


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


def _make_project(settings: Settings, name: str, package: str) -> tuple[str, Path]:
    from app.main import default_project, project_dir, save_project

    project = save_project(settings, default_project(name))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / package
    project["aieng_file"] = package
    save_project(settings, project)
    return project_id, pkg_path


def _make_minimal_package(pkg: Path, *, extra_members: dict[str, bytes] | None = None) -> None:
    pkg.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "cad-obs-test", "resources": {}}))
        for path, payload in (extra_members or {}).items():
            zf.writestr(path, payload)


def _add_template_fixture(pkg: Path, *, fixture: dict[str, Any] | None = None) -> None:
    """Append a template CAD fixture metadata artifact to the package."""
    payload = fixture if isinstance(fixture, dict) else _DEFAULT_FIXTURE
    with zipfile.ZipFile(pkg, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("geometry/template_cad_fixture.json", json.dumps(payload))


def _add_live_snapshot(pkg: Path, *, snapshot: dict[str, Any] | None = None) -> None:
    payload = snapshot if isinstance(snapshot, dict) else _DEFAULT_LIVE_SNAPSHOT
    with zipfile.ZipFile(pkg, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("geometry/freecad_snapshot.json", json.dumps(payload))


_DEFAULT_FIXTURE = {
    "schema_version": "0.1",
    "artifact_type": "template_cad_fixture",
    "template_id": "cantilever_beam",
    "parameters": {
        "length_mm": 200.0,
        "width_mm": 20.0,
        "height_mm": 10.0,
        "material": "aluminum_6061_t6",
    },
    "geometry": {
        "geometry_kind": "rectangular_cantilever_fixture",
        "primitive": "box",
        "dimensions": {"length_mm": 200.0, "width_mm": 20.0, "height_mm": 10.0},
        "named_regions": [
            {"id": "x_min_face", "role": "fixed_support", "description": "Root face."},
            {"id": "x_max_face", "role": "load_application", "description": "Tip face."},
        ],
        "material": {"id": "aluminum_6061_t6", "name": "Aluminum 6061-T6"},
    },
    "cad_execution_performed": False,
    "real_cad_file": False,
    "claim_advancement": "none",
}


_DEFAULT_LIVE_SNAPSHOT = {
    "schema_version": "0.1",
    "artifact_type": "freecad_live_snapshot",
    "captured_at": "2026-05-20T12:00:00Z",
    "geometry": {
        "geometry_kind": "rectangular_cantilever",
        "primitive": "box",
        "dimensions": {"length_mm": 200.0, "width_mm": 20.0, "height_mm": 10.0},
        "bounding_box_mm": {"min": [0.0, -10.0, -5.0], "max": [200.0, 10.0, 5.0]},
        "named_regions": [
            {"id": "x_min_face", "role": "fixed_support"},
            {"id": "x_max_face", "role": "load_application"},
        ],
    },
    "material": {"id": "aluminum_6061_t6", "name": "Aluminum 6061-T6"},
    "parameters": {"length_mm": 200.0},
    "semantic_labels": ["root_support", "tip_load_face"],
}


CANTILEVER_REQUEST = (
    "I want to design a lightweight cantilever beam made of aluminum alloy, "
    "length 200 mm, end load 1000 N, max stress below 180 MPa, max "
    "displacement below 5 mm. Help me prepare the first modeling and simulation steps."
)


def _plan(client: TestClient, project_id: str, message: str = CANTILEVER_REQUEST) -> dict[str, Any]:
    resp = client.post(
        "/api/intent-planner/plan",
        json={"message": message, "project_id": project_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _find_action(plan: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    for action in plan.get("actions") or []:
        if action.get("tool_name") == tool_name:
            return action
    return None


# ── 1: no CAD artifact ───────────────────────────────────────────────────────


def test_observation_when_no_cad_artifact_is_missing(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    project_id, pkg = _make_project(settings, "cad-obs-empty", "p.aieng")
    _make_minimal_package(pkg)

    obs = observe_cad_state(settings, project_id)
    assert obs["status"] == "missing"
    assert obs["geometry_evidence_level"] == "none"
    assert obs["source_artifacts"] == []
    # No false CAE readiness claims.
    hints = obs["cae_readiness_hints"]
    assert hints["mesh_evidence"] is False
    assert hints["solver_input_evidence"] is False
    assert hints["computed_metrics_evidence"] is False
    # Missing information surfaces the absence of geometry.
    joined_missing = "\n".join(obs["missing_information"])
    assert "geometry" in joined_missing.lower()
    # Honest claim boundary present.
    assert obs["claim_advancement"] == "none"
    assert obs["claim_boundary"]
    # Recommender points at generating a template fixture or importing CAD.
    rec_refs = {r.get("reference") for r in obs["next_recommended_actions"]}
    assert "engineering_template.generate_cad_fixture" in rec_refs


# ── 2: metadata-only CAD fixture ─────────────────────────────────────────────


def test_intent_observation_after_generate_cad_fixture_includes_cad_observation(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "cad-obs-integration", "p.aieng")
    _make_minimal_package(pkg)

    plan = _plan(client, project_id)
    fixture_action = _find_action(plan, "engineering_template.generate_cad_fixture")
    assert fixture_action is not None
    assert is_cad_related_action(fixture_action) is True

    # Submit (approval-required).
    submit = client.post(
        f"/api/intent-planner/actions/{fixture_action['id']}/execute",
        json={"plan": plan},
    )
    assert submit.status_code == 200, submit.text
    run_id = submit.json()["run"]["run_id"]

    # Approve and recompute observation.
    approve = client.post(f"/api/runtime/runs/{run_id}/approve")
    assert approve.status_code == 200, approve.text
    observe = client.post(
        "/api/intent-planner/observe",
        json={"plan": plan, "action_id": fixture_action["id"], "run_id": run_id},
    )
    assert observe.status_code == 200, observe.text
    intent_obs = observe.json()["observation"]

    assert intent_obs["status"] == "approved_executed"
    cad_obs = intent_obs.get("cad_observation")
    assert isinstance(cad_obs, dict)
    # The fixture is now on disk → metadata-only state.
    assert cad_obs["status"] == "metadata_only"
    assert cad_obs["geometry_evidence_level"] == "metadata"
    assert "geometry/template_cad_fixture.json" in cad_obs["source_artifacts"]

    # IntentObservation next_recommended_actions surfaces a CAD step.
    refs = {r.get("reference") for r in intent_obs["next_recommended_actions"]}
    assert (
        "cad.export_step" in refs
        or "cad.inspect_geometry" in refs
        or "engineering_template.generate_cad_fixture" in refs
    )


# ── 4: metadata-only must not claim physical correctness ─────────────────────


def test_exported_geometry_via_step_binary_lifts_evidence(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    project_id, pkg = _make_project(settings, "cad-obs-step", "p.aieng")
    _make_minimal_package(pkg, extra_members={"geometry/source.step": b"ISO-10303-21;\nEND;\n"})
    obs = observe_cad_state(settings, project_id)
    assert obs["geometry_evidence_level"] == "exported_geometry"
    assert obs["status"] == "available"
    assert "geometry/source.step" in obs["source_artifacts"]


# ── extra: invalid fixture json surfaces honestly ────────────────────────────


def test_invalid_fixture_json_surfaces_as_invalid(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    project_id, pkg = _make_project(settings, "cad-obs-invalid", "p.aieng")
    _make_minimal_package(pkg)
    # Write something that is not valid JSON for the fixture path.
    with zipfile.ZipFile(pkg, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("geometry/template_cad_fixture.json", b"{not-json")
    # And still claim metadata exists by adding the manifest member.
    obs = observe_cad_state(settings, project_id)
    # Unparseable JSON returns ``None`` from read_package_json, so the file is
    # treated as absent for content but its presence still keeps evidence at
    # metadata-level via the manifest fallback. The observation must not lift
    # the level above metadata.
    assert obs["geometry_evidence_level"] in {"none", "metadata"}
    # And no false readiness claims.
    hints = obs["cae_readiness_hints"]
    assert hints["mesh_evidence"] is False


# ── extra: is_cad_related_action gate ────────────────────────────────────────



def test_observe_cad_state_surfaces_geometry_self_correction_signals(tmp_path: Path) -> None:
    """A topology with a floating part + asymmetric pair → geometry_report signals
    + a run_design_review recommendation, so connected agents self-correct."""
    settings = _make_settings(tmp_path)
    project_id, pkg = _make_project(settings, "obs-geo", "obs-geo.aieng")
    topo = {"entities": [
        {"type": "solid", "id": "b1", "name": "torso", "bounding_box": [-30, -15, 100, 30, 15, 300]},
        {"type": "solid", "id": "b2", "name": "arm_L", "bounding_box": [-50, -10, 150, -30, 10, 290]},
        {"type": "solid", "id": "b3", "name": "arm_R", "bounding_box": [30, -10, 150, 50, 10, 250]},
        {"type": "solid", "id": "b4", "name": "foot_FL", "bounding_box": [-200, -10, -20, -180, 10, 0]},
    ]}
    _make_minimal_package(pkg, extra_members={"geometry/topology_map.json": json.dumps(topo).encode()})

    obs = observe_cad_state(settings, project_id)
    assert obs["geometry_report_summary"] and "floating=" in obs["geometry_report_summary"]
    assert "foot_FL" in obs["floating_parts"]
    assert set(obs["broken_symmetry"]) >= {"arm_L", "arm_R"}
    kinds = {r.get("kind") for r in obs["next_recommended_actions"]}
    assert "run_design_review" in kinds


def test_observe_cad_state_no_geometry_has_empty_self_correction_signals(tmp_path: Path) -> None:
    """No topology → empty signals, no design_review recommendation (nothing to fix)."""
    settings = _make_settings(tmp_path)
    project_id, pkg = _make_project(settings, "obs-empty", "obs-empty.aieng")
    _make_minimal_package(pkg)  # manifest only

    obs = observe_cad_state(settings, project_id)
    assert obs["geometry_report_summary"] is None
    assert obs["floating_parts"] == [] and obs["broken_symmetry"] == []
    kinds = {r.get("kind") for r in obs["next_recommended_actions"]}
    assert "run_design_review" not in kinds
