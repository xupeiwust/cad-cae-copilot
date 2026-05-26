"""Tests for the .aieng patch proposal bridge."""

import json
from pathlib import Path
from typing import Any

import pytest

from freecad_mcp.aieng_bridge.stub_executor import StubFreecadExecutor
from freecad_mcp.bridge.executor import FreecadExecutor
from freecad_mcp.tools_aieng import register_aieng_tools


class SpyExecutor(FreecadExecutor):
    """Mock executor that returns canned responses without a real FreeCAD connection."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._results: dict[str, Any] = {}
        self._default_result: dict[str, Any] = {"success": True, "result": {}}

    def set_result(self, key: str, result: dict[str, Any]) -> None:
        self._results[key] = result

    def set_default_result(self, result: dict[str, Any]) -> None:
        self._default_result = result

    async def execute_async(self, code: str) -> dict[str, Any]:
        self.calls.append(code)
        for key, value in self._results.items():
            if key in code:
                return value
        return self._default_result

    async def get_version_async(self) -> dict[str, Any]:
        self.calls.append("get_version")
        return {"version": "0.21.0", "revision": "12345", "gui_available": False}


def _make_mcp_with_executor() -> tuple[Any, SpyExecutor]:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(name="test")
    executor = SpyExecutor()
    register_aieng_tools(mcp, executor)
    return mcp, executor


# ---------------------------------------------------------------------------
# Parse tests
# ---------------------------------------------------------------------------

class TestParsePatch:
    @pytest.mark.asyncio
    async def test_parse_direct_patch_json(self) -> None:
        mcp, _ = _make_mcp_with_executor()
        tool = mcp._tool_manager._tools["aieng_parse_patch"].fn
        response = await tool(
            patch_json={
                "patch_id": "p1",
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "feat_base",
                        "parameter_name": "Length",
                        "new_value": 20.0,
                    }
                ],
            }
        )

        assert response["status"] == "success"
        assert response["patch_id"] == "p1"
        assert len(response["supported_operations"]) == 1
        assert response["supported_operations"][0]["operation"] == "modify_parameter"
        assert response["claim_policy"]["claims_advanced"] is False

    @pytest.mark.asyncio
    async def test_parse_alias_fields(self) -> None:
        mcp, _ = _make_mcp_with_executor()
        tool = mcp._tool_manager._tools["aieng_parse_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {
                        "op": "modify_parameter",
                        "feature_id": "feat_base",
                        "parameter": "Length",
                        "value": 20.0,
                    }
                ],
            }
        )

        assert response["status"] == "success"
        assert len(response["supported_operations"]) == 1
        assert response["supported_operations"][0]["operation"] == "modify_parameter"
        assert response["supported_operations"][0]["target_feature_id"] == "feat_base"
        assert response["supported_operations"][0]["parameter_name"] == "Length"
        assert response["supported_operations"][0]["new_value"] == 20.0

    @pytest.mark.asyncio
    async def test_parse_unsupported_operation_reported(self) -> None:
        mcp, _ = _make_mcp_with_executor()
        tool = mcp._tool_manager._tools["aieng_parse_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "feat_base", "parameter_name": "Length", "new_value": 20.0},
                    {"operation": "remove_feature", "target_feature_id": "feat_hole"},
                ],
            }
        )

        assert response["status"] == "success"
        assert len(response["supported_operations"]) == 1
        assert len(response["unsupported_operations"]) == 1
        assert response["unsupported_operations"][0]["reason"] == "Operation 'remove_feature' is not supported"

    @pytest.mark.asyncio
    async def test_parse_patch_is_read_only(self, tmp_path: Path) -> None:
        mcp, _ = _make_mcp_with_executor()
        patch_file = tmp_path / "patch.json"
        patch_file.write_text(
            json.dumps(
                {
                    "patch_id": "p1",
                    "operations": [
                        {"operation": "modify_parameter", "target_feature_id": "feat_base", "parameter_name": "Length", "new_value": 20.0}
                    ],
                }
            )
        )

        tool = mcp._tool_manager._tools["aieng_parse_patch"].fn
        response = await tool(patch_path=str(patch_file))

        assert response["status"] == "success"
        # No evidence or trace files should be written
        assert not (tmp_path / "results").exists()
        assert not (tmp_path / "provenance").exists()


# ---------------------------------------------------------------------------
# Execute tests — standalone mode
# ---------------------------------------------------------------------------

class TestExecutePatchStandalone:
    @pytest.mark.asyncio
    async def test_execute_modify_parameter_standalone(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "patch_id": "p1",
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            }
        )

        assert response["status"] == "success"
        assert response["patch_id"] == "p1"
        assert len(response["steps"]) == 1
        assert response["steps"][0]["status"] == "success"
        assert response["steps"][0]["result"]["old_value"] == 10.0
        assert response["claim_policy"]["claims_advanced"] is False

    @pytest.mark.asyncio
    async def test_execute_dry_run_does_not_call_backend(self) -> None:
        mcp, executor = _make_mcp_with_executor()

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            dry_run=True,
        )

        assert response["status"] == "success"
        assert len(response["steps"]) == 1
        assert response["steps"][0]["status"] == "success"
        assert response["steps"][0]["result"]["dry_run"] is True
        # Backend should not have been called
        assert not executor.calls

    @pytest.mark.asyncio
    async def test_unsupported_operation_does_not_modify(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "remove_feature", "target_feature_id": "feat_hole"},
                ],
            }
        )

        assert response["status"] == "unsupported"
        assert not executor.calls

    @pytest.mark.asyncio
    async def test_first_failure_stops_second(self) -> None:
        mcp, executor = _make_mcp_with_executor()

        class FailingExecutor(SpyExecutor):
            async def execute_async(self, code: str) -> dict[str, Any]:
                self.calls.append(code)
                raise RuntimeError("FreeCAD crashed")

        failing = FailingExecutor()
        from mcp.server.fastmcp import FastMCP
        mcp2 = FastMCP(name="test")
        register_aieng_tools(mcp2, failing)

        tool = mcp2._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0},
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Width", "new_value": 30.0},
                ],
            }
        )

        assert response["status"] == "failed"
        assert len(response["steps"]) == 1
        assert response["steps"][0]["status"] == "failed"
        assert "FreeCAD crashed" in str(response["steps"][0]["errors"])


# ---------------------------------------------------------------------------
# Execute tests — .aieng-enhanced mode with guards
# ---------------------------------------------------------------------------

class TestExecutePatchAiengEnhanced:
    @pytest.mark.asyncio
    async def test_execute_with_package_path_uses_guards(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "task").mkdir()
        import yaml
        (tmp_path / "task" / "task_spec.yaml").write_text(
            yaml.safe_dump({"allowed_operations": ["cad_set_parameter"]})
        )
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": True},
                    "freecad_object_name": "Box",
                    "parameters": [
                        {"name": "Length", "freecad_parameter_name": "Length"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        assert response["persistence"] is not None
        assert (tmp_path / "results" / "evidence_index.json").exists()
        assert (tmp_path / "provenance" / "tool_trace.json").exists()

    @pytest.mark.asyncio
    async def test_semantic_only_feature_rejected(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": False},
                    "freecad_object_name": "Box",
                    "parameters": [
                        {"name": "Length", "freecad_parameter_name": "Length"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            package_path=str(tmp_path),
        )

        assert response["status"] == "rejected"
        assert len(response["steps"]) == 1
        assert response["steps"][0]["status"] == "rejected"
        assert any("semantic-only" in e.lower() or "not executable" in e.lower() for e in response["steps"][0]["errors"])
        # Backend should not have been called
        assert not executor.calls

    @pytest.mark.asyncio
    async def test_protected_region_rejected(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": True},
                    "freecad_object_name": "Box",
                    "parameters": [
                        {"name": "Length", "freecad_parameter_name": "Length"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))
        constraints = {
            "protected_regions": [
                {"name": "mounting_zone", "features": ["Box"]}
            ]
        }
        (tmp_path / "graph" / "constraints.json").write_text(json.dumps(constraints))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            package_path=str(tmp_path),
        )

        assert response["status"] == "rejected"
        assert len(response["steps"]) == 1
        assert response["steps"][0]["status"] == "rejected"
        assert any("protected" in e.lower() for e in response["steps"][0]["errors"])
        assert not executor.calls

    @pytest.mark.asyncio
    async def test_unresolved_feature_parameter_rejected(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        # Feature exists but has no freecad_object_name mapping
        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": True},
                    "parameters": [
                        {"name": "Length", "freecad_parameter_name": "Length"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            package_path=str(tmp_path),
        )

        assert response["status"] == "rejected"
        assert len(response["steps"]) == 1
        assert response["steps"][0]["status"] == "rejected"
        assert any("resolve" in e.lower() for e in response["steps"][0]["errors"])
        assert not executor.calls

    @pytest.mark.asyncio
    async def test_persist_without_package_path_rejected(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            persist_to_aieng=True,
        )

        assert response["status"] == "rejected"
        assert response["primary_error_code"] == "POLICY_VIOLATION"
        assert any("package_path" in e.lower() for e in response["errors"])

    @pytest.mark.asyncio
    async def test_persist_failure_returns_error_code(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        from freecad_mcp.aieng_bridge import patch as patch_mod
        from freecad_mcp.aieng_bridge.persistence import PersistenceError
        from freecad_mcp.aieng_bridge.context import AiengPackageContext

        def standalone_context(package_path: str | None) -> AiengPackageContext:
            return AiengPackageContext(mode="standalone", available=False)

        monkeypatch.setattr(patch_mod, "load_aieng_context", standalone_context)

        def failing_persist(*args: Any, **kwargs: Any) -> Any:
            raise PersistenceError("disk full")

        monkeypatch.setattr(patch_mod, "persist_standard_result_to_aieng", failing_persist)

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            persist_to_aieng=True,
            package_path=str(tmp_path),
        )

        assert response["status"] == "success"
        assert response["primary_error_code"] == "PERSISTENCE_FAILED"
        assert any("disk full" in e.lower() for e in response["errors"])

    @pytest.mark.asyncio
    async def test_persist_does_not_modify_claim_map(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": True},
                    "freecad_object_name": "Box",
                    "parameters": [
                        {"name": "Length", "freecad_parameter_name": "Length"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        after = json.loads((tmp_path / "results" / "claim_map.json").read_text())
        assert after == claim_map

    @pytest.mark.asyncio
    async def test_input_fcstd_passed_to_set_parameter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When input_fcstd is provided, it must be forwarded to _execute_set_parameter."""
        mcp, executor = _make_mcp_with_executor()

        captured_calls: list[dict] = []

        async def capture_set_parameter(*args: Any, **kwargs: Any) -> dict[str, Any]:
            captured_calls.append({"args": args, "kwargs": kwargs})
            return {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}

        from freecad_mcp.aieng_bridge import patch as patch_mod
        monkeypatch.setattr(patch_mod, "_execute_set_parameter", capture_set_parameter)

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": True},
                    "freecad_object_name": "Box",
                    "parameters": [
                        {"name": "Length", "freecad_parameter_name": "Length"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        fcstd_path = str(tmp_path / "input.FCStd")

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            package_path=str(tmp_path),
            input_fcstd=fcstd_path,
        )

        assert response["status"] == "success"
        assert len(captured_calls) == 1
        assert captured_calls[0]["kwargs"].get("input_fcstd") == fcstd_path

    @pytest.mark.asyncio
    async def test_input_fcstd_passed_to_export_calls(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When input_fcstd is provided with export flags, it must be forwarded to export helpers."""
        mcp, executor = _make_mcp_with_executor()

        set_calls: list[dict] = []
        export_step_calls: list[dict] = []
        export_fcstd_calls: list[dict] = []

        async def capture_set_parameter(*args: Any, **kwargs: Any) -> dict[str, Any]:
            set_calls.append({"args": args, "kwargs": kwargs})
            return {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}

        async def capture_export_step(*args: Any, **kwargs: Any) -> dict[str, Any]:
            export_step_calls.append({"args": args, "kwargs": kwargs})
            return {"file_path": args[1] if len(args) > 1 else kwargs.get("file_path")}

        async def capture_export_fcstd(*args: Any, **kwargs: Any) -> dict[str, Any]:
            export_fcstd_calls.append({"args": args, "kwargs": kwargs})
            return {"file_path": args[1] if len(args) > 1 else kwargs.get("file_path")}

        from freecad_mcp.aieng_bridge import patch as patch_mod
        monkeypatch.setattr(patch_mod, "_execute_set_parameter", capture_set_parameter)
        monkeypatch.setattr(patch_mod, "_execute_export_step", capture_export_step)
        monkeypatch.setattr(patch_mod, "_execute_export_fcstd", capture_export_fcstd)

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {"name": "thickness_mm", "freecad_parameter_name": "Thickness"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        fcstd_path = str(tmp_path / "input.FCStd")

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "patch_id": "p1",
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "feat_base_plate_001", "parameter_name": "thickness_mm", "new_value": 8.0}
                ],
            },
            package_path=str(tmp_path),
            export_modified_step=True,
            export_modified_fcstd=True,
            input_fcstd=fcstd_path,
        )

        assert response["status"] == "success"
        assert len(set_calls) == 1
        assert set_calls[0]["kwargs"].get("input_fcstd") == fcstd_path
        assert len(export_step_calls) == 1
        assert export_step_calls[0]["kwargs"].get("input_fcstd") == fcstd_path
        assert len(export_fcstd_calls) == 1
        assert export_fcstd_calls[0]["kwargs"].get("input_fcstd") == fcstd_path

    @pytest.mark.asyncio
    async def test_without_input_fcstd_defaults_to_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When input_fcstd is omitted, _execute_set_parameter receives None (backward compat)."""
        mcp, executor = _make_mcp_with_executor()

        captured_calls: list[dict] = []

        async def capture_set_parameter(*args: Any, **kwargs: Any) -> dict[str, Any]:
            captured_calls.append({"args": args, "kwargs": kwargs})
            return {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}

        from freecad_mcp.aieng_bridge import patch as patch_mod
        monkeypatch.setattr(patch_mod, "_execute_set_parameter", capture_set_parameter)

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": True},
                    "freecad_object_name": "Box",
                    "parameters": [
                        {"name": "Length", "freecad_parameter_name": "Length"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            package_path=str(tmp_path),
        )

        assert response["status"] == "success"
        assert len(captured_calls) == 1
        assert captured_calls[0]["kwargs"].get("input_fcstd") is None


# ---------------------------------------------------------------------------
# Tests: fixture, export, run records
# ---------------------------------------------------------------------------

class TestFixtureAndExport:
    @pytest.mark.asyncio
    async def test_example_fixture_loads_as_context(self) -> None:
        from freecad_mcp.aieng_bridge.context import load_aieng_context

        fixture_dir = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / "package"
        ctx = load_aieng_context(str(fixture_dir))

        assert ctx.mode == "aieng_enhanced"
        assert ctx.available is True
        assert ctx.manifest is not None
        assert ctx.feature_graph is not None
        features = ctx.feature_graph.get("features", {})
        assert "feat_base_plate_001" in features
        assert "feat_mounting_holes_001" in features
        assert "feat_semantic_rib_001" in features

    @pytest.mark.asyncio
    async def test_valid_fixture_patch_parses(self) -> None:
        mcp, _ = _make_mcp_with_executor()
        tool = mcp._tool_manager._tools["aieng_parse_patch"].fn

        fixture_dir = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket"
        response = await tool(patch_path=str(fixture_dir / "patches" / "reduce_base_plate_thickness.json"))

        assert response["status"] == "success"
        assert len(response["supported_operations"]) == 1
        assert response["supported_operations"][0]["operation"] == "modify_parameter"
        assert response["supported_operations"][0]["target_feature_id"] == "feat_base_plate_001"

    @pytest.mark.asyncio
    async def test_fixture_protected_patch_rejected(self) -> None:
        mcp, _ = _make_mcp_with_executor()
        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn

        fixture_dir = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket"
        response = await tool(
            patch_path=str(fixture_dir / "patches" / "reject_protected_hole_edit.json"),
            package_path=str(fixture_dir / "package"),
        )

        assert response["status"] == "rejected"
        assert len(response["steps"]) == 1
        assert any("protected" in e.lower() for e in response["steps"][0]["errors"])

    @pytest.mark.asyncio
    async def test_fixture_semantic_only_patch_rejected(self) -> None:
        mcp, _ = _make_mcp_with_executor()
        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn

        fixture_dir = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket"
        response = await tool(
            patch_path=str(fixture_dir / "patches" / "reject_semantic_only_edit.json"),
            package_path=str(fixture_dir / "package"),
        )

        assert response["status"] == "rejected"
        assert len(response["steps"]) == 1
        assert any("semantic-only" in e.lower() or "not executable" in e.lower() for e in response["steps"][0]["errors"])

    @pytest.mark.asyncio
    async def test_export_options_record_artifacts_written(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "BasePlate", "parameter_name": "Thickness", "old_value": 10.0, "new_value": 8.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {"name": "thickness_mm", "freecad_parameter_name": "Thickness"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "patch_id": "p1",
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "feat_base_plate_001", "parameter_name": "thickness_mm", "new_value": 8.0}
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
            export_modified_step=True,
            export_modified_fcstd=True,
        )

        assert response["status"] == "success"
        assert len(response["artifacts_written"]) >= 2
        assert any(".step" in a for a in response["artifacts_written"])
        assert any(".FCStd" in a for a in response["artifacts_written"])

    @pytest.mark.asyncio
    async def test_patch_execution_record_created(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "BasePlate", "parameter_name": "Thickness", "old_value": 10.0, "new_value": 8.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {"name": "thickness_mm", "freecad_parameter_name": "Thickness"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "patch_id": "p1",
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "feat_base_plate_001", "parameter_name": "thickness_mm", "new_value": 8.0}
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        runs_dir = tmp_path / "execution" / "patch_runs"
        assert runs_dir.exists()
        run_files = list(runs_dir.glob("*.json"))
        assert len(run_files) == 1

        record = json.loads(run_files[0].read_text())
        assert record["patch_id"] == "p1"
        assert record["status"] == "success"
        assert record["claim_policy"]["claims_advanced"] is False

    @pytest.mark.asyncio
    async def test_multiple_runs_do_not_overwrite(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "BasePlate", "parameter_name": "Thickness", "old_value": 10.0, "new_value": 8.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {"name": "thickness_mm", "freecad_parameter_name": "Thickness"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        for _ in range(3):
            response = await tool(
                patch_json={
                    "patch_id": "p1",
                    "operations": [
                        {"operation": "modify_parameter", "target_feature_id": "feat_base_plate_001", "parameter_name": "thickness_mm", "new_value": 8.0}
                    ],
                },
                package_path=str(tmp_path),
                persist_to_aieng=True,
            )
            assert response["status"] == "success"

        runs_dir = tmp_path / "execution" / "patch_runs"
        run_files = sorted(runs_dir.glob("*.json"))
        assert len(run_files) == 3
        assert "_run_001" in run_files[0].name
        assert "_run_002" in run_files[1].name
        assert "_run_003" in run_files[2].name

    @pytest.mark.asyncio
    async def test_claim_map_unchanged_after_export_and_run_record(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "BasePlate", "parameter_name": "Thickness", "old_value": 10.0, "new_value": 8.0}}
        )

        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {"name": "thickness_mm", "freecad_parameter_name": "Thickness"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "patch_id": "p1",
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "feat_base_plate_001", "parameter_name": "thickness_mm", "new_value": 8.0}
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
            export_modified_step=True,
            export_modified_fcstd=True,
        )

        assert response["status"] == "success"
        after = json.loads((tmp_path / "results" / "claim_map.json").read_text())
        assert after == claim_map


def test_demo_script_runs() -> None:
    """Verify the demo script exits cleanly in mock mode."""
    import subprocess
    import sys

    script = Path(__file__).resolve().parent.parent / "scripts" / "run_aieng_patch_demo.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)

    assert result.returncode == 0, f"Demo script failed:\n{result.stderr}"
    assert "Demo completed successfully" in result.stdout
    assert "claim_map.json: UNCHANGED" in result.stdout


# ---------------------------------------------------------------------------
# Tests: artifact metadata discipline
# ---------------------------------------------------------------------------

class TestArtifactMetadataDiscipline:
    @pytest.mark.asyncio
    async def test_artifact_metadata_includes_source_preserved(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "BasePlate", "parameter_name": "Thickness", "old_value": 10.0, "new_value": 8.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {"name": "thickness_mm", "freecad_parameter_name": "Thickness"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "patch_id": "p1",
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "feat_base_plate_001", "parameter_name": "thickness_mm", "new_value": 8.0}
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
            export_modified_step=True,
            export_modified_fcstd=True,
        )

        assert response["status"] == "success"
        evidence = json.loads((tmp_path / "results" / "evidence_index.json").read_text())
        entry = evidence["entries"][0]
        metadata = entry.get("metadata", {})

        artifacts = metadata.get("artifacts", [])
        assert len(artifacts) >= 2
        for artifact in artifacts:
            assert artifact.get("source_artifact_preserved") is True
            assert artifact.get("artifact_type") in ("modified_step", "modified_fcstd")

    @pytest.mark.asyncio
    async def test_artifact_evidence_does_not_advance_claims(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "BasePlate", "parameter_name": "Thickness", "old_value": 10.0, "new_value": 8.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {"name": "thickness_mm", "freecad_parameter_name": "Thickness"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "patch_id": "p1",
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "feat_base_plate_001", "parameter_name": "thickness_mm", "new_value": 8.0}
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
            export_modified_step=True,
            export_modified_fcstd=True,
        )

        assert response["status"] == "success"
        evidence = json.loads((tmp_path / "results" / "evidence_index.json").read_text())
        entry = evidence["entries"][0]

        assert entry.get("claims_advanced") is False
        metadata = entry.get("metadata", {})
        assert metadata.get("claims_advanced") is False

    @pytest.mark.asyncio
    async def test_evidence_metadata_includes_param_details(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "BasePlate", "parameter_name": "Thickness", "old_value": 10.0, "new_value": 8.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {"name": "thickness_mm", "freecad_parameter_name": "Thickness"}
                    ],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "patch_id": "p1",
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "feat_base_plate_001", "parameter_name": "thickness_mm", "new_value": 8.0}
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        evidence = json.loads((tmp_path / "results" / "evidence_index.json").read_text())
        entry = evidence["entries"][0]
        metadata = entry.get("metadata", {})

        assert metadata.get("target_feature_id") == "feat_base_plate_001"
        assert metadata.get("parameter_name") == "thickness_mm"
        assert metadata.get("old_value") == 10.0
        assert metadata.get("new_value") == 8.0
        assert metadata.get("producer_kind") == "freecad"
        assert metadata.get("operation") == "modify_parameter"


# ---------------------------------------------------------------------------
# MVP 1B: Stubbed execution with parameter validation
# ---------------------------------------------------------------------------

def _make_mcp_with_stub(feature_graph: dict[str, Any] | None = None) -> tuple[Any, StubFreecadExecutor]:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(name="test")
    executor = StubFreecadExecutor(feature_graph=feature_graph)
    register_aieng_tools(mcp, executor)
    return mcp, executor


class TestStubbedExecutionDirectory:
    @pytest.mark.asyncio
    async def test_stubbed_execute_valid_parameter(self, tmp_path: Path) -> None:
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {
                            "name": "thickness_mm",
                            "freecad_parameter_name": "Thickness",
                            "current_value": 10.0,
                            "type": "App::PropertyLength",
                        }
                    ],
                }
            }
        }
        mcp, executor = _make_mcp_with_stub(feature_graph)

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "patch_id": "p1",
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "feat_base_plate_001",
                        "parameter_name": "thickness_mm",
                        "new_value": 8.0,
                    }
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        assert len(response["steps"]) == 1
        assert response["steps"][0]["status"] == "success"
        assert response["steps"][0]["result"]["old_value"] == 10.0
        assert response["steps"][0]["result"]["new_value"] == 8.0
        assert response["claim_policy"]["claims_advanced"] is False
        # Evidence and trace should be written
        assert (tmp_path / "results" / "evidence_index.json").exists()
        assert (tmp_path / "provenance" / "tool_trace.json").exists()

    @pytest.mark.asyncio
    async def test_stubbed_reject_unknown_parameter(self, tmp_path: Path) -> None:
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {
                            "name": "thickness_mm",
                            "freecad_parameter_name": "Thickness",
                            "current_value": 10.0,
                        }
                    ],
                }
            }
        }
        mcp, _ = _make_mcp_with_stub(feature_graph)

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "feat_base_plate_001",
                        "parameter_name": "width_mm",
                        "new_value": 50.0,
                    }
                ],
            },
            package_path=str(tmp_path),
        )

        assert response["status"] == "rejected"
        assert len(response["steps"]) == 1
        assert response["steps"][0]["status"] == "rejected"
        # Unknown parameter is caught by resolve_feature_parameter before validation
        assert any("resolve" in e.lower() for e in response["steps"][0]["errors"])

    @pytest.mark.asyncio
    async def test_stubbed_reject_out_of_range_value(self, tmp_path: Path) -> None:
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {
                            "name": "thickness_mm",
                            "freecad_parameter_name": "Thickness",
                            "current_value": 10.0,
                            "min_value": 2.0,
                            "max_value": 20.0,
                            "type": "App::PropertyLength",
                        }
                    ],
                }
            }
        }
        mcp, _ = _make_mcp_with_stub(feature_graph)

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "feat_base_plate_001",
                        "parameter_name": "thickness_mm",
                        "new_value": 50.0,
                    }
                ],
            },
            package_path=str(tmp_path),
        )

        assert response["status"] == "rejected"
        assert len(response["steps"]) == 1
        assert response["steps"][0]["status"] == "rejected"
        assert any("exceeds maximum" in e.lower() for e in response["steps"][0]["errors"])

    @pytest.mark.asyncio
    async def test_stubbed_reject_type_mismatch(self, tmp_path: Path) -> None:
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {
                            "name": "thickness_mm",
                            "freecad_parameter_name": "Thickness",
                            "current_value": 10.0,
                            "type": "App::PropertyLength",
                        }
                    ],
                }
            }
        }
        mcp, _ = _make_mcp_with_stub(feature_graph)

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "feat_base_plate_001",
                        "parameter_name": "thickness_mm",
                        "new_value": "too_thick",
                    }
                ],
            },
            package_path=str(tmp_path),
        )

        assert response["status"] == "rejected"
        assert len(response["steps"]) == 1
        assert response["steps"][0]["status"] == "rejected"
        assert any("numeric" in e.lower() for e in response["steps"][0]["errors"])

    @pytest.mark.asyncio
    async def test_stubbed_claim_map_unchanged(self, tmp_path: Path) -> None:
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {
                            "name": "thickness_mm",
                            "freecad_parameter_name": "Thickness",
                            "current_value": 10.0,
                        }
                    ],
                }
            }
        }
        mcp, _ = _make_mcp_with_stub(feature_graph)

        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "feat_base_plate_001",
                        "parameter_name": "thickness_mm",
                        "new_value": 8.0,
                    }
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        after = json.loads((tmp_path / "results" / "claim_map.json").read_text())
        assert after == claim_map

    @pytest.mark.asyncio
    async def test_stubbed_references_marked_needs_review(self, tmp_path: Path) -> None:
        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {
                            "name": "thickness_mm",
                            "freecad_parameter_name": "Thickness",
                            "current_value": 10.0,
                        }
                    ],
                }
            }
        }
        mcp, _ = _make_mcp_with_stub(feature_graph)

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))
        (tmp_path / "objects").mkdir()
        ref_map = {
            "schema_version": "0.1.0",
            "geometry_references": [
                {
                    "ref_id": "ref_001",
                    "feature_id": "feat_base_plate_001",
                    "status": "valid",
                }
            ],
            "cae_targets": [],
        }
        (tmp_path / "objects" / "reference_map.json").write_text(json.dumps(ref_map))

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "feat_base_plate_001",
                        "parameter_name": "thickness_mm",
                        "new_value": 8.0,
                    }
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        updated_ref_map = json.loads((tmp_path / "objects" / "reference_map.json").read_text())
        assert updated_ref_map["geometry_references"][0]["status"] == "needs_review"


class TestStubbedExecutionZip:
    @pytest.mark.asyncio
    async def test_stubbed_execute_against_aieng_zip(self, tmp_path: Path) -> None:
        import zipfile

        feature_graph = {
            "features": {
                "feat_base_plate_001": {
                    "editability": {"executable": True},
                    "freecad_object_name": "BasePlate",
                    "parameters": [
                        {
                            "name": "thickness_mm",
                            "freecad_parameter_name": "Thickness",
                            "current_value": 10.0,
                        }
                    ],
                }
            }
        }

        zip_path = tmp_path / "package.aieng"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({"name": "x"}))
            zf.writestr("graph/feature_graph.json", json.dumps(feature_graph))
            zf.writestr("results/evidence_index.json", json.dumps({"entries": []}))
            zf.writestr("provenance/tool_trace.json", json.dumps({"entries": []}))

        mcp, _ = _make_mcp_with_stub(feature_graph)

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "patch_id": "zip_p1",
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "feat_base_plate_001",
                        "parameter_name": "thickness_mm",
                        "new_value": 8.0,
                    }
                ],
            },
            package_path=str(zip_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        assert response["steps"][0]["status"] == "success"
        assert response["steps"][0]["result"]["old_value"] == 10.0
        assert response["steps"][0]["result"]["new_value"] == 8.0
        assert response["claim_policy"]["claims_advanced"] is False

        # Verify evidence and trace were written into the zip
        with zipfile.ZipFile(zip_path, "r") as zf:
            evidence = json.loads(zf.read("results/evidence_index.json"))
            trace = json.loads(zf.read("provenance/tool_trace.json"))

        assert len(evidence["entries"]) == 1
        assert len(trace["entries"]) == 1
        assert evidence["entries"][0]["metadata"]["old_value"] == 10.0
        assert evidence["entries"][0]["metadata"]["new_value"] == 8.0

    @pytest.mark.asyncio
    async def test_stubbed_zip_claim_map_preserved(self, tmp_path: Path) -> None:
        import zipfile

        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": True},
                    "freecad_object_name": "Box",
                    "parameters": [
                        {"name": "Length", "freecad_parameter_name": "Length", "current_value": 10.0}
                    ],
                }
            }
        }
        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}

        zip_path = tmp_path / "package.aieng"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({"name": "x"}))
            zf.writestr("graph/feature_graph.json", json.dumps(feature_graph))
            zf.writestr("results/claim_map.json", json.dumps(claim_map))
            zf.writestr("results/evidence_index.json", json.dumps({"entries": []}))
            zf.writestr("provenance/tool_trace.json", json.dumps({"entries": []}))

        mcp, _ = _make_mcp_with_stub(feature_graph)

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "Box",
                        "parameter_name": "Length",
                        "new_value": 20.0,
                    }
                ],
            },
            package_path=str(zip_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        with zipfile.ZipFile(zip_path, "r") as zf:
            after_claim_map = json.loads(zf.read("results/claim_map.json"))
        assert after_claim_map == claim_map

    @pytest.mark.asyncio
    async def test_stubbed_zip_reject_unknown_parameter(self, tmp_path: Path) -> None:
        import zipfile

        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": True},
                    "freecad_object_name": "Box",
                    "parameters": [
                        {"name": "Length", "freecad_parameter_name": "Length", "current_value": 10.0}
                    ],
                }
            }
        }

        zip_path = tmp_path / "package.aieng"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({"name": "x"}))
            zf.writestr("graph/feature_graph.json", json.dumps(feature_graph))

        mcp, _ = _make_mcp_with_stub(feature_graph)

        tool = mcp._tool_manager._tools["aieng_execute_patch"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "Box",
                        "parameter_name": "Width",
                        "new_value": 50.0,
                    }
                ],
            },
            package_path=str(zip_path),
        )

        assert response["status"] == "rejected"
        assert any("resolve" in e.lower() for e in response["steps"][0]["errors"])

