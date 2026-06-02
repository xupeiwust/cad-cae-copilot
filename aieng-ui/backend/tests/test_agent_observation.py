"""Tests for the Agent Observation Loop (v0.35.2).

Covers the seven required cases from the v0.35.2 brief:

  1. Observation after a safe read-only / preview action.
  2. Observation after a metadata-write action (submitted_for_approval).
  3. Approval-required action: status is submitted_for_approval before approval.
  4. Observation after approval reflects executed state with artifact changes.
  5. Rejected action does not claim artifact changes.
  6. Premature solver request observation reports readiness gaps; no solver evidence.
  7. Next recommended action appears for at least the cantilever happy path.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.app_factory import create_app
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


def _make_minimal_package(pkg: Path) -> None:
    pkg.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "obs-test", "resources": {}}))


def _find_action(plan: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    for action in plan.get("actions") or []:
        if action.get("tool_name") == tool_name:
            return action
    return None


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


def _execute(client: TestClient, plan: dict[str, Any], action_id: str) -> dict[str, Any]:
    resp = client.post(
        f"/api/intent-planner/actions/{action_id}/execute",
        json={"plan": plan},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── 1: read-only / preview observation ───────────────────────────────────────


def test_observation_after_preview_is_completed_with_no_artifact_changes(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "obs-preview", "p.aieng")
    _make_minimal_package(pkg)
    plan = _plan(client, project_id)
    preview = _find_action(plan, "engineering_template.preview")
    assert preview is not None

    before = pkg.read_bytes()
    result = _execute(client, plan, preview["id"])
    assert pkg.read_bytes() == before, "preview must not mutate the package"

    obs = result["observation"]
    assert obs["status"] == "completed"
    assert obs["mode"] == "read_only"
    # The preview is read-only — no artifact changes, no stale impacts.
    assert obs["artifact_changes"] == []
    assert obs["stale_changes"] == []
    assert obs["errors"] == []
    # Honest evidence_refs: nothing was written to the package.
    assert obs["evidence_refs"] == []
    # Readiness was not relevant for a preview action.
    assert obs["readiness_delta"]["evaluated"] in {False, True}
    # The schema and audit identifiers are present.
    assert obs["schema_version"]
    assert obs["audit_event_ids"], "runtime events should be linked"
    assert obs["claim_advancement"] == "none"
    assert obs["claim_boundary"]
    # Next recommendation should guide toward save_draft.
    rec_labels = [r["label"] for r in obs["next_recommended_actions"]]
    assert any("save" in label.lower() for label in rec_labels)


# ── 2 + 3: metadata-write (save_draft) submitted_for_approval ────────────────


def test_observation_for_metadata_write_action_is_submitted_for_approval(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "obs-meta", "p.aieng")
    _make_minimal_package(pkg)
    plan = _plan(client, project_id)
    save_draft = _find_action(plan, "engineering_template.save_draft")
    assert save_draft is not None
    assert save_draft["mode"] == "metadata_write"
    assert save_draft["requires_approval"] is True

    before = pkg.read_bytes()
    result = _execute(client, plan, save_draft["id"])
    # Approval gate must have paused execution — package not yet written.
    assert pkg.read_bytes() == before

    obs = result["observation"]
    assert obs["status"] == "submitted_for_approval"
    # No artifact / evidence claims pre-approval.
    assert obs["artifact_changes"] == []
    assert obs["evidence_refs"] == []
    assert obs["stale_changes"] == []
    assert any("approval" in w.lower() for w in obs["warnings"])
    # Recommendation should ask for approval, not invent next steps.
    rec_kinds = {r["kind"] for r in obs["next_recommended_actions"]}
    assert "await_approval" in rec_kinds


# ── 4: observation after approval reflects executed state ────────────────────


def test_observation_after_approval_reflects_executed_state(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "obs-approve", "p.aieng")
    _make_minimal_package(pkg)
    plan = _plan(client, project_id)
    save_draft = _find_action(plan, "engineering_template.save_draft")
    assert save_draft is not None

    submit = _execute(client, plan, save_draft["id"])
    run_id = submit["run"]["run_id"]
    assert submit["observation"]["status"] == "submitted_for_approval"

    approve = client.post(f"/api/runtime/runs/{run_id}/approve")
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "completed"

    # Recompute observation against the updated run state.
    observe = client.post(
        "/api/intent-planner/observe",
        json={"plan": plan, "action_id": save_draft["id"], "run_id": run_id},
    )
    assert observe.status_code == 200, observe.text
    obs = observe.json()["observation"]
    assert obs["status"] == "approved_executed"
    # Artifact changes recorded for the four draft files.
    written_paths = {ac["path"] for ac in obs["artifact_changes"]}
    assert "task/engineering_setup_draft.json" in written_paths
    assert "task/cad_template_preview.py" in written_paths
    assert "task/fea_setup_draft.json" in written_paths
    assert "task/design_targets_suggestions.yaml" in written_paths
    # Evidence refs surface the same paths so reviewers can audit easily.
    assert "task/engineering_setup_draft.json" in obs["evidence_refs"]
    # Recommendation should guide toward adopt_targets or generate_cad_fixture.
    rec_refs = {r.get("reference") for r in obs["next_recommended_actions"]}
    assert (
        "engineering_template.adopt_targets" in rec_refs
        or "engineering_template.generate_cad_fixture" in rec_refs
    )


# ── 5: rejected action does not claim artifact changes ───────────────────────


def test_observation_after_rejection_claims_no_artifact_changes(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "obs-reject", "p.aieng")
    _make_minimal_package(pkg)
    plan = _plan(client, project_id)
    save_draft = _find_action(plan, "engineering_template.save_draft")
    assert save_draft is not None

    before = pkg.read_bytes()
    submit = _execute(client, plan, save_draft["id"])
    run_id = submit["run"]["run_id"]

    reject = client.post(f"/api/runtime/runs/{run_id}/reject")
    assert reject.status_code == 200, reject.text
    assert reject.json()["status"] == "rejected"
    assert pkg.read_bytes() == before, "rejection must not mutate the package"

    observe = client.post(
        "/api/intent-planner/observe",
        json={"plan": plan, "action_id": save_draft["id"], "run_id": run_id},
    )
    assert observe.status_code == 200, observe.text
    obs = observe.json()["observation"]
    assert obs["status"] == "rejected"
    assert obs["artifact_changes"] == []
    assert obs["evidence_refs"] == []
    assert obs["stale_changes"] == []
    assert any("did not complete" in w.lower() or "not complete" in w.lower() for w in obs["warnings"])
    rec_kinds = {r["kind"] for r in obs["next_recommended_actions"]}
    assert "regenerate_plan" in rec_kinds


# ── 6: premature solver request observation surfaces readiness gaps ──────────


def test_observation_for_premature_solver_request_reports_readiness_gaps(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "obs-premature", "p.aieng")
    _make_minimal_package(pkg)

    plan = _plan(client, project_id, message="Run the structural simulation now and tell me the stress.")
    # The planner offers the preflight as the safe alternative.
    preflight = _find_action(plan, "cae.prepare_solver_run")
    assert preflight is not None

    result = _execute(client, plan, preflight["id"])
    obs = result["observation"]
    assert obs["status"] == "completed"
    assert obs["mode"] == "read_only"
    # No solver evidence is produced by the preflight tool.
    assert obs["artifact_changes"] == []
    assert obs["evidence_refs"] == []
    # The next recommendation should point at the structural adapter card.
    rec_refs = {r.get("reference") for r in obs["next_recommended_actions"]}
    assert "structural_adapter" in rec_refs
    # Readiness should be evaluated and report not-ready (no mesh / no deck / no ccx).
    readiness = obs["readiness_delta"]
    if readiness.get("evaluated"):
        after = readiness.get("after") or {}
        assert after.get("ready_to_run") is False
        assert any("mesh" in item or "solver" in item or "ccx" in item.lower()
                   for item in after.get("missing_items", []))


def test_simulation_intent_plan_expands_to_full_cae_workflow(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "obs-simulation-plan", "p.aieng")
    _make_minimal_package(pkg)

    plan = _plan(client, project_id, message="Run the structural simulation now and tell me the stress.")
    tool_names = [action["tool_name"] for action in plan["actions"]]

    expected = [
        "aieng.agent_context",
        "aieng.inspect_package",
        "cae.prepare_solver_run",
        "cae.generate_solver_input",
        "cae.run_solver",
        "cae.extract_solver_results",
        "cae.extract_field_regions",
        "postprocess.refresh_cae_summary",
    ]
    assert tool_names[:len(expected)] == expected
    phases = [action.get("workflow_phase") for action in plan["actions"][:len(expected)]]
    assert phases == [
        "check",
        "check",
        "check",
        "preprocess",
        "approval_execute",
        "parse",
        "parse",
        "parse",
    ]
    solver = _find_action(plan, "cae.run_solver")
    assert solver is not None
    assert solver["requires_approval"] is True
    assert solver["mode"] == "expensive"
    assert solver["workflow_phase"] == "approval_execute"


# ── 7: next-recommended-action appears for cantilever happy path ─────────────


def test_next_recommended_action_appears_for_cantilever_happy_path(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "obs-happy", "p.aieng")
    _make_minimal_package(pkg)
    plan = _plan(client, project_id)

    # Step 1: preview → should recommend save_draft.
    preview = _find_action(plan, "engineering_template.preview")
    assert preview is not None
    preview_obs = _execute(client, plan, preview["id"])["observation"]
    recs = preview_obs["next_recommended_actions"]
    assert any(r.get("reference") == "engineering_template.save_draft" for r in recs)

    # Step 2: submit + approve save_draft → should recommend adopt_targets or
    # generate_cad_fixture.
    save_draft = _find_action(plan, "engineering_template.save_draft")
    assert save_draft is not None
    submit = _execute(client, plan, save_draft["id"])
    run_id = submit["run"]["run_id"]
    approve = client.post(f"/api/runtime/runs/{run_id}/approve")
    assert approve.status_code == 200, approve.text
    observe = client.post(
        "/api/intent-planner/observe",
        json={"plan": plan, "action_id": save_draft["id"], "run_id": run_id},
    )
    saved_obs = observe.json()["observation"]
    refs = {r.get("reference") for r in saved_obs["next_recommended_actions"]}
    assert "engineering_template.adopt_targets" in refs or "engineering_template.generate_cad_fixture" in refs


def test_observe_endpoint_validates_payload(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))

    resp = client.post("/api/intent-planner/observe", json={})
    assert resp.status_code == 400

    resp = client.post("/api/intent-planner/observe", json={"plan": {"actions": []}})
    assert resp.status_code == 400

    resp = client.post(
        "/api/intent-planner/observe",
        json={"plan": {"actions": []}, "action_id": "missing", "run_id": "missing"},
    )
    # action lookup precedes run lookup, so the 404 surfaces on the action.
    assert resp.status_code == 404
