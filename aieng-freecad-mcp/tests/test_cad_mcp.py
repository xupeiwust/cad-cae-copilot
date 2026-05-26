"""Tests for CAD MCP tools with optional .aieng context."""

import json
from pathlib import Path
from typing import Any

import pytest

from freecad_mcp.bridge.executor import FreecadExecutor
from freecad_mcp.tools_cad import register_cad_tools


class SpyExecutor(FreecadExecutor):
    """Mock executor that returns canned responses without a real FreeCAD connection."""

    def __init__(self) -> None:
        # Bypass parent __init__ to avoid config dependencies
        self.calls: list[str] = []
        self._results: dict[str, Any] = {}
        self._default_result: dict[str, Any] = {"success": True, "result": {}}

    def set_result(self, key: str, result: dict[str, Any]) -> None:
        self._results[key] = result

    def set_default_result(self, result: dict[str, Any]) -> None:
        self._default_result = result

    async def execute_async(self, code: str) -> dict[str, Any]:
        self.calls.append(code)
        # Try to match by simple heuristic; fallback to default
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
    register_cad_tools(mcp, executor)
    return mcp, executor


# ---------------------------------------------------------------------------
# Tests: standalone mode and standard result fields
# ---------------------------------------------------------------------------

class TestCadStandalone:
    @pytest.mark.asyncio
    async def test_cad_get_version_standalone(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        tool = mcp._tool_manager._tools["cad_get_version"].fn
        response = await tool()

        assert response["status"] == "success"
        assert response["operation"] == "cad_get_version"
        assert response["claim_policy"]["claims_advanced"] is False
        assert response["claim_policy"]["requires_explicit_update_claim"] is True
        assert response["evidence"]["producer_kind"] == "freecad"
        assert response["trace"]["producer"] == "freecad_mcp"
        assert response["version"] == "0.21.0"  # backward compat

    @pytest.mark.asyncio
    async def test_cad_list_objects_standalone(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result({"result": [{"name": "Box", "label": "Box", "type_id": "Part::Box"}]})
        tool = mcp._tool_manager._tools["cad_list_objects"].fn
        response = await tool(doc_name="Unnamed")

        assert response["status"] == "success"
        assert response["operation"] == "cad_list_objects"
        assert response["claim_policy"]["claims_advanced"] is False
        assert len(response["objects"]) == 1
        assert response["objects"][0]["name"] == "Box"

    @pytest.mark.asyncio
    async def test_cad_inspect_object_standalone(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {
                "result": {
                    "name": "Box",
                    "label": "Box",
                    "type_id": "Part::Box",
                    "shape": {"volume_mm3": 1000.0},
                }
            }
        )
        tool = mcp._tool_manager._tools["cad_inspect_object"].fn
        response = await tool(object_name="Box")

        assert response["status"] == "success"
        assert response["name"] == "Box"
        assert response["shape"]["volume_mm3"] == 1000.0
        assert response["claim_policy"]["claims_advanced"] is False

    @pytest.mark.asyncio
    async def test_cad_get_mass_properties_standalone(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {
                "result": {
                    "volume_mm3": 1000.0,
                    "mass_kg": 2.7,
                    "center_of_gravity_mm": [0.0, 0.0, 0.0],
                    "object_name": "Box",
                }
            }
        )
        tool = mcp._tool_manager._tools["cad_get_mass_properties"].fn
        response = await tool()

        assert response["status"] == "success"
        assert response["volume_mm3"] == 1000.0
        assert response["claim_policy"]["claims_advanced"] is False

    @pytest.mark.asyncio
    async def test_cad_export_step_standalone(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result({"result": {"file_path": "/tmp/test.step", "object_count": 1}})
        tool = mcp._tool_manager._tools["cad_export_step"].fn
        response = await tool(file_path="/tmp/test.step")

        assert response["status"] == "success"
        assert response["artifacts_written"] == ["/tmp/test.step"]
        assert response["file_path"] == "/tmp/test.step"

    @pytest.mark.asyncio
    async def test_cad_list_parameters_standalone(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {
                "result": {
                    "parameters": [
                        {
                            "object_name": "Box",
                            "object_label": "Box",
                            "parameters": [
                                {"name": "Length", "value": 10.0, "type": "App::PropertyLength"}
                            ],
                        }
                    ]
                }
            }
        )
        tool = mcp._tool_manager._tools["cad_list_parameters"].fn
        response = await tool()

        assert response["status"] == "success"
        assert response["parameters"][0]["object_name"] == "Box"
        assert response["claim_policy"]["claims_advanced"] is False

    @pytest.mark.asyncio
    async def test_cad_get_parameter_standalone(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "value": 10.0, "type": "App::PropertyLength"}}
        )
        tool = mcp._tool_manager._tools["cad_get_parameter"].fn
        response = await tool(object_name="Box", parameter_name="Length")

        assert response["status"] == "success"
        assert response["value"] == 10.0
        assert response["claim_policy"]["claims_advanced"] is False

    @pytest.mark.asyncio
    async def test_cad_set_parameter_standalone(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )
        tool = mcp._tool_manager._tools["cad_set_parameter"].fn
        response = await tool(object_name="Box", parameter_name="Length", value=20.0)

        assert response["status"] == "success"
        assert response["old_value"] == 10.0
        assert response["new_value"] == 20.0
        assert response["claim_policy"]["claims_advanced"] is False

    @pytest.mark.asyncio
    async def test_cad_recompute_document_standalone(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"success": True, "document": "Unnamed", "failed_features": []}}
        )
        tool = mcp._tool_manager._tools["cad_recompute_document"].fn
        response = await tool()

        assert response["status"] == "success"
        assert response["success"] is True
        assert response["claim_policy"]["claims_advanced"] is False

    @pytest.mark.asyncio
    async def test_cad_export_fcstd_standalone(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result({"result": {"file_path": "/tmp/test.FCStd", "document": "Unnamed"}})
        tool = mcp._tool_manager._tools["cad_export_fcstd"].fn
        response = await tool(file_path="/tmp/test.FCStd")

        assert response["status"] == "success"
        assert response["artifacts_written"] == ["/tmp/test.FCStd"]
        assert response["file_path"] == "/tmp/test.FCStd"


# ---------------------------------------------------------------------------
# Tests: .aieng-enhanced mode with persistence
# ---------------------------------------------------------------------------

class TestCadAiengEnhanced:
    @pytest.mark.asyncio
    async def test_cad_set_parameter_persists_evidence(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        tool = mcp._tool_manager._tools["cad_set_parameter"].fn
        response = await tool(
            object_name="Box",
            parameter_name="Length",
            value=20.0,
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        assert response["persistence"] is not None
        assert (tmp_path / "results" / "evidence_index.json").exists()
        assert (tmp_path / "provenance" / "tool_trace.json").exists()

    @pytest.mark.asyncio
    async def test_cad_set_parameter_no_package_path_with_persist_rejected(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )
        tool = mcp._tool_manager._tools["cad_set_parameter"].fn
        response = await tool(
            object_name="Box",
            parameter_name="Length",
            value=20.0,
            persist_to_aieng=True,
        )

        assert response["status"] == "rejected"
        assert "persist_to_aieng=true requires a valid package_path" in str(response.get("errors", []))

    @pytest.mark.asyncio
    async def test_cad_persist_failure_returns_error_code(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        import freecad_mcp.tools_cad as tools_cad_mod
        from freecad_mcp.aieng_bridge.persistence import PersistenceError

        def failing_persist(*args: Any, **kwargs: Any) -> Any:
            raise PersistenceError("disk full")

        monkeypatch.setattr(tools_cad_mod, "persist_standard_result_to_aieng", failing_persist)

        tool = mcp._tool_manager._tools["cad_set_parameter"].fn
        response = await tool(
            object_name="Box",
            parameter_name="Length",
            value=20.0,
            persist_to_aieng=True,
            package_path=str(tmp_path),
        )

        assert response["status"] == "success"
        assert response["persistence"]["error_code"] == "PERSISTENCE_FAILED"
        assert response["persistence"]["persisted"] is False
        assert "disk full" in response["persistence"]["error"]

    @pytest.mark.asyncio
    async def test_cad_inspect_object_persists_evidence(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {
                "result": {
                    "name": "Box",
                    "label": "Box",
                    "type_id": "Part::Box",
                    "shape": {"volume_mm3": 1000.0},
                }
            }
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        tool = mcp._tool_manager._tools["cad_inspect_object"].fn
        response = await tool(
            object_name="Box",
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        assert response["persistence"] is not None
        assert (tmp_path / "results" / "evidence_index.json").exists()
        assert (tmp_path / "provenance" / "tool_trace.json").exists()


# ---------------------------------------------------------------------------
# Tests: guard checks
# ---------------------------------------------------------------------------

class TestCadGuards:
    @pytest.mark.asyncio
    async def test_cad_set_parameter_rejected_on_semantic_only(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Box": {"editability": {"executable": False}, "semantic_only": True}
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["cad_set_parameter"].fn
        response = await tool(
            object_name="Box",
            parameter_name="Length",
            value=20.0,
            package_path=str(tmp_path),
            persist_to_aieng=True,
            target_feature_id="Box",
        )

        assert response["status"] == "rejected"
        assert "semantic-only" in str(response.get("errors", [])).lower() or "not executable" in str(response.get("errors", [])).lower()

    @pytest.mark.asyncio
    async def test_cad_inspect_object_allowed_on_semantic_only(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {
                "result": {
                    "name": "Box",
                    "label": "Box",
                    "type_id": "Part::Box",
                    "shape": {"volume_mm3": 1000.0},
                }
            }
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Box": {"editability": {"executable": False}, "semantic_only": True}
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["cad_inspect_object"].fn
        response = await tool(
            object_name="Box",
            package_path=str(tmp_path),
            persist_to_aieng=True,
            target_feature_id="Box",
        )

        assert response["status"] == "success"
        assert response["name"] == "Box"

    @pytest.mark.asyncio
    async def test_cad_set_parameter_rejected_on_protected_region(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        constraints = {
            "protected_regions": [
                {"name": "mounting_zone", "features": ["Box"]}
            ]
        }
        (tmp_path / "graph" / "constraints.json").write_text(json.dumps(constraints))

        tool = mcp._tool_manager._tools["cad_set_parameter"].fn
        response = await tool(
            object_name="Box",
            parameter_name="Length",
            value=20.0,
            package_path=str(tmp_path),
            persist_to_aieng=True,
            target_feature_id="Box",
        )

        assert response["status"] == "rejected"
        assert "protected" in str(response.get("errors", [])).lower()

    @pytest.mark.asyncio
    async def test_cad_set_parameter_allowed_when_valid(self, tmp_path: Path) -> None:
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
                "Box": {"editability": {"executable": True}}
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        tool = mcp._tool_manager._tools["cad_set_parameter"].fn
        response = await tool(
            object_name="Box",
            parameter_name="Length",
            value=20.0,
            package_path=str(tmp_path),
            persist_to_aieng=True,
            target_feature_id="Box",
        )

        assert response["status"] == "success"
        assert response["persistence"] is not None


# ---------------------------------------------------------------------------
# Tests: persistence discipline
# ---------------------------------------------------------------------------

class TestCadPersistenceDiscipline:
    @pytest.mark.asyncio
    async def test_persistence_does_not_modify_claim_map(self, tmp_path: Path) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))

        tool = mcp._tool_manager._tools["cad_set_parameter"].fn
        response = await tool(
            object_name="Box",
            parameter_name="Length",
            value=20.0,
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        after = json.loads((tmp_path / "results" / "claim_map.json").read_text())
        assert after == claim_map

    @pytest.mark.asyncio
    async def test_source_artifact_not_modified_in_place(self, tmp_path: Path) -> None:
        # This is a policy test: cad_set_parameter operates on a live FreeCAD
        # document parameter, not on a source STEP/FCStd file directly.
        # The tool response should not claim source artifact immutability;
        # instead it should record the parameter change.
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {"result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
        )

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        tool = mcp._tool_manager._tools["cad_set_parameter"].fn
        response = await tool(
            object_name="Box",
            parameter_name="Length",
            value=20.0,
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )

        assert response["status"] == "success"
        assert response["old_value"] == 10.0
        assert response["new_value"] == 20.0
        # No source artifact path should appear in artifacts_written for a param edit
        assert response.get("artifacts_written", []) == []


# ---------------------------------------------------------------------------
# Tests: backward compatibility
# ---------------------------------------------------------------------------

class TestCadBackwardCompatibility:
    @pytest.mark.asyncio
    async def test_unmigrated_tool_still_works(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result({"result": {"name": "Box", "label": "Box", "type_id": "Part::Box", "changes": {}}})
        tool = mcp._tool_manager._tools["cad_create_box"].fn
        response = await tool(length=20.0)

        # Unmigrated tool should still return raw dict (no standard wrapper yet)
        assert "name" in response
        assert response["name"] == "Box"

    @pytest.mark.asyncio
    async def test_migrated_tool_preserves_original_fields(self) -> None:
        mcp, executor = _make_mcp_with_executor()
        executor.set_default_result(
            {
                "result": {
                    "name": "Box",
                    "label": "Box",
                    "type_id": "Part::Box",
                    "shape": {"volume_mm3": 1000.0},
                }
            }
        )
        tool = mcp._tool_manager._tools["cad_inspect_object"].fn
        response = await tool(object_name="Box")

        # Original fields preserved at top level
        assert response["name"] == "Box"
        assert response["label"] == "Box"
        assert response["type_id"] == "Part::Box"
        assert response["shape"]["volume_mm3"] == 1000.0
        # Standard fields also present
        assert response["status"] == "success"
        assert response["claim_policy"]["claims_advanced"] is False
