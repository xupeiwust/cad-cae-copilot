from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

UPDATED_DECK_PATH = "simulation/updated_deck.inp"
SIMULATION_SETUP_PATH = "simulation/setup.yaml"
SOURCE_DECK_PATH = "simulation/cae_imports/source_solver_deck.inp"
CAE_MAPPING_PATH = "simulation/cae_mapping.json"
STATUS_PATH = "validation/status.yaml"

_SCAFFOLD_MARKER = "This is not a complete runnable FEA model."


def export_updated_deck_package(
    package_path: str | Path,
    *,
    out: str | Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Export an updated CalculiX deck that reflects the current simulation/setup.yaml.

    This differs from export-calculix in two ways:
    - It reads setup.yaml as it currently stands (including any parameter changes
      applied by aieng apply-patch or manual edits).
    - It incorporates simulation/cae_mapping.json mapped entity references when present.

    Writes simulation/updated_deck.inp inside the package. Does not run a solver,
    generate a mesh, or claim engineering validity.
    """
    package_file = Path(package_path)
    if not package_file.exists():
        raise FileNotFoundError(f"package does not exist: {package_file}")
    if package_file.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    try:
        with zipfile.ZipFile(package_file, mode="r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if SIMULATION_SETUP_PATH not in names:
                raise FileNotFoundError(
                    f"{SIMULATION_SETUP_PATH} missing; run aieng apply-context first"
                )
            if UPDATED_DECK_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{UPDATED_DECK_PATH} already exists; use --overwrite to replace it"
                )

            manifest = json.loads(zf.read("manifest.json"))
            setup = yaml.safe_load(zf.read(SIMULATION_SETUP_PATH))
            cae_mapping = _read_optional_json(zf, CAE_MAPPING_PATH)
            source_deck_text = (
                zf.read(SOURCE_DECK_PATH).decode("utf-8", errors="replace")
                if SOURCE_DECK_PATH in names
                else None
            )
            raw_status = zf.read(STATUS_PATH) if STATUS_PATH in names else None
            members = _read_existing_members(zf)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {package_file}") from exc

    deck_text = _generate_updated_deck(manifest, setup, cae_mapping, source_deck_text)
    updated_status = _patch_status_yaml(raw_status, exported=True)

    _rewrite_package(package_file, members, manifest, deck_text, updated_status)

    if out is not None:
        out_path = Path(out)
        if out_path.exists() and not overwrite:
            raise FileExistsError(
                f"output file already exists: {out_path}; use --overwrite to replace it"
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(deck_text, encoding="utf-8")

    return package_file


def _generate_updated_deck(
    manifest: dict[str, Any],
    setup: Any,
    cae_mapping: Any | None,
    source_deck_text: str | None,
) -> str:
    if not isinstance(setup, dict):
        raise ValueError("simulation/setup.yaml must be a mapping")

    model_id = manifest.get("model_id", "unknown_model")
    simulation_id = setup.get("simulation_id", "unknown")
    solver_target = setup.get("solver_target", "calculix")
    units = setup.get("units", {}) or {}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    lines: list[str] = []

    # ---- Header ----
    lines += [
        "** AIENG Updated CalculiX Deck",
        f"** model_id: {model_id}",
        f"** simulation_id: {simulation_id}",
        f"** solver_target: {solver_target}",
        f"** units: length={units.get('length', 'mm')} force={units.get('force', 'N')} stress={units.get('stress', 'MPa')}",
        f"** generated_at: {now}",
        "** Source: current simulation/setup.yaml (reflects any parameter updates)",
        "**",
        f"** {_SCAFFOLD_MARKER}",
        "** This file was generated from the current state of simulation/setup.yaml.",
        "** Parameters reflect any modifications applied since initial import.",
        "** No mesh nodes or elements are generated.",
        "** No solver has been run.",
        "** Do not submit this file to a solver without adding a complete mesh.",
        "",
    ]

    if source_deck_text is not None:
        lines += [
            "** Note: simulation/cae_imports/source_solver_deck.inp was present.",
            "** This updated deck supersedes it for the current parameter state.",
            "",
        ]

    # ---- Material definitions (from current setup.yaml) ----
    materials = setup.get("materials", {}) or {}
    if isinstance(materials, dict) and materials:
        lines.append("** --- Material definitions (current setup.yaml state) ---")
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

    # ---- Boundary conditions (current setup.yaml) ----
    bcs = setup.get("boundary_conditions", []) or []
    if isinstance(bcs, list) and bcs:
        lines.append("** --- Boundary condition intent (current setup.yaml state) ---")
        for bc in bcs:
            if not isinstance(bc, dict):
                continue
            bc_id = bc.get("id", "unknown")
            bc_type = bc.get("type", "unknown")
            bc_target = bc.get("target_feature", "unknown")
            lines += [
                f"** Boundary condition: {bc_id}",
                f"**   type: {bc_type}",
                f"**   target feature: {bc_target}",
                "** *BOUNDARY requires a generated node set - not yet available.",
                "",
            ]

    # ---- Loads (current setup.yaml) ----
    loads = setup.get("loads", []) or []
    if isinstance(loads, list) and loads:
        lines.append("** --- Load intent (current setup.yaml state) ---")
        for load in loads:
            if not isinstance(load, dict):
                continue
            load_id = load.get("id", "unknown")
            load_target = load.get("target_feature", "unknown")
            load_type = load.get("type", "unknown")
            load_value = load.get("value_n", "unknown")
            load_dir = load.get("direction", "unknown")
            lines += [
                f"** Load: {load_id}",
                f"**   target: {load_target}  type: {load_type}",
                f"**   force: {load_value} N  direction: {load_dir}",
                "** *CLOAD requires a generated node set - not yet available.",
                "",
            ]

    # ---- Validation targets ----
    targets = setup.get("targets", {}) or {}
    if isinstance(targets, dict) and targets:
        lines.append("** --- Validation targets ---")
        for key, value in sorted(targets.items()):
            lines.append(f"** {key} < {value}")
        lines.append("")

    # ---- CAE mapping traceability ----
    if isinstance(cae_mapping, dict):
        mappings = cae_mapping.get("mappings", []) or []
        mapped = [
            m for m in mappings
            if isinstance(m, dict) and m.get("mapping_status") in {"mapped", "partially_mapped"}
        ]
        if mapped:
            lines.append("** --- CAE entity mapping (from simulation/cae_mapping.json) ---")
            for m in mapped:
                entity = m.get("cae_entity", "unknown")
                maps_to = m.get("maps_to") or {}
                fid = maps_to.get("feature_id", "")
                iid = maps_to.get("interface_id", "")
                method = m.get("mapping_method", "")
                targets_str = ", ".join(filter(None, [fid, iid]))
                lines.append(f"** {entity} -> {targets_str} (method: {method})")
            lines.append(
                "** These mappings are provided for traceability only. "
                "Node/element set generation is required before execution."
            )
            lines.append("")

    # ---- Missing mesh notice ----
    lines += [
        "** --- Missing mesh notice ---",
        "** No mesh has been generated. Required before solver submission:",
        "**   *NODE, *ELEMENT, *NSET, *ELSET, *SOLID SECTION",
        "**   *BOUNDARY, *CLOAD",
        "**   *STEP / *STATIC / *NODE FILE",
        "",
        "** END OF AIENG UPDATED DECK",
    ]

    return "\n".join(lines) + "\n"


def _patch_status_yaml(raw_status: bytes | None, *, exported: bool) -> bytes | None:
    if raw_status is None:
        return None
    try:
        status = yaml.safe_load(raw_status)
    except Exception:
        return raw_status
    if not isinstance(status, dict):
        return raw_status
    cae = status.setdefault("cae_import_status", {})
    if isinstance(cae, dict):
        cae["updated_deck_exported"] = exported
        cae["updated_deck_path"] = UPDATED_DECK_PATH if exported else None
    return yaml.dump(status, default_flow_style=False, allow_unicode=True).encode()


def _read_optional_json(zf: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(zf.namelist()):
        return None
    return json.loads(zf.read(member))


def _read_existing_members(
    zf: zipfile.ZipFile,
) -> list[tuple[zipfile.ZipInfo, bytes]]:
    skip = {"manifest.json", UPDATED_DECK_PATH, STATUS_PATH}
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in zf.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else zf.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package(
    path: Path,
    members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    deck_text: str,
    status_bytes: bytes | None,
) -> None:
    resources = manifest.setdefault("resources", {})
    sim = resources.setdefault("simulation", {})
    if not isinstance(sim, dict):
        raise ValueError("manifest resources.simulation must be an object")
    sim["updated_deck"] = UPDATED_DECK_PATH

    manifest_json = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as fh:
        temp_path = Path(fh.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for info, data in members:
                zf.writestr(info, data)
            zf.writestr("manifest.json", manifest_json)
            zf.writestr(UPDATED_DECK_PATH, deck_text.encode())
            if status_bytes is not None:
                zf.writestr(STATUS_PATH, status_bytes)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
