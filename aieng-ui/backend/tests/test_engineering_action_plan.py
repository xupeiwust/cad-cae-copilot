import json
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.app_factory import create_app
from app.config import Settings
from app.engineering_action_plan import classify_engineering_message

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


def test_change_material_beats_broad_cad_refine() -> None:
    plan = classify_engineering_message(
        "change material to steel",
        has_generated_cad=True,
        has_setup=True,
    )

    assert plan["intent"] == "change_material"
    assert plan["extracted_inputs"]["material_hint"] == "Steel-1045"
    assert plan["action"]["id"] == "cae.change_material"


def test_set_target_beats_broad_cad_refine() -> None:
    plan = classify_engineering_message(
        "set stress limit to 250 MPa",
        has_generated_cad=True,
    )

    assert plan["intent"] == "set_target"
    assert plan["action"]["id"] == "targets.set_from_chat"


def test_generation_beats_refine_for_new_part_phrase() -> None:
    plan = classify_engineering_message(
        "make a bracket with four M6 holes",
        has_generated_cad=True,
    )

    assert plan["intent"] == "generate"
    assert plan["action"]["id"] == "cad.generate"


def test_refine_cad_when_existing_model_and_no_specific_intent() -> None:
    plan = classify_engineering_message(
        "make it thicker",
        has_generated_cad=True,
    )

    assert plan["intent"] == "refine"
    assert plan["action"]["id"] == "cad.refine"


def test_refine_mesh_extracts_mesh_size() -> None:
    plan = classify_engineering_message("refine mesh to 1.25 mm")

    assert plan["intent"] == "refine_mesh"
    assert plan["extracted_inputs"]["mesh_size_mm"] == 1.25
    assert plan["execution_policy"]["approval_tier"] == "gate"
    assert plan["execution_policy"]["must_not_auto_execute_external_tools"] is True
    assert plan["action"]["tool_chain"] == ["cae.generate_mesh", "cae.prepare_solver_run"]
    assert "run-simulation-stream" not in plan["action"]["endpoint"]


def test_simulation_plan_uses_mcp_first_solver_chain() -> None:
    plan = classify_engineering_message("run the simulation")

    assert plan["intent"] == "simulate"
    assert plan["action"]["id"] == "cae.simulate"
    assert plan["action"]["endpoint"] == "MCP cae.prepare_solver_run -> cae.run_solver"
    assert plan["action"]["tool_chain"] == ["cae.prepare_solver_run", "cae.run_solver"]
    assert "run-simulation-stream" not in json.dumps(plan["action"])


def test_action_plan_returns_independent_action_copy() -> None:
    plan = classify_engineering_message("run simulation")
    plan["action"]["writes"].append("mutated")

    fresh = classify_engineering_message("run simulation")

    assert "mutated" not in fresh["action"]["writes"]


def test_endpoint_uses_package_state_for_existing_cad(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    project_id = "aabbccdd2211"
    project_dir = settings.projects_root / project_id
    package_dir = project_dir / "packages"
    package_dir.mkdir(parents=True)
    pkg = package_dir / "model.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("geometry/source.py", "result = None\n")
        zf.writestr("simulation/setup.yaml", "material_name: Al6061-T6\n")
    (project_dir / "metadata.json").write_text(
        json.dumps({"id": project_id, "name": "Action Plan", "aieng_file": "packages/model.aieng"}),
        encoding="utf-8",
    )

    client = TestClient(create_app(settings))
    resp = client.post(
        f"/api/projects/{project_id}/engineering-action-plan",
        json={"message": "make it thicker"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "refine"
    assert data["project_state"]["has_generated_cad"] is True
    assert data["project_state"]["has_setup"] is True
