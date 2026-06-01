"""Tests for freecad_mcp.tools_runtime MCP tool wrappers.

Uses a fake AiengRuntimeClient to verify that MCP tools call the correct
client methods with correct arguments.  No HTTP or FreeCAD connection needed.
"""

from __future__ import annotations

from typing import Any

import pytest

from freecad_mcp.aieng_runtime_client import AiengRuntimeClient, AiengRuntimeError
from freecad_mcp.tools_runtime import register_runtime_tools


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeRuntimeClient(AiengRuntimeClient):
    """Test double that records calls and returns canned responses."""

    def __init__(self) -> None:
        # Bypass parent __init__ to avoid env-var / network concerns
        self.base_url = "http://fake-runtime"
        self.timeout = 1
        self.calls: list[dict[str, Any]] = []
        self._responses: dict[str, Any] = {}
        self._error: AiengRuntimeError | None = None

    def set_response(self, key: str, value: Any) -> None:
        self._responses[key] = value

    def set_error(self, exc: AiengRuntimeError) -> None:
        self._error = exc

    def _raise_if_error(self) -> None:
        if self._error is not None:
            raise self._error

    def list_tools(self) -> list[dict[str, Any]]:
        self._raise_if_error()
        self.calls.append({"method": "list_tools"})
        return self._responses.get("list_tools", [])

    def start_run(
        self,
        message: str,
        project_id: str | None = None,
        tool_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._raise_if_error()
        self.calls.append({
            "method": "start_run",
            "message": message,
            "project_id": project_id,
            "tool_input": tool_input,
        })
        return self._responses.get("start_run", {"run_id": "fake-run", "status": "completed"})

    def get_run(self, run_id: str) -> dict[str, Any]:
        self._raise_if_error()
        self.calls.append({"method": "get_run", "run_id": run_id})
        return self._responses.get("get_run", {"run_id": run_id, "status": "completed"})

    def get_run_events(self, run_id: str) -> list[dict[str, Any]]:
        self._raise_if_error()
        self.calls.append({"method": "get_run_events", "run_id": run_id})
        return self._responses.get("get_run_events", [])

    def approve_run(self, run_id: str) -> dict[str, Any]:
        self._raise_if_error()
        self.calls.append({"method": "approve_run", "run_id": run_id})
        return self._responses.get("approve_run", {"run_id": run_id, "status": "completed"})

    def reject_run(self, run_id: str) -> dict[str, Any]:
        self._raise_if_error()
        self.calls.append({"method": "reject_run", "run_id": run_id})
        return self._responses.get("reject_run", {"run_id": run_id, "status": "rejected"})

    def get_cae_artifacts(self, project_id: str) -> dict[str, Any]:
        self._raise_if_error()
        self.calls.append({"method": "get_cae_artifacts", "project_id": project_id})
        return self._responses.get("get_cae_artifacts", {"mode": "cad_only", "artifacts": {}})

    def get_cae_result_summary(self, project_id: str) -> dict[str, Any]:
        self._raise_if_error()
        self.calls.append({"method": "get_cae_result_summary", "project_id": project_id})
        return self._responses.get(
            "get_cae_result_summary",
            {
                "schema_version": "0.1",
                "summary_type": "cae_postprocessing",
                "status": {"mode": "cad_only", "warnings": []},
                "computed_values": {"extrema_computed": False},
                "llm_summary": {"one_line": "CAD-only package; no CAE artifacts detected."},
            },
        )

    def get_cae_preprocessing_summary(self, project_id: str) -> dict[str, Any]:
        self._raise_if_error()
        self.calls.append({"method": "get_cae_preprocessing_summary", "project_id": project_id})
        return self._responses.get(
            "get_cae_preprocessing_summary",
            {"schema_version": "0.1", "status": {"has_cae_setup": False, "ready_for_solver": False}},
        )

    def get_cae_simulation_run_summary(self, project_id: str) -> dict[str, Any]:
        self._raise_if_error()
        self.calls.append({"method": "get_cae_simulation_run_summary", "project_id": project_id})
        return self._responses.get(
            "get_cae_simulation_run_summary",
            {"schema_version": "0.1", "status": {"has_simulation_runs": False, "run_count": 0}},
        )

    def wait_for_run(self, run_id: str, timeout_seconds: float = 60, poll_interval: float = 2) -> dict[str, Any]:
        self._raise_if_error()
        self.calls.append({"method": "wait_for_run", "run_id": run_id})
        return self._responses.get("wait_for_run", {"run_id": run_id, "status": "completed"})


def _make_mcp_with_client() -> tuple[Any, FakeRuntimeClient]:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(name="test-runtime")
    client = FakeRuntimeClient()
    register_runtime_tools(mcp, client)
    return mcp, client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_tool(mcp: Any, name: str):
    return mcp._tool_manager._tools[name].fn


# ---------------------------------------------------------------------------
# aieng_list_runtime_tools
# ---------------------------------------------------------------------------

class TestListRuntimeTools:
    def test_calls_client_list_tools(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("list_tools", [{"name": "freecad.inspect_geometry"}])
        tool = _get_tool(mcp, "aieng_list_runtime_tools")
        result = tool()
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert any(c["method"] == "list_tools" for c in client.calls)

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_list_runtime_tools")
        result = tool()
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"
        assert "backend down" in result["message"]


# ---------------------------------------------------------------------------
# aieng_start_runtime_run
# ---------------------------------------------------------------------------

class TestStartRuntimeRun:
    def test_calls_start_run_with_message(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "r1", "status": "completed"})
        tool = _get_tool(mcp, "aieng_start_runtime_run")
        result = tool(message="inspect geometry")
        assert result["run_id"] == "r1"
        call = next(c for c in client.calls if c["method"] == "start_run")
        assert call["message"] == "inspect geometry"
        assert call["project_id"] is None

    def test_passes_project_id_when_given(self) -> None:
        mcp, client = _make_mcp_with_client()
        tool = _get_tool(mcp, "aieng_start_runtime_run")
        tool(message="export step", project_id="proj-42")
        call = next(c for c in client.calls if c["method"] == "start_run")
        assert call["project_id"] == "proj-42"

    def test_returns_error_on_connection_failure(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("Connection refused"))
        tool = _get_tool(mcp, "aieng_start_runtime_run")
        result = tool(message="inspect geometry")
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# aieng_get_runtime_run
# ---------------------------------------------------------------------------

class TestGetRuntimeRun:
    def test_calls_get_run_with_id(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("get_run", {"run_id": "abc", "status": "failed"})
        tool = _get_tool(mcp, "aieng_get_runtime_run")
        result = tool(run_id="abc")
        assert result["status"] == "failed"
        assert any(c["method"] == "get_run" and c["run_id"] == "abc" for c in client.calls)


# ---------------------------------------------------------------------------
# aieng_inspect_geometry
# ---------------------------------------------------------------------------

class TestInspectGeometry:
    def test_starts_run_with_correct_message(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "ig1", "status": "completed"})
        tool = _get_tool(mcp, "aieng_inspect_geometry")
        tool()
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        assert "inspect geometry" in start_call["message"]

    def test_returns_immediately_when_run_completes_in_start(self) -> None:
        mcp, client = _make_mcp_with_client()
        run = {"run_id": "ig2", "status": "completed", "tool_results": []}
        client.set_response("start_run", run)
        tool = _get_tool(mcp, "aieng_inspect_geometry")
        result = tool()
        assert result["status"] == "completed"
        # wait_for_run should NOT be called when start_run already returns terminal status
        assert not any(c["method"] == "wait_for_run" for c in client.calls)

    def test_returns_awaiting_approval_without_auto_approving(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "ig3", "status": "awaiting_approval"})
        tool = _get_tool(mcp, "aieng_inspect_geometry")
        result = tool()
        assert result["status"] == "awaiting_approval"
        # Must not have called approve_run
        assert not any(c["method"] == "approve_run" for c in client.calls)

    def test_calls_wait_for_run_on_pending_status(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "ig4", "status": "running"})
        client.set_response("wait_for_run", {"run_id": "ig4", "status": "completed"})
        tool = _get_tool(mcp, "aieng_inspect_geometry")
        result = tool()
        assert result["status"] == "completed"
        assert any(c["method"] == "wait_for_run" for c in client.calls)

    def test_passes_project_id_to_start_run(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "ig5", "status": "completed"})
        tool = _get_tool(mcp, "aieng_inspect_geometry")
        tool(project_id="my-project")
        call = next(c for c in client.calls if c["method"] == "start_run")
        assert call["project_id"] == "my-project"


# ---------------------------------------------------------------------------
# aieng_export_step
# ---------------------------------------------------------------------------

class TestExportStep:
    def test_starts_run_with_correct_message(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "es1", "status": "completed"})
        tool = _get_tool(mcp, "aieng_export_step")
        tool()
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        assert "export step" in start_call["message"]

    def test_does_not_invoke_freecad_directly(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "es2", "status": "completed"})
        tool = _get_tool(mcp, "aieng_export_step")
        tool()
        # All calls must go through the client (no FreeCAD subprocess calls)
        assert all(c["method"] in ("start_run", "wait_for_run", "get_run") for c in client.calls)

    def test_returns_error_on_runtime_failure(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("FreeCADCmd not found"))
        tool = _get_tool(mcp, "aieng_export_step")
        result = tool()
        assert result["status"] == "error"
        assert "FreeCADCmd" in result["message"]


# ---------------------------------------------------------------------------
# aieng_approve_runtime_run / aieng_reject_runtime_run
# ---------------------------------------------------------------------------

class TestApproveRejectTools:
    def test_approve_calls_client_approve(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("approve_run", {"run_id": "ar1", "status": "completed"})
        tool = _get_tool(mcp, "aieng_approve_runtime_run")
        result = tool(run_id="ar1")
        assert result["status"] == "completed"
        assert any(c["method"] == "approve_run" and c["run_id"] == "ar1" for c in client.calls)

    def test_reject_calls_client_reject(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("reject_run", {"run_id": "rr1", "status": "rejected"})
        tool = _get_tool(mcp, "aieng_reject_runtime_run")
        result = tool(run_id="rr1")
        assert result["status"] == "rejected"
        assert any(c["method"] == "reject_run" and c["run_id"] == "rr1" for c in client.calls)

    def test_approve_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("Run not found", status_code=404))
        tool = _get_tool(mcp, "aieng_approve_runtime_run")
        result = tool(run_id="missing")
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# Tool registry sanity check
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# aieng_get_cae_status
# ---------------------------------------------------------------------------

class TestGetCaeStatus:
    def test_calls_get_cae_artifacts_with_project_id(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("get_cae_artifacts", {"mode": "cae_setup", "has_mesh": True})
        tool = _get_tool(mcp, "aieng_get_cae_status")
        result = tool(project_id="proj-99")
        assert result["mode"] == "cae_setup"
        call = next(c for c in client.calls if c["method"] == "get_cae_artifacts")
        assert call["project_id"] == "proj-99"

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_get_cae_status")
        result = tool(project_id="proj-99")
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# Tool registry sanity check
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# aieng_get_cae_result_summary
# ---------------------------------------------------------------------------

class TestGetCaeResultSummary:
    def test_calls_get_cae_result_summary_with_project_id(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response(
            "get_cae_result_summary",
            {
                "schema_version": "0.1",
                "status": {"mode": "cae_result", "warnings": []},
                "llm_summary": {"one_line": "Result summary."},
            },
        )
        tool = _get_tool(mcp, "aieng_get_cae_result_summary")
        result = tool(project_id="proj-88")
        assert result["status"]["mode"] == "cae_result"
        call = next(c for c in client.calls if c["method"] == "get_cae_result_summary")
        assert call["project_id"] == "proj-88"

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_get_cae_result_summary")
        result = tool(project_id="proj-88")
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# Tool registry sanity check
# ---------------------------------------------------------------------------

class TestGenerateComputedMetrics:
    def test_calls_start_run_with_tool_input(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("wait_for_run", {"run_id": "cm-run", "status": "completed"})
        tool = _get_tool(mcp, "aieng_generate_computed_metrics")
        result = tool(
            input_path="/tmp/raw.json",
            output_path="/tmp/computed_metrics.json",
            project_id="proj-99",
            load_case_id="lc_001",
            software="TestSolver",
            source_files=["/tmp/result.vtu"],
        )
        assert result["status"] == "completed"
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        assert start_call["message"] == "generate computed metrics"
        assert start_call["project_id"] == "proj-99"
        assert start_call["tool_input"]["inputPath"] == "/tmp/raw.json"
        assert start_call["tool_input"]["outputPath"] == "/tmp/computed_metrics.json"
        assert start_call["tool_input"]["loadCaseId"] == "lc_001"
        assert start_call["tool_input"]["software"] == "TestSolver"
        assert start_call["tool_input"]["sourceFiles"] == ["/tmp/result.vtu"]

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_generate_computed_metrics")
        result = tool(input_path="/tmp/raw.json")
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


class TestRefreshCaeSummary:
    def test_calls_start_run_with_tool_input(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("wait_for_run", {"run_id": "rs-run", "status": "completed"})
        tool = _get_tool(mcp, "aieng_refresh_cae_summary")
        result = tool(
            project_id="proj-88",
            package_path="/tmp/project.aieng",
            overwrite=True,
        )
        assert result["status"] == "completed"
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        assert start_call["message"] == "refresh cae summary"
        assert start_call["project_id"] == "proj-88"
        assert start_call["tool_input"]["packagePath"] == "/tmp/project.aieng"
        assert start_call["tool_input"]["overwrite"] is True

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_refresh_cae_summary")
        result = tool(project_id="proj-88")
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# aieng_get_cae_preprocessing_summary
# ---------------------------------------------------------------------------

class TestGetCaePreprocessingSummary:
    def test_calls_get_cae_preprocessing_summary_with_project_id(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response(
            "get_cae_preprocessing_summary",
            {"schema_version": "0.1", "status": {"has_cae_setup": True, "ready_for_solver": True}},
        )
        tool = _get_tool(mcp, "aieng_get_cae_preprocessing_summary")
        result = tool(project_id="proj-77")
        assert result["status"]["ready_for_solver"] is True
        call = next(c for c in client.calls if c["method"] == "get_cae_preprocessing_summary")
        assert call["project_id"] == "proj-77"

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_get_cae_preprocessing_summary")
        result = tool(project_id="proj-77")
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# aieng_get_cae_simulation_run_summary
# ---------------------------------------------------------------------------

class TestGetCaeSimulationRunSummary:
    def test_calls_get_cae_simulation_run_summary_with_project_id(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response(
            "get_cae_simulation_run_summary",
            {"schema_version": "0.1", "status": {"has_simulation_runs": True, "run_count": 2}},
        )
        tool = _get_tool(mcp, "aieng_get_cae_simulation_run_summary")
        result = tool(project_id="proj-66")
        assert result["status"]["run_count"] == 2
        call = next(c for c in client.calls if c["method"] == "get_cae_simulation_run_summary")
        assert call["project_id"] == "proj-66"

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_get_cae_simulation_run_summary")
        result = tool(project_id="proj-66")
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# aieng_apply_cae_setup_patch
# ---------------------------------------------------------------------------

class TestApplyCaeSetupPatch:
    def test_calls_start_run_with_patches_in_tool_input(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "patch-run", "status": "completed"})
        tool = _get_tool(mcp, "aieng_apply_cae_setup_patch")
        patches = [{"path": "simulation/solver_settings.json", "action_type": "replace_json", "pointer": "/n_cpus", "value": 4}]
        result = tool(patches=patches, project_id="proj-55")
        assert result["status"] == "completed"
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        assert start_call["message"] == "apply cae setup patch"
        assert start_call["project_id"] == "proj-55"
        assert start_call["tool_input"]["patches"] == patches

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_apply_cae_setup_patch")
        result = tool(patches=[])
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# aieng_extract_solver_results
# ---------------------------------------------------------------------------

class TestExtractSolverResults:
    def test_calls_start_run_with_frd_path_in_tool_input(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "frd-run", "status": "completed"})
        tool = _get_tool(mcp, "aieng_extract_solver_results")
        result = tool(frd_path="/tmp/job.frd", project_id="proj-44", load_case_id="lc_002", software="CalculiX")
        assert result["status"] == "completed"
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        assert start_call["message"] == "extract solver results"
        assert start_call["project_id"] == "proj-44"
        assert start_call["tool_input"]["frdPath"] == "/tmp/job.frd"
        assert start_call["tool_input"]["loadCaseId"] == "lc_002"

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_extract_solver_results")
        result = tool(frd_path="/tmp/job.frd")
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# aieng_prepare_solver_run
# ---------------------------------------------------------------------------

class TestPrepareSolverRun:
    def test_calls_start_run_with_correct_message_and_payload(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "preflight-run", "status": "completed"})
        tool = _get_tool(mcp, "aieng_prepare_solver_run")
        result = tool(
            project_id="proj-33",
            run_id="run_002",
            solver="CalculiX",
            load_case_id="lc_001",
            extract_results=True,
            refresh_summary=False,
        )
        assert result["status"] == "completed"
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        assert start_call["message"] == "prepare solver run"
        assert start_call["project_id"] == "proj-33"
        ti = start_call["tool_input"]
        assert ti["runId"] == "run_002"
        assert ti["loadCaseId"] == "lc_001"
        assert ti["extractResults"] is True
        assert ti["refreshSummary"] is False

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_prepare_solver_run")
        result = tool()
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# aieng_run_solver
# ---------------------------------------------------------------------------

class TestRunSolver:
    def test_calls_start_run_with_correct_message_and_payload(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "solver-run", "status": "awaiting_approval"})
        tool = _get_tool(mcp, "aieng_run_solver")
        result = tool(
            project_id="proj-44",
            run_id="run_003",
            solver="CalculiX",
            input_deck_path="simulation/runs/run_003/solver_input.inp",
            extract_results=True,
            refresh_summary=False,
            overwrite=True,
            timeout_seconds=180,
        )
        assert result["status"] == "awaiting_approval"
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        assert start_call["message"] == "execute solver run"
        assert start_call["project_id"] == "proj-44"
        ti = start_call["tool_input"]
        assert ti["runId"] == "run_003"
        assert ti["solver"] == "CalculiX"
        assert ti["inputDeckPath"] == "simulation/runs/run_003/solver_input.inp"
        assert ti["extractResults"] is True
        assert ti["refreshSummary"] is False
        assert ti["overwrite"] is True
        assert ti["timeoutSeconds"] == 180

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_run_solver")
        result = tool(project_id="proj-44")
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"

    def test_does_not_auto_approve_awaiting_approval(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "solver-run2", "status": "awaiting_approval"})
        tool = _get_tool(mcp, "aieng_run_solver")
        result = tool(project_id="proj-44")
        assert result["status"] == "awaiting_approval"
        assert not any(c["method"] == "approve_run" for c in client.calls)

    def test_passes_through_completed_run_honestly(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "solver-run3", "status": "completed"})
        tool = _get_tool(mcp, "aieng_run_solver")
        result = tool(project_id="proj-44")
        assert result["status"] == "completed"

    def test_payload_passthrough_without_semantic_rewriting(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "solver-run4", "status": "completed"})
        tool = _get_tool(mcp, "aieng_run_solver")
        tool(
            project_id="proj-55",
            run_id="custom_run",
            solver="OpenFOAM",
            input_deck_path="custom/path.inp",
            extract_results=False,
            refresh_summary=False,
            overwrite=False,
            timeout_seconds=60,
        )
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        ti = start_call["tool_input"]
        assert ti["runId"] == "custom_run"
        assert ti["solver"] == "OpenFOAM"
        assert ti["inputDeckPath"] == "custom/path.inp"
        assert ti["extractResults"] is False
        assert ti["overwrite"] is False
        assert ti["timeoutSeconds"] == 60


# ---------------------------------------------------------------------------
# aieng_generate_solver_input
# ---------------------------------------------------------------------------

class TestGenerateSolverInput:
    def test_calls_start_run_with_tool_input(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "gen-run", "status": "completed"})
        tool = _get_tool(mcp, "aieng_generate_solver_input")
        result = tool(project_id="proj-22", run_id="run_005", overwrite=False)
        assert result["status"] == "completed"
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        assert start_call["message"] == "generate solver input"
        assert start_call["project_id"] == "proj-22"
        assert start_call["tool_input"]["runId"] == "run_005"
        assert start_call["tool_input"]["overwrite"] is False

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_generate_solver_input")
        result = tool(project_id="proj-22")
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# aieng_extract_field_regions
# ---------------------------------------------------------------------------

class TestExtractFieldRegions:
    def test_calls_start_run_with_tool_input(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "reg-run", "status": "completed"})
        tool = _get_tool(mcp, "aieng_extract_field_regions")
        result = tool(
            frd_path="/tmp/job.frd",
            project_id="proj-11",
            field="S",
            metric="von_mises",
            max_clusters=5,
            threshold_percentile=85.0,
            overwrite=False,
            refresh_field_summary=False,
        )
        assert result["status"] == "completed"
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        assert start_call["message"] == "extract field regions"
        assert start_call["project_id"] == "proj-11"
        ti = start_call["tool_input"]
        assert ti["frdPath"] == "/tmp/job.frd"
        assert ti["field"] == "S"
        assert ti["metric"] == "von_mises"
        assert ti["maxClusters"] == 5
        assert ti["thresholdPercentile"] == 85.0
        assert ti["overwrite"] is False
        assert ti["refreshFieldSummary"] is False

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_extract_field_regions")
        result = tool(frd_path="/tmp/job.frd")
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# aieng_edit_cad_parameter
# ---------------------------------------------------------------------------

class TestEditCadParameter:
    def test_calls_start_run_with_tool_input_and_waits_for_approval(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "cad-edit-run", "status": "awaiting_approval"})
        tool = _get_tool(mcp, "aieng_edit_cad_parameter")
        result = tool(
            feature_id="feat_base_001",
            parameter_name="thickness_mm",
            new_value=8.5,
            project_id="proj-77",
            input_fcstd="/tmp/bracket.FCStd",
        )
        assert result["status"] == "awaiting_approval"
        start_call = next(c for c in client.calls if c["method"] == "start_run")
        assert start_call["message"] == "edit cad parameter"
        assert start_call["project_id"] == "proj-77"
        ti = start_call["tool_input"]
        assert ti["feature_id"] == "feat_base_001"
        assert ti["parameter_name"] == "thickness_mm"
        assert ti["new_value"] == 8.5
        assert ti["inputFcstd"] == "/tmp/bracket.FCStd"

    def test_does_not_auto_approve_awaiting_approval(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_response("start_run", {"run_id": "cad-edit-run2", "status": "awaiting_approval"})
        tool = _get_tool(mcp, "aieng_edit_cad_parameter")
        result = tool(feature_id="feat_base_001", parameter_name="thickness_mm", new_value=9.0)
        assert result["status"] == "awaiting_approval"
        assert not any(c["method"] == "approve_run" for c in client.calls)

    def test_returns_error_on_runtime_error(self) -> None:
        mcp, client = _make_mcp_with_client()
        client.set_error(AiengRuntimeError("backend down", status_code=503))
        tool = _get_tool(mcp, "aieng_edit_cad_parameter")
        result = tool(feature_id="feat_base_001", parameter_name="thickness_mm", new_value=9.0)
        assert result["status"] == "error"
        assert result["code"] == "runtime_error"


# ---------------------------------------------------------------------------
# Tool registry sanity check
# ---------------------------------------------------------------------------

class TestToolRegistration:
    def test_all_runtime_tools_registered(self) -> None:
        mcp, _ = _make_mcp_with_client()
        expected = {
            "aieng_list_runtime_tools",
            "aieng_start_runtime_run",
            "aieng_get_runtime_run",
            "aieng_inspect_geometry",
            "aieng_export_step",
            "aieng_approve_runtime_run",
            "aieng_reject_runtime_run",
            "aieng_get_cae_status",
            "aieng_get_cae_result_summary",
            "aieng_get_cae_preprocessing_summary",
            "aieng_get_cae_simulation_run_summary",
            "aieng_generate_computed_metrics",
            "aieng_refresh_cae_summary",
            "aieng_apply_cae_setup_patch",
            "aieng_extract_solver_results",
            "aieng_prepare_solver_run",
            "aieng_run_solver",
            "aieng_generate_solver_input",
            "aieng_extract_field_regions",
            "aieng_edit_cad_parameter",
        }
        registered = set(mcp._tool_manager._tools.keys())
        assert expected.issubset(registered), (
            f"Missing tools: {expected - registered}"
        )


# ---------------------------------------------------------------------------
# Docs contract — critical MCP tools must be documented
# ---------------------------------------------------------------------------
# Agent-facing tools cannot drift between code and docs silently. The
# critical set below maps to the runtime CAE lifecycle the workbench
# advertises: preprocessing, simulation runs, results, setup patching,
# FRD extraction, and external solver execution.
#
# Substring presence only — no markdown parsing. If a tool gets renamed,
# the doc must be updated in the same change.

CRITICAL_MCP_TOOLS: tuple[str, ...] = (
    "aieng_get_cae_preprocessing_summary",
    "aieng_get_cae_simulation_run_summary",
    "aieng_get_cae_result_summary",
    "aieng_apply_cae_setup_patch",
    "aieng_extract_solver_results",
    "aieng_prepare_solver_run",
    "aieng_run_solver",
    "aieng_edit_cad_parameter",
)


class TestCriticalToolsContract:
    def test_critical_tools_registered(self) -> None:
        mcp, _ = _make_mcp_with_client()
        registered = set(mcp._tool_manager._tools.keys())
        missing = [name for name in CRITICAL_MCP_TOOLS if name not in registered]
        assert not missing, (
            f"Critical MCP tools missing from runtime registration: {missing}. "
            f"Either register them in tools_runtime/__init__.py or remove them "
            f"from CRITICAL_MCP_TOOLS if intentionally deprecated."
        )

    def test_critical_tools_documented_in_mcp_runtime_tools_md(self) -> None:
        from pathlib import Path

        docs_path = (
            Path(__file__).resolve().parent.parent
            / "docs"
            / "mcp_runtime_tools.md"
        )
        assert docs_path.exists(), f"Expected docs at {docs_path}"
        body = docs_path.read_text(encoding="utf-8")

        missing = [name for name in CRITICAL_MCP_TOOLS if name not in body]
        assert not missing, (
            f"Critical MCP tools missing from mcp_runtime_tools.md: {missing}. "
            f"Add a section per tool or update CRITICAL_MCP_TOOLS to reflect a "
            f"deliberate rename."
        )
