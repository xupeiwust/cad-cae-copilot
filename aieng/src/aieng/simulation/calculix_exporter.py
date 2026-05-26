from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

SOLVER_DECK_PATH = "simulation/solver_deck.inp"
SIMULATION_SETUP_PATH = "simulation/setup.yaml"
FEATURE_GRAPH_PATH = "graph/feature_graph.json"
PROTECTED_REGIONS_PATH = "ai/protected_regions.json"

_SCAFFOLD_MARKER = "This is not a complete runnable FEA model."


def export_calculix_package(
    package_path: str | Path,
    *,
    out: str | Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Generate a CalculiX scaffold deck from an existing .aieng package.

    Always writes simulation/solver_deck.inp inside the package and updates
    manifest.json. If --out is provided, also writes the same content to that
    external filesystem path.
    """
    package_file = Path(package_path)
    if not package_file.exists():
        raise FileNotFoundError(f"package does not exist: {package_file}")
    if package_file.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    try:
        with zipfile.ZipFile(package_file, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if SIMULATION_SETUP_PATH not in names:
                raise FileNotFoundError(f"{SIMULATION_SETUP_PATH} missing; run aieng apply-context first")
            if SOLVER_DECK_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{SOLVER_DECK_PATH} already exists; use --overwrite to replace it"
                )

            manifest = json.loads(package.read("manifest.json"))
            setup = yaml.safe_load(package.read(SIMULATION_SETUP_PATH))
            feature_graph = _read_optional_json(package, FEATURE_GRAPH_PATH)
            protected_regions = _read_optional_json(package, PROTECTED_REGIONS_PATH)
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {package_file}") from exc

    deck_text = _generate_deck(manifest, setup, feature_graph, protected_regions)
    _rewrite_package_with_deck(package_file, existing_members, manifest, deck_text)

    if out is not None:
        out_path = Path(out)
        if out_path.exists() and not overwrite:
            raise FileExistsError(f"output file already exists: {out_path}; use --overwrite to replace it")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(deck_text, encoding="utf-8")

    return package_file


def _generate_deck(
    manifest: dict[str, Any],
    setup: Any,
    feature_graph: Any | None,
    protected_regions: Any | None,
) -> str:
    if not isinstance(setup, dict):
        raise ValueError("simulation/setup.yaml must be a mapping")

    model_id = manifest.get("model_id", "unknown_model")
    simulation_id = setup.get("simulation_id", "unknown")
    solver_target = setup.get("solver_target", "calculix")
    units = setup.get("units", {}) or {}

    lines: list[str] = []

    # ---- Header ----
    lines += [
        "** AIENG CalculiX Scaffold Deck",
        f"** model_id: {model_id}",
        f"** simulation_id: {simulation_id}",
        f"** solver_target: {solver_target}",
        f"** units: length={units.get('length', 'mm')} force={units.get('force', 'N')} stress={units.get('stress', 'MPa')}",
        "** Source: simulation/setup.yaml",
        "**",
        f"** {_SCAFFOLD_MARKER}",
        "** This file was generated from simulation/setup.yaml.",
        "** No mesh nodes or elements are generated in Phase 6A.",
        "** No solver has been run.",
        "** Feature-to-node-set mapping is not implemented in Phase 6A.",
        "** Do not submit this file to a solver without adding a complete mesh.",
        "",
    ]

    # ---- Material definitions ----
    materials = setup.get("materials", {}) or {}
    if isinstance(materials, dict) and materials:
        lines.append("** --- Material definitions ---")
        for mat_name, mat_props in sorted(materials.items()):
            if not isinstance(mat_props, dict):
                continue
            E = mat_props.get("youngs_modulus_mpa", "")
            nu = mat_props.get("poisson_ratio", "")
            rho = mat_props.get("density_kg_m3", "")
            lines += [
                f"*MATERIAL, NAME={mat_name}",
                "*ELASTIC",
                f"{E}, {nu}",
                "*DENSITY",
                f"{rho}",
                "",
            ]

    # ---- Material assignments ----
    assignments = setup.get("assignments", []) or []
    if isinstance(assignments, list) and assignments:
        lines.append("** --- Material assignments ---")
        for assignment in assignments:
            if not isinstance(assignment, dict):
                continue
            mat = assignment.get("material", "unknown")
            body = assignment.get("target_body", "unknown")
            lines.append(f"** Material '{mat}' assigned to body '{body}'")
            lines.append("** NOTE: *SOLID SECTION requires a generated element set.")
        lines.append("")

    # ---- Boundary conditions ----
    bcs = setup.get("boundary_conditions", []) or []
    if isinstance(bcs, list) and bcs:
        lines.append("** --- Boundary condition intent from .aieng ---")
        for bc in bcs:
            if not isinstance(bc, dict):
                continue
            bc_id = bc.get("id", "unknown")
            bc_type = bc.get("type", "unknown")
            bc_target = bc.get("target_feature", "unknown")
            lines += [
                f"** Boundary condition: {bc_id}",
                f"** Type: {bc_type}",
                f"** Target feature: {bc_target}",
                "** NOTE: Feature-to-node-set mapping is not implemented in Phase 6A.",
                "** *BOUNDARY would require a generated node set.",
                "",
            ]

    # ---- Loads ----
    loads = setup.get("loads", []) or []
    if isinstance(loads, list) and loads:
        lines.append("** --- Load intent from .aieng ---")
        for load in loads:
            if not isinstance(load, dict):
                continue
            load_id = load.get("id", "unknown")
            load_target = load.get("target_feature", "unknown")
            load_type = load.get("type", "unknown")
            load_value = load.get("value_n", "unknown")
            load_dir = load.get("direction", "unknown")
            lines += [
                f"** Load ID: {load_id}",
                f"** Target feature: {load_target}",
                f"** Type: {load_type}",
                f"** Force: {load_value} N",
                f"** Direction: {load_dir}",
                "** NOTE: Feature-to-node mapping is not implemented in Phase 6A.",
                "** *CLOAD would require a generated node set.",
                "",
            ]

    # ---- Validation targets ----
    targets = setup.get("targets", {}) or {}
    if isinstance(targets, dict) and targets:
        lines.append("** --- Validation targets ---")
        for key, value in sorted(targets.items()):
            lines.append(f"** {key} < {value}")
        lines.append("")

    # ---- Protected regions ----
    if isinstance(protected_regions, dict) and isinstance(protected_regions.get("protected_regions"), list):
        regions = protected_regions["protected_regions"]
        if regions:
            lines.append("** --- Protected regions (must not be modified by patch operations) ---")
            for region in regions:
                if not isinstance(region, dict):
                    continue
                fid = region.get("feature_id", "unknown")
                forbidden = region.get("forbidden_operations", [])
                lines.append(f"** Protected feature: {fid}")
                if forbidden:
                    lines.append(f"** Forbidden operations: {', '.join(forbidden)}")
            lines.append("")

    # ---- Missing mesh notice ----
    lines += [
        "** --- Missing mesh notice ---",
        "** No mesh has been generated. The following sections are required before",
        "** this scaffold can be submitted to a CalculiX solver:",
        "**   *NODE        - mesh node coordinates",
        "**   *ELEMENT     - element connectivity",
        "**   *NSET/*ELSET - node/element sets for boundary conditions and loads",
        "**   *SOLID SECTION - material assignments to element sets",
        "**   *BOUNDARY    - fixed support definitions",
        "**   *CLOAD       - force load definitions",
        "**   *STEP / *STATIC / *NODE FILE - analysis step and output requests",
        "",
        "** --- Required next steps ---",
        "** 1. Generate a mesh from geometry/source.step using a mesher (e.g. Gmsh).",
        "** 2. Map topology feature IDs to mesh node/element sets.",
        "** 3. Add *NODE, *ELEMENT, *NSET, *ELSET sections.",
        "** 4. Populate *BOUNDARY and *CLOAD from the intent sections above.",
        "** 5. Add *STEP, *STATIC, and output request sections.",
        "** 6. Validate and run with CalculiX.",
        "** 7. Attach results to the .aieng package under results/.",
        "",
        "** END OF AIENG SCAFFOLD DECK",
    ]

    return "\n".join(lines) + "\n"


def _read_optional_json(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    return json.loads(package.read(member))


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    skip = {"manifest.json", SOLVER_DECK_PATH}
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_deck(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    deck_text: str,
) -> None:
    resources = manifest.setdefault("resources", {})
    simulation_resources = resources.setdefault("simulation", {})
    if not isinstance(simulation_resources, dict):
        raise ValueError("manifest resources.simulation must be an object")
    simulation_resources["solver_deck"] = SOLVER_DECK_PATH

    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    deck_bytes = deck_text

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(SOLVER_DECK_PATH, deck_bytes)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
