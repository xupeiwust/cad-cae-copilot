"""Tests for audit report generation.

Covers:
- Audit report generation from fixture package
- Evidence, trace, claim counts
- Reference map status detection
- Markdown generation
- MCP tool claim policy
- Claim discipline detection
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from freecad_mcp.aieng_bridge.audit import generate_audit_report


def _copy_parametric_bracket(tmp_path: Path) -> Path:
    fixture = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / "package"
    assert fixture.exists(), f"Fixture not found: {fixture}"
    dst = tmp_path / "package"
    shutil.copytree(fixture, dst)
    return dst


def _build_reference_map(package_path: Path) -> None:
    from freecad_mcp.aieng_bridge.references import build_reference_map, write_reference_map

    ref_map = build_reference_map(str(package_path))
    write_reference_map(str(package_path), ref_map)


class TestAuditReportGeneration:
    def test_generate_audit_report_creates_json_and_md(self, tmp_path: Path) -> None:
        package_path = _copy_parametric_bracket(tmp_path)
        _build_reference_map(package_path)

        result = generate_audit_report(str(package_path))
        assert result["status"] == "success"
        assert len(result["written_paths"]) == 2

        audit_json = package_path / "reports" / "audit_report.json"
        audit_md = package_path / "reports" / "audit_report.md"
        assert audit_json.exists()
        assert audit_md.exists()

    def test_audit_report_counts_empty_package(self, tmp_path: Path) -> None:
        package_path = _copy_parametric_bracket(tmp_path)
        result = generate_audit_report(str(package_path), output_markdown=False)

        report = result["report"]
        assert report["evidence_summary"]["total"] == 0
        assert report["trace_summary"]["total"] == 0
        assert report["patch_run_summary"]["total"] == 0
        assert report["reference_map_summary"]["exists"] is False
        assert report["claim_summary"]["total"] == 3

    def test_audit_report_counts_evidence_and_traces(self, tmp_path: Path) -> None:
        package_path = _copy_parametric_bracket(tmp_path)
        from freecad_mcp.aieng_bridge.persistence import append_evidence_entry, append_trace_entry

        append_evidence_entry(
            str(package_path),
            {
                "evidence_id": "ev-test-001",
                "evidence_type": "solver_execution",
                "producer_kind": "surrogate",
                "status": "success",
                "metadata": {"engineering_validation": False, "claims_advanced": False},
            },
        )
        append_evidence_entry(
            str(package_path),
            {
                "evidence_id": "ev-test-002",
                "evidence_type": "postprocess",
                "producer_kind": "freecad_fem",
                "status": "partial",
                "metadata": {"engineering_validation": False, "claims_advanced": False},
            },
        )
        append_trace_entry(
            str(package_path),
            {
                "trace_id": "trace-test-001",
                "producer": "freecad_mcp",
                "operation": "aieng_execute_patch",
                "status": "success",
                "inputs": {},
                "outputs": {},
            },
        )

        result = generate_audit_report(str(package_path), output_markdown=False)
        report = result["report"]

        assert report["evidence_summary"]["total"] == 2
        assert report["evidence_summary"]["by_type"]["solver_execution"] == 1
        assert report["evidence_summary"]["by_type"]["postprocess"] == 1
        assert report["evidence_summary"]["by_producer_kind"]["surrogate"] == 1
        assert report["evidence_summary"]["by_producer_kind"]["freecad_fem"] == 1
        assert report["trace_summary"]["total"] == 1
        assert report["trace_summary"]["by_operation"]["aieng_execute_patch"] == 1

    def test_audit_report_detects_reference_map_needs_review(self, tmp_path: Path) -> None:
        package_path = _copy_parametric_bracket(tmp_path)
        from freecad_mcp.aieng_bridge.references import (
            GeometryReference,
            ReferenceMap,
            write_reference_map,
        )

        ref_map = ReferenceMap(
            geometry_references=[
                GeometryReference(ref_id="ref-1", feature_id="feat-1", status="valid"),
                GeometryReference(ref_id="ref-2", feature_id="feat-2", status="needs_review"),
                GeometryReference(ref_id="ref-3", feature_id="feat-3", status="unresolved"),
            ],
            cae_targets=[],
        )
        write_reference_map(str(package_path), ref_map)

        result = generate_audit_report(str(package_path), output_markdown=False)
        report = result["report"]

        assert report["reference_map_summary"]["exists"] is True
        assert report["reference_map_summary"]["geometry_reference_count"] == 3
        assert report["reference_map_summary"]["status_counts"]["valid"] == 1
        assert report["reference_map_summary"]["status_counts"]["needs_review"] == 1
        assert report["reference_map_summary"]["status_counts"]["unresolved"] == 1

    def test_audit_report_markdown_is_human_readable(self, tmp_path: Path) -> None:
        package_path = _copy_parametric_bracket(tmp_path)
        _build_reference_map(package_path)

        result = generate_audit_report(str(package_path), output_json=False)
        md_path = package_path / "reports" / "audit_report.md"
        assert md_path.exists()

        content = md_path.read_text(encoding="utf-8")
        assert "# .aieng Package Audit Report" in content
        assert "## Evidence Summary" in content
        assert "## Claim Summary" in content
        assert "## Claim Discipline" in content
        assert package_path.name in content

    def test_audit_report_claim_discipline_no_violations(self, tmp_path: Path) -> None:
        package_path = _copy_parametric_bracket(tmp_path)
        from freecad_mcp.aieng_bridge.persistence import append_evidence_entry

        append_evidence_entry(
            str(package_path),
            {
                "evidence_id": "ev-clean",
                "evidence_type": "test",
                "producer_kind": "mock",
                "status": "success",
                "metadata": {"engineering_validation": False, "claims_advanced": False},
            },
        )

        result = generate_audit_report(str(package_path), output_markdown=False)
        report = result["report"]

        assert report["claim_discipline_summary"]["tools_did_not_auto_advance_claims"] is True
        assert report["claim_discipline_summary"]["violations"] == []
        assert report["claim_discipline_summary"]["explicit_update_trace_count"] == 0

    def test_audit_report_detects_claim_advancement_violation(self, tmp_path: Path) -> None:
        package_path = _copy_parametric_bracket(tmp_path)
        from freecad_mcp.aieng_bridge.persistence import append_evidence_entry

        append_evidence_entry(
            str(package_path),
            {
                "evidence_id": "ev-bad",
                "evidence_type": "test",
                "producer_kind": "mock",
                "status": "success",
                "metadata": {"claims_advanced": True},
            },
        )

        result = generate_audit_report(str(package_path), output_markdown=False)
        report = result["report"]

        assert report["claim_discipline_summary"]["tools_did_not_auto_advance_claims"] is False
        assert len(report["claim_discipline_summary"]["violations"]) == 1
        assert "claims_advanced=True" in report["claim_discipline_summary"]["violations"][0]

    def test_audit_report_counts_patch_runs(self, tmp_path: Path) -> None:
        package_path = _copy_parametric_bracket(tmp_path)
        patch_runs_dir = package_path / "execution" / "patch_runs"
        patch_runs_dir.mkdir(parents=True, exist_ok=True)
        (patch_runs_dir / "run_001.json").write_text("{}", encoding="utf-8")
        (patch_runs_dir / "run_002.json").write_text("{}", encoding="utf-8")

        result = generate_audit_report(str(package_path), output_markdown=False)
        report = result["report"]

        assert report["patch_run_summary"]["total"] == 2
        assert "run_001" in report["patch_run_summary"]["run_ids"]
        assert "run_002" in report["patch_run_summary"]["run_ids"]

    def test_audit_report_claim_policy(self, tmp_path: Path) -> None:
        package_path = _copy_parametric_bracket(tmp_path)
        result = generate_audit_report(str(package_path), output_markdown=False)
        assert result["claim_policy"]["claims_advanced"] is False
        assert result["claim_policy"]["requires_explicit_update_claim"] is True


class TestAuditMcpTool:
    @pytest.mark.anyio
    async def test_aieng_generate_audit_report_tool_returns_result(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.tools_aieng import register_aieng_tools
        from freecad_mcp.bridge.executor import FreecadExecutor

        class _NoOpExecutor(FreecadExecutor):
            async def execute_async(self, code: str) -> dict:
                return {}
            async def get_version_async(self) -> dict:
                return {}

        mcp = FastMCP(name="test")
        register_aieng_tools(mcp, _NoOpExecutor())
        tool = mcp._tool_manager._tools["aieng_generate_audit_report"].fn

        with pytest.MonkeyPatch.context() as mp:
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                pkg = Path(td) / "package"
                shutil.copytree(
                    Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / "package",
                    pkg,
                )
                result = await tool(package_path=str(pkg))
                assert result["status"] == "success"
                assert result["operation"] == "aieng_generate_audit_report"
                assert result["claim_policy"]["claims_advanced"] is False
                assert any("audit_report.json" in p for p in result["written_paths"])
                assert any("audit_report.md" in p for p in result["written_paths"])

    @pytest.mark.anyio
    async def test_aieng_generate_audit_report_rejects_invalid_package(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.tools_aieng import register_aieng_tools
        from freecad_mcp.bridge.executor import FreecadExecutor

        class _NoOpExecutor(FreecadExecutor):
            async def execute_async(self, code: str) -> dict:
                return {}
            async def get_version_async(self) -> dict:
                return {}

        mcp = FastMCP(name="test")
        register_aieng_tools(mcp, _NoOpExecutor())
        tool = mcp._tool_manager._tools["aieng_generate_audit_report"].fn

        result = await tool(package_path="/nonexistent/path")
        assert result["status"] == "rejected"
