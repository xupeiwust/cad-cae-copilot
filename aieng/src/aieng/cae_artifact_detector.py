"""CAE artifact detector for .aieng packages.

Scans a package ZIP and reports which CAE-related artifacts are present.
This is pure detection — no solver is executed, no results are synthesized.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

# Canonical CAE artifact paths inside a .aieng package.
# Keep this list ordered by logical phase (setup → mesh → solve → post → validation).
CAE_ARTIFACT_PATHS: tuple[str, ...] = (
    # CAD/CAE setup
    "graph/constraints.json",
    "simulation/cae_imports/parsed_materials.json",
    "simulation/cae_imports/parsed_boundary_conditions.json",
    "simulation/cae_imports/parsed_loads.json",
    "simulation/cae_mapping.json",
    # Mesh
    "simulation/mesh/mesh_metadata.json",
    "simulation/mesh/model.vtk",
    "simulation/mesh/model.vtu",
    # Solver settings (scaffold / handoff)
    "simulation/solver_settings.json",
    # Results / external solver-output integration
    "simulation/results_summary.json",
    "results/evidence_index.json",
    "results/result_summary.json",
    "results/field_regions.json",
    "results/field_summary.json",
    "results/fields/displacement.vtu",
    "results/fields/von_mises_stress.vtu",
    "results/fields/safety_factor.vtu",
    # Validation / review
    "validation/status.yaml",
)

# Paths that indicate CAE setup phase
_CAE_SETUP_PATHS: set[str] = {
    "graph/constraints.json",
    "simulation/cae_imports/parsed_materials.json",
    "simulation/cae_imports/parsed_boundary_conditions.json",
    "simulation/cae_imports/parsed_loads.json",
    "simulation/cae_mapping.json",
    "simulation/solver_settings.json",
}

# Paths that indicate mesh presence
_MESH_PATHS: set[str] = {
    "simulation/mesh/mesh_metadata.json",
    "simulation/mesh/model.vtk",
    "simulation/mesh/model.vtu",
}

# Paths that indicate result presence (external solver-output integration)
_RESULT_PATHS: set[str] = {
    "simulation/results_summary.json",
    "results/evidence_index.json",
    "results/result_summary.json",
    "results/field_regions.json",
    "results/field_summary.json",
}

# Paths that indicate field presence (external solver-output fields)
_FIELD_PATHS: set[str] = {
    "results/fields/displacement.vtu",
    "results/fields/von_mises_stress.vtu",
    "results/fields/safety_factor.vtu",
}


def detect_cae_artifacts(package_path: str | Path) -> dict[str, Any]:
    """Scan a .aieng package and return honest CAE artifact presence.

    Args:
        package_path: Path to the .aieng ZIP package.

    Returns:
        dict with keys:
            - mode: "cad_only" | "cae_setup" | "cae_result" | "cae_validation"
            - artifacts: {path: bool} for each CAE_ARTIFACT_PATHS entry
            - has_cae_setup: bool
            - has_mesh: bool
            - has_solver_settings: bool
            - has_results: bool
            - has_fields: bool
            - has_validation: bool
            - detected_count: int
            - total_count: int
    """
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package not found: {path}")

    with zipfile.ZipFile(path, "r") as zf:
        members = set(zf.namelist())

    artifacts: dict[str, bool] = {}
    for artifact_path in CAE_ARTIFACT_PATHS:
        # zipfile namelist may contain trailing slashes for directories;
        # we only care about actual files.
        artifacts[artifact_path] = artifact_path in members

    has_cae_setup = any(artifacts[p] for p in _CAE_SETUP_PATHS)
    has_mesh = any(artifacts[p] for p in _MESH_PATHS)
    has_solver_settings = artifacts.get("simulation/solver_settings.json", False)
    has_results = any(artifacts[p] for p in _RESULT_PATHS)
    has_fields = any(artifacts[p] for p in _FIELD_PATHS)
    has_validation = artifacts.get("validation/status.yaml", False)

    # Determine mode
    if has_validation:
        mode = "cae_validation"
    elif has_results or has_fields:
        mode = "cae_result"
    elif has_cae_setup or has_mesh or has_solver_settings:
        mode = "cae_setup"
    else:
        mode = "cad_only"

    detected_count = sum(artifacts.values())

    return {
        "mode": mode,
        "artifacts": artifacts,
        "has_cae_setup": has_cae_setup,
        "has_mesh": has_mesh,
        "has_solver_settings": has_solver_settings,
        "has_results": has_results,
        "has_fields": has_fields,
        "has_validation": has_validation,
        "detected_count": detected_count,
        "total_count": len(CAE_ARTIFACT_PATHS),
    }
