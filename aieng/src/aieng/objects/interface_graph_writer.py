from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from aieng import FORMAT_VERSION

INTERFACE_GRAPH_PATH = "objects/interface_graph.json"
OBJECTS_DIR = "objects/"
INTERFACE_GRAPH_FORMAT = "aieng.interface_graph"

_FEATURE_GRAPH_PATH = "graph/feature_graph.json"
_CONSTRAINTS_PATH = "graph/constraints.json"
_SIMULATION_SETUP_PATH = "simulation/setup.yaml"
_PROTECTED_REGIONS_PATH = "ai/protected_regions.json"
_VISUAL_ANNOTATION_PATH = "visual/annotation_layers.json"
_OBJECT_REGISTRY_PATH = "objects/object_registry.json"
_CAE_MAPPING_PATH = "simulation/cae_mapping.json"

_PROTECTION_CONSTRAINT_TYPES = {
    "protect_geometry",
    "protect_position",
    "protect_dimension",
    "preserve_interface",
}

_SOURCE_ORDER = [
    _FEATURE_GRAPH_PATH,
    _CONSTRAINTS_PATH,
    _SIMULATION_SETUP_PATH,
    _PROTECTED_REGIONS_PATH,
    _VISUAL_ANNOTATION_PATH,
    _OBJECT_REGISTRY_PATH,
    _CAE_MAPPING_PATH,
]


def build_interface_graph_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write objects/interface_graph.json to an existing .aieng package."""
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    try:
        with zipfile.ZipFile(path, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if _FEATURE_GRAPH_PATH not in names:
                raise FileNotFoundError(
                    "graph/feature_graph.json missing; "
                    "build-interface-graph requires graph/feature_graph.json — "
                    "run aieng recognize-features first"
                )
            if INTERFACE_GRAPH_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{INTERFACE_GRAPH_PATH} already exists; use --overwrite to replace it"
                )

            manifest = json.loads(package.read("manifest.json"))
            feature_graph = json.loads(package.read(_FEATURE_GRAPH_PATH))
            constraints = _read_optional_json(package, _CONSTRAINTS_PATH)
            simulation_setup = _read_optional_yaml(package, _SIMULATION_SETUP_PATH)
            protected_regions = _read_optional_json(package, _PROTECTED_REGIONS_PATH)
            annotation_layers = _read_optional_json(package, _VISUAL_ANNOTATION_PATH)
            cae_mapping = _read_optional_json(package, _CAE_MAPPING_PATH)
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    interface_graph = _build_interface_graph(
        names=names,
        feature_graph=feature_graph,
        constraints=constraints,
        simulation_setup=simulation_setup,
        protected_regions=protected_regions,
        annotation_layers=annotation_layers,
        cae_mapping=cae_mapping,
    )

    _rewrite_package_with_interface_graph(path, existing_members, manifest, interface_graph)
    return path


def _build_interface_graph(
    *,
    names: set[str],
    feature_graph: dict[str, Any],
    constraints: Any | None,
    simulation_setup: Any | None,
    protected_regions: Any | None,
    annotation_layers: Any | None,
    cae_mapping: Any | None,
) -> dict[str, Any]:
    features = _feature_map(feature_graph)
    protected_map = _protected_region_by_feature(protected_regions)
    constraint_refs = _constraint_refs_by_feature(constraints)
    fixed_refs, load_refs = _simulation_refs_by_feature(simulation_setup)
    visual_refs = _visual_refs_by_feature(annotation_layers)

    interfaces: list[dict[str, Any]] = []

    for feature_id in sorted(features.keys()):
        feature = features[feature_id]

        mounting_candidate = _is_mounting_interface_candidate(feature)
        protected_region = protected_map.get(feature_id)
        fixed_ids = fixed_refs.get(feature_id, [])
        load_ids = load_refs.get(feature_id, [])
        constraint_ids = constraint_refs.get(feature_id, [])
        annotation_ids = visual_refs.get(feature_id, [])

        should_include = any(
            [
                mounting_candidate,
                protected_region is not None,
                bool(fixed_ids),
                bool(load_ids),
                bool(constraint_ids),
            ]
        )
        if not should_include:
            continue

        roles: set[str] = set()
        if mounting_candidate:
            roles.add("mounting_interface_candidate")
        if fixed_ids:
            roles.add("fixed_support_interface")
        if load_ids:
            roles.add("load_application_interface")
        if protected_region is not None:
            roles.add("protected_external_interface")

        interface_type = _interface_type(
            mounting_candidate=mounting_candidate,
            has_fixed=bool(fixed_ids),
            has_load=bool(load_ids),
            has_protected=protected_region is not None,
        )

        topo_faces, topo_edges = _topology_refs_from_feature(feature)

        allowed_operations = []
        forbidden_operations = []
        if protected_region is not None:
            allowed_operations = list(protected_region.get("allowed_operations", []))
            forbidden_operations = list(protected_region.get("forbidden_operations", []))

        interfaces.append(
            {
                "id": f"iface_{_slug(feature_id)}",
                "type": interface_type,
                "feature_ids": [feature_id],
                "topology_refs": {
                    "faces": topo_faces,
                    "edges": topo_edges,
                },
                "roles": sorted(roles),
                "protected": protected_region is not None,
                "constraint_refs": sorted(set(constraint_ids)),
                "simulation_refs": sorted(set(fixed_ids + load_ids)),
                "visual_refs": sorted(set(annotation_ids)),
                "allowed_operations": sorted(set(allowed_operations)),
                "forbidden_operations": sorted(set(forbidden_operations)),
                "status": "candidate_from_structured_context",
                "notes": [
                    "Interface graph is generated from structured resources.",
                    "Interface labels are not independent engineering certification.",
                ],
            }
        )

    _enrich_interfaces_with_cae_mapping(
        interfaces,
        features=features,
        protected_map=protected_map,
        cae_mapping=cae_mapping,
    )

    return {
        "format": INTERFACE_GRAPH_FORMAT,
        "format_version": FORMAT_VERSION,
        "source_files": [path for path in _SOURCE_ORDER if path in names],
        "interfaces": sorted(interfaces, key=lambda item: item["id"]),
        "notes": [
            "This graph is a generated interface index, not the source of truth.",
            "Feature graph, constraints, protected regions, and simulation setup remain authoritative.",
            "Explicit CAE mappings may enrich interfaces with CAE deck entity references; no automatic CAE inference is performed.",
        ],
    }


def _enrich_interfaces_with_cae_mapping(
    interfaces: list[dict[str, Any]],
    *,
    features: dict[str, dict[str, Any]],
    protected_map: dict[str, dict[str, Any]],
    cae_mapping: Any | None,
) -> None:
    """Attach explicit CAE mapping refs to generated interfaces.

    Phase 10C only mirrors user-provided/explicit mapping data into the
    interface index. It does not infer new mappings from CAE names.
    """
    if not isinstance(cae_mapping, dict):
        return
    mappings = cae_mapping.get("mappings")
    if not isinstance(mappings, list):
        return

    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        if mapping.get("mapping_status") not in {"mapped", "partially_mapped"}:
            continue
        maps_to = mapping.get("maps_to")
        if not isinstance(maps_to, dict):
            continue

        feature_id = maps_to.get("feature_id")
        interface_id = maps_to.get("interface_id")
        if not isinstance(feature_id, str):
            feature_id = None
        if not isinstance(interface_id, str):
            interface_id = None

        target = _find_interface_for_mapping(
            interfaces,
            interface_id=interface_id,
            feature_id=feature_id,
        )
        if target is None and feature_id and feature_id in features:
            target = _make_cae_mapped_interface(
                feature_id=feature_id,
                feature=features[feature_id],
                protected_region=protected_map.get(feature_id),
            )
            interfaces.append(target)

        if target is None:
            continue

        ref = _cae_ref_from_mapping(mapping)
        if ref is None:
            continue
        _add_unique_cae_ref(target, ref)

        roles = set(item for item in target.get("roles", []) if isinstance(item, str))
        roles.add("cae_mapped_interface")
        cae_role = _cae_role(mapping.get("cae_type"))
        if cae_role:
            roles.add(cae_role)
        target["roles"] = sorted(roles)

        notes = list(target.get("notes", [])) if isinstance(target.get("notes"), list) else []
        note = "Interface includes explicit CAE deck entity references from simulation/cae_mapping.json."
        if note not in notes:
            notes.append(note)
        target["notes"] = notes


def _find_interface_for_mapping(
    interfaces: list[dict[str, Any]],
    *,
    interface_id: str | None,
    feature_id: str | None,
) -> dict[str, Any] | None:
    if interface_id:
        for interface in interfaces:
            if interface.get("id") == interface_id:
                return interface
    if feature_id:
        for interface in interfaces:
            feature_ids = interface.get("feature_ids", [])
            if isinstance(feature_ids, list) and feature_id in feature_ids:
                return interface
    return None


def _make_cae_mapped_interface(
    *,
    feature_id: str,
    feature: dict[str, Any],
    protected_region: dict[str, Any] | None,
) -> dict[str, Any]:
    topo_faces, topo_edges = _topology_refs_from_feature(feature)
    allowed_operations = []
    forbidden_operations = []
    if protected_region is not None:
        allowed_operations = list(protected_region.get("allowed_operations", []))
        forbidden_operations = list(protected_region.get("forbidden_operations", []))

    return {
        "id": f"iface_{_slug(feature_id)}",
        "type": "cae_mapped_interface",
        "feature_ids": [feature_id],
        "topology_refs": {
            "faces": topo_faces,
            "edges": topo_edges,
        },
        "roles": ["cae_mapped_feature_interface"],
        "protected": protected_region is not None,
        "constraint_refs": [],
        "simulation_refs": [],
        "visual_refs": [],
        "allowed_operations": sorted(set(allowed_operations)),
        "forbidden_operations": sorted(set(forbidden_operations)),
        "status": "candidate_from_cae_mapping",
        "notes": [
            "Interface was conservatively created from an explicit CAE mapping to a feature.",
            "No automatic CAE-to-feature inference or engineering certification is implied.",
        ],
    }


def _cae_ref_from_mapping(mapping: dict[str, Any]) -> dict[str, Any] | None:
    cae_entity = mapping.get("cae_entity")
    cae_type = mapping.get("cae_type")
    mapping_status = mapping.get("mapping_status")
    mapping_method = mapping.get("mapping_method")
    confidence = mapping.get("confidence")
    maps_to = mapping.get("maps_to")
    if not all(isinstance(item, str) and item for item in (cae_entity, cae_type, mapping_status, mapping_method, confidence)):
        return None
    if not isinstance(maps_to, dict):
        return None

    clean_maps_to = {
        key: value
        for key, value in maps_to.items()
        if key in {"feature_id", "interface_id"} and isinstance(value, str) and value
    }
    if not clean_maps_to:
        return None

    return {
        "cae_entity": cae_entity,
        "cae_type": cae_type,
        "source_file": _CAE_MAPPING_PATH,
        "mapping_status": mapping_status,
        "mapping_method": mapping_method,
        "confidence": confidence,
        "maps_to": clean_maps_to,
    }


def _add_unique_cae_ref(interface: dict[str, Any], ref: dict[str, Any]) -> None:
    refs = interface.setdefault("cae_refs", [])
    if not isinstance(refs, list):
        refs = []
        interface["cae_refs"] = refs
    key = json.dumps(ref, sort_keys=True)
    existing = {json.dumps(item, sort_keys=True) for item in refs if isinstance(item, dict)}
    if key not in existing:
        refs.append(ref)
    refs.sort(key=lambda item: (str(item.get("cae_entity", "")), str(item.get("cae_type", ""))))


def _cae_role(cae_type: Any) -> str | None:
    if cae_type == "boundary_condition_target":
        return "cae_boundary_condition_target"
    if cae_type == "load_target":
        return "cae_load_target"
    return None


def _feature_map(feature_graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    features = feature_graph.get("features", [])
    if not isinstance(features, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, dict):
            continue
        feature_id = feature.get("id")
        if isinstance(feature_id, str) and feature_id:
            result[feature_id] = feature
    return result


def _is_mounting_interface_candidate(feature: dict[str, Any]) -> bool:
    if feature.get("type") == "mounting_hole_pattern":
        return True

    intent = feature.get("intent")
    if isinstance(intent, dict):
        role = intent.get("role")
        if isinstance(role, str):
            return role == "mounting_interface_candidate"
        if isinstance(role, list):
            return any(item == "mounting_interface_candidate" for item in role)

    return False


def _interface_type(*, mounting_candidate: bool, has_fixed: bool, has_load: bool, has_protected: bool) -> str:
    if mounting_candidate:
        return "mounting_interface"
    if has_fixed:
        return "fixed_support_interface"
    if has_load:
        return "load_interface"
    if has_protected:
        return "protected_external_interface"
    return "context_interface"


def _topology_refs_from_feature(feature: dict[str, Any]) -> tuple[list[str], list[str]]:
    refs = feature.get("geometry_refs")
    if isinstance(refs, list):
        return ([item for item in refs if isinstance(item, str)], [])
    if isinstance(refs, dict):
        faces = [item for item in refs.get("faces", []) if isinstance(item, str)]
        edges = [item for item in refs.get("edges", []) if isinstance(item, str)]
        entities = [item for item in refs.get("entities", []) if isinstance(item, str)]
        # Keep backwards compatibility with entity-only refs by treating them as face-like refs.
        return (sorted(set(faces + entities)), sorted(set(edges)))
    return ([], [])


def _protected_region_by_feature(protected_regions: Any | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(protected_regions, dict):
        return result
    regions = protected_regions.get("protected_regions")
    if not isinstance(regions, list):
        return result
    for region in regions:
        if not isinstance(region, dict):
            continue
        feature_id = region.get("feature_id")
        if isinstance(feature_id, str) and feature_id:
            result[feature_id] = region
    return result


def _constraint_refs_by_feature(constraints: Any | None) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    if not isinstance(constraints, dict):
        return refs
    items = constraints.get("constraints")
    if not isinstance(items, list):
        return refs
    for constraint in items:
        if not isinstance(constraint, dict):
            continue
        constraint_id = constraint.get("id")
        target = constraint.get("target")
        constraint_type = constraint.get("type")
        if not isinstance(constraint_id, str) or not constraint_id:
            continue
        if not isinstance(target, str) or not target:
            continue

        is_interface_constraint = False
        if isinstance(constraint_type, str):
            is_interface_constraint = (
                constraint_type in _PROTECTION_CONSTRAINT_TYPES
                or "protect" in constraint_type
                or "interface" in constraint_type
            )
        if not is_interface_constraint:
            continue

        refs.setdefault(target, []).append(constraint_id)

    return refs


def _simulation_refs_by_feature(simulation_setup: Any | None) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    fixed: dict[str, list[str]] = {}
    loads: dict[str, list[str]] = {}
    if not isinstance(simulation_setup, dict):
        return fixed, loads

    for bc in simulation_setup.get("boundary_conditions", []) or []:
        if not isinstance(bc, dict):
            continue
        if bc.get("type") != "fixed":
            continue
        bc_id = bc.get("id")
        target = bc.get("target_feature")
        if isinstance(bc_id, str) and bc_id and isinstance(target, str) and target:
            fixed.setdefault(target, []).append(bc_id)

    for load in simulation_setup.get("loads", []) or []:
        if not isinstance(load, dict):
            continue
        load_id = load.get("id")
        target = load.get("target_feature")
        if isinstance(load_id, str) and load_id and isinstance(target, str) and target:
            loads.setdefault(target, []).append(load_id)

    return fixed, loads


def _visual_refs_by_feature(annotation_layers: Any | None) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    if not isinstance(annotation_layers, dict):
        return refs
    layers = annotation_layers.get("layers")
    if not isinstance(layers, list):
        return refs

    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for item in layer.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            ann_id = item.get("id")
            feature_id = item.get("feature_id")
            if isinstance(ann_id, str) and ann_id and isinstance(feature_id, str) and feature_id:
                refs.setdefault(feature_id, []).append(ann_id)

    return refs


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return slug or "unknown"


def _read_optional_json(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    try:
        return json.loads(package.read(member))
    except Exception:
        return None


def _read_optional_yaml(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    try:
        return yaml.safe_load(package.read(member))
    except Exception:
        return None


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    skip = {"manifest.json", INTERFACE_GRAPH_PATH}
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_interface_graph(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    interface_graph: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    object_resources = resources.setdefault("objects", {})
    if not isinstance(object_resources, dict):
        raise ValueError("manifest resources.objects must be an object")
    object_resources["interface_graph"] = INTERFACE_GRAPH_PATH

    interface_json = json.dumps(interface_graph, indent=2, sort_keys=True) + "\n"
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    existing_filenames = {info.filename for info, _ in existing_members}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            if OBJECTS_DIR not in existing_filenames:
                out_package.writestr(OBJECTS_DIR, b"")
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(INTERFACE_GRAPH_PATH, interface_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
