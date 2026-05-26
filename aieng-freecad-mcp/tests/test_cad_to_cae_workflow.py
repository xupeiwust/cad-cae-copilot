"""Tests for the CAD-to-CAE evidence workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from freecad_mcp.bridge.executor import FreecadExecutor
from freecad_mcp.cae_core.facade import CAEFacade
from freecad_mcp.cae_core.toolset import SurrogateStaticCaeToolset
from freecad_mcp.tools_aieng import register_aieng_tools


class SpyExecutor(FreecadExecutor):
    """Mock executor that returns canned responses."""

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


def _make_mcp_with_facade() -> tuple[Any, SpyExecutor, CAEFacade]:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(name="test")
    executor = SpyExecutor()
    facade = CAEFacade(SurrogateStaticCaeToolset())
    register_aieng_tools(mcp, executor, facade)
    return mcp, executor, facade


# ---------------------------------------------------------------------------
# Request model tests
# ---------------------------------------------------------------------------

class TestWorkflowRequest:
    def test_request_defaults(self) -> None:
        from freecad_mcp.aieng_bridge.workflow import CadToCaeWorkflowRequest

        req = CadToCaeWorkflowRequest()
        assert req.persist_to_aieng is False
        assert req.dry_run is False
        assert req.export_modified_fcstd is True
        assert req.export_modified_step is True
        assert req.run_mesh is True
        assert req.export_solver_deck is True
        assert req.run_solver is False
        assert req.import_solver_evidence is True
        assert req.analysis_type == "static_structural"
        assert req.stop_on_failure is True


# ---------------------------------------------------------------------------
# MCP tool tests
# ---------------------------------------------------------------------------

class TestCadToCaeMcpTool:
    @pytest.mark.asyncio
    async def test_tool_rejects_persist_without_package_path(self) -> None:
        mcp, _, _ = _make_mcp_with_facade()
        tool = mcp._tool_manager._tools["aieng_run_cad_to_cae_workflow"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ]
            },
            persist_to_aieng=True,
        )

        assert response["status"] == "rejected"
        assert "package_path" in str(response.get("errors", []))

    @pytest.mark.asyncio
    async def test_dry_run_performs_no_mutation(self, tmp_path: Path) -> None:
        mcp, executor, _ = _make_mcp_with_facade()
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

        tool = mcp._tool_manager._tools["aieng_run_cad_to_cae_workflow"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ]
            },
            package_path=str(tmp_path),
            dry_run=True,
        )

        assert response["status"] == "success"
        # No evidence should be written in dry-run mode
        assert not (tmp_path / "results").exists()
        assert not (tmp_path / "provenance").exists()

    @pytest.mark.asyncio
    async def test_mock_workflow_writes_patch_and_cae_evidence(self, tmp_path: Path) -> None:
        mcp, executor, _ = _make_mcp_with_facade()
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

        tool = mcp._tool_manager._tools["aieng_run_cad_to_cae_workflow"].fn
        response = await tool(
            patch_json={
                "patch_id": "p1",
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
            export_modified_step=True,
            export_modified_fcstd=True,
        )

        assert response["status"] == "success"

        # Both patch evidence and workflow evidence should exist
        evidence = json.loads((tmp_path / "results" / "evidence_index.json").read_text())
        assert len(evidence.get("entries", [])) >= 2

        trace = json.loads((tmp_path / "provenance" / "tool_trace.json").read_text())
        assert len(trace.get("entries", [])) >= 2

    @pytest.mark.asyncio
    async def test_workflow_identifies_modified_step(self, tmp_path: Path) -> None:
        mcp, executor, _ = _make_mcp_with_facade()
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

        tool = mcp._tool_manager._tools["aieng_run_cad_to_cae_workflow"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            package_path=str(tmp_path),
            persist_to_aieng=True,
            export_modified_step=True,
        )

        assert response["status"] == "success"
        assert any(
            a.get("artifact_type") == "modified_step"
            for a in response.get("cad_artifacts", [])
        )

    @pytest.mark.asyncio
    async def test_claim_map_unchanged(self, tmp_path: Path) -> None:
        mcp, executor, _ = _make_mcp_with_facade()
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

        tool = mcp._tool_manager._tools["aieng_run_cad_to_cae_workflow"].fn
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
    async def test_solver_not_run_by_default(self, tmp_path: Path) -> None:
        mcp, executor, _ = _make_mcp_with_facade()
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

        tool = mcp._tool_manager._tools["aieng_run_cad_to_cae_workflow"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            package_path=str(tmp_path),
        )

        assert response["status"] == "success"
        cae_steps = response.get("cae_steps", [])
        solver_step = next((s for s in cae_steps if s["step_name"] == "solver"), None)
        assert solver_step is None

    @pytest.mark.asyncio
    async def test_surrogate_marked_correctly(self, tmp_path: Path) -> None:
        mcp, executor, _ = _make_mcp_with_facade()
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

        tool = mcp._tool_manager._tools["aieng_run_cad_to_cae_workflow"].fn
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
        evidence = json.loads((tmp_path / "results" / "evidence_index.json").read_text())
        last_entry = evidence["entries"][-1]
        meta = last_entry.get("metadata", {})

        assert meta.get("producer_kind") == "surrogate"
        assert meta.get("solver_executed") is False
        assert meta.get("engineering_validation") is False
        assert meta.get("claims_advanced") is False
        assert "Surrogate CAE result is not solver validation evidence" in str(meta.get("warning", ""))

    @pytest.mark.asyncio
    async def test_failure_in_patch_stops_cae_when_stop_on_failure(self, tmp_path: Path) -> None:
        mcp, executor, _ = _make_mcp_with_facade()
        # Make the executor fail on parameter set
        class FailingExecutor(SpyExecutor):
            async def execute_async(self, code: str) -> dict[str, Any]:
                self.calls.append(code)
                raise RuntimeError("FreeCAD crashed")

        failing = FailingExecutor()
        from mcp.server.fastmcp import FastMCP
        mcp2 = FastMCP(name="test")
        register_aieng_tools(mcp2, failing, CAEFacade(SurrogateStaticCaeToolset()))

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

        tool = mcp2._tool_manager._tools["aieng_run_cad_to_cae_workflow"].fn
        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ],
            },
            package_path=str(tmp_path),
            stop_on_failure=True,
        )

        assert response["status"] == "failed"
        assert len(response.get("cae_steps", [])) == 0


def test_demo_script_runs() -> None:
    """Verify the CAD-to-CAE demo script exits cleanly in mock mode."""
    import subprocess
    import sys

    script = Path(__file__).resolve().parent.parent / "scripts" / "run_cad_to_cae_demo.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)

    assert result.returncode == 0, f"Demo script failed:\n{result.stderr}"
    assert "Demo completed successfully" in result.stdout
    assert "surrogate" in result.stdout.lower()
    assert "solver_executed: False" in result.stdout



# ---------------------------------------------------------------------------
# Workflow independence tests
# ---------------------------------------------------------------------------

class TestWorkflowIndependence:
    """CAD patch execution and CAE operations are independent first-class workflows."""

    @pytest.mark.asyncio
    async def test_patch_execution_does_not_auto_trigger_cae(self, tmp_path: Path) -> None:
        """aieng_execute_patch must not call CAE workflow automatically."""
        from freecad_mcp.aieng_bridge.patch import execute_patch_plan, parse_patch_proposal
        from freecad_mcp.bridge.executor import FreecadExecutor

        class _SpyExecutor(FreecadExecutor):
            def __init__(self) -> None:
                self.calls: list[str] = []

            async def execute_async(self, code: str) -> dict[str, Any]:
                self.calls.append(code)
                if "setattr(obj," in code:
                    return {
                        "success": True,
                        "result": {
                            "object_name": "Box",
                            "parameter_name": "Length",
                            "old_value": 10.0,
                            "new_value": 20.0,
                        },
                    }
                if "exportStep" in code:
                    return {"success": True, "result": {"file_path": str(tmp_path / "out.step"), "object_count": 1}}
                return {"success": True, "result": {}}

            async def get_version_async(self) -> dict[str, Any]:
                return {"version": "0.21.0_mock", "gui_available": False}

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        (tmp_path / "results").mkdir()
        (tmp_path / "provenance").mkdir()
        (tmp_path / "results" / "evidence_index.json").write_text(json.dumps({"entries": []}))
        (tmp_path / "provenance" / "tool_trace.json").write_text(json.dumps({"entries": []}))
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

        patch_raw = {
            "patch_id": "test_patch",
            "operations": [
                {
                    "operation": "modify_parameter",
                    "target_feature_id": "Box",
                    "parameter_name": "Length",
                    "new_value": 20.0,
                }
            ],
        }
        plan = parse_patch_proposal(patch_raw)
        executor = _SpyExecutor()
        summary = await execute_patch_plan(
            plan,
            executor,
            package_path=str(tmp_path),
            persist_to_aieng=True,
            export_modified_step=True,
        )
        assert summary.status == "success"
        # Patch execution should NOT invoke any CAE-related code
        assert all("mesh" not in c.lower() and "cae" not in c.lower() and "solver" not in c.lower() for c in executor.calls)

    @pytest.mark.asyncio
    async def test_cae_tool_can_run_without_prior_patch(self, tmp_path: Path) -> None:
        """CAE post-processing should be callable without any preceding CAD patch."""
        from freecad_mcp.aieng_bridge.postprocessing import PostprocessRequest, postprocess_results

        (tmp_path / "results").mkdir()
        (tmp_path / "provenance").mkdir()
        (tmp_path / "results" / "evidence_index.json").write_text(json.dumps({"entries": []}))
        (tmp_path / "provenance" / "tool_trace.json").write_text(json.dumps({"entries": []}))

        # Create a mock result summary
        result_source = str(tmp_path / "mock_result.json")
        with open(result_source, "w") as f:
            json.dump({"max_displacement_mm": 1.5, "max_von_mises_mpa": 120.0}, f)

        request = PostprocessRequest(
            package_path=str(tmp_path),
            result_source=result_source,
            persist_to_aieng=True,
            export_csv=True,
            output_dir=str(tmp_path),
            producer_kind="surrogate",
            analysis_type="static_structural",
        )
        summary = await postprocess_results(request)
        assert summary.status in ("success", "partial")
        assert summary.claim_policy.claims_advanced is False

    @pytest.mark.asyncio
    async def test_workflow_tool_is_only_invoked_explicitly(self, tmp_path: Path) -> None:
        """The orchestration helper must be explicitly invoked; it is not a default."""
        mcp, _, _ = _make_mcp_with_facade()
        tool = mcp._tool_manager._tools["aieng_run_cad_to_cae_workflow"].fn

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

        response = await tool(
            patch_json={
                "operations": [
                    {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
                ]
            },
            package_path=str(tmp_path),
            persist_to_aieng=False,
        )
        # Tool returns a result, but claim_policy must show no auto-advancement
        assert response["claim_policy"]["claims_advanced"] is False

    def test_workflow_tool_alias_exists(self) -> None:
        """The clearer alias aieng_orchestrate_cad_cae_sequence should exist."""
        mcp, _, _ = _make_mcp_with_facade()
        assert "aieng_orchestrate_cad_cae_sequence" in mcp._tool_manager._tools
        alias_tool = mcp._tool_manager._tools["aieng_orchestrate_cad_cae_sequence"]
        original_tool = mcp._tool_manager._tools["aieng_run_cad_to_cae_workflow"]
        assert alias_tool.fn is original_tool.fn
