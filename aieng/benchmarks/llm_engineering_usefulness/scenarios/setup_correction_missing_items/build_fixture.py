"""Build the .aieng fixture for the setup_correction_missing_items scenario.

The scenario asks the model to identify what is missing from a CAE setup
and to propose a correction plan. The fixture is engineered with three
distinct symptoms a competent reviewer should surface:

  1. ``simulation/cae_imports/parsed_loads.json`` is absent. The package
     declares materials, boundary conditions, mesh metadata, and a load
     case, but never defines the loads themselves.
  2. ``simulation/solver_settings.json`` is absent. The solver step
     parameters (analysis type, increments, output requests) are not
     part of the package.
  3. ``simulation/load_cases/load_case_001.json`` references a load id
     (``load_lateral``) that the missing loads file would have defined
     — a dangling reference that would cause solver setup to fail even
     if the loads file were re-added with different content.

Everything else (manifest, materials, BCs, mesh metadata + listing,
topology, features, constraints) is well-formed so the rubric scores
the model on whether it identifies *these specific* gaps.

The aieng pre-processing summarizer (``aieng.cae_preprocessing_summary``)
will detect the missing items automatically and surface them in the
``missing_items`` list — Condition B can call the corresponding tool
and read the answer directly. Condition A must infer the same gaps
from the raw artifact dump (the absence is not flagged anywhere).
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


_MANIFEST = {
    "model_id": "setup_correction_missing_items_fixture",
    "format_version": "0.1.0",
    "resources": {
        "graph": ["graph/constraints.json"],
        "simulation": [
            "simulation/cae_imports/parsed_materials.json",
            "simulation/cae_imports/parsed_boundary_conditions.json",
            "simulation/cae_imports/parsed_topology.json",
            "simulation/cae_imports/parsed_features.json",
            "simulation/mesh/mesh_metadata.json",
            "simulation/mesh/element_listing.json",
            "simulation/load_cases/load_case_001.json",
            # Intentionally absent:
            #   simulation/cae_imports/parsed_loads.json
            #   simulation/solver_settings.json
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
        },
    ],
}

_BOUNDARY_CONDITIONS = {
    "boundary_conditions": [
        {"id": "bc_fixed_mounting", "type": "fixed", "target_face_ids": ["face_0001", "face_0002"]},
    ],
}

_FEATURES = {
    "features": [
        {
            "id": "back_wall",
            "kind": "wall",
            "parameters": {"thickness_mm": 12.0, "width_mm": 120.0, "height_mm": 80.0},
        },
        {
            "id": "central_rib",
            "kind": "rib",
            "parameters": {"thickness_mm": 8.0, "length_mm": 100.0, "height_mm": 60.0},
        },
        {
            "id": "flange",
            "kind": "flange",
            "parameters": {"thickness_mm": 12.0, "width_mm": 80.0},
        },
        {
            "id": "mounting_hole",
            "kind": "hole",
            "parameters": {"diameter_mm": 10.0, "depth_mm": 12.0},
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
                else "flange" if i < 130
                else "mounting_hole"
            ),
            "area_mm2": round(110.0 + (i * 0.31) % 700, 3),
            "normal": [0.0, 0.0, 1.0] if i % 3 == 0 else [1.0, 0.0, 0.0],
        }
        for i in range(count)
    ]


def _topology_edges(count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"edge_{i:04d}",
            "kind": "circular_arc" if i % 5 == 0 else "straight",
            "length_mm": round(5.0 + (i * 0.17) % 50, 3),
        }
        for i in range(count)
    ]


_TOPOLOGY = {
    "faces": _topology_faces(150),
    "edges": _topology_edges(190),
    "vertex_count": 88,
    "schema_note": "structural topology export; no engineering claims",
}


_MESH_METADATA = {
    "element_count": 14200,
    "node_count": 16800,
    "element_type": "C3D10",
    "min_edge_length_mm": 0.5,
    "max_aspect_ratio": 4.1,
}


_ELEMENT_LISTING = {
    "elements": [
        {
            "id": i + 1,
            "type": "C3D10",
            "nodes": [(i * 10 + n) % 16800 + 1 for n in range(10)],
        }
        for i in range(120)
    ],
    "note": "subset of mesh elements for inspector readability",
}


# The load case references a load id (load_lateral) that the missing
# parsed_loads.json would have defined. This is the dangling-reference
# defect the rubric explicitly looks for.
_LOAD_CASE_001 = {
    "id": "load_case_001",
    "name": "lateral_load_case",
    "type": "static",
    "material_ref": "Steel",
    "boundary_condition_refs": ["bc_fixed_mounting"],
    "load_refs": ["load_lateral"],  # <-- references a load that is never defined
}


_CONSTRAINTS = {
    "constraints": [
        {"id": "c1", "kind": "geometric", "description": "Mounting bosses bolted to chassis (fully fixed)"},
    ],
}


def build_setup_correction_package(target_path: str | Path) -> Path:
    """Build the setup-correction fixture at ``target_path``.

    Always overwrites. Parent directory is created if needed.
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    # NOTE: parsed_loads.json and solver_settings.json are intentionally
    # absent. Do not add them here.
    members = {
        "manifest.json": _MANIFEST,
        "graph/constraints.json": _CONSTRAINTS,
        "simulation/cae_imports/parsed_materials.json": _MATERIALS,
        "simulation/cae_imports/parsed_boundary_conditions.json": _BOUNDARY_CONDITIONS,
        "simulation/cae_imports/parsed_topology.json": _TOPOLOGY,
        "simulation/cae_imports/parsed_features.json": _FEATURES,
        "simulation/mesh/mesh_metadata.json": _MESH_METADATA,
        "simulation/mesh/element_listing.json": _ELEMENT_LISTING,
        "simulation/load_cases/load_case_001.json": _LOAD_CASE_001,
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in members.items():
            zf.writestr(name, json.dumps(payload, indent=2))
    return target


if __name__ == "__main__":  # pragma: no cover
    out = build_setup_correction_package(Path(__file__).parent / "fixture.aieng")
    print(f"built fixture at {out}")
