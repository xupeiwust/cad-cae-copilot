from __future__ import annotations

from collections import Counter
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from aieng import FORMAT_VERSION

ASSEMBLY_GRAPH_PATH = "assembly/assembly_graph.json"
ASSEMBLY_DIR = "assembly/"
ASSEMBLY_GRAPH_FORMAT = "aieng.assembly_graph"

_VALID_MATE_TYPES = {
    "planar", "cylindrical", "coincident", "parallel", "perpendicular",
    "fixed", "revolute", "slider", "pin_slot", "custom",
}


def build_assembly_graph_package(
    package_path: str | Path,
    definition_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write assembly/assembly_graph.json to an existing .aieng package.

    Reads the assembly structure from an external YAML definition file and
    writes it as a first-class package resource. Does not modify geometry.
    """
    path = Path(package_path)
    definition = Path(definition_path)

    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if not definition.exists():
        raise FileNotFoundError(f"definition file does not exist: {definition}")

    try:
        raw = yaml.safe_load(definition.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"definition file is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("definition file must be a YAML mapping")

    _validate_definition(raw, definition)

    try:
        with zipfile.ZipFile(path, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if ASSEMBLY_GRAPH_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{ASSEMBLY_GRAPH_PATH} already exists; use --overwrite to replace it"
                )
            manifest = json.loads(package.read("manifest.json"))
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    assembly_graph = _build_assembly_graph(raw, definition)
    _rewrite_package_with_assembly_graph(path, existing_members, manifest, assembly_graph)
    return path


def _validate_definition(raw: dict[str, Any], definition: Path) -> None:
    parts = raw.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError(f"{definition}: 'parts' must be a non-empty list")

    part_ids: list[str] = []
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ValueError(f"{definition}: parts[{i}] must be a mapping")
        pid = part.get("part_id")
        if not isinstance(pid, str) or not pid.strip():
            raise ValueError(f"{definition}: parts[{i}] missing 'part_id'")
        if not part.get("label"):
            raise ValueError(f"{definition}: parts[{i}] missing 'label'")
        part_ids.append(pid)

    duplicates = [part_id for part_id, count in Counter(part_ids).items() if count > 1]
    if duplicates:
        raise ValueError(
            f"{definition}: duplicate part_id values: {', '.join(sorted(duplicates))}"
        )

    mates = raw.get("mates")
    if mates is not None:
        if not isinstance(mates, list):
            raise ValueError(f"{definition}: 'mates' must be a list")
        mate_ids: list[str] = []
        for i, mate in enumerate(mates):
            if not isinstance(mate, dict):
                raise ValueError(f"{definition}: mates[{i}] must be a mapping")
            mid = mate.get("mate_id")
            if not isinstance(mid, str) or not mid.strip():
                raise ValueError(f"{definition}: mates[{i}] missing 'mate_id'")
            mate_ids.append(mid)
            for field in ("part_a", "part_b"):
                if not mate.get(field):
                    raise ValueError(f"{definition}: mates[{i}] missing '{field}'")
            mate_type = mate.get("mate_type")
            if mate_type not in _VALID_MATE_TYPES:
                raise ValueError(
                    f"{definition}: mates[{i}] mate_type {mate_type!r} is not valid; "
                    f"choose from: {', '.join(sorted(_VALID_MATE_TYPES))}"
                )

        dup_mates = [mate_id for mate_id, count in Counter(mate_ids).items() if count > 1]
        if dup_mates:
            raise ValueError(
                f"{definition}: duplicate mate_id values: {', '.join(sorted(dup_mates))}"
            )

    cs = raw.get("coordinate_system")
    if not isinstance(cs, dict) or not cs.get("frame"):
        raise ValueError(f"{definition}: 'coordinate_system' must have a 'frame' key")

    policy = raw.get("claim_policy")
    if not isinstance(policy, dict):
        raise ValueError(f"{definition}: 'claim_policy' must be a mapping")
    if not policy.get("allowed"):
        raise ValueError(f"{definition}: 'claim_policy.allowed' must be a non-empty list")
    if "forbidden" not in policy:
        raise ValueError(f"{definition}: 'claim_policy' must include a 'forbidden' list")


def _build_assembly_graph(raw: dict[str, Any], definition: Path) -> dict[str, Any]:
    parts = [
        {
            k: v for k, v in part.items()
            if k in ("part_id", "label", "step_ref", "aieng_package_ref")
        }
        for part in raw.get("parts", [])
    ]

    mates = [
        {
            k: v for k, v in mate.items()
            if k in ("mate_id", "part_a", "part_b", "mate_type", "interface_refs", "notes")
        }
        for mate in raw.get("mates", [])
    ]

    cs_raw = raw.get("coordinate_system", {})
    coordinate_system: dict[str, Any] = {"frame": cs_raw.get("frame", "global_origin")}
    if "notes" in cs_raw:
        coordinate_system["notes"] = cs_raw["notes"]

    policy_raw = raw.get("claim_policy", {})
    claim_policy: dict[str, Any] = {
        "allowed": list(policy_raw.get("allowed", [])),
        "forbidden": list(policy_raw.get("forbidden", [])),
    }

    graph: dict[str, Any] = {
        "format": ASSEMBLY_GRAPH_FORMAT,
        "format_version": FORMAT_VERSION,
        "source_files": [str(definition.name)],
        "parts": parts,
        "mates": mates,
        "coordinate_system": coordinate_system,
        "claim_policy": claim_policy,
    }

    notes = raw.get("notes")
    if notes:
        graph["notes"] = list(notes)

    return graph


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    skip = {"manifest.json", ASSEMBLY_GRAPH_PATH}
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_assembly_graph(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    assembly_graph: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    assembly_resources = resources.setdefault("assembly", {})
    if not isinstance(assembly_resources, dict):
        raise ValueError("manifest resources.assembly must be an object")
    assembly_resources["assembly_graph"] = ASSEMBLY_GRAPH_PATH

    graph_json = json.dumps(assembly_graph, indent=2, sort_keys=True) + "\n"
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    existing_filenames = {info.filename for info, _ in existing_members}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            if ASSEMBLY_DIR not in existing_filenames:
                out_package.writestr(ASSEMBLY_DIR, b"")
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(ASSEMBLY_GRAPH_PATH, graph_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
