from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

CAE_MAPPING_PATH = "simulation/cae_mapping.json"
FEATURE_GRAPH_PATH = "graph/feature_graph.json"
INTERFACE_GRAPH_PATH = "objects/interface_graph.json"

_VALID_CONFIDENCE = {"high", "medium", "low"}


def apply_cae_mapping_package(
    package_path: str | Path,
    *,
    mapping_path: str | Path,
    overwrite: bool = False,
) -> Path:
    package_file = Path(package_path)
    mapping_file = Path(mapping_path)

    if not package_file.exists():
        raise FileNotFoundError(f"package does not exist: {package_file}")
    if package_file.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")
    if not mapping_file.exists():
        raise FileNotFoundError(f"mapping file does not exist: {mapping_file}")

    user_mappings = _read_and_validate_mapping_yaml(mapping_file)

    try:
        with zipfile.ZipFile(package_file, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if CAE_MAPPING_PATH not in names:
                raise FileNotFoundError(
                    "simulation/cae_mapping.json missing; run aieng import-cae-deck before apply-cae-mapping"
                )

            manifest = json.loads(package.read("manifest.json"))
            cae_mapping = json.loads(package.read(CAE_MAPPING_PATH))
            feature_graph = _read_optional_json(package, FEATURE_GRAPH_PATH)
            interface_graph = _read_optional_json(package, INTERFACE_GRAPH_PATH)
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {package_file}") from exc

    updated = _apply_user_mappings(
        cae_mapping=cae_mapping,
        user_mappings=user_mappings,
        feature_graph=feature_graph,
        interface_graph=interface_graph,
        overwrite=overwrite,
        source_mapping_file=mapping_file.name,
    )

    _rewrite_package_with_cae_mapping(
        package_file,
        existing_members,
        manifest,
        updated,
    )
    return package_file


def _read_and_validate_mapping_yaml(mapping_file: Path) -> list[dict[str, Any]]:
    try:
        data = yaml.safe_load(mapping_file.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError(f"mapping file must be UTF-8 text: {mapping_file}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"mapping file is invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("mapping YAML root must be an object")

    mappings = data.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError("mapping YAML must include a mappings list")

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(mappings):
        if not isinstance(item, dict):
            raise ValueError(f"mapping at index {index} must be an object")

        cae_entity = item.get("cae_entity")
        if not isinstance(cae_entity, str) or not cae_entity.strip():
            raise ValueError(f"mapping at index {index} missing non-empty cae_entity")

        maps_to = item.get("maps_to")
        if not isinstance(maps_to, dict):
            raise ValueError(f"mapping {cae_entity} must include maps_to object")

        feature_id = maps_to.get("feature_id")
        interface_id = maps_to.get("interface_id")
        if not isinstance(feature_id, str):
            feature_id = None
        if not isinstance(interface_id, str):
            interface_id = None
        if not feature_id and not interface_id:
            raise ValueError(
                f"mapping {cae_entity} maps_to must include at least one of feature_id or interface_id"
            )

        mapping_method = item.get("mapping_method", "user_provided")
        if mapping_method != "user_provided":
            raise ValueError(
                f"mapping {cae_entity} mapping_method must be user_provided in Phase 10B"
            )

        confidence = item.get("confidence", "high")
        if not isinstance(confidence, str) or confidence not in _VALID_CONFIDENCE:
            raise ValueError(
                f"mapping {cae_entity} has invalid confidence {confidence!r}; expected one of high, medium, low"
            )

        notes = item.get("notes")
        normalized_notes: list[str] = []
        if notes is not None:
            if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
                raise ValueError(f"mapping {cae_entity} notes must be a list of strings")
            normalized_notes = [note for note in notes if note.strip()]

        normalized.append(
            {
                "cae_entity": cae_entity.strip(),
                "maps_to": {
                    key: value
                    for key, value in {
                        "feature_id": feature_id,
                        "interface_id": interface_id,
                    }.items()
                    if isinstance(value, str)
                },
                "mapping_method": "user_provided",
                "confidence": confidence,
                "notes": normalized_notes,
            }
        )

    return normalized


def _apply_user_mappings(
    *,
    cae_mapping: dict[str, Any],
    user_mappings: list[dict[str, Any]],
    feature_graph: Any | None,
    interface_graph: Any | None,
    overwrite: bool,
    source_mapping_file: str,
) -> dict[str, Any]:
    if not isinstance(cae_mapping, dict):
        raise ValueError("simulation/cae_mapping.json must be a JSON object")

    existing = cae_mapping.get("mappings")
    if not isinstance(existing, list):
        raise ValueError("simulation/cae_mapping.json mappings must be an array")

    feature_ids = _feature_ids(feature_graph)
    interface_ids = _interface_ids(interface_graph)

    index_by_entity: dict[str, int] = {}
    for idx, item in enumerate(existing):
        if isinstance(item, dict) and isinstance(item.get("cae_entity"), str):
            index_by_entity[item["cae_entity"]] = idx

    for user_entry in user_mappings:
        cae_entity = user_entry["cae_entity"]
        if cae_entity not in index_by_entity:
            raise ValueError(f"mapping references unknown cae_entity: {cae_entity}")

        maps_to = user_entry["maps_to"]
        feature_id = maps_to.get("feature_id")
        interface_id = maps_to.get("interface_id")

        if isinstance(feature_id, str):
            if feature_graph is None:
                raise ValueError(
                    f"mapping {cae_entity} provides feature_id but graph/feature_graph.json is missing"
                )
            if feature_id not in feature_ids:
                raise ValueError(f"mapping {cae_entity} references unknown feature_id {feature_id}")

        if isinstance(interface_id, str):
            if interface_graph is None:
                raise ValueError(
                    f"mapping {cae_entity} provides interface_id but objects/interface_graph.json is missing"
                )
            if interface_id not in interface_ids:
                raise ValueError(f"mapping {cae_entity} references unknown interface_id {interface_id}")

        idx = index_by_entity[cae_entity]
        current = existing[idx]
        if not isinstance(current, dict):
            raise ValueError(f"simulation/cae_mapping.json mapping for {cae_entity} is invalid")

        current_status = current.get("mapping_status")
        if not overwrite and current_status in {"mapped", "partially_mapped"}:
            raise FileExistsError(
                f"CAE entity {cae_entity} is already mapped; use --overwrite to replace user mapping"
            )

        updated = dict(current)
        updated["maps_to"] = dict(user_entry["maps_to"])
        updated["mapping_status"] = "mapped"
        updated["mapping_method"] = "user_provided"
        updated["confidence"] = user_entry["confidence"]

        existing_notes = updated.get("notes")
        note_list: list[str] = []
        if isinstance(existing_notes, list):
            note_list.extend(note for note in existing_notes if isinstance(note, str))
        note_list.extend(user_entry.get("notes", []))
        if note_list:
            updated["notes"] = _dedupe(note_list)

        existing[idx] = updated

    mapped_count = 0
    for item in existing:
        if isinstance(item, dict) and item.get("mapping_status") in {"mapped", "partially_mapped"}:
            mapped_count += 1

    cae_mapping["mapping_summary"] = {
        "mapped_count": mapped_count,
        "unmapped_count": max(0, len(existing) - mapped_count),
    }

    files = cae_mapping.get("source_mapping_files")
    if not isinstance(files, list):
        files = []
    files = [entry for entry in files if isinstance(entry, str)]
    if source_mapping_file not in files:
        files.append(source_mapping_file)
    cae_mapping["source_mapping_files"] = sorted(files)

    return cae_mapping


def _feature_ids(feature_graph: Any | None) -> set[str]:
    if not isinstance(feature_graph, dict):
        return set()
    features = feature_graph.get("features")
    if not isinstance(features, list):
        return set()
    return {
        feature["id"]
        for feature in features
        if isinstance(feature, dict) and isinstance(feature.get("id"), str)
    }


def _interface_ids(interface_graph: Any | None) -> set[str]:
    if not isinstance(interface_graph, dict):
        return set()
    interfaces = interface_graph.get("interfaces")
    if not isinstance(interfaces, list):
        return set()
    return {
        interface["id"]
        for interface in interfaces
        if isinstance(interface, dict) and isinstance(interface.get("id"), str)
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _read_optional_json(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    try:
        return json.loads(package.read(member))
    except Exception:
        return None


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    skip = {"manifest.json", CAE_MAPPING_PATH}
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_cae_mapping(
    package_file: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    cae_mapping: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    simulation_resources = resources.setdefault("simulation", {})
    if not isinstance(simulation_resources, dict):
        raise ValueError("manifest resources.simulation must be an object")
    simulation_resources.setdefault("cae_mapping", CAE_MAPPING_PATH)

    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    mapping_json = json.dumps(cae_mapping, indent=2, sort_keys=True) + "\n"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=package_file.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(CAE_MAPPING_PATH, mapping_json)

        shutil.move(str(temp_path), package_file)
    finally:
        if temp_path.exists():
            temp_path.unlink()
