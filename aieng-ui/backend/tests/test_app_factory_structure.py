from __future__ import annotations

import ast
from pathlib import Path

from app import app_factory
from app.config import Settings


def test_app_factory_remains_a_lightweight_composition_layer() -> None:
    source_path = Path(app_factory.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    create_app = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "create_app"
    )

    calls = {
        node.func.id
        for node in ast.walk(create_app)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    expected_registrars = {
        "register_agent_routes",
        "register_cad_live_routes",
        "register_discovery_routes",
        "register_evidence_routes",
        "register_intent_planner_routes",
        "register_project_analysis_routes",
        "register_project_chat_routes",
        "register_project_workflow_routes",
        "register_runtime_routes",
        "register_settings_routes",
        "register_system_routes",
        "register_runtime_tools",
    }

    assert len(source.splitlines()) < 200
    assert expected_registrars <= calls
    assert "_sync_main_symbols" not in calls


def test_app_factory_openapi_schema_builds(tmp_path: Path) -> None:
    settings = Settings(
        platform_root=tmp_path / "platform",
        workspace_root=tmp_path / "workspace",
        data_root=tmp_path / "data",
        aieng_root=tmp_path / "workspace" / "aieng",
        sample_step=tmp_path / "workspace" / "sample.step",
    )
    schema = app_factory.create_app(settings).openapi()

    assert schema["info"]["title"] == "aieng-platform"
    assert "/api/projects" in schema["paths"]
