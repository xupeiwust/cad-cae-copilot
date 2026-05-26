"""Tests for the Natural Language Intent Planner (v0.35.1).

Covers the four required demos from the task brief:

  1. Complete cantilever beam request → full template pilot plan.
  2. Incomplete drone-arm request → honest missing_information, safe actions only.
  3. Premature solver execution request → readiness gaps surfaced, never proposes
     ``cae.run_solver``.
  4. Approval-required action cannot execute silently (runtime gate is preserved
     when the executor is reached through the intent-planner endpoint).
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
        zf.writestr("manifest.json", json.dumps({"model_id": "intent-test", "resources": {}}))


def _find_action(plan: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    for action in plan.get("actions") or []:
        if action.get("tool_name") == tool_name:
            return action
    return None


# ── Demo 1: complete cantilever request ──────────────────────────────────────


CANTILEVER_REQUEST = (
    "I want to design a lightweight cantilever beam made of aluminum alloy, "
    "length 200 mm, end load 1000 N, max stress below 180 MPa, max "
    "displacement below 5 mm. Help me prepare the first modeling and simulation steps."
)


def test_intent_plan_for_cantilever_extracts_constraints_and_proposes_template_actions(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "cb-pilot", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        "/api/intent-planner/plan",
        json={"message": CANTILEVER_REQUEST, "project_id": project_id},
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["claim_advancement"] == "none"
    assert plan["claim_boundary"]
    assert plan["inferred_engineering_domain"] == "structural_static_linear"
    assert plan["inferred_template_id"] == "cantilever_beam"

    params = plan["extracted_parameters"]
    assert params["material"] == "aluminum_6061_t6"
    assert params["length_mm"] == 200.0
    assert params["tip_load_N"] == 1000.0
    assert params["allowable_stress_MPa"] == 180.0
    assert params["max_displacement_mm"] == 5.0

    constraint_kinds = {c["kind"] for c in plan["extracted_constraints"]}
    assert {"material", "geometry", "load", "design_target", "template_match"} <= constraint_kinds

    proposed_tool_names = [a["tool_name"] for a in plan["actions"]]
    assert "aieng.agent_context" in proposed_tool_names
    assert "aieng.inspect_package" in proposed_tool_names
    assert "engineering_template.preview" in proposed_tool_names
    assert "engineering_template.save_draft" in proposed_tool_names
    assert "engineering_template.adopt_targets" in proposed_tool_names
    assert "engineering_template.generate_cad_fixture" in proposed_tool_names

    # Mode classification: preview is read-only; the writes are metadata_write
    # (not "mutation"/"expensive") because they touch package draft state only.
    preview = _find_action(plan, "engineering_template.preview")
    assert preview is not None and preview["mode"] == "read_only"
    assert preview["requires_approval"] is False
    save_draft = _find_action(plan, "engineering_template.save_draft")
    assert save_draft is not None and save_draft["mode"] == "metadata_write"
    assert save_draft["requires_approval"] is True
    cad_fixture = _find_action(plan, "engineering_template.generate_cad_fixture")
    assert cad_fixture is not None and cad_fixture["mode"] == "metadata_write"
    assert cad_fixture["requires_approval"] is True
    # The cad fixture action should advertise downstream stale impacts so the
    # UI / reviewer can see that approval will mark mesh/results stale.
    assert any("simulation/mesh" in s for s in cad_fixture["stale_impacts"])

    # The planner never proposes cae.run_solver from natural language.
    assert "cae.run_solver" not in proposed_tool_names
    assert plan["agent_context"]["agent_brief"]["next_decision_focus"]
    assert plan["action_selection"]["policy"]
    assert any(a["id"] == "generate_cad_fixture" for a in plan["action_selection"]["allowed_actions"])

    # required_approvals lists the ids of every approval-gated action.
    approval_ids = set(plan["required_approvals"])
    for action in plan["actions"]:
        if action["requires_approval"]:
            assert action["id"] in approval_ids


# ── Demo 2: incomplete drone-arm request ─────────────────────────────────────


def test_intent_plan_for_drone_arm_returns_honest_missing_information(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "drone", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        "/api/intent-planner/plan",
        json={
            "message": "Help me design a drone arm and check whether it is strong enough.",
            "project_id": project_id,
        },
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()

    # No template match.
    assert plan["inferred_template_id"] is None
    # The classifier should recognise it as a structural request but not commit
    # to the linear-static pilot path (no template).
    assert plan["inferred_engineering_domain"] in {"structural_unspecified", "unclassified"}

    missing = plan["missing_information"]
    assert any("template_match" in item for item in missing)
    assert "material" in missing
    assert any(item.startswith("primary_dimensions") or item == "primary_dimensions" for item in missing)
    assert any(item.startswith("load") for item in missing)
    assert any(item.startswith("boundary_conditions") or item == "boundary_conditions" for item in missing)
    assert any(item.startswith("design_targets") or item == "design_targets" for item in missing)

    # Only safe inspection actions are proposed; no mutating / expensive steps.
    for action in plan["actions"]:
        assert action["mode"] == "read_only"
        assert action["requires_approval"] is False
    assert plan["required_approvals"] == []

    # Honest evidence scope — no fake claim that AIENG can analyse this yet.
    assert any("Safe inspection only" in line for line in plan["evidence_scope"])

    # The planner must NOT silently invent a template.
    tool_names = {a["tool_name"] for a in plan["actions"]}
    assert "engineering_template.save_draft" not in tool_names
    assert "engineering_template.generate_cad_fixture" not in tool_names
    assert "cae.run_solver" not in tool_names


# ── Demo 3: premature solver execution request ───────────────────────────────


def test_intent_plan_for_run_solver_now_reports_readiness_gaps_and_proposes_solver(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "solver-now", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        "/api/intent-planner/plan",
        json={
            "message": "Run the structural simulation now and tell me the stress.",
            "project_id": project_id,
        },
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()

    # Solver is now proposed (approval-gated) instead of refused outright.
    tool_names = {a["tool_name"] for a in plan["actions"]}
    assert "cae.run_solver" in tool_names
    # Preflight is still offered as the safe first step.
    assert "cae.prepare_solver_run" in tool_names

    # Missing information should surface concrete readiness gaps coming from
    # the structural preflight (mesh / settings / load case / deck / ccx).
    missing_joined = "\n".join(plan["missing_information"])
    assert "solver_run_readiness" in missing_joined

    # The solver action itself is expensive / approval-gated.
    solver_action = next(a for a in plan["actions"] if a["tool_name"] == "cae.run_solver")
    assert solver_action["requires_approval"] is True


# ── Demo 4: approval-required action cannot execute silently ─────────────────


def test_intent_action_execute_save_draft_awaits_approval(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "approval", "p.aieng")
    _make_minimal_package(pkg)

    plan_resp = client.post(
        "/api/intent-planner/plan",
        json={"message": CANTILEVER_REQUEST, "project_id": project_id},
    )
    assert plan_resp.status_code == 200, plan_resp.text
    plan = plan_resp.json()
    save_draft = _find_action(plan, "engineering_template.save_draft")
    assert save_draft is not None
    assert save_draft["requires_approval"] is True

    # Capture the package digest before executing the approval-required action.
    before_bytes = pkg.read_bytes()

    resp = client.post(
        f"/api/intent-planner/actions/{save_draft['id']}/execute",
        json={"plan": plan},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    run = body["run"]

    # The runtime must pause on approval; no package mutation may happen yet.
    assert run["status"] == "awaiting_approval", run
    assert pkg.read_bytes() == before_bytes, (
        "Approval-required intent action wrote to the package without approval."
    )

    # The action card is echoed back so the UI can render it.
    assert body["action"]["tool_name"] == "engineering_template.save_draft"
    assert body["action"]["mode"] == "metadata_write"

    # Approving the run completes the write.
    approve = client.post(f"/api/runtime/runs/{run['run_id']}/approve")
    assert approve.status_code == 200, approve.text
    approved = approve.json()
    assert approved["status"] == "completed", approved
    after_members = set()
    with zipfile.ZipFile(pkg, "r") as zf:
        after_members = set(zf.namelist())
    assert "task/engineering_setup_draft.json" in after_members
    assert "task/cad_template_preview.py" in after_members
    assert "task/fea_setup_draft.json" in after_members
    assert "task/design_targets_suggestions.yaml" in after_members


def test_intent_action_execute_rejects_unknown_action_id(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "unknown-action", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        "/api/intent-planner/actions/action_does_not_exist/execute",
        json={"plan": {"plan_id": "p1", "actions": [], "project_id": project_id}},
    )
    assert resp.status_code == 404


def test_intent_plan_requires_message(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    resp = client.post("/api/intent-planner/plan", json={"project_id": None})
    assert resp.status_code == 400
