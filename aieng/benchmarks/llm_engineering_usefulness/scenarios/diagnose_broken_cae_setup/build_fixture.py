"""Build the deliberately-broken .aieng fixture for the diagnose scenario.

The fixture is generated at run time from primitive JSON so reviewers can read
the build script and see *exactly* what makes the package broken — no binary
artifact in the repo to unzip and inspect.

The defect (single, identifiable, deterministic):

  ``simulation/load_cases/load_case_001.json`` references material
  ``Aluminum6061``. ``simulation/cae_imports/parsed_materials.json`` only
  defines ``Steel``.

Everything else in the fixture is intentionally well-formed so the rubric
scores the model on whether it identifies *this* defect — not on whether it
finds whatever broken thing comes to mind.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


_MANIFEST = {
    "model_id": "diagnose_broken_cae_setup_fixture",
    "format_version": "0.1.0",
    "resources": {
        "graph": ["graph/constraints.json", "graph/assembly_metadata.json"],
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
            "simulation/load_cases/load_case_002.json",
            "simulation/load_cases/load_case_003.json",
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
        },
    ],
}

_BOUNDARY_CONDITIONS = {
    "boundary_conditions": [
        {"id": "bc_fixed_face_a", "type": "fixed", "target_face_ids": ["face_1"]},
    ],
}

_LOADS = {
    "loads": [
        {"id": "load_y_neg", "type": "force", "magnitude_n": 1000.0, "direction": [0, -1, 0]},
    ],
}

_MESH_METADATA = {
    "element_count": 12450,
    "node_count": 14200,
    "element_type": "C3D10",
    "min_edge_length_mm": 0.4,
}

_SOLVER_SETTINGS = {
    "solver": "CalculiX",
    "analysis_type": "linear_static",
    "load_step": {"initial_time_increment": 1.0, "final_time": 1.0},
}

# The DEFECT — load case references a material that materials.json never defines.
_LOAD_CASE_001 = {
    "id": "load_case_001",
    "name": "y-axis force on free end",
    "type": "static",
    "material_ref": "Aluminum6061",  # <-- undefined; materials.json only has Steel
    "boundary_condition_refs": ["bc_fixed_face_a"],
    "load_refs": ["load_y_neg"],
}

_CONSTRAINTS = {
    "constraints": [
        {"id": "c1", "kind": "geometric", "description": "Fixed face A is constrained in all DOFs"},
    ],
}


# ---------------------------------------------------------------------------
# Bulk artifacts — present so the defect is buried in plausible noise rather
# than obvious in a ~700-token prompt. The first Kimi run on the small
# version of this scenario produced ceiling at correctness=1.0 for both
# conditions; making the haystack bigger is the cleanest way to give the
# structured-access condition a chance to differentiate. Sizes target ~30 KB
# total, which is ~6-10K input tokens — comfortably over the 2,000-token
# budget but well under any model's context limit.
#
# None of these artifacts contain real defects. The single, identifiable
# defect remains the Aluminum6061 reference in load_case_001.json.

def _generate_topology_faces(count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"face_{i:04d}",
            "feature_ref": f"feature_{(i // 4) + 1:03d}",
            "edge_count": 4 if i % 7 else 6,
            "vertex_count": 4,
            "area_mm2": round(150.0 + (i * 0.37) % 800, 3),
            "centroid_mm": [round((i * 1.1) % 100, 3), round((i * 0.7) % 50, 3), round((i * 0.31) % 20, 3)],
            "normal": [0.0, 0.0, 1.0] if i % 3 == 0 else [1.0, 0.0, 0.0],
            "is_planar": True,
        }
        for i in range(count)
    ]


def _generate_topology_edges(count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"edge_{i:04d}",
            "feature_ref": f"feature_{(i // 12) + 1:03d}",
            "kind": "straight" if i % 5 else "circular_arc",
            "length_mm": round(8.0 + (i * 0.13) % 60, 3),
            "endpoints": [f"vertex_{i:04d}", f"vertex_{(i + 1) % count:04d}"],
        }
        for i in range(count)
    ]


_TOPOLOGY = {
    "faces": _generate_topology_faces(180),
    "edges": _generate_topology_edges(220),
    "vertex_count": 96,
    "schema_note": "structural topology export; no engineering claims",
}


_FEATURES = {
    "features": [
        {
            "id": f"feature_{i:03d}",
            "kind": ["extrude", "fillet", "hole", "chamfer", "pocket"][i % 5],
            "parent_ref": f"feature_{max(1, i - 1):03d}" if i > 1 else None,
            "parameters": {
                "depth_mm": round(2.5 + (i * 0.4) % 18, 3),
                "draft_angle_deg": 0.0 if i % 3 else round((i * 0.2) % 4, 3),
                "tolerance_mm": 0.02,
            },
            "created_at_step": i,
            "notes": "auto-generated feature for fixture size; not a real defect site",
        }
        for i in range(1, 51)
    ],
}


_ELEMENT_LISTING = {
    "elements": [
        {
            "id": i + 1,
            "type": "C3D10",
            "nodes": [(i * 10 + n) % 14200 + 1 for n in range(10)],
            "material_section_ref": "section_default",
        }
        for i in range(150)
    ],
    "note": (
        "subset of mesh elements for inspector readability; the actual mesh "
        "is described by mesh_metadata.json"
    ),
}


# Extra load cases that are NOT broken — material_ref points to Steel
# (which is defined). These are the red herrings: a model that confuses
# "many load cases exist" with "many possible defects" will go looking
# in the wrong place; the rubric will mark that as partial credit
# rather than C.
_LOAD_CASE_002 = {
    "id": "load_case_002",
    "name": "z-axis force on top face",
    "type": "static",
    "material_ref": "Steel",
    "boundary_condition_refs": ["bc_fixed_face_a"],
    "load_refs": ["load_y_neg"],
}

_LOAD_CASE_003 = {
    "id": "load_case_003",
    "name": "combined bending",
    "type": "static",
    "material_ref": "Steel",
    "boundary_condition_refs": ["bc_fixed_face_a"],
    "load_refs": ["load_y_neg"],
}


# Assembly metadata is informational — it references a subassembly_id
# that is not defined as a separate part because the .aieng package
# describes a single part. Not a defect; the runtime does not consume
# this reference. A model that flags this as the defect is wrong.
_ASSEMBLY_METADATA = {
    "model_kind": "single_part",
    "subassembly_id": "sa_root",
    "child_parts": [],
    "note": "single-part packages may carry assembly metadata for forward compatibility",
}


def build_broken_package(target_path: str | Path) -> Path:
    """Build the broken .aieng fixture at the given path.

    Args:
        target_path: Destination for the .aieng ZIP. Parent directory is
            created if it does not exist. Any existing file at the path is
            overwritten.

    Returns:
        The resolved path of the built fixture.
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    members = {
        "manifest.json": _MANIFEST,
        "graph/constraints.json": _CONSTRAINTS,
        "graph/assembly_metadata.json": _ASSEMBLY_METADATA,
        "simulation/cae_imports/parsed_materials.json": _MATERIALS,
        "simulation/cae_imports/parsed_boundary_conditions.json": _BOUNDARY_CONDITIONS,
        "simulation/cae_imports/parsed_loads.json": _LOADS,
        "simulation/cae_imports/parsed_topology.json": _TOPOLOGY,
        "simulation/cae_imports/parsed_features.json": _FEATURES,
        "simulation/mesh/mesh_metadata.json": _MESH_METADATA,
        "simulation/mesh/element_listing.json": _ELEMENT_LISTING,
        "simulation/solver_settings.json": _SOLVER_SETTINGS,
        "simulation/load_cases/load_case_001.json": _LOAD_CASE_001,
        "simulation/load_cases/load_case_002.json": _LOAD_CASE_002,
        "simulation/load_cases/load_case_003.json": _LOAD_CASE_003,
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in members.items():
            zf.writestr(name, json.dumps(payload, indent=2))
    return target


if __name__ == "__main__":  # pragma: no cover
    out = build_broken_package(Path(__file__).parent / "fixture.aieng")
    print(f"built fixture at {out}")
