from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from aieng import FORMAT_VERSION
from aieng.context.materials import get_material
from aieng.graph.feature_graph import FEATURE_GRAPH_PATH
from aieng.geometry.topology_extractor import TOPOLOGY_MAP_PATH

NUMERIC_TYPES = (int, float)

CONSTRAINTS_PATH = "graph/constraints.json"
SIMULATION_SETUP_PATH = "simulation/setup.yaml"
PROTECTED_REGIONS_PATH = "ai/protected_regions.json"
ALLOWED_PROTECTED_OPERATIONS = ["read", "use_as_boundary_condition", "reference"]
FORBIDDEN_PROTECTED_OPERATIONS = ["move", "resize", "delete", "change_diameter", "remove"]


def apply_context_package(
    package_path: str | Path,
    context_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Apply user-provided engineering context YAML to an existing .aieng package."""
    package_file = Path(package_path)
    context_file = Path(context_path)
    if not package_file.exists():
        raise FileNotFoundError(f"package does not exist: {package_file}")
    if package_file.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")
    if not context_file.exists():
        raise FileNotFoundError(f"context file does not exist: {context_file}")

    context = _read_context_yaml(context_file)
    material_name = _required_string(context, "material")
    material_data = get_material(material_name)

    try:
        with zipfile.ZipFile(package_file, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if FEATURE_GRAPH_PATH not in names:
                raise FileNotFoundError(f"{FEATURE_GRAPH_PATH} missing")
            existing_outputs = [path for path in (CONSTRAINTS_PATH, SIMULATION_SETUP_PATH, PROTECTED_REGIONS_PATH) if path in names]
            if existing_outputs and not overwrite:
                raise FileExistsError(
                    f"generated context resources already exist: {', '.join(existing_outputs)}; use --overwrite to replace them"
                )

            manifest = json.loads(package.read("manifest.json"))
            feature_graph = json.loads(package.read(FEATURE_GRAPH_PATH))
            topology_map = _read_optional_json(package, TOPOLOGY_MAP_PATH)
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {package_file}") from exc

    feature_ids = _feature_ids(feature_graph)
    protected_features = _string_list(context.get("protected_features", []), "protected_features")
    _require_known_features(protected_features, feature_ids, "protected_features")

    simulation = context.get("simulation", {})
    if not isinstance(simulation, dict):
        raise ValueError("simulation must be a mapping")
    simulation_type = simulation.get("type", "static_structural")
    if simulation_type != "static_structural":
        raise ValueError("only static_structural simulation type is supported in v0.1")

    fixed_features = _string_list(simulation.get("fixed", []), "simulation.fixed")
    _require_known_features(fixed_features, feature_ids, "simulation.fixed")
    loads = _loads(simulation.get("loads", []), feature_ids)
    targets = context.get("targets", {})
    if targets is None:
        targets = {}
    if not isinstance(targets, dict):
        raise ValueError("targets must be a mapping")
    assumptions = _string_list(context.get("assumptions", []), "assumptions")
    body_id = _first_solid_body_id(topology_map) or "body_001"

    constraints = _build_constraints(protected_features, targets, assumptions)
    simulation_setup = _build_simulation_setup(
        material_name=material_name,
        material_data=material_data,
        body_id=body_id,
        simulation_type=simulation_type,
        fixed_features=fixed_features,
        loads=loads,
        targets=targets,
        assumptions=assumptions,
        units=manifest.get("units", {}),
    )
    protected_regions = _build_protected_regions(protected_features)

    _rewrite_package_with_context(package_file, existing_members, manifest, constraints, simulation_setup, protected_regions)
    return package_file


def _read_context_yaml(context_file: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(context_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"context YAML is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("context YAML must contain a mapping at the top level")
    return data


def _read_optional_json(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    return json.loads(package.read(member))


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    skip = {"manifest.json", CONSTRAINTS_PATH, SIMULATION_SETUP_PATH, PROTECTED_REGIONS_PATH}
    seen: set[str] = set()
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return list(value)


def _feature_ids(feature_graph: dict[str, Any]) -> set[str]:
    features = feature_graph.get("features", [])
    if not isinstance(features, list):
        raise ValueError("feature_graph features must be a list")
    ids = {feature.get("id") for feature in features if isinstance(feature, dict) and isinstance(feature.get("id"), str)}
    if not ids:
        raise ValueError("feature_graph contains no feature IDs")
    return ids


def _require_known_features(feature_ids: list[str], known_feature_ids: set[str], field_name: str) -> None:
    unknown = sorted(set(feature_ids) - known_feature_ids)
    if unknown:
        raise ValueError(f"{field_name} references unknown feature IDs: {', '.join(unknown)}")


def _loads(value: Any, known_feature_ids: set[str]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("simulation.loads must be a list")
    loads: list[dict[str, Any]] = []
    for index, load in enumerate(value, start=1):
        if not isinstance(load, dict):
            raise ValueError(f"simulation.loads[{index}] must be a mapping")
        target = load.get("target")
        if not isinstance(target, str) or target not in known_feature_ids:
            raise ValueError(f"simulation.loads[{index}] references unknown target feature ID: {target}")
        load_type = load.get("type")
        if not isinstance(load_type, str) or not load_type:
            raise ValueError(f"simulation.loads[{index}].type must be a non-empty string")
        value_n = load.get("value_n")
        if not isinstance(value_n, NUMERIC_TYPES):
            raise ValueError(f"simulation.loads[{index}].value_n must be numeric")
        direction = load.get("direction")
        if not _is_numeric_vector3(direction):
            raise ValueError(f"simulation.loads[{index}].direction must be a length-3 numeric array")
        loads.append(
            {
                "id": f"load_{index:03d}",
                "target_feature": target,
                "type": load_type,
                "value_n": float(value_n),
                "direction": [float(component) for component in direction],
            }
        )
    return loads


def _is_numeric_vector3(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 3 and all(
        isinstance(component, NUMERIC_TYPES) for component in value
    )


def _first_solid_body_id(topology_map: Any | None) -> str | None:
    if not isinstance(topology_map, dict):
        return None
    entities = topology_map.get("entities", [])
    if not isinstance(entities, list):
        return None
    for entity in entities:
        if isinstance(entity, dict) and entity.get("type") == "solid" and isinstance(entity.get("id"), str):
            return entity["id"]
    return None


def _build_constraints(protected_features: list[str], targets: dict[str, Any], assumptions: list[str]) -> dict[str, Any]:
    constraints: list[dict[str, Any]] = []
    for index, feature_id in enumerate(protected_features, start=1):
        constraints.append(
            {
                "id": f"con_protect_{index:03d}",
                "type": "protect_geometry",
                "target": feature_id,
                "reason": "User-provided protected feature.",
            }
        )
    if "max_von_mises_stress_mpa" in targets:
        constraints.append(
            {
                "id": "con_sim_target_001",
                "type": "simulation_target",
                "target": "sim_static_001",
                "reason": "User-provided static structural target.",
                "metric": "max_von_mises_stress_mpa",
                "operator": "<",
                "value": targets["max_von_mises_stress_mpa"],
            }
        )
    return {"format_version": FORMAT_VERSION, "constraints": constraints, "assumptions": assumptions}


def _build_simulation_setup(
    *,
    material_name: str,
    material_data: dict[str, float],
    body_id: str,
    simulation_type: str,
    fixed_features: list[str],
    loads: list[dict[str, Any]],
    targets: dict[str, Any],
    assumptions: list[str],
    units: dict[str, Any],
) -> dict[str, Any]:
    return {
        "simulation_id": "sim_static_001",
        "simulation_type": simulation_type,
        "solver_target": "calculix",
        "units": units,
        "materials": {material_name: material_data},
        "assignments": [{"target_body": body_id, "material": material_name}],
        "boundary_conditions": [
            {"id": f"bc_fixed_{index:03d}", "type": "fixed", "target_feature": feature_id}
            for index, feature_id in enumerate(fixed_features, start=1)
        ],
        "loads": loads,
        "targets": dict(targets),
        "assumptions": assumptions,
    }


def _build_protected_regions(protected_features: list[str]) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "protected_regions": [
            {
                "feature_id": feature_id,
                "reason": "User-provided protected feature.",
                "allowed_operations": list(ALLOWED_PROTECTED_OPERATIONS),
                "forbidden_operations": list(FORBIDDEN_PROTECTED_OPERATIONS),
            }
            for feature_id in protected_features
        ],
    }


def _rewrite_package_with_context(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    constraints: dict[str, Any],
    simulation_setup: dict[str, Any],
    protected_regions: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    graph_resources = resources.setdefault("graph", {})
    simulation_resources = resources.setdefault("simulation", {})
    ai_resources = resources.setdefault("ai", {})
    if not isinstance(graph_resources, dict):
        raise ValueError("manifest resources.graph must be an object")
    if not isinstance(simulation_resources, dict):
        raise ValueError("manifest resources.simulation must be an object")
    if not isinstance(ai_resources, dict):
        raise ValueError("manifest resources.ai must be an object")

    graph_resources["constraints"] = CONSTRAINTS_PATH
    simulation_resources["setup"] = SIMULATION_SETUP_PATH
    ai_resources["protected_regions"] = PROTECTED_REGIONS_PATH

    constraints_json = json.dumps(constraints, indent=2, sort_keys=True) + "\n"
    protected_regions_json = json.dumps(protected_regions, indent=2, sort_keys=True) + "\n"
    simulation_yaml = yaml.safe_dump(simulation_setup, sort_keys=True)
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(CONSTRAINTS_PATH, constraints_json)
            out_package.writestr(SIMULATION_SETUP_PATH, simulation_yaml)
            out_package.writestr(PROTECTED_REGIONS_PATH, protected_regions_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
