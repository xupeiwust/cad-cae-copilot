"""Build the .aieng fixture for the stress-concentrator-recommendation scenario.

The scenario asks the model to identify a high-stress region, recommend a
reasonable design response, and avoid overstating certainty.

The fixture is engineered so the answer is unambiguous *for the diagnosis*
(which feature is the concentrator) while staying intentionally honest
about *the recommendation* (a fillet radius increase is reasonable, but
the analyst should re-run analysis to verify).

The defect (single, identifiable, deterministic):

  Feature ``fillet_inner_corner`` is the 1 mm fillet at the joint between
  ``central_rib`` and ``flange``. Under the documented load case, it sits
  at 280 MPa von-Mises against a 350 MPa yield strength — safety factor
  1.25, below the 1.5 floor declared in the package. Every other feature
  has a much larger safety margin (SF 2.5+).

Reasonable response: increase the fillet radius. The fixture does NOT
prescribe the new radius — the model should propose one and acknowledge
that re-analysis is required to confirm the new SF.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


_MANIFEST = {
    "model_id": "stress_concentrator_recommendation_fixture",
    "format_version": "0.1.0",
    "resources": {
        "graph": ["graph/constraints.json"],
        "simulation": [
            "simulation/cae_imports/parsed_materials.json",
            "simulation/cae_imports/parsed_boundary_conditions.json",
            "simulation/cae_imports/parsed_loads.json",
            "simulation/cae_imports/parsed_topology.json",
            "simulation/cae_imports/parsed_features.json",
            "simulation/mesh/mesh_metadata.json",
            "simulation/mesh/element_listing.json",
            "simulation/solver_settings.json",
            "simulation/load_cases/load_case_001.json",
        ],
        "results": [
            "results/computed_metrics.json",
            "results/stress_by_feature.json",
        ],
    },
}

_MATERIALS = {
    "materials": [
        {
            "name": "Steel",
            "youngs_modulus_mpa": 210000.0,
            "poissons_ratio": 0.3,
            "density_kg_m3": 7850.0,
            "yield_strength_mpa": 350.0,
            "ultimate_strength_mpa": 510.0,
        },
    ],
}

_BOUNDARY_CONDITIONS = {
    "boundary_conditions": [
        {"id": "bc_fixed_mounting", "type": "fixed", "target_face_ids": ["face_0001", "face_0002"]},
    ],
}

_LOADS = {
    "loads": [
        {
            "id": "load_lateral",
            "type": "force",
            "magnitude_n": 6500.0,
            "direction": [0, -1, 0],
            "target_face_id": "face_0124",
        },
    ],
}


_FEATURES = {
    "features": [
        {
            "id": "back_wall",
            "kind": "wall",
            "parameters": {"thickness_mm": 12.0, "width_mm": 120.0, "height_mm": 80.0},
            "mass_contribution_kg": 0.90,
            "notes": "Rear support wall",
        },
        {
            "id": "central_rib",
            "kind": "rib",
            "parameters": {"thickness_mm": 8.0, "length_mm": 100.0, "height_mm": 60.0},
            "mass_contribution_kg": 0.38,
            "notes": "Primary load-bearing rib",
        },
        {
            "id": "flange",
            "kind": "flange",
            "parameters": {"thickness_mm": 12.0, "width_mm": 80.0},
            "mass_contribution_kg": 0.24,
            "notes": "Mounting flange",
        },
        {
            "id": "fillet_inner_corner",
            "kind": "fillet",
            "parameters": {"radius_mm": 1.0, "edge_count": 1, "joins": ["central_rib", "flange"]},
            "mass_contribution_kg": 0.001,
            "notes": "Inner-corner fillet at the rib-to-flange joint",
        },
        {
            "id": "fillet_outer_corner",
            "kind": "fillet",
            "parameters": {"radius_mm": 5.0, "edge_count": 1, "joins": ["back_wall", "flange"]},
            "mass_contribution_kg": 0.003,
            "notes": "Outer-corner fillet at the back-wall-to-flange joint",
        },
        {
            "id": "mounting_hole",
            "kind": "hole",
            "parameters": {"diameter_mm": 8.0, "depth_mm": 12.0},
            "mass_contribution_kg": -0.008,
            "notes": "Bolt clearance hole",
        },
        {
            "id": "mounting_bosses",
            "kind": "boss_group",
            "parameters": {"count": 4, "diameter_mm": 14.0, "height_mm": 8.0},
            "mass_contribution_kg": 0.09,
            "notes": "Four mounting bosses",
        },
    ],
}


def _topology_faces(count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"face_{i:04d}",
            "feature_ref": (
                "back_wall" if i < 50
                else "central_rib" if i < 90
                else "flange" if i < 120
                else "fillet_inner_corner" if i < 122
                else "fillet_outer_corner" if i < 130
                else "mounting_hole" if i < 140
                else "mounting_bosses"
            ),
            "area_mm2": round(110.0 + (i * 0.41) % 720, 3),
            "normal": [0.0, 0.0, 1.0] if i % 3 == 0 else [1.0, 0.0, 0.0],
        }
        for i in range(count)
    ]


def _topology_edges(count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"edge_{i:04d}",
            "kind": "circular_arc" if i % 7 == 0 else "straight",
            "length_mm": round(5.0 + (i * 0.17) % 45, 3),
        }
        for i in range(count)
    ]


_TOPOLOGY = {
    "faces": _topology_faces(170),
    "edges": _topology_edges(210),
    "vertex_count": 92,
    "schema_note": "structural topology export; no engineering claims",
}


_MESH_METADATA = {
    "element_count": 22850,
    "node_count": 26100,
    "element_type": "C3D10",
    "min_edge_length_mm": 0.3,
    "max_aspect_ratio": 5.2,
    "refinement_zones": [
        {
            "id": "rz_fillet_inner_corner",
            "feature_ref": "fillet_inner_corner",
            "target_edge_length_mm": 0.3,
            "notes": "local refinement around 1 mm fillet to capture concentration",
        },
    ],
}


_ELEMENT_LISTING = {
    "elements": [
        {
            "id": i + 1,
            "type": "C3D10",
            "nodes": [(i * 10 + n) % 26100 + 1 for n in range(10)],
        }
        for i in range(150)
    ],
    "note": "subset of mesh elements for inspector readability",
}


_SOLVER_SETTINGS = {
    "solver": "CalculiX",
    "analysis_type": "linear_static",
    "load_step": {"initial_time_increment": 1.0, "final_time": 1.0},
}


_LOAD_CASE_001 = {
    "id": "load_case_001",
    "name": "lateral_6.5kN_negative_y",
    "type": "static",
    "material_ref": "Steel",
    "boundary_condition_refs": ["bc_fixed_mounting"],
    "load_refs": ["load_lateral"],
    "design_constraint": {"minimum_safety_factor": 1.5},
}


_CONSTRAINTS = {
    "constraints": [
        {"id": "c1", "kind": "geometric", "description": "Mounting bosses bolted to chassis (fully fixed)"},
    ],
}


_COMPUTED_METRICS = {
    "schema_version": "0.1",
    "metrics_source": {"tool": "external_postprocessor", "software": "CalculiX"},
    "load_cases": [
        {
            "id": "load_case_001",
            "metrics": {
                "max_displacement": {"value": 0.62, "unit": "mm", "field": "displacement_magnitude"},
                "max_von_mises_stress": {
                    "value": 280.0,
                    "unit": "MPa",
                    "field": "von_mises_stress",
                    "location_feature_ref": "fillet_inner_corner",
                },
                "minimum_safety_factor": {
                    "value": 1.25,
                    "basis": "yield_strength / max_von_mises_stress",
                },
                "total_mass": {"value": 1.61, "unit": "kg"},
            },
        }
    ],
}


# Per-feature stress data — engineered so fillet_inner_corner is the single
# stress concentrator below the SF=1.5 floor, with every other feature
# comfortably above.
_STRESS_BY_FEATURE = {
    "schema_version": "0.1",
    "load_case_id": "load_case_001",
    "material_ref": "Steel",
    "yield_strength_mpa": 350.0,
    "minimum_required_safety_factor": 1.5,
    "max_allowable_stress_mpa": 233.0,
    "features": [
        {
            "feature_ref": "back_wall",
            "max_von_mises_stress_mpa": 45.0,
            "mean_stress_mpa": 22.0,
            "safety_factor": 7.78,
            "notes": "Bulk wall; far from yield",
        },
        {
            "feature_ref": "central_rib",
            "max_von_mises_stress_mpa": 140.0,
            "mean_stress_mpa": 95.0,
            "safety_factor": 2.50,
            "notes": "Primary load path; SF comfortably above 1.5",
        },
        {
            "feature_ref": "flange",
            "max_von_mises_stress_mpa": 95.0,
            "mean_stress_mpa": 62.0,
            "safety_factor": 3.68,
            "notes": "Mounting interface",
        },
        {
            "feature_ref": "fillet_inner_corner",
            "max_von_mises_stress_mpa": 280.0,
            "mean_stress_mpa": 215.0,
            "safety_factor": 1.25,
            "notes": (
                "STRESS CONCENTRATOR. 1 mm fillet at the central_rib / flange "
                "joint. Below the 1.5 SF floor declared in the load case."
            ),
        },
        {
            "feature_ref": "fillet_outer_corner",
            "max_von_mises_stress_mpa": 78.0,
            "mean_stress_mpa": 52.0,
            "safety_factor": 4.49,
            "notes": "5 mm fillet at the back_wall / flange joint; comfortable",
        },
        {
            "feature_ref": "mounting_hole",
            "max_von_mises_stress_mpa": 110.0,
            "mean_stress_mpa": 78.0,
            "safety_factor": 3.18,
            "notes": "Stress concentration at the hole, well below allowable",
        },
        {
            "feature_ref": "mounting_bosses",
            "max_von_mises_stress_mpa": 52.0,
            "mean_stress_mpa": 34.0,
            "safety_factor": 6.73,
            "notes": "Bosses see localised contact stress only",
        },
    ],
}


def build_concentrator_package(target_path: str | Path) -> Path:
    """Build the stress-concentrator fixture at ``target_path``.

    Always overwrites. Parent directory is created if needed.
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    members = {
        "manifest.json": _MANIFEST,
        "graph/constraints.json": _CONSTRAINTS,
        "simulation/cae_imports/parsed_materials.json": _MATERIALS,
        "simulation/cae_imports/parsed_boundary_conditions.json": _BOUNDARY_CONDITIONS,
        "simulation/cae_imports/parsed_loads.json": _LOADS,
        "simulation/cae_imports/parsed_topology.json": _TOPOLOGY,
        "simulation/cae_imports/parsed_features.json": _FEATURES,
        "simulation/mesh/mesh_metadata.json": _MESH_METADATA,
        "simulation/mesh/element_listing.json": _ELEMENT_LISTING,
        "simulation/solver_settings.json": _SOLVER_SETTINGS,
        "simulation/load_cases/load_case_001.json": _LOAD_CASE_001,
        "results/computed_metrics.json": _COMPUTED_METRICS,
        "results/stress_by_feature.json": _STRESS_BY_FEATURE,
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in members.items():
            zf.writestr(name, json.dumps(payload, indent=2))
    return target


if __name__ == "__main__":  # pragma: no cover
    out = build_concentrator_package(Path(__file__).parent / "fixture.aieng")
    print(f"built fixture at {out}")
