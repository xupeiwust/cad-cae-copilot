from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_AIENG_SRC = _WORKSPACE_ROOT / "aieng" / "src"
_TESTS_DIR = Path(__file__).resolve().parent
if str(_AIENG_SRC) not in sys.path:
    sys.path.insert(0, str(_AIENG_SRC))
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from aieng.converters.assembly_topopt import (
    ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH,
    ASSEMBLY_TOPOPT_EXECUTION_PATH,
    ASSEMBLY_TOPOPT_PROBLEM_PATH,
    PART_OPTIMIZED_SHAPE_IR_TEMPLATE,
    PART_TOPOLOGY_OPTIMIZATION_TEMPLATE,
    STANDARD_TOPOPT_PROBLEM_PATH,
    write_assembly_topopt_problem,
)
from app.main import Settings, create_app, default_project, project_dir, save_project
from starlette.testclient import TestClient

from assembly_topopt_demo_fixture import (
    FROZEN_PART_IDS,
    PROCESS_ARTIFACTS,
    SELECTED_PART_ID,
    SETUP_ARTIFACTS,
    expected_run_artifacts,
    write_demo_package,
)


def _make_settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=_WORKSPACE_ROOT / "aieng",
        sample_step=workspace / "sample.step",
    )


def _make_project_with_demo_package(tmp_path: Path, *, safe: bool) -> tuple[TestClient, str, Path]:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("assembly-topopt-demo" if safe else "assembly-topopt-unsafe"))
    project_id = project["id"]
    pkg = project_dir(settings, project_id) / ("assembly-topopt-demo.aieng" if safe else "assembly-topopt-unsafe.aieng")
    write_demo_package(pkg, safe=safe)
    project["aieng_file"] = pkg.name
    save_project(settings, project)
    return client, project_id, pkg


def test_canonical_demo_package_runs_full_loop_and_preserves_scope(tmp_path: Path) -> None:
    client, project_id, pkg = _make_project_with_demo_package(tmp_path, safe=True)

    process = client.post(f"/api/projects/{project_id}/assembly/process", json={})
    assert process.status_code == 200
    process_body = process.json()
    assert process_body["assembly_present"] is True
    assert process_body["validation_status"] == "passed"
    assert process_body["assembly_cae_model_status"] == "ready"

    setup = write_assembly_topopt_problem(pkg, resolution=12, max_iters=6, use_result_guidance=True)
    assert setup["status"] == "ready"
    assert setup["selected_part_id"] == SELECTED_PART_ID
    assert setup["standard_problem_emitted"] is True
    assert setup["problem"]["provenance"]["contact_physics_modeled"] is False
    assert setup["problem"]["provenance"]["bolt_preload_modeled"] is False

    run = client.post(
        f"/api/projects/{project_id}/assembly/topology-optimization/run",
        json={"method": "voxels", "representation": "manifold_mesh"},
    )
    assert run.status_code == 200
    run_body = run.json()["assembly_topology_optimization"]
    assert run_body["status"] == "derived_part_artifact_written"
    assert run_body["selected_part_id"] == SELECTED_PART_ID

    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        required = PROCESS_ARTIFACTS | SETUP_ARTIFACTS | expected_run_artifacts()
        required.add("analysis/assembly_result_map.json")
        assert required <= names
        assert STANDARD_TOPOPT_PROBLEM_PATH in names
        assert "geometry/shape_ir.json" not in names
        for part_id in FROZEN_PART_IDS:
            assert PART_TOPOLOGY_OPTIMIZATION_TEMPLATE.format(part_id=part_id) not in names
            assert PART_OPTIMIZED_SHAPE_IR_TEMPLATE.format(part_id=part_id) not in names

        problem = json.loads(zf.read(ASSEMBLY_TOPOPT_PROBLEM_PATH))
        standard = json.loads(zf.read(STANDARD_TOPOPT_PROBLEM_PATH))
        execution = json.loads(zf.read(ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH))
        execution_diag = json.loads(zf.read(ASSEMBLY_TOPOPT_EXECUTION_PATH))
        part_result = json.loads(
            zf.read(PART_TOPOLOGY_OPTIMIZATION_TEMPLATE.format(part_id=SELECTED_PART_ID))
        )
        part_shape = json.loads(
            zf.read(PART_OPTIMIZED_SHAPE_IR_TEMPLATE.format(part_id=SELECTED_PART_ID))
        )
        manifest = json.loads(zf.read("provenance/conversion_manifest.json"))

    assert len(problem["candidate_parts"]) == 1
    assert {region["interface_id"] for region in problem["preserve_regions"]} >= {"if_mount", "if_load"}
    assert execution["assembly_result_guidance"]["available"] is True
    assert execution["assembly_result_guidance"]["preserve_or_reinforce_regions"][0]["region_id"] == "hot_stress"
    assert execution["assembly_result_guidance"]["stiffness_sensitive_regions"][0]["region_id"] == "tip_deflection"
    assert execution["topology_optimization"]["result"]["compliance_history"]
    assert execution["topology_optimization"]["result"]["result_guidance_consumed"] is True
    assert part_result["problem"]["assembly_preserve_constraints"]["preserve_regions_total"] >= 2
    assert part_shape["assembly_writeback"]["selected_part_id"] == SELECTED_PART_ID
    assert part_shape["assembly_writeback"]["original_geometry_ref_preserved"] == "geometry/bracket.step"
    assert {
        "analysis/assembly_topopt_problem.json",
        "analysis/topology_optimization_problem.json",
        "assembly/assembly_ir.json",
        "assembly/connection_graph.json",
        "assembly/interface_resolution.json",
        "analysis/assembly_result_map.json",
    } <= set(execution["provenance"]["source_artifacts"])
    assert standard["derivation"]["contact_physics_modeled"] is False
    assert standard["derivation"]["bolt_preload_modeled"] is False
    assert execution["provenance"]["contact_physics_modeled"] is False
    assert execution["provenance"]["bolt_preload_modeled"] is False
    assert execution_diag["summary"]["writeback_status"] == "derived_part_artifact_written"
    assert manifest["assembly"]["assembly_topopt_execution_status"] == "derived_part_artifact_written"
    assert manifest["assembly"]["assembly_topopt_part_shape_path"] == (
        f"parts/{SELECTED_PART_ID}/geometry/optimized_shape_ir.json"
    )


def test_canonical_demo_package_unsafe_data_stays_needs_input_and_does_not_overwrite(tmp_path: Path) -> None:
    client, project_id, pkg = _make_project_with_demo_package(tmp_path, safe=False)

    process = client.post(f"/api/projects/{project_id}/assembly/process", json={})
    assert process.status_code == 200
    assert process.json()["assembly_present"] is True

    setup = write_assembly_topopt_problem(pkg, resolution=12, max_iters=6, use_result_guidance=True)
    assert setup["status"] == "needs_user_input"
    assert setup["standard_problem_emitted"] is False
    assert "missing_loads_supports" in setup["diagnostics"]

    with zipfile.ZipFile(pkg) as zf:
        before_names = set(zf.namelist())
        assert STANDARD_TOPOPT_PROBLEM_PATH not in before_names

    run = client.post(
        f"/api/projects/{project_id}/assembly/topology-optimization/run",
        json={"method": "voxels", "representation": "manifold_mesh"},
    )
    assert run.status_code == 200
    run_body = run.json()["assembly_topology_optimization"]
    assert run_body["status"] == "needs_user_input"
    assert "missing_topology_optimization_problem" in run_body["diagnostics"]

    with zipfile.ZipFile(pkg) as zf:
        after_names = set(zf.namelist())
        assert ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH in after_names
        assert ASSEMBLY_TOPOPT_EXECUTION_PATH in after_names
        assert PART_TOPOLOGY_OPTIMIZATION_TEMPLATE.format(part_id=SELECTED_PART_ID) not in after_names
        assert PART_OPTIMIZED_SHAPE_IR_TEMPLATE.format(part_id=SELECTED_PART_ID) not in after_names
        assert "geometry/shape_ir.json" not in after_names
        assert PART_OPTIMIZED_SHAPE_IR_TEMPLATE.format(part_id="wall") not in after_names
        execution = json.loads(zf.read(ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH))
        diag = json.loads(zf.read(ASSEMBLY_TOPOPT_EXECUTION_PATH))

    assert execution["writeback"]["status"] == "not_attempted"
    assert execution["provenance"]["optimizer_executed"] is False
    assert diag["status"] == "needs_user_input"
    assert after_names - before_names <= {
        ASSEMBLY_TOPOLOGY_OPTIMIZATION_PATH,
        ASSEMBLY_TOPOPT_EXECUTION_PATH,
        "provenance/conversion_manifest.json",
    }