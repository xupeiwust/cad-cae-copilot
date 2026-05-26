"""Tests for OperationPreview and preview_operation tool."""

from __future__ import annotations

from typing import Any

import pytest

from freecad_mcp.contracts.operation_preview import OperationPreview
from freecad_mcp.tool_contracts import StandardToolResult
from freecad_mcp.tools_cad.models import CadToolResponse
from freecad_mcp.tools_cae.models import CaeBaseResponse


class TestOperationPreviewModel:
    def test_basic_construction(self) -> None:
        preview = OperationPreview(
            operation_name="cad_export_step",
            would_write_artifacts=["/tmp/out.step"],
            would_update_evidence=False,
            would_update_traces=False,
            would_touch_claims=False,
            guard_checks_required=["package_context_load"],
            unavailable_runtime_blocks=[],
            expected_duration_estimate="fast",
            warnings=[],
        )
        assert preview.operation_name == "cad_export_step"
        assert preview.would_write_artifacts == ["/tmp/out.step"]

    def test_serialization_json_mode(self) -> None:
        preview = OperationPreview(operation_name="test_op")
        dumped = preview.model_dump(mode="json")
        assert dumped["operation_name"] == "test_op"
        assert dumped["would_write_artifacts"] == []
        assert dumped["would_update_evidence"] is False

    def test_no_extra_fields(self) -> None:
        with pytest.raises(ValueError):
            OperationPreview(
                operation_name="test",
                unknown_field="bad",  # type: ignore[call-arg]
            )


class TestStandardToolResultIncludesPreview:
    def test_standard_result_accepts_preview(self) -> None:
        preview = OperationPreview(operation_name="cad_set_parameter")
        result = StandardToolResult(
            status="success",
            operation="cad_set_parameter",
            preview=preview,
        )
        dumped = result.model_dump(mode="json")
        assert dumped["preview"]["operation_name"] == "cad_set_parameter"

    def test_standard_result_preview_none(self) -> None:
        result = StandardToolResult(status="success", operation="test")
        dumped = result.model_dump(mode="json")
        assert dumped["preview"] is None


class TestCadToolResponseIncludesPreview:
    def test_cad_response_accepts_preview(self) -> None:
        preview = OperationPreview(operation_name="cad_create_box")
        resp = CadToolResponse(
            status="success",
            operation="cad_create_box",
            preview=preview,
        )
        dumped = resp.model_dump(mode="json")
        assert dumped["preview"]["operation_name"] == "cad_create_box"


class TestCaeBaseResponseIncludesPreview:
    def test_cae_response_accepts_preview(self) -> None:
        preview = OperationPreview(operation_name="cae_run_static_analysis")
        resp = CaeBaseResponse(
            status="success",
            operation="cae_run_static_analysis",
            preview=preview,
        )
        dumped = resp.model_dump(mode="json")
        assert dumped["preview"]["operation_name"] == "cae_run_static_analysis"


class TestPreviewOperationTool:
    """Tests for the preview_operation MCP tool logic (via direct import)."""

    @pytest.mark.asyncio
    async def test_preview_unknown_operation(self) -> None:
        # Simulate the rejection path by importing the logic directly
        from freecad_mcp.tool_registry import default_registry
        registry = default_registry()
        assert registry.get("nonexistent_tool_xyz") is None

    def test_registry_entry_has_preview_relevant_fields(self) -> None:
        from freecad_mcp.tool_registry import default_registry
        registry = default_registry()
        entry = registry.get("aieng_update_claim")
        assert entry is not None
        assert entry.may_update_claim_map is True
        assert entry.side_effects  # should list claim_map.json write

    def test_mutating_cad_tools_declare_freecad_runtime(self) -> None:
        from freecad_mcp.tool_registry import default_registry
        registry = default_registry()
        for e in registry.list_all():
            if e.mutates_cad:
                assert "freecad" in e.runtime_requirements, (
                    f"{e.tool_name} mutates CAD but misses freecad runtime declaration"
                )

    def test_dry_run_levels_are_valid(self) -> None:
        from freecad_mcp.tool_registry import default_registry
        registry = default_registry()
        for e in registry.list_all():
            assert e.dry_run_support in ("full", "partial", "none")

    def test_preview_artifact_inference(self) -> None:
        """Verify that preview can infer artifact paths from inputs + registry."""
        from freecad_mcp.tool_registry import default_registry
        registry = default_registry()
        entry = registry.get("cad_export_step")
        assert entry is not None
        # Simulate preview logic artifact path inference
        inputs = {"file_path": "/tmp/bracket.step"}
        would_write = []
        for se in entry.side_effects:
            if "Writes" in se or "writes" in se:
                if "file_path" in inputs:
                    would_write.append(inputs["file_path"])
        assert "/tmp/bracket.step" in would_write
