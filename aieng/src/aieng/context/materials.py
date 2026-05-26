from __future__ import annotations

MATERIALS: dict[str, dict[str, float]] = {
    "Al6061-T6": {
        "youngs_modulus_mpa": 69000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2700,
        "yield_strength_mpa": 276,
    },
    "Al7075-T6": {
        "youngs_modulus_mpa": 71700,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2810,
        "yield_strength_mpa": 503,
    },
    "Steel-1045": {
        "youngs_modulus_mpa": 205000,
        "poisson_ratio": 0.29,
        "density_kg_m3": 7850,
        "yield_strength_mpa": 530,
    },
    "Steel-316L": {
        "youngs_modulus_mpa": 193000,
        "poisson_ratio": 0.27,
        "density_kg_m3": 7990,
        "yield_strength_mpa": 170,
    },
    "Ti-6Al-4V": {
        "youngs_modulus_mpa": 114000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 4430,
        "yield_strength_mpa": 880,
    },
    "Cast-Iron-Grey": {
        "youngs_modulus_mpa": 110000,
        "poisson_ratio": 0.26,
        "density_kg_m3": 7200,
        "yield_strength_mpa": 180,
    },
    "Nylon-PA66": {
        "youngs_modulus_mpa": 3000,
        "poisson_ratio": 0.39,
        "density_kg_m3": 1140,
        "yield_strength_mpa": 80,
    },
    "PETG-CF": {
        "youngs_modulus_mpa": 5500,
        "poisson_ratio": 0.38,
        "density_kg_m3": 1270,
        "yield_strength_mpa": 55,
    },
}

MATERIAL_DESCRIPTIONS: dict[str, str] = {
    "Al6061-T6": "General-purpose aluminum alloy, good machinability, moderate strength",
    "Al7075-T6": "High-strength aluminum alloy, aerospace grade, excellent strength-to-weight",
    "Steel-1045": "Medium-carbon steel, good strength and toughness, widely used in mechanical parts",
    "Steel-316L": "Austenitic stainless steel, corrosion resistant, lower strength than carbon steel",
    "Ti-6Al-4V": "Titanium alloy, very high strength-to-weight ratio, biocompatible, expensive",
    "Cast-Iron-Grey": "Grey cast iron, good compressive strength, brittle, vibration damping",
    "Nylon-PA66": "Engineering thermoplastic, self-lubricating, moderate strength, light weight",
    "PETG-CF": "Carbon-fiber reinforced PETG, good for FDM 3D printing, improved stiffness",
}


def get_material(name: str) -> dict[str, float]:
    try:
        return dict(MATERIALS[name])
    except KeyError as exc:
        raise ValueError(f"unknown material {name!r}; supported materials: {', '.join(sorted(MATERIALS))}") from exc


def list_materials_for_llm() -> str:
    lines = []
    for name, props in MATERIALS.items():
        desc = MATERIAL_DESCRIPTIONS.get(name, "")
        lines.append(
            f"- {name}: E={props['youngs_modulus_mpa']} MPa, "
            f"ν={props['poisson_ratio']}, "
            f"ρ={props['density_kg_m3']} kg/m³, "
            f"σy={props['yield_strength_mpa']} MPa"
            + (f"  [{desc}]" if desc else "")
        )
    return "\n".join(lines)
