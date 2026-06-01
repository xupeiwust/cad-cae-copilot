"""Tests for the unified tool transparency registry."""

from __future__ import annotations

import pytest

from freecad_mcp.tool_registry import ToolRegistry, ToolRegistryEntry, default_registry


class TestToolRegistryBasics:
    def test_default_registry_loads(self) -> None:
        registry = default_registry()
        entries = registry.list_all()
        assert len(entries) > 0
        # Every entry should have a non-empty tool_name and purpose
        for e in entries:
            assert e.tool_name
            assert e.purpose

    def test_registry_lookup_by_name(self) -> None:
        registry = default_registry()
        entry = registry.get("aieng_update_claim")
        assert entry is not None
        assert entry.category == "claim"
        assert entry.may_update_claim_map is True
        assert entry.mutates_cad is False

    def test_registry_lookup_missing(self) -> None:
        registry = default_registry()
        assert registry.get("nonexistent_tool_12345") is None


class TestToolRegistryFiltering:
    def test_filter_by_category(self) -> None:
        registry = default_registry()
        cad_tools = registry.filter(category="cad")
        assert all(e.category == "cad" for e in cad_tools)
        assert len(cad_tools) >= 10

    def test_filter_by_keyword(self) -> None:
        registry = default_registry()
        results = registry.filter(keyword="claim")
        assert len(results) >= 1
        # Should include aieng_update_claim and possibly others
        names = {e.tool_name for e in results}
        assert "aieng_update_claim" in names

    def test_filter_by_mutability_cad(self) -> None:
        registry = default_registry()
        results = registry.filter(mutability="cad")
        assert all(e.mutates_cad for e in results)
        assert len(results) >= 5

    def test_filter_by_mutability_package(self) -> None:
        registry = default_registry()
        results = registry.filter(mutability="package")
        assert all(e.mutates_package for e in results)
        assert len(results) >= 3

    def test_filter_by_mutability_claim_map(self) -> None:
        registry = default_registry()
        results = registry.filter(mutability="claim_map")
        assert all(e.may_update_claim_map for e in results)
        assert len(results) == 1
        assert results[0].tool_name == "aieng_update_claim"

    def test_filter_by_mutability_none(self) -> None:
        registry = default_registry()
        results = registry.filter(mutability="none")
        assert all(
            not e.mutates_cad and not e.mutates_package and not e.may_update_claim_map
            for e in results
        )
        assert len(results) >= 5

    def test_filter_by_mutability_any(self) -> None:
        registry = default_registry()
        results = registry.filter(mutability="any")
        assert all(
            e.mutates_cad or e.mutates_package or e.may_update_claim_map for e in results
        )
        assert len(results) >= 5

    def test_filter_combined(self) -> None:
        registry = default_registry()
        results = registry.filter(category="cad", mutability="none")
        assert all(e.category == "cad" for e in results)
        assert all(not e.mutates_cad for e in results)

    def test_filter_no_match(self) -> None:
        registry = default_registry()
        results = registry.filter(category="nonexistent_category")
        assert results == []


class TestToolRegistryConsistency:
    """Verify registry declarations match implementation reality."""

    _EXPECTED_TOOLS: set[str] = {
        # CAD
        "cad_get_version",
        "cad_create_document",
        "cad_save_document",
        "cad_close_document",
        "cad_list_documents",
        "cad_list_objects",
        "cad_inspect_object",
        "cad_delete_object",
        "cad_set_placement",
        "cad_create_box",
        "cad_create_cylinder",
        "cad_create_sphere",
        "cad_create_cone",
        "cad_create_partdesign_body",
        "cad_create_sketch",
        "cad_pad_sketch",
        "cad_pocket_sketch",
        "cad_fillet_edges",
        "cad_chamfer_edges",
        "cad_boolean_fuse",
        "cad_boolean_cut",
        "cad_boolean_common",
        "cad_export_step",
        "cad_export_fcstd",
        "cad_set_parameter",
        "cad_import_step",
        # CAE
        "aieng_inspect_context",
        "cae_create_analysis",
        "cae_generate_mesh",
        "cae_run_static_analysis",
        "cae_extract_results",
        "cae_generate_report_data",
        "cae_inspect_geometry",
        "cae_run_thermal_analysis",
        "cae_run_modal_analysis",
        "cae_run_buckling_analysis",
        # AIENG / bridge
        "aieng_parse_patch",
        "aieng_execute_patch",
        "aieng_run_cad_to_cae_workflow",
        "aieng_orchestrate_cad_cae_sequence",
        "aieng_postprocess_results",
        "aieng_update_claim",
        "aieng_get_reference_map",
        "aieng_build_reference_map",
        "aieng_mark_references_needing_review",
        "aieng_inspect_capabilities",
        "aieng_plan_capabilities",
        "aieng_read_design_targets",
        "aieng_read_design_target_comparisons",
        "aieng_generate_audit_report",
        "freecad_runtime_capabilities",
        # Registry
        "aieng_tool_registry_query",
    }

    def test_all_expected_tools_present(self) -> None:
        registry = default_registry()
        registered_names = {e.tool_name for e in registry.list_all()}
        missing = self._EXPECTED_TOOLS - registered_names
        assert not missing, f"Missing registry entries: {missing}"

    def test_no_unexpected_tools(self) -> None:
        registry = default_registry()
        registered_names = {e.tool_name for e in registry.list_all()}
        extra = registered_names - self._EXPECTED_TOOLS
        assert not extra, f"Unexpected registry entries: {extra}"

    def test_claim_tool_is_unique_claim_map_mutator(self) -> None:
        registry = default_registry()
        claim_map_mutators = [
            e for e in registry.list_all() if e.may_update_claim_map
        ]
        assert len(claim_map_mutators) == 1
        assert claim_map_mutators[0].tool_name == "aieng_update_claim"

    def test_all_tools_have_dry_run_declaration(self) -> None:
        registry = default_registry()
        for e in registry.list_all():
            assert e.dry_run_support in ("full", "partial", "none")

    def test_all_mutating_tools_have_runtime_declared(self) -> None:
        registry = default_registry()
        for e in registry.list_all():
            if e.mutates_cad:
                assert "freecad" in e.runtime_requirements, (
                    f"{e.tool_name} mutates CAD but does not declare freecad runtime"
                )

    def test_registry_serialization(self) -> None:
        registry = default_registry()
        dumped = registry.model_dump(mode="json")
        assert isinstance(dumped, list)
        assert len(dumped) == len(registry.list_all())
        for item in dumped:
            assert "tool_name" in item
            assert "category" in item
            assert "purpose" in item


class TestToolRegistryEntryModel:
    def test_entry_creation(self) -> None:
        entry = ToolRegistryEntry(
            tool_name="test_tool",
            category="cad",
            purpose="Test purpose",
            mutates_cad=True,
            dry_run_support="none",
        )
        assert entry.tool_name == "test_tool"
        assert entry.mutates_package is False

    def test_entry_invalid_category(self) -> None:
        with pytest.raises(ValueError):
            ToolRegistryEntry(
                tool_name="bad",
                category="invalid_category",  # type: ignore[arg-type]
                purpose="bad",
            )

    def test_entry_invalid_dry_run(self) -> None:
        with pytest.raises(ValueError):
            ToolRegistryEntry(
                tool_name="bad",
                category="cad",
                purpose="bad",
                dry_run_support="maybe",  # type: ignore[arg-type]
            )
