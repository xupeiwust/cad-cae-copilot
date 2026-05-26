from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

NUMERIC_TYPES = (int, float)

CAE_IMPORT_DIR = "simulation/cae_imports/"
CAE_SOURCE_DECK_PATH = "simulation/cae_imports/source_solver_deck.inp"
CAE_PARSED_MATERIALS_PATH = "simulation/cae_imports/parsed_materials.json"
CAE_PARSED_BOUNDARY_CONDITIONS_PATH = "simulation/cae_imports/parsed_boundary_conditions.json"
CAE_PARSED_LOADS_PATH = "simulation/cae_imports/parsed_loads.json"
CAE_MAPPING_PATH = "simulation/cae_mapping.json"

FEATURE_GRAPH_PATH = "graph/feature_graph.json"
INTERFACE_GRAPH_PATH = "objects/interface_graph.json"

SUPPORTED_FORMATS = {"calculix"}
PARSER_SCOPE = "phase_10a_minimal_cards"


@dataclass
class ParsedDeck:
    materials: list[dict[str, Any]]
    boundary_conditions: list[dict[str, Any]]
    loads: list[dict[str, Any]]


def import_cae_deck_package(
    package_path: str | Path,
    *,
    deck_path: str | Path,
    deck_format: str,
    overwrite: bool = False,
) -> Path:
    package_file = Path(package_path)
    deck_file = Path(deck_path)

    if not package_file.exists():
        raise FileNotFoundError(f"package does not exist: {package_file}")
    if package_file.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")
    if not deck_file.exists():
        raise FileNotFoundError(f"CAE deck file does not exist: {deck_file}")

    normalized_format = deck_format.strip().lower()
    if normalized_format not in SUPPORTED_FORMATS:
        raise ValueError(
            f"unsupported CAE deck format {deck_format!r}; supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}"
        )

    try:
        deck_text = deck_file.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"CAE deck file must be UTF-8 text: {deck_file}") from exc

    try:
        with zipfile.ZipFile(package_file, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")

            generated_outputs = {
                CAE_SOURCE_DECK_PATH,
                CAE_PARSED_MATERIALS_PATH,
                CAE_PARSED_BOUNDARY_CONDITIONS_PATH,
                CAE_PARSED_LOADS_PATH,
                CAE_MAPPING_PATH,
            }
            existing_outputs = sorted(path for path in generated_outputs if path in names)
            if existing_outputs and not overwrite:
                raise FileExistsError(
                    "CAE import resources already exist: "
                    f"{', '.join(existing_outputs)}; use --overwrite to replace them"
                )

            manifest = json.loads(package.read("manifest.json"))
            feature_graph = _read_optional_json(package, FEATURE_GRAPH_PATH)
            interface_graph = _read_optional_json(package, INTERFACE_GRAPH_PATH)
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {package_file}") from exc

    parsed = _parse_calculix_minimal(deck_text)

    materials_doc = {
        "format": "aieng.parsed_cae_materials",
        "format_version": FORMAT_VERSION,
        "source_file": CAE_SOURCE_DECK_PATH,
        "materials": parsed.materials,
        "parser": {
            "format": normalized_format,
            "scope": PARSER_SCOPE,
        },
    }

    bcs_doc = {
        "format": "aieng.parsed_cae_boundary_conditions",
        "format_version": FORMAT_VERSION,
        "source_file": CAE_SOURCE_DECK_PATH,
        "boundary_conditions": parsed.boundary_conditions,
        "parser": {
            "format": normalized_format,
            "scope": PARSER_SCOPE,
        },
    }

    loads_doc = {
        "format": "aieng.parsed_cae_loads",
        "format_version": FORMAT_VERSION,
        "source_file": CAE_SOURCE_DECK_PATH,
        "loads": parsed.loads,
        "parser": {
            "format": normalized_format,
            "scope": PARSER_SCOPE,
        },
    }

    mapping_doc = _build_cae_mapping_doc(
        parsed=parsed,
        feature_graph=feature_graph,
        interface_graph=interface_graph,
    )

    _rewrite_package_with_cae_imports(
        package_file,
        existing_members,
        manifest,
        source_deck_text=deck_text,
        materials_doc=materials_doc,
        bcs_doc=bcs_doc,
        loads_doc=loads_doc,
        mapping_doc=mapping_doc,
    )

    return package_file


def _parse_calculix_minimal(deck_text: str) -> ParsedDeck:
    lines = deck_text.splitlines()

    materials: list[dict[str, Any]] = []
    boundary_conditions: list[dict[str, Any]] = []
    loads: list[dict[str, Any]] = []

    current_material: dict[str, Any] | None = None

    index = 0
    while index < len(lines):
        raw = lines[index].strip()
        if not raw or raw.startswith("**"):
            index += 1
            continue

        if not raw.startswith("*"):
            index += 1
            continue

        card_upper = raw.upper()

        if card_upper.startswith("*MATERIAL"):
            material_name = _material_name_from_card(raw)
            current_material = {
                "name": material_name,
                "elastic": None,
                "density": None,
            }
            materials.append(current_material)
            index += 1
            continue

        if card_upper.startswith("*ELASTIC"):
            values = _next_numeric_csv_values(lines, index + 1)
            if values is not None and len(values) >= 2 and current_material is not None:
                current_material["elastic"] = {
                    "youngs_modulus": values[0],
                    "poisson_ratio": values[1],
                }
            index += 1
            continue

        if card_upper.startswith("*DENSITY"):
            values = _next_numeric_csv_values(lines, index + 1)
            if values is not None and values and current_material is not None:
                current_material["density"] = values[0]
            index += 1
            continue

        if card_upper.startswith("*BOUNDARY"):
            index = _parse_boundary_block(lines, index + 1, boundary_conditions)
            continue

        if card_upper.startswith("*CLOAD"):
            index = _parse_cload_block(lines, index + 1, loads)
            continue

        index += 1

    # Remove empty material properties while preserving parsed names.
    normalized_materials: list[dict[str, Any]] = []
    for material in materials:
        normalized: dict[str, Any] = {"name": material["name"]}
        if isinstance(material.get("elastic"), dict):
            normalized["elastic"] = material["elastic"]
        if isinstance(material.get("density"), NUMERIC_TYPES):
            normalized["density"] = material["density"]
        normalized_materials.append(normalized)

    return ParsedDeck(
        materials=normalized_materials,
        boundary_conditions=boundary_conditions,
        loads=loads,
    )


def _material_name_from_card(card_line: str) -> str:
    # Example: *MATERIAL, NAME=Al6061-T6
    for item in card_line.split(","):
        part = item.strip()
        if part.upper().startswith("NAME="):
            name = part.split("=", 1)[1].strip()
            if name:
                return name
    return "unnamed_material"


def _next_numeric_csv_values(lines: list[str], start_index: int) -> list[int | float] | None:
    idx = start_index
    while idx < len(lines):
        raw = lines[idx].strip()
        if not raw or raw.startswith("**"):
            idx += 1
            continue
        if raw.startswith("*"):
            return None
        values: list[int | float] = []
        for token in raw.split(","):
            clean = token.strip()
            if not clean:
                continue
            parsed = _parse_number(clean)
            if parsed is None:
                return None
            values.append(parsed)
        return values
    return None


def _parse_boundary_block(
    lines: list[str],
    start_index: int,
    boundary_conditions: list[dict[str, Any]],
) -> int:
    idx = start_index
    while idx < len(lines):
        raw = lines[idx].strip()
        if not raw or raw.startswith("**"):
            idx += 1
            continue
        if raw.startswith("*"):
            break

        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if len(parts) >= 3:
            target = parts[0]
            dof_start = _parse_int(parts[1])
            dof_end = _parse_int(parts[2])
            if dof_start is not None and dof_end is not None:
                value: int | float = 0
                if len(parts) >= 4:
                    parsed_value = _parse_number(parts[3])
                    if parsed_value is not None:
                        value = parsed_value
                boundary_conditions.append(
                    {
                        "id": f"cae_bc_{len(boundary_conditions) + 1:03d}",
                        "target": target,
                        "dof_start": dof_start,
                        "dof_end": dof_end,
                        "value": value,
                    }
                )
        idx += 1

    return idx


def _parse_cload_block(lines: list[str], start_index: int, loads: list[dict[str, Any]]) -> int:
    idx = start_index
    while idx < len(lines):
        raw = lines[idx].strip()
        if not raw or raw.startswith("**"):
            idx += 1
            continue
        if raw.startswith("*"):
            break

        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if len(parts) >= 3:
            target = parts[0]
            dof = _parse_int(parts[1])
            value = _parse_number(parts[2])
            if dof is not None and value is not None:
                loads.append(
                    {
                        "id": f"cae_load_{len(loads) + 1:03d}",
                        "target": target,
                        "dof": dof,
                        "value": value,
                    }
                )
        idx += 1

    return idx


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _parse_number(value: str) -> int | float | None:
    try:
        as_float = float(value)
    except ValueError:
        return None

    if as_float.is_integer():
        return int(as_float)
    return as_float


def _build_cae_mapping_doc(
    *,
    parsed: ParsedDeck,
    feature_graph: Any | None,
    interface_graph: Any | None,
) -> dict[str, Any]:
    targets: list[tuple[str, str]] = []
    for bc in parsed.boundary_conditions:
        target = bc.get("target")
        if isinstance(target, str) and target:
            targets.append((target, "boundary_condition_target"))
    for load in parsed.loads:
        target = load.get("target")
        if isinstance(target, str) and target:
            targets.append((target, "load_target"))

    seen_targets: set[tuple[str, str]] = set()
    unique_targets: list[tuple[str, str]] = []
    for item in targets:
        if item in seen_targets:
            continue
        seen_targets.add(item)
        unique_targets.append(item)

    mappings: list[dict[str, Any]] = []
    for target, cae_type in unique_targets:
        mappings.append(
            {
                "cae_entity": target,
                "cae_type": cae_type,
                "maps_to": None,
                "mapping_status": "unmapped",
                "mapping_method": "not_inferred_phase_10a",
                "confidence": "none",
            }
        )

    source_files = [
        CAE_PARSED_BOUNDARY_CONDITIONS_PATH,
        CAE_PARSED_LOADS_PATH,
    ]
    if interface_graph is not None:
        source_files.append(INTERFACE_GRAPH_PATH)

    notes = [
        "Phase 10A imports CAE deck entities but does not automatically map them to geometry features.",
        "Mapping to feature_id or interface_id requires named selections, user context, or later mapping logic.",
    ]

    return {
        "format": "aieng.cae_mapping",
        "format_version": FORMAT_VERSION,
        "source_files": source_files,
        "mappings": mappings,
        "notes": notes,
        "mapping_summary": {
            "mapped_count": 0,
            "unmapped_count": len(mappings),
        },
    }


def _read_optional_json(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    try:
        return json.loads(package.read(member))
    except Exception:
        return None


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    skip = {
        "manifest.json",
        CAE_SOURCE_DECK_PATH,
        CAE_PARSED_MATERIALS_PATH,
        CAE_PARSED_BOUNDARY_CONDITIONS_PATH,
        CAE_PARSED_LOADS_PATH,
        CAE_MAPPING_PATH,
    }
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_cae_imports(
    package_file: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    *,
    source_deck_text: str,
    materials_doc: dict[str, Any],
    bcs_doc: dict[str, Any],
    loads_doc: dict[str, Any],
    mapping_doc: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    simulation_resources = resources.setdefault("simulation", {})
    if not isinstance(simulation_resources, dict):
        raise ValueError("manifest resources.simulation must be an object")

    simulation_resources["cae_import_source_solver_deck"] = CAE_SOURCE_DECK_PATH
    simulation_resources["cae_import_parsed_materials"] = CAE_PARSED_MATERIALS_PATH
    simulation_resources["cae_import_parsed_boundary_conditions"] = CAE_PARSED_BOUNDARY_CONDITIONS_PATH
    simulation_resources["cae_import_parsed_loads"] = CAE_PARSED_LOADS_PATH
    simulation_resources["cae_mapping"] = CAE_MAPPING_PATH

    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    materials_json = json.dumps(materials_doc, indent=2, sort_keys=True) + "\n"
    bcs_json = json.dumps(bcs_doc, indent=2, sort_keys=True) + "\n"
    loads_json = json.dumps(loads_doc, indent=2, sort_keys=True) + "\n"
    mapping_json = json.dumps(mapping_doc, indent=2, sort_keys=True) + "\n"

    existing_filenames = {info.filename for info, _ in existing_members}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=package_file.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)

            if CAE_IMPORT_DIR not in existing_filenames:
                out_package.writestr(CAE_IMPORT_DIR, b"")

            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(CAE_SOURCE_DECK_PATH, source_deck_text)
            out_package.writestr(CAE_PARSED_MATERIALS_PATH, materials_json)
            out_package.writestr(CAE_PARSED_BOUNDARY_CONDITIONS_PATH, bcs_json)
            out_package.writestr(CAE_PARSED_LOADS_PATH, loads_json)
            out_package.writestr(CAE_MAPPING_PATH, mapping_json)

        shutil.move(str(temp_path), package_file)
    finally:
        if temp_path.exists():
            temp_path.unlink()
