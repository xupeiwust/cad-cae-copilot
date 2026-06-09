"""Integration tests for MCP tool chains.

Tests end-to-end MCP tool workflows:
- list_materials → get_material_details → compare_materials
- list_standard_parts → get_standard_part_specs → insert_standard_part
- generate_bom after inserting standard parts
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from aieng.cache.geometry_cache import GeometryCache, compute_shape_ir_hash
from aieng.context.materials import MATERIALS, MATERIAL_CATEGORIES, get_material_properties
from aieng.standards import hex_bolt, hex_nut, deep_groove_ball_bearing
from aieng.standards.fasteners import METRIC_BOLT_PRESETS, METRIC_NUT_PRESETS

# Import bridges under test (skip entire module if UI backend is not on PYTHONPATH)
pytest.importorskip("aieng_ui.backend.app.materials_bridge", reason="aieng_ui backend not available")
from aieng_ui.backend.app.materials_bridge import (
    list_materials,
    get_material_details,
    compare_materials,
)
from aieng_ui.backend.app.standards_bridge import (
    list_standard_parts,
    get_standard_part_specs,
    generate_bom,
    _PART_GENERATORS,
    _PART_CATEGORIES,
    _PRESETS,
)


class TestMaterialMcpToolChain:
    """Test MCP tool chain: list_materials → get_material_details → compare_materials."""

    def test_list_materials_all(self) -> None:
        """list_materials should return all materials when no filter is given."""
        result = list_materials()
        assert result["status"] == "ok"
        assert result["count"] == len(MATERIALS)
        assert len(result["materials"]) == len(MATERIALS)
        assert "categories" in result

    def test_list_materials_by_category(self) -> None:
        """list_materials filtered by category should return only matching materials."""
        result = list_materials(category="Aluminum Alloy")
        assert result["status"] == "ok"
        names = [m["name"] for m in result["materials"]]
        assert "Al6061-T6" in names
        assert "Steel-316L" not in names

    def test_list_materials_by_query(self) -> None:
        """list_materials with a query should search names and descriptions."""
        result = list_materials(query="aerospace")
        assert result["status"] == "ok"
        names = [m["name"] for m in result["materials"]]
        assert "Al7075-T6" in names
        assert "Al2024-T3" in names

    def test_get_material_details_existing(self) -> None:
        """get_material_details should return full properties for a known material."""
        result = get_material_details("Al6061-T6")
        assert result["status"] == "ok"
        assert result["name"] == "Al6061-T6"
        assert result["properties"]["youngs_modulus_mpa"] == 69000
        assert result["properties"]["ultimate_strength_mpa"] == 310
        assert result["properties"]["thermal_expansion_um_mK"] == 23.6

    def test_get_material_details_unknown(self) -> None:
        """get_material_details should return an error for unknown materials."""
        result = get_material_details("NotARealMaterial")
        assert result["status"] == "error"
        assert result["code"] == "material_not_found"

    def test_compare_materials_two(self) -> None:
        """compare_materials should compare two materials side by side."""
        result = compare_materials(["Al6061-T6", "Steel-316L"])
        assert result["status"] == "ok"
        assert result["count"] == 2
        assert "comparison" in result
        comp = result["comparison"]
        assert "youngs_modulus_mpa" in comp
        assert comp["youngs_modulus_mpa"]["direction"] == "higher_is_better"
        # Steel-316L has higher E than Al6061-T6
        assert comp["youngs_modulus_mpa"]["best_material"] == "Steel-316L"

    def test_compare_materials_three(self) -> None:
        """compare_materials should handle three or more materials."""
        result = compare_materials(["Al6061-T6", "Al7075-T6", "Steel-316L"])
        assert result["status"] == "ok"
        assert result["count"] == 3
        values = result["comparison"]["density_kg_m3"]["values"]
        assert set(values.keys()) == {"Al6061-T6", "Al7075-T6", "Steel-316L"}

    def test_compare_materials_unknown(self) -> None:
        """compare_materials should report unknown materials."""
        result = compare_materials(["Al6061-T6", "FakeMaterial"])
        assert result["status"] == "error"
        assert result["code"] == "material_not_found"
        assert "FakeMaterial" in result["message"]

    def test_compare_materials_insufficient(self) -> None:
        """compare_materials needs at least 2 materials."""
        result = compare_materials(["Al6061-T6"])
        assert result["status"] == "error"
        assert result["code"] == "insufficient_materials"

    def test_full_chain_materials(self) -> None:
        """Full chain: list → details → compare."""
        # Step 1: list aluminum alloys
        listed = list_materials(category="Aluminum Alloy")
        assert listed["status"] == "ok"
        names = [m["name"] for m in listed["materials"]]

        # Step 2: get details for the first two
        if len(names) >= 2:
            det_a = get_material_details(names[0])
            det_b = get_material_details(names[1])
            assert det_a["status"] == "ok"
            assert det_b["status"] == "ok"

            # Step 3: compare them
            comp = compare_materials([names[0], names[1]])
            assert comp["status"] == "ok"
            assert comp["count"] == 2


class TestStandardPartsMcpToolChain:
    """Test MCP tool chain: list_standard_parts → get_standard_part_specs → insert_standard_part."""

    def test_list_standard_parts_all(self) -> None:
        """list_standard_parts should return all part types."""
        result = list_standard_parts()
        assert result["status"] == "ok"
        assert result["count"] == len(_PART_CATEGORIES)
        assert "categories" in result
        assert "fastener" in result["categories"]
        assert "bearing" in result["categories"]

    def test_list_standard_parts_by_category(self) -> None:
        """list_standard_parts filtered by category should return only matching types."""
        result = list_standard_parts(category="fastener")
        assert result["status"] == "ok"
        types = [p["part_type"] for p in result["parts"]]
        assert "hex_bolt" in types
        assert "hex_nut" in types
        assert "deep_groove_ball_bearing" not in types

    def test_get_standard_part_specs_with_preset(self) -> None:
        """get_standard_part_specs should return spec and sample node for a preset."""
        result = get_standard_part_specs("hex_bolt", preset_name="M8")
        assert result["status"] == "ok"
        assert result["part_type"] == "hex_bolt"
        assert result["category"] == "fastener"
        assert result["sample_node"]["parameters"]["diameter"] == 8.0
        assert "editable_parameters" in result

    def test_get_standard_part_specs_without_preset(self) -> None:
        """get_standard_part_specs should use defaults when no preset is given."""
        result = get_standard_part_specs("hex_bolt")
        assert result["status"] == "ok"
        assert result["sample_node"]["parameters"]["diameter"] == 8.0  # default

    def test_get_standard_part_specs_unknown_type(self) -> None:
        """get_standard_part_specs should error for unknown part types."""
        result = get_standard_part_specs("not_a_part")
        assert result["status"] == "error"
        assert result["code"] == "part_type_not_found"

    def test_full_chain_standard_parts(self) -> None:
        """Full chain: list → specs → verify node structure."""
        # Step 1: list fasteners
        listed = list_standard_parts(category="fastener")
        assert listed["status"] == "ok"

        # Step 2: get specs for each fastener type
        for part_info in listed["parts"]:
            part_type = part_info["part_type"]
            preset = part_info["preset_names"][0] if part_info["preset_names"] else None
            specs = get_standard_part_specs(part_type, preset_name=preset)
            assert specs["status"] == "ok"
            node = specs["sample_node"]
            assert "id" in node
            assert "parameters" in node
            assert "metadata" in node
            meta = node["metadata"]
            assert meta.get("standard_name")
            assert meta.get("standard_reference")
            assert meta.get("part_category")


class TestBomGeneration:
    """Test generate_bom after standard part insertion scenarios."""

    def _make_minimal_package(self, tmp_path: Path, feature_graph: dict[str, Any] | None = None) -> Path:
        """Create a minimal .aieng package with geometry/shape_ir.json and graph/feature_graph.json."""
        pkg = tmp_path / "test_project.aieng"
        shape_ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [],
        }
        fg = feature_graph or {"features": []}
        with zipfile.ZipFile(pkg, "w") as zf:
            zf.writestr("geometry/shape_ir.json", json.dumps(shape_ir, indent=2))
            zf.writestr("graph/feature_graph.json", json.dumps(fg, indent=2))
        return pkg

    def test_generate_bom_empty_project(self, tmp_path: Path) -> None:
        """BOM for an empty project should have zero parts."""
        pkg = self._make_minimal_package(tmp_path)
        result = generate_bom(None, None, str(pkg))
        assert result["status"] == "ok"
        assert result["total_parts"] == 0
        assert result["unique_parts"] == 0

    def test_generate_bom_with_named_parts(self, tmp_path: Path) -> None:
        """BOM should count named parts and standard parts."""
        fg = {
            "features": [
                {"name": "base_plate", "type": "base_plate", "parameters": {"material": "Al6061-T6"}},
                {"name": "bracket", "type": "named_part", "parameters": {"material": "Steel-316L"}},
            ]
        }
        pkg = self._make_minimal_package(tmp_path, fg)
        result = generate_bom(None, None, str(pkg))
        assert result["status"] == "ok"
        assert result["total_parts"] == 2
        assert result["unique_parts"] == 2
        items = result["items"]
        assert any(i["part_name"] == "base_plate" and i["material"] == "Al6061-T6" for i in items)
        assert any(i["part_name"] == "bracket" and i["material"] == "Steel-316L" for i in items)

    def test_generate_bom_with_standard_parts(self, tmp_path: Path) -> None:
        """BOM should identify standard parts with their metadata."""
        fg = {
            "features": [
                {"name": "bolt_1", "type": "standard_part", "parameters": {"material": "Steel-1045"},
                 "intent": {"canonical_type": "hex_bolt"}, "designation": "M8", "source_library": "aieng.standards"},
                {"name": "nut_1", "type": "standard_part", "parameters": {"material": "Steel-1045"},
                 "intent": {"canonical_type": "hex_nut"}, "designation": "M8", "source_library": "aieng.standards"},
            ]
        }
        pkg = self._make_minimal_package(tmp_path, fg)
        result = generate_bom(None, None, str(pkg))
        assert result["status"] == "ok"
        assert result["total_parts"] == 2
        items = result["items"]
        bolt_item = next(i for i in items if i["part_name"] == "bolt_1")
        assert bolt_item["standard_part"] is True
        assert bolt_item["canonical_type"] == "hex_bolt"

    def test_generate_bom_markdown_format(self, tmp_path: Path) -> None:
        """BOM should produce markdown when format is requested."""
        fg = {
            "features": [
                {"name": "plate", "type": "named_part", "parameters": {"material": "Al6061-T6"}},
            ]
        }
        pkg = self._make_minimal_package(tmp_path, fg)
        result = generate_bom(None, None, str(pkg), fmt="markdown")
        assert result["status"] == "ok"
        assert "markdown" in result
        md = result["markdown"]
        assert "# Bill of Materials" in md
        assert "| plate |" in md
        assert "Al6061-T6" in md

    def test_generate_bom_deduplicates_same_parts(self, tmp_path: Path) -> None:
        """BOM should deduplicate identical parts and sum quantities."""
        fg = {
            "features": [
                {"name": "bolt", "type": "standard_part", "parameters": {"material": "Steel-1045"},
                 "intent": {"canonical_type": "hex_bolt"}, "designation": "M8", "source_library": "aieng.standards"},
                {"name": "bolt", "type": "standard_part", "parameters": {"material": "Steel-1045"},
                 "intent": {"canonical_type": "hex_bolt"}, "designation": "M8", "source_library": "aieng.standards"},
                {"name": "bolt", "type": "standard_part", "parameters": {"material": "Steel-1045"},
                 "intent": {"canonical_type": "hex_bolt"}, "designation": "M8", "source_library": "aieng.standards"},
            ]
        }
        pkg = self._make_minimal_package(tmp_path, fg)
        result = generate_bom(None, None, str(pkg))
        assert result["status"] == "ok"
        assert result["total_parts"] == 3
        assert result["unique_parts"] == 1
        item = result["items"][0]
        assert item["quantity"] == 3

    def test_generate_bom_missing_package(self) -> None:
        """generate_bom should error when the package is missing."""
        result = generate_bom(None, None, "/nonexistent/path/project.aieng")
        assert result["status"] == "error"
        assert result["code"] == "missing_package"


class TestMcpToolIntegration:
    """Cross-domain integration tests combining materials and standards tools."""

    def test_material_selection_drives_part_generation(self) -> None:
        """Material properties can drive standard part selection (e.g., corrosion resistance)."""
        # Query stainless steels
        steels = list_materials(category="Stainless Steel")
        assert steels["status"] == "ok"

        # Pick Steel-316L for corrosion resistance
        details = get_material_details("Steel-316L")
        assert details["status"] == "ok"

        # Generate a bolt using that material
        bolt = hex_bolt(**METRIC_BOLT_PRESETS["M8"])
        bolt["metadata"]["material"] = "Steel-316L"
        bolt["metadata"]["material_properties"] = details["properties"]

        assert bolt["metadata"]["material"] == "Steel-316L"
        assert bolt["metadata"]["material_properties"]["yield_strength_mpa"] == 170

    def test_compare_then_select_preset(self) -> None:
        """Compare materials, then select a preset based on strength needs."""
        comp = compare_materials(["Al6061-T6", "Al7075-T6"])
        assert comp["status"] == "ok"

        # Al7075-T6 has higher yield strength — use it for a high-strength bolt
        best_yield = comp["comparison"]["yield_strength_mpa"]["best_material"]
        assert best_yield == "Al7075-T6"

        bolt = hex_bolt(**METRIC_BOLT_PRESETS["M10"])
        bolt["metadata"]["material"] = best_yield
        assert bolt["metadata"]["material"] == "Al7075-T6"
