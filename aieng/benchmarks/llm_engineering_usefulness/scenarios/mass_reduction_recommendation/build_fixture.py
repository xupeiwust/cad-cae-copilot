"""Build the .aieng fixture for the mass-reduction-recommendation scenario.

The scenario asks the model to choose, from four proposed mass-reduction
changes, the one that most safely satisfies a safety-factor ≥ 1.5 constraint.
The decision requires reading per-feature stress data, looking up yield
strength, computing margins, and evaluating each proposal.

The correct answer is engineered into the fixture so the rubric can score
deterministically: the back_wall feature is at 22 MPa (SF ~ 15.9 against
yield 350 MPa), so thinning it from 20 mm to 10 mm preserves a very large
margin. The other three features touch high-stress regions:
    central_rib    195 MPa  SF 1.79  — removing it would shift load to
                                       surrounding features, very likely
                                       violating SF 1.5
    mounting_hole  195 MPa  SF 1.79  — enlarging the hole increases
                                       stress concentration
    mounting_bosses 48 MPa  SF 7.30  — removing some saves little mass and
                                       compromises mounting integrity

This is a recommendation task, not a defect-spotting task. It is a different
shape of question from scenario 1 — the test of whether `.aieng` access
generalises beyond cross-reference checks.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import yaml


_MANIFEST = {
    "model_id": "mass_reduction_recommendation_fixture",
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
        "task": [
            "task/design_targets.yaml",
        ],
    },
}


# Design targets carried as a structured task resource. The two requirements
# the scenario evaluates against — a mass-reduction floor (≥10 percent) and a
# minimum safety factor (1.5) — are encoded here in both legacy (id/metric/
# operator/value) and modern (target_id/target_type/comparator/threshold)
# field styles so legacy and current readers both validate.
_DESIGN_TARGETS = {
    "format_version": "0.1.1",
    "target_set_id": "mass_reduction_recommendation_v1",
    "provenance": {
        "author": "benchmark_authoring_pass",
        "rationale": (
            "Benchmark scenario 2 expresses its requirements as a structured "
            "task resource so Condition A and Condition B receive the same "
            "numeric targets via package contents (no prompt-only advantage)."
        ),
    },
    "targets": [
        {
            "id": "mass_reduce_10pct",
            "metric": "mass_reduction_percent",
            "operator": "reduce_by_at_least",
            "value": 10.0,
            "unit": "percent",
            "target_id": "mass_reduce_10pct",
            "target_type": "mass_reduction_target",
            "description": "Mass must drop by at least 10 percent relative to the baseline bracket mass (2.30 kg).",
            "comparator": "reduce_by_at_least",
            "threshold": 10.0,
            "priority": "high",
            "baseline_ref": "results/computed_metrics.json",
        },
        {
            "id": "safety_factor_min",
            "metric": "minimum_safety_factor",
            "operator": ">=",
            "value": 1.5,
            "unit": "dimensionless",
            "target_id": "safety_factor_min",
            "target_type": "minimum_safety_factor",
            "description": "After the change, minimum safety factor must remain >= 1.5 against the 350 MPa yield strength.",
            "comparator": ">=",
            "threshold": 1.5,
            "priority": "critical",
            "evidence_refs": [
                "results/computed_metrics.json",
                "results/stress_by_feature.json",
            ],
        },
    ],
    "claim_policy": {
        "targets_are_acceptance_criteria": True,
        "compliance_requires_evidence": True,
        "physical_correctness_not_claimed": True,
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
            "magnitude_n": 5000.0,
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
            "parameters": {"thickness_mm": 20.0, "width_mm": 120.0, "height_mm": 80.0},
            "mass_contribution_kg": 1.51,
            "notes": "Rear support wall behind central rib",
        },
        {
            "id": "central_rib",
            "kind": "rib",
            "parameters": {"thickness_mm": 8.0, "length_mm": 100.0, "height_mm": 60.0},
            "mass_contribution_kg": 0.38,
            "notes": "Primary load-bearing rib transferring lateral load to mounting face",
        },
        {
            "id": "mounting_hole",
            "kind": "hole",
            "parameters": {"diameter_mm": 10.0, "depth_mm": 20.0},
            "mass_contribution_kg": -0.012,
            "notes": "Bolt clearance hole near loaded edge",
        },
        {
            "id": "mounting_bosses",
            "kind": "boss_group",
            "parameters": {"count": 4, "diameter_mm": 14.0, "height_mm": 8.0},
            "mass_contribution_kg": 0.09,
            "notes": "Four mounting bosses on rear flange",
        },
        {
            "id": "flange",
            "kind": "flange",
            "parameters": {"thickness_mm": 12.0, "width_mm": 80.0},
            "mass_contribution_kg": 0.24,
            "notes": "Mounting flange interface to chassis",
        },
        {
            "id": "reinforcement_gusset",
            "kind": "gusset",
            "parameters": {"thickness_mm": 6.0, "leg_length_mm": 30.0},
            "mass_contribution_kg": 0.07,
            "notes": "Corner stiffening gusset between flange and back_wall",
        },
    ],
}


def _topology_faces(count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"face_{i:04d}",
            "feature_ref": (
                "back_wall" if i < 60
                else "central_rib" if i < 100
                else "mounting_hole" if i < 110
                else "mounting_bosses" if i < 130
                else "flange" if i < 160
                else "reinforcement_gusset"
            ),
            "area_mm2": round(120.0 + (i * 0.31) % 800, 3),
            "normal": [0.0, 0.0, 1.0] if i % 3 == 0 else [1.0, 0.0, 0.0],
        }
        for i in range(count)
    ]


def _topology_edges(count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"edge_{i:04d}",
            "kind": "straight" if i % 4 else "circular_arc",
            "length_mm": round(6.0 + (i * 0.21) % 50, 3),
        }
        for i in range(count)
    ]


_TOPOLOGY = {
    "faces": _topology_faces(180),
    "edges": _topology_edges(220),
    "vertex_count": 96,
    "schema_note": "structural topology export; no engineering claims",
}


_MESH_METADATA = {
    "element_count": 18420,
    "node_count": 21100,
    "element_type": "C3D10",
    "min_edge_length_mm": 0.6,
    "max_aspect_ratio": 4.2,
}


_ELEMENT_LISTING = {
    "elements": [
        {
            "id": i + 1,
            "type": "C3D10",
            "nodes": [(i * 10 + n) % 21100 + 1 for n in range(10)],
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
    "name": "lateral_5kN_negative_y",
    "type": "static",
    "material_ref": "Steel",
    "boundary_condition_refs": ["bc_fixed_mounting"],
    "load_refs": ["load_lateral"],
}


_CONSTRAINTS = {
    "constraints": [
        {"id": "c1", "kind": "geometric", "description": "Mounting bosses bolted to chassis (fully fixed)"},
    ],
}


# The two artifacts that carry the actual decision-relevant data:

_COMPUTED_METRICS = {
    "schema_version": "0.1",
    "metrics_source": {"tool": "external_postprocessor", "software": "CalculiX"},
    "load_cases": [
        {
            "id": "load_case_001",
            "metrics": {
                "max_displacement": {"value": 0.41, "unit": "mm", "field": "displacement_magnitude"},
                "max_von_mises_stress": {
                    "value": 195.0,
                    "unit": "MPa",
                    "field": "von_mises_stress",
                    "location_feature_ref": "central_rib",
                },
                "minimum_safety_factor": {
                    "value": 1.79,
                    "basis": "yield_strength / max_von_mises_stress",
                },
                "total_mass": {"value": 2.30, "unit": "kg"},
            },
        }
    ],
}


# Per-feature stress data — the table the model has to read carefully.
# Engineered so back_wall is unambiguously the safest reduction target.
_STRESS_BY_FEATURE = {
    "schema_version": "0.1",
    "load_case_id": "load_case_001",
    "material_ref": "Steel",
    "yield_strength_mpa": 350.0,
    "minimum_required_safety_factor": 1.5,
    "max_allowable_stress_mpa": 233.0,  # 350 / 1.5
    "features": [
        {
            "feature_ref": "back_wall",
            "max_von_mises_stress_mpa": 22.0,
            "mean_stress_mpa": 9.8,
            "safety_factor": 15.91,
            "notes": "Heavily over-designed; stress is very low across the entire wall",
        },
        {
            "feature_ref": "central_rib",
            "max_von_mises_stress_mpa": 195.0,
            "mean_stress_mpa": 142.0,
            "safety_factor": 1.79,
            "notes": "Primary load path; close to the safety-factor floor of 1.5",
        },
        {
            "feature_ref": "mounting_hole",
            "max_von_mises_stress_mpa": 195.0,
            "mean_stress_mpa": 110.0,
            "safety_factor": 1.79,
            "notes": "Stress concentration at the hole boundary",
        },
        {
            "feature_ref": "mounting_bosses",
            "max_von_mises_stress_mpa": 48.0,
            "mean_stress_mpa": 31.0,
            "safety_factor": 7.29,
            "notes": "Bosses see localised contact stress only; not load-bearing in bulk",
        },
        {
            "feature_ref": "flange",
            "max_von_mises_stress_mpa": 110.0,
            "mean_stress_mpa": 78.0,
            "safety_factor": 3.18,
            "notes": "Mounting interface; transfers load to the chassis",
        },
        {
            "feature_ref": "reinforcement_gusset",
            "max_von_mises_stress_mpa": 65.0,
            "mean_stress_mpa": 42.0,
            "safety_factor": 5.38,
            "notes": "Corner stiffener",
        },
    ],
}


def build_recommendation_package(target_path: str | Path) -> Path:
    """Build the mass-reduction-recommendation fixture at ``target_path``.

    Always overwrites. Parent directory is created if needed.
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    json_members = {
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
    yaml_members = {
        "task/design_targets.yaml": _DESIGN_TARGETS,
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in json_members.items():
            zf.writestr(name, json.dumps(payload, indent=2))
        for name, payload in yaml_members.items():
            zf.writestr(name, yaml.safe_dump(payload, sort_keys=False))
    return target


if __name__ == "__main__":  # pragma: no cover
    out = build_recommendation_package(Path(__file__).parent / "fixture.aieng")
    print(f"built fixture at {out}")
