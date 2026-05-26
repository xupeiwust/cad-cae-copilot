"""Tests for the capability inspection tool (aieng_bridge.planner).

The planner is read-only and planning-neutral. It must never:
- execute CAD or CAE operations
- modify the filesystem
- advance claims
- prescribe workflow sequences or ranking
"""

from __future__ import annotations

import pytest

from freecad_mcp.aieng_bridge.planner import (
    CapabilityInspectionRequest,
    CapabilityInspectionSummary,
    CapabilityToolInfo,
    CapabilityPlanRequest,
    CapabilityPlanSummary,
    inspect_capabilities,
    plan_capabilities,
    _load_package_context,
    _match_tools_by_outcome,
)


class TestLoadPackageContext:
    def test_none_path_returns_empty(self):
        ctx = _load_package_context(None)
        assert ctx == {}

    def test_nonexistent_package_returns_minimal(self):
        ctx = _load_package_context("/nonexistent/package")
        assert ctx["package_path"] == "/nonexistent/package"
        assert ctx.get("has_simulation_setup") is False
        assert ctx.get("has_evidence") is False
        assert ctx.get("has_claims") is False


class TestMatchToolsByOutcome:
    def test_cad_inspect_outcome(self):
        request = CapabilityInspectionRequest(desired_outcome="inspect cad model")
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, {}, {})
        tool_names = [t.tool_name for t in tools]
        assert "freecad_inspect_model" in tool_names
        assert "freecad_runtime_capabilities" in tool_names
        assert "freecad_create_static_structural_analysis" not in tool_names

    def test_cad_modify_outcome(self):
        request = CapabilityInspectionRequest(desired_outcome="modify parameter")
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, {}, {})
        tool_names = [t.tool_name for t in tools]
        assert "freecad_inspect_model" in tool_names
        assert "freecad_apply_parameter_edit" in tool_names
        # Neutral inspection does not auto-add export; only keyword-matched tools appear

    def test_cae_outcome_includes_mesh_and_solver(self):
        request = CapabilityInspectionRequest(desired_outcome="run stress analysis")
        runtime = {"solver_available": True}
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, runtime, {})
        tool_names = [t.tool_name for t in tools]
        assert "freecad_create_static_structural_analysis" in tool_names
        assert "freecad_run_calculix" in tool_names
        assert "aieng_postprocess_results" in tool_names
        # Neutral inspection exposes keyword-matched tools, not full CAE pipeline steps

    def test_cae_solver_unavailable_warning(self):
        request = CapabilityInspectionRequest(desired_outcome="run stress analysis")
        runtime = {"solver_available": False}
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, runtime, {})
        assert any("CalculiX solver not detected" in u for u in unsupported)
        assert any("CalculiX solver not available" in m for m in missing)

    def test_claim_outcome_includes_update_claim(self):
        request = CapabilityInspectionRequest(desired_outcome="update claim")
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, {}, {})
        tool_names = [t.tool_name for t in tools]
        assert "aieng_update_claim" in tool_names

    def test_claim_with_prior_tools_no_missing_evidence_warning(self):
        request = CapabilityInspectionRequest(desired_outcome="run stress analysis and update claim")
        runtime = {"solver_available": True}
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, runtime, {})
        tool_names = [t.tool_name for t in tools]
        assert "freecad_run_calculix" in tool_names
        assert "aieng_postprocess_results" in tool_names
        assert "aieng_update_claim" in tool_names

    def test_reference_outcome(self):
        request = CapabilityInspectionRequest(desired_outcome="build reference map")
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, {}, {})
        tool_names = [t.tool_name for t in tools]
        assert "aieng_build_reference_map" in tool_names
        assert "aieng_mark_references_needing_review" in tool_names

    def test_audit_outcome(self):
        request = CapabilityInspectionRequest(desired_outcome="audit package")
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, {}, {})
        tool_names = [t.tool_name for t in tools]
        assert "aieng_generate_audit_report" in tool_names

    def test_unknown_outcome_fallback(self):
        request = CapabilityInspectionRequest(desired_outcome="do something weird")
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, {}, {})
        assert tools == []
        assert any("did not match any known capability keywords" in w for w in warns)

    def test_cad_disallowed_skips_cad_tools(self):
        request = CapabilityInspectionRequest(
            desired_outcome="inspect cad model", allow_cad_operations=False
        )
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, {}, {})
        tool_names = [t.tool_name for t in tools]
        assert "freecad_inspect_model" not in tool_names
        assert "freecad_apply_parameter_edit" not in tool_names

    def test_cae_disallowed_skips_cae_tools(self):
        request = CapabilityInspectionRequest(
            desired_outcome="run stress analysis", allow_cae_operations=False
        )
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, {}, {})
        tool_names = [t.tool_name for t in tools]
        assert "freecad_create_static_structural_analysis" not in tool_names
        assert "freecad_generate_mesh" not in tool_names
        assert "freecad_run_calculix" not in tool_names

    def test_claim_disallowed_skips_claim_tools(self):
        request = CapabilityInspectionRequest(
            desired_outcome="update claim", allow_claim_update=False
        )
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, {}, {})
        tool_names = [t.tool_name for t in tools]
        assert "aieng_update_claim" not in tool_names

    def test_no_sequencing_or_ranking(self):
        """Tools must not be ranked or sequenced; just exposed."""
        request = CapabilityInspectionRequest(desired_outcome="run stress analysis")
        runtime = {"solver_available": True}
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, runtime, {})
        # There should be no step_id or ordering metadata
        for tool in tools:
            assert not hasattr(tool, "step_id")
            assert not hasattr(tool, "order")
            assert not hasattr(tool, "rank")

    def test_tools_expose_side_effects(self):
        request = CapabilityInspectionRequest(desired_outcome="modify parameter")
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, {}, {})
        modify_tool = next((t for t in tools if t.tool_name == "freecad_apply_parameter_edit"), None)
        assert modify_tool is not None
        assert modify_tool.side_effects
        assert modify_tool.mutates_cad is True
        assert modify_tool.mutates_package is True
        assert modify_tool.may_update_claim_map is False

    def test_claim_tool_only_one_with_may_update_claim_map(self):
        request = CapabilityInspectionRequest(desired_outcome="update claim")
        tools, missing, unsupported, warns = _match_tools_by_outcome(request, {}, {})
        claim_tool = next((t for t in tools if t.tool_name == "aieng_update_claim"), None)
        assert claim_tool is not None
        assert claim_tool.may_update_claim_map is True
        for tool in tools:
            if tool.tool_name != "aieng_update_claim":
                assert tool.may_update_claim_map is False


class TestInspectCapabilities:
    def test_standalone_mode_no_package(self):
        request = CapabilityInspectionRequest(desired_outcome="inspect model")
        summary = inspect_capabilities(request)
        assert summary.mode == "standalone"
        assert summary.status in ("success", "partial", "unsupported")
        assert summary.desired_outcome == "inspect model"
        assert any(
            "CAD modification does not automatically trigger CAE execution" in r
            for r in summary.policy_reminders
        )
        assert any(
            "The agent or caller decides workflow ordering" in r
            for r in summary.policy_reminders
        )

    def test_aieng_enhanced_mode_with_package(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "manifest.json").write_text('{"version": "1.0.0"}')
        request = CapabilityInspectionRequest(
            desired_outcome="inspect model", package_path=str(pkg)
        )
        summary = inspect_capabilities(request)
        assert summary.mode == "aieng_enhanced"
        assert "manifest.json available" in summary.available_context

    def test_unsupported_when_freecad_missing(self, monkeypatch):
        """If FreeCAD is not detected, status should be unsupported."""
        monkeypatch.setattr(
            "freecad_mcp.aieng_bridge.planner.detect_freecad_runtime",
            lambda: {
                "freecad_available": False,
                "fem_workbench": False,
                "solver_available": False,
            },
        )
        request = CapabilityInspectionRequest(desired_outcome="run stress analysis")
        summary = inspect_capabilities(request)
        assert summary.status == "unsupported"
        assert any("FreeCAD not detected" in u for u in summary.unsupported_operations)

    def test_partial_when_simulation_setup_missing(self, tmp_path, monkeypatch):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        monkeypatch.setattr(
            "freecad_mcp.aieng_bridge.planner.detect_freecad_runtime",
            lambda: {
                "freecad_available": True,
                "fem_workbench": True,
                "solver_available": True,
            },
        )
        request = CapabilityInspectionRequest(
            desired_outcome="run stress analysis", package_path=str(pkg)
        )
        summary = inspect_capabilities(request)
        assert summary.status == "partial"
        assert any("simulation/setup.yaml" in m for m in summary.missing_information)

    def test_no_mutating_side_effects(self, tmp_path):
        """inspect_capabilities must not create or modify files."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        before = set(pkg.iterdir())
        request = CapabilityInspectionRequest(
            desired_outcome="audit package", package_path=str(pkg)
        )
        inspect_capabilities(request)
        after = set(pkg.iterdir())
        assert before == after

    def test_no_claim_advancement(self):
        request = CapabilityInspectionRequest(desired_outcome="update claim")
        summary = inspect_capabilities(request)
        # The inspection itself does not advance claims
        assert summary.possibly_relevant_tools
        claim_tool = next(
            (t for t in summary.possibly_relevant_tools if t.tool_name == "aieng_update_claim"), None
        )
        assert claim_tool is not None
        assert claim_tool.may_update_claim_map is True

    def test_neutral_language_no_recommended_steps(self):
        request = CapabilityInspectionRequest(desired_outcome="run stress analysis")
        summary = inspect_capabilities(request)
        # Must use possibly_relevant_tools, not recommended_steps
        assert hasattr(summary, "possibly_relevant_tools")
        assert not hasattr(summary, "recommended_steps")

    def test_needs_review_for_risky_tools(self):
        request = CapabilityInspectionRequest(desired_outcome="modify parameter and run solver")
        summary = inspect_capabilities(request)
        assert any("CAD modification" in n for n in summary.needs_review)
        assert any("Solver execution" in n for n in summary.needs_review)


class TestPlanCapabilitiesBackwardCompatibility:
    def test_legacy_request_returns_legacy_summary(self, monkeypatch):
        monkeypatch.setattr(
            "freecad_mcp.aieng_bridge.planner.detect_freecad_runtime",
            lambda: {
                "freecad_available": True,
                "fem_workbench": True,
                "solver_available": True,
            },
        )
        request = CapabilityPlanRequest(desired_outcome="inspect model")
        with pytest.warns(DeprecationWarning):
            summary = plan_capabilities(request)
        assert isinstance(summary, CapabilityPlanSummary)
        assert summary.mode in ("standalone", "aieng_enhanced")
        assert hasattr(summary, "recommended_steps")


class TestCapabilityModels:
    def test_tool_info_defaults(self):
        tool = CapabilityToolInfo(tool_name="x", category="cad", purpose="y")
        assert tool.required_inputs == []
        assert tool.optional_inputs == []
        assert tool.side_effects == []
        assert tool.mutates_cad is False
        assert tool.mutates_package is False
        assert tool.may_update_claim_map is False
        assert tool.notes == []

    def test_inspection_summary_defaults(self):
        summary = CapabilityInspectionSummary(
            status="success", mode="standalone"
        )
        assert summary.possibly_relevant_tools == []
        assert summary.missing_information == []
        assert summary.unsupported_operations == []
        assert summary.needs_review == []
        assert summary.policy_reminders == []
        assert summary.warnings == []

    def test_inspection_request_defaults(self):
        req = CapabilityInspectionRequest(desired_outcome="test")
        assert req.package_path is None
        assert req.include_runtime_capabilities is True
        assert req.allow_cad_operations is True
        assert req.allow_cae_operations is True
        assert req.allow_claim_update is True
