"""Bridge to the aieng materials library for MCP tool handlers.

Provides material query, comparison, and project-binding utilities.
"""
from __future__ import annotations

from typing import Any

from aieng.context.materials import (
    MATERIALS,
    MATERIAL_CATEGORIES,
    MATERIAL_DESCRIPTIONS,
    MATERIAL_PROPERTIES,
    get_material_properties,
    list_materials_by_category,
    search_materials,
)


def list_materials(category: str | None = None, query: str | None = None) -> dict[str, Any]:
    """List available materials, optionally filtered by category or search query."""
    if category and query:
        # Intersection: search within category
        category_names = set(list_materials_by_category().get(category, []))
        search_names = set(search_materials(query))
        names = sorted(category_names & search_names)
    elif category:
        names = list_materials_by_category().get(category, [])
    elif query:
        names = search_materials(query)
    else:
        names = sorted(MATERIALS.keys())

    results: list[dict[str, Any]] = []
    for name in names:
        props = MATERIALS.get(name, {})
        results.append(
            {
                "name": name,
                "category": MATERIAL_CATEGORIES.get(name, "Unknown"),
                "description": MATERIAL_DESCRIPTIONS.get(name, ""),
                "youngs_modulus_mpa": props.get("youngs_modulus_mpa"),
                "poisson_ratio": props.get("poisson_ratio"),
                "density_kg_m3": props.get("density_kg_m3"),
                "yield_strength_mpa": props.get("yield_strength_mpa"),
            }
        )

    categories = sorted(set(MATERIAL_CATEGORIES.values()))
    return {
        "status": "ok",
        "count": len(results),
        "categories": categories,
        "materials": results,
    }


def get_material_details(material_name: str) -> dict[str, Any]:
    """Return full properties for a specific material."""
    try:
        props = get_material_properties(material_name)
    except ValueError as exc:
        return {
            "status": "error",
            "code": "material_not_found",
            "message": str(exc),
        }

    return {
        "status": "ok",
        "name": material_name,
        "category": MATERIAL_CATEGORIES.get(material_name, "Unknown"),
        "description": MATERIAL_DESCRIPTIONS.get(material_name, ""),
        "properties": {
            "youngs_modulus_mpa": props.get("youngs_modulus_mpa"),
            "poisson_ratio": props.get("poisson_ratio"),
            "density_kg_m3": props.get("density_kg_m3"),
            "yield_strength_mpa": props.get("yield_strength_mpa"),
            "ultimate_strength_mpa": props.get("ultimate_strength_mpa"),
            "thermal_expansion_um_mK": props.get("thermal_expansion_um_mK"),
        },
    }


def compare_materials(material_names: list[str]) -> dict[str, Any]:
    """Compare properties of two or more materials side by side."""
    not_found: list[str] = []
    materials: list[dict[str, Any]] = []
    for name in material_names:
        try:
            props = get_material_properties(name)
        except ValueError:
            not_found.append(name)
            continue
        materials.append(
            {
                "name": name,
                "category": MATERIAL_CATEGORIES.get(name, "Unknown"),
                "description": MATERIAL_DESCRIPTIONS.get(name, ""),
                "youngs_modulus_mpa": props.get("youngs_modulus_mpa"),
                "poisson_ratio": props.get("poisson_ratio"),
                "density_kg_m3": props.get("density_kg_m3"),
                "yield_strength_mpa": props.get("yield_strength_mpa"),
                "ultimate_strength_mpa": props.get("ultimate_strength_mpa"),
                "thermal_expansion_um_mK": props.get("thermal_expansion_um_mK"),
            }
        )

    if not_found:
        return {
            "status": "error",
            "code": "material_not_found",
            "message": f"Unknown material(s): {', '.join(not_found)}",
            "known_materials": sorted(MATERIALS.keys()),
        }

    if len(materials) < 2:
        return {
            "status": "error",
            "code": "insufficient_materials",
            "message": "At least 2 materials are required for comparison.",
        }

    # Build a comparison table with normalized scores (best = 1.0)
    keys = [
        ("youngs_modulus_mpa", "higher_is_better"),
        ("density_kg_m3", "lower_is_better"),
        ("yield_strength_mpa", "higher_is_better"),
        ("ultimate_strength_mpa", "higher_is_better"),
    ]
    comparison: dict[str, Any] = {}
    for key, direction in keys:
        values = [m["properties"][key] for m in materials if m["properties"].get(key) is not None]
        if not values:
            continue
        best = max(values) if direction == "higher_is_better" else min(values)
        worst = min(values) if direction == "higher_is_better" else max(values)
        span = best - worst if best != worst else 1.0
        comparison[key] = {
            "direction": direction,
            "best_material": next(m["name"] for m in materials if m["properties"].get(key) == best),
            "values": {m["name"]: m["properties"].get(key) for m in materials},
            "normalized": {
                m["name"]: round((m["properties"][key] - worst) / span, 3) if m["properties"].get(key) is not None else None
                for m in materials
            }
            if direction == "higher_is_better"
            else {
                m["name"]: round((best - m["properties"][key]) / span, 3) if m["properties"].get(key) is not None else None
                for m in materials
            },
        }

    return {
        "status": "ok",
        "count": len(materials),
        "materials": materials,
        "comparison": comparison,
    }
