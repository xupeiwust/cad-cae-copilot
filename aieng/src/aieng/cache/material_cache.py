"""Material data cache.

Material data is static (51 engineering materials) so it is pre-loaded into
memory once and indexed for fast lookup by name, category, or property range.
"""
from __future__ import annotations

from typing import Any

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


class MaterialCache:
    """Pre-loaded, indexed material data cache.

    All lookups are O(1) or O(log n) and run entirely in memory.
    """

    def __init__(self) -> None:
        self._materials: dict[str, dict[str, float]] = dict(MATERIALS)
        self._properties: dict[str, dict[str, float | None]] = dict(MATERIAL_PROPERTIES)
        self._descriptions: dict[str, str] = dict(MATERIAL_DESCRIPTIONS)
        self._categories: dict[str, str] = dict(MATERIAL_CATEGORIES)
        # Build reverse index: category -> list of material names
        self._by_category: dict[str, list[str]] = list_materials_by_category()
        # Build name index for fast prefix search
        self._names: list[str] = sorted(self._materials.keys())

    # ── lookup API ────────────────────────────────────────────────────────────

    def get(self, name: str) -> dict[str, float]:
        """Return basic material properties by name.

        Raises:
            ValueError: if the material name is not known.
        """
        # Try direct lookup first (O(1))
        if name in self._materials:
            return dict(self._materials[name])
        # Fall back to the original function for consistent error messages
        return get_material(name)

    def get_full(self, name: str) -> dict[str, float | None]:
        """Return full material properties including optional fields."""
        if name in self._properties:
            return dict(self._properties[name])
        return get_material_properties(name)

    def get_description(self, name: str) -> str:
        """Return the human-readable description for a material."""
        return self._descriptions.get(name, "")

    def get_category(self, name: str) -> str:
        """Return the category for a material."""
        return self._categories.get(name, "Unknown")

    def list_by_category(self, category: str | None = None) -> dict[str, list[str]] | list[str]:
        """List materials grouped by category, or a single category's materials."""
        if category is None:
            return {k: list(v) for k, v in self._by_category.items()}
        return list(self._by_category.get(category, []))

    def search(self, query: str) -> list[str]:
        """Search materials by name or description (case-insensitive)."""
        return search_materials(query)

    def search_by_property(
        self,
        property_name: str,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> list[str]:
        """Search materials by a numeric property range.

        Args:
            property_name: e.g. ``"youngs_modulus_mpa"``, ``"density_kg_m3"``.
            min_value: Optional lower bound (inclusive).
            max_value: Optional upper bound (inclusive).
        """
        matches: list[str] = []
        for name, props in self._materials.items():
            value = props.get(property_name)
            if value is None:
                continue
            if min_value is not None and value < min_value:
                continue
            if max_value is not None and value > max_value:
                continue
            matches.append(name)
        return sorted(matches)

    def all_names(self) -> list[str]:
        """Return all material names, sorted."""
        return list(self._names)

    def all_categories(self) -> list[str]:
        """Return all category names, sorted."""
        return sorted(self._by_category.keys())

    def count(self) -> int:
        """Return the total number of materials."""
        return len(self._materials)

    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        return {
            "total_materials": self.count(),
            "categories": len(self._by_category),
            "memory_entries": self.count(),
            "hit_rate": 1.0,  # In-memory, always hits
        }
