from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from aieng import FORMAT_VERSION, __version__

MESH_HANDOFF_PATH = "simulation/mesh_handoff_contract.json"
TOPOLOGY_MAP_PATH = "geometry/topology_map.json"


def write_mesh_handoff_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
    handoff_id: str = "mesh_handoff_001",
) -> Path:
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
            if MESH_HANDOFF_PATH in names and not overwrite:
                raise FileExistsError(f"{MESH_HANDOFF_PATH} already exists; use --overwrite to replace it")
            if TOPOLOGY_MAP_PATH not in names:
                raise FileNotFoundError(
                    "geometry/topology_map.json missing; run aieng extract-topology before write-mesh-handoff"
                )

            manifest = json.loads(package.read("manifest.json"))
            topology_map = json.loads(package.read(TOPOLOGY_MAP_PATH))
            setup_yaml = _read_optional_yaml(package, "simulation/setup.yaml")
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {package_file}") from exc

    contract = _build_mesh_handoff_contract(
        handoff_id=handoff_id,
        names=names,
        topology_map=topology_map,
        setup_yaml=setup_yaml,
    )

    _rewrite_package_with_contract(package_file, existing_members, manifest, contract)
    return package_file


def _build_mesh_handoff_contract(
    *,
    handoff_id: str,
    names: set[str],
    topology_map: dict[str, Any],
    setup_yaml: Any | None,
) -> dict[str, Any]:
    geometry_source = "geometry/normalized.step" if "geometry/normalized.step" in names else "geometry/source.step"

    entities = topology_map.get("entities")
    if not isinstance(entities, list):
        raise ValueError("geometry/topology_map.json entities must be an array")

    body_ids = sorted(
        entity.get("id")
        for entity in entities
        if isinstance(entity, dict) and entity.get("type") == "solid" and isinstance(entity.get("id"), str)
    )
    face_ids = sorted(
        entity.get("id")
        for entity in entities
        if isinstance(entity, dict) and entity.get("type") == "face" and isinstance(entity.get("id"), str)
    )
    edge_ids = sorted(
        entity.get("id")
        for entity in entities
        if isinstance(entity, dict) and entity.get("type") == "edge" and isinstance(entity.get("id"), str)
    )

    if not face_ids:
        raise ValueError("topology map contains no face entities; mesh handoff requires topology face references")

    target_claim_ids = ["claim_mesh_evidence_001"]
    mesh_size = _mesh_size_from_setup(setup_yaml)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "format_version": FORMAT_VERSION,
        "handoff_id": handoff_id,
        "generated_by": f"aieng {__version__}",
        "generated_at_utc": now,
        "geometry_source": geometry_source,
        "mesher_target": "gmsh",
        "mesh_recommendations": {
            "element_type": "tetra",
            "global_element_size": mesh_size,
        },
        "topology_refs": {
            "body_ids": body_ids,
            "face_ids": face_ids,
            "edge_ids": edge_ids,
        },
        "target_claim_ids": target_claim_ids,
        "execution_boundary": {
            "external_tools_execute": True,
            "aieng_core_executes_mesher": False,
        },
        "notes": [
            "Contract describes handoff expectations only; .aieng core does not execute meshing.",
            "Mesh evidence should be written back via import-mesh-evidence after external execution.",
        ],
    }


def _mesh_size_from_setup(setup_yaml: Any | None) -> float | None:
    if not isinstance(setup_yaml, dict):
        return None
    mesh = setup_yaml.get("mesh")
    if not isinstance(mesh, dict):
        return None
    value = mesh.get("element_size")
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def _read_optional_yaml(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    try:
        return yaml.safe_load(package.read(member).decode("utf-8"))
    except Exception:
        return None


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    skip = {"manifest.json", MESH_HANDOFF_PATH}
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_contract(
    package_file: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    contract: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    simulation_resources = resources.setdefault("simulation", {})
    if not isinstance(simulation_resources, dict):
        raise ValueError("manifest resources.simulation must be an object")
    simulation_resources["mesh_handoff_contract"] = MESH_HANDOFF_PATH

    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    contract_json = json.dumps(contract, indent=2, sort_keys=True) + "\n"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=package_file.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(MESH_HANDOFF_PATH, contract_json)
        shutil.move(str(temp_path), package_file)
    finally:
        if temp_path.exists():
            temp_path.unlink()
