"""Tests for the post-processing evidence layer."""

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

class TestPostprocessRequest:
    def test_request_defaults(self) -> None:
        from freecad_mcp.aieng_bridge.postprocessing import PostprocessRequest

        req = PostprocessRequest()
        assert req.package_path is None
        assert req.result_source is None
        assert req.persist_to_aieng is False
        assert req.export_csv is True
        assert req.export_vtk is False
        assert req.output_dir is None
        assert req.producer_kind == "surrogate"
        assert req.analysis_type == "static_structural"


# ---------------------------------------------------------------------------
# Metric extraction tests
# ---------------------------------------------------------------------------

class TestMetricExtraction:
    def test_extract_from_json_summary_static_structural(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.postprocessing import extract_result_metrics

        result_file = tmp_path / "result.json"
        result_file.write_text(
            json.dumps(
                {
                    "max_von_mises_stress_mpa": 150.5,
                    "max_displacement_mm": 0.42,
                    "factor_of_safety": 1.83,
                    "meets_stress_limit": True,
                    "meets_displacement_limit": True,
                }
            )
        )

        metrics = extract_result_metrics(str(result_file), "static_structural", "freecad_fem")
        names = {m.name for m in metrics}

        assert "max_von_mises_stress_mpa" in names
        assert "max_displacement_mm" in names
        assert "factor_of_safety" in names

        stress_metric = next(m for m in metrics if m.name == "max_von_mises_stress_mpa")
        assert stress_metric.value == 150.5
        assert stress_metric.status == "found"

    def test_missing_metrics_recorded_as_not_found(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.postprocessing import extract_result_metrics

        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps({"max_von_mises_stress_mpa": 150.5}))

        metrics = extract_result_metrics(str(result_file), "static_structural", "freecad_fem")

        displacement = next(m for m in metrics if m.name == "max_displacement_mm")
        assert displacement.status == "not_found"
        assert displacement.value is None

    def test_surrogate_defaults_when_no_result_source(self) -> None:
        from freecad_mcp.aieng_bridge.postprocessing import extract_result_metrics

        metrics = extract_result_metrics(None, "static_structural", "surrogate")
        names = {m.name for m in metrics}

        assert "max_von_mises_stress_mpa" in names
        assert all(m.status == "not_found" for m in metrics)

    def test_thermal_metrics(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.postprocessing import extract_result_metrics

        result_file = tmp_path / "result.json"
        result_file.write_text(
            json.dumps(
                {
                    "max_temperature_c": 85.0,
                    "min_temperature_c": 20.0,
                    "max_heat_flux_w_m2": 1200.5,
                }
            )
        )

        metrics = extract_result_metrics(str(result_file), "thermal", "surrogate")
        names = {m.name for m in metrics}

        assert "max_temperature_c" in names
        assert "min_temperature_c" in names
        assert "max_heat_flux_w_m2" in names

    def test_modal_metrics(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.postprocessing import extract_result_metrics

        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps({"natural_frequencies_hz": [45.2, 120.5, 300.1]}))

        metrics = extract_result_metrics(str(result_file), "modal", "surrogate")
        names = {m.name for m in metrics}

        assert "first_natural_frequency_hz" in names
        first = next(m for m in metrics if m.name == "first_natural_frequency_hz")
        assert first.value == 45.2

    def test_buckling_metrics(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.postprocessing import extract_result_metrics

        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps({"critical_load_factor": 2.5, "is_stable": True}))

        metrics = extract_result_metrics(str(result_file), "buckling", "surrogate")
        names = {m.name for m in metrics}

        assert "critical_load_factor" in names
        assert "is_stable" in names


# ---------------------------------------------------------------------------
# MCP tool tests
# ---------------------------------------------------------------------------

class TestPostprocessMcpTool:
    @pytest.mark.asyncio
    async def test_tool_rejects_persist_without_package_path(self) -> None:
        mcp, _, _ = _make_mcp_with_facade()
        tool = mcp._tool_manager._tools["aieng_postprocess_results"].fn
        response = await tool(persist_to_aieng=True)

        assert response["status"] == "rejected"
        assert "package_path" in str(response.get("errors", []))

    @pytest.mark.asyncio
    async def test_csv_artifact_export(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.postprocessing import export_postprocess_csv, ResultMetric

        metrics = [
            ResultMetric(name="stress", value=100.0, unit="MPa", status="found"),
            ResultMetric(name="displacement", value=0.5, unit="mm", status="found"),
        ]
        artifacts = export_postprocess_csv(metrics, str(tmp_path))

        assert len(artifacts) == 1
        assert artifacts[0].artifact_type == "csv"
        csv_path = Path(artifacts[0].path)
        assert csv_path.exists()

        lines = csv_path.read_text().strip().splitlines()
        assert lines[0] == "name,value,unit,status,source"
        assert "stress,100.0,MPa,found," in lines[1]

    @pytest.mark.asyncio
    async def test_vtk_unsupported_warning(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.postprocessing import (
            export_postprocess_vtk,
            ResultMetric,
        )

        metrics = [ResultMetric(name="stress", value=100.0, status="found")]
        artifacts = export_postprocess_vtk(metrics, str(tmp_path))

        assert len(artifacts) == 0

    @pytest.mark.asyncio
    async def test_postprocess_evidence_persists(self, tmp_path: Path) -> None:
        mcp, _, _ = _make_mcp_with_facade()

        # Create a mock result JSON
        result_file = tmp_path / "result.json"
        result_file.write_text(
            json.dumps(
                {
                    "max_von_mises_stress_mpa": 150.5,
                    "max_displacement_mm": 0.42,
                    "factor_of_safety": 1.83,
                    "meets_stress_limit": True,
                    "meets_displacement_limit": True,
                }
            )
        )

        # Build minimal .aieng package
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(
            json.dumps({"claims": [{"id": "c1", "status": "unsupported"}]})
        )

        tool = mcp._tool_manager._tools["aieng_postprocess_results"].fn
        response = await tool(
            package_path=str(tmp_path),
            result_source=str(result_file),
            persist_to_aieng=True,
            export_csv=True,
            export_vtk=False,
            producer_kind="surrogate",
            analysis_type="static_structural",
        )

        assert response["status"] == "success"
        assert len(response.get("artifacts_written", [])) >= 1

        evidence = json.loads((tmp_path / "results" / "evidence_index.json").read_text())
        assert len(evidence.get("entries", [])) >= 1

        trace = json.loads((tmp_path / "provenance" / "tool_trace.json").read_text())
        assert len(trace.get("entries", [])) >= 1

    @pytest.mark.asyncio
    async def test_claim_map_unchanged(self, tmp_path: Path) -> None:
        mcp, _, _ = _make_mcp_with_facade()

        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))

        tool = mcp._tool_manager._tools["aieng_postprocess_results"].fn
        response = await tool(
            package_path=str(tmp_path),
            persist_to_aieng=True,
            export_csv=False,
            export_vtk=False,
        )

        assert response["status"] in ("success", "partial")
        after = json.loads((tmp_path / "results" / "claim_map.json").read_text())
        assert after == claim_map

    @pytest.mark.asyncio
    async def test_standalone_mode_works(self) -> None:
        mcp, _, _ = _make_mcp_with_facade()

        tool = mcp._tool_manager._tools["aieng_postprocess_results"].fn
        response = await tool(
            persist_to_aieng=False,
            export_csv=True,
            export_vtk=False,
            producer_kind="surrogate",
            analysis_type="static_structural",
        )

        assert response["status"] == "success"
        assert len(response.get("metrics", [])) > 0
        assert response["claim_policy"]["claims_advanced"] is False

    @pytest.mark.asyncio
    async def test_claims_advanced_always_false(self, tmp_path: Path) -> None:
        mcp, _, _ = _make_mcp_with_facade()

        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps({"max_von_mises_stress_mpa": 150.5}))
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(
            json.dumps({"claims": [{"id": "c1", "status": "unsupported"}]})
        )

        tool = mcp._tool_manager._tools["aieng_postprocess_results"].fn
        response = await tool(
            package_path=str(tmp_path),
            result_source=str(result_file),
            persist_to_aieng=True,
            export_csv=True,
        )

        assert response["claim_policy"]["claims_advanced"] is False
        assert response["claim_policy"]["requires_explicit_update_claim"] is True

    @pytest.mark.asyncio
    async def test_metric_extraction_from_tool(self, tmp_path: Path) -> None:
        mcp, _, _ = _make_mcp_with_facade()

        result_file = tmp_path / "result.json"
        result_file.write_text(
            json.dumps(
                {
                    "max_von_mises_stress_mpa": 150.5,
                    "max_displacement_mm": 0.42,
                    "factor_of_safety": 1.83,
                }
            )
        )

        tool = mcp._tool_manager._tools["aieng_postprocess_results"].fn
        response = await tool(
            result_source=str(result_file),
            persist_to_aieng=False,
            export_csv=False,
            producer_kind="freecad_fem",
            analysis_type="static_structural",
        )

        assert response["status"] == "success"
        metrics = response.get("metrics", [])
        names = {m["name"] for m in metrics}
        assert "max_von_mises_stress_mpa" in names
        assert "max_displacement_mm" in names
        assert "factor_of_safety" in names


# ---------------------------------------------------------------------------
# CAD-to-CAE workflow integration tests
# ---------------------------------------------------------------------------

class TestCadToCaeWorkflowWithPostprocess:
    @pytest.mark.asyncio
    async def test_workflow_with_run_postprocess_includes_postprocess_summary(self, tmp_path: Path) -> None:
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
            run_postprocess=True,
            export_postprocess_csv=True,
            export_postprocess_vtk=False,
        )

        assert response["status"] in ("success", "partial")
        assert response.get("postprocess_summary") is not None

    @pytest.mark.asyncio
    async def test_workflow_postprocess_csv_artifact_included(self, tmp_path: Path) -> None:
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
            run_postprocess=True,
            export_postprocess_csv=True,
            export_postprocess_vtk=False,
        )

        assert response["status"] in ("success", "partial")
        artifacts = response.get("artifacts_written", [])
        assert any("postprocess_metrics.csv" in a for a in artifacts)


# ---------------------------------------------------------------------------
# Demo script test
# ---------------------------------------------------------------------------

def test_demo_script_runs() -> None:
    """Verify the post-processing demo script exits cleanly in mock mode."""
    import subprocess
    import sys

    script = Path(__file__).resolve().parent.parent / "scripts" / "run_postprocessing_demo.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)

    assert result.returncode == 0, f"Demo script failed:\n{result.stderr}"
    assert "Demo completed successfully" in result.stdout
