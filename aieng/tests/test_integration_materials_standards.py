"""Integration tests for materials library and standards library.

Tests the integration between:
- Material assignment to standard parts
- Material query → standard part generation → Shape IR compilation flow
- Cache system integration with materials and standards
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from aieng.cache.geometry_cache import CachedGeometry, GeometryCache, compute_shape_ir_hash
from aieng.cache.material_cache import MaterialCache
from aieng.context.materials import (
    MATERIALS,
    MATERIAL_CATEGORIES,
    MATERIAL_DESCRIPTIONS,
    MATERIAL_PROPERTIES,
    get_material,
    get_material_properties,
    list_materials_by_category,
    search_materials,
)
from aieng.standards import (
    hex_bolt,
    hex_nut,
    deep_groove_ball_bearing,
    METRIC_BOLT_PRESETS,
)
from aieng.standards.fasteners import METRIC_NUT_PRESETS


class TestMaterialAssignmentToStandardParts:
    """Test assigning materials to standard parts and verifying metadata."""

    def test_assign_material_to_hex_bolt(self) -> None:
        """A standard part node should accept material metadata."""
        bolt = hex_bolt(diameter=8.0, length=25.0)
        material = get_material("Steel-316L")

        # Inject material into metadata
        bolt["metadata"]["material"] = "Steel-316L"
        bolt["metadata"]["material_properties"] = material

        assert bolt["metadata"]["material"] == "Steel-316L"
        assert bolt["metadata"]["material_properties"]["density_kg_m3"] == 7990

    def test_assign_material_to_bearing(self) -> None:
        """Bearings should accept material assignment for rings and balls."""
        bearing = deep_groove_ball_bearing(bore=20.0, outer_diameter=47.0)
        steel_props = get_material("Steel-1045")

        bearing["metadata"]["material"] = "Steel-1045"
        bearing["metadata"]["material_properties"] = steel_props

        assert bearing["metadata"]["material"] == "Steel-1045"
        assert bearing["metadata"]["material_properties"]["youngs_modulus_mpa"] == 205000

    def test_aluminum_bolt_weight_estimate(self) -> None:
        """Estimate bolt weight using material density and geometry volume."""
        bolt = hex_bolt(diameter=8.0, length=25.0, head_diameter=13.0, head_height=5.3)
        al_props = get_material("Al6061-T6")
        density = al_props["density_kg_m3"]  # kg/m³

        # Approximate volume: shank cylinder + head cylinder
        shank_volume = math.pi * (4.0**2) * 25.0  # mm³
        head_volume = math.pi * (6.5**2) * 5.3  # mm³
        total_volume_mm3 = shank_volume + head_volume
        total_volume_m3 = total_volume_mm3 * 1e-9
        mass_kg = total_volume_m3 * density

        assert density == 2700
        assert mass_kg > 0
        assert mass_kg < 0.1  # A single M8 bolt is < 100g

    def test_material_category_matches_part_category(self) -> None:
        """Fasteners typically use steel; structural profiles use aluminum or steel."""
        steel_fasteners = ["Steel-316L", "Steel-1045", "Steel-4140"]
        for mat_name in steel_fasteners:
            cat = MATERIAL_CATEGORIES.get(mat_name, "")
            assert "Steel" in cat or "Carbon" in cat

    def test_all_materials_assignable_to_parts(self) -> None:
        """Every material in the database should be assignable to a part node."""
        bolt = hex_bolt()
        for name in MATERIALS:
            bolt["metadata"]["material"] = name
            assert bolt["metadata"]["material"] == name


class TestMaterialQueryToShapeIrFlow:
    """Test the full workflow: material query → standard part → Shape IR payload."""

    def test_search_material_then_generate_part(self) -> None:
        """Search for a material, then generate a part using it."""
        results = search_materials("aerospace")
        assert "Al7075-T6" in results

        # Select aerospace-grade aluminum for a lightweight bolt
        material = get_material("Al7075-T6")
        bolt = hex_bolt(diameter=6.0, length=20.0)
        bolt["metadata"]["material"] = "Al7075-T6"
        bolt["metadata"]["material_properties"] = material

        assert bolt["parameters"]["diameter"] == 6.0
        assert bolt["metadata"]["material"] == "Al7075-T6"

    def test_compare_materials_then_select_for_part(self) -> None:
        """Compare two materials and select the better one for a part."""
        mat_a = get_material_properties("Al6061-T6")
        mat_b = get_material_properties("Steel-316L")

        # For strength-critical: pick higher yield strength
        assert mat_a["yield_strength_mpa"] == 276
        assert mat_b["yield_strength_mpa"] == 170
        selected = "Al6061-T6" if mat_a["yield_strength_mpa"] > mat_b["yield_strength_mpa"] else "Steel-316L"
        assert selected == "Al6061-T6"

        bolt = hex_bolt()
        bolt["metadata"]["material"] = selected
        assert bolt["metadata"]["material"] == "Al6061-T6"

    def test_build_payload_with_materials_and_parts(self) -> None:
        """Build a complete Shape IR payload with multiple materialized parts."""
        bolt = hex_bolt(**METRIC_BOLT_PRESETS["M8"])
        nut = hex_nut(**METRIC_NUT_PRESETS["M8"])

        bolt["metadata"]["material"] = "Steel-316L"
        nut["metadata"]["material"] = "Steel-316L"

        payload = {
            "format_version": "0.1",
            "model_id": "assembly_001",
            "representation": "brep_build123d",
            "parts": [bolt, nut],
        }

        assert len(payload["parts"]) == 2
        for p in payload["parts"]:
            assert "metadata" in p
            assert p["metadata"]["material"] == "Steel-316L"

    def test_category_filter_then_list_parts(self) -> None:
        """Filter materials by category, then generate parts suitable for that category."""
        cats = list_materials_by_category()
        aluminum_names = cats.get("Aluminum Alloy", [])
        assert "Al6061-T6" in aluminum_names

        # Generate a lightweight structural tube using aluminum
        from aieng.standards import round_tube
        tube = round_tube(outer_diameter=50.0, wall_thickness=2.5, length=200.0)
        tube["metadata"]["material"] = "Al6061-T6"

        assert tube["metadata"]["material"] in aluminum_names


class TestCacheIntegrationWithMaterialsAndStandards:
    """Test cache system integration with material queries and standard parts."""

    def test_material_cache_lookup(self) -> None:
        """MaterialCache should provide fast lookups for all materials."""
        cache = MaterialCache()
        assert cache.count() == len(MATERIALS)

        props = cache.get("Al6061-T6")
        assert props["youngs_modulus_mpa"] == 69000

        full = cache.get_full("Al6061-T6")
        assert full["ultimate_strength_mpa"] == 310

    def test_material_cache_search_by_property(self) -> None:
        """Search materials by property range using MaterialCache."""
        cache = MaterialCache()
        # Find lightweight metals (density < 3000 kg/m³)
        light_metals = cache.search_by_property("density_kg_m3", max_value=3000)
        assert "Al6061-T6" in light_metals
        assert "Mg-AZ31B" in light_metals
        assert "Steel-316L" not in light_metals

    def test_geometry_cache_with_standard_part_payload(self, tmp_path: Path) -> None:
        """GeometryCache should cache standard-part Shape IR payloads."""
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        bolt = hex_bolt(**METRIC_BOLT_PRESETS["M8"])
        payload = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [bolt],
        }
        h = compute_shape_ir_hash(payload)

        cg = CachedGeometry(
            shape_ir_hash=h,
            metadata={"part_type": "hex_bolt", "preset": "M8"},
        )
        cache.set(h, cg)
        retrieved = cache.get(h)
        assert retrieved is not None
        assert retrieved.metadata["part_type"] == "hex_bolt"

    def test_cache_invalidation_by_project_with_materials(self, tmp_path: Path) -> None:
        """Cache invalidation should work for projects with material assignments."""
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        bolt = hex_bolt()
        bolt["metadata"]["material"] = "Ti-6Al-4V"
        payload = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [bolt],
        }
        h = compute_shape_ir_hash(payload)
        cache.set(h, CachedGeometry(shape_ir_hash=h, metadata={"project_id": "proj_a"}))

        # Invalidate project_a
        cache.invalidate(project_id="proj_a")
        assert cache.get(h) is None

    def test_material_cache_stats(self) -> None:
        """MaterialCache should report accurate statistics."""
        cache = MaterialCache()
        stats = cache.get_stats()
        assert stats["total_materials"] == len(MATERIALS)
        assert stats["categories"] == len(list_materials_by_category())
        assert stats["hit_rate"] == 1.0

