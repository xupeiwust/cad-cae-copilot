from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from aieng import FORMAT_VERSION

ANNOTATION_LAYERS_PATH = "visual/annotation_layers.json"
VISUAL_DIR = "visual/"
ANNOTATION_FORMAT = "aieng.visual_annotation_layers"

_FEATURE_GRAPH_PATH = "graph/feature_graph.json"
_TOPOLOGY_MAP_PATH = "geometry/topology_map.json"
_PROTECTED_REGIONS_PATH = "ai/protected_regions.json"
_CONSTRAINTS_PATH = "graph/constraints.json"
_SIMULATION_SETUP_PATH = "simulation/setup.yaml"


def build_visual_index_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write visual/annotation_layers.json to an existing .aieng package."""
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
                    f"{_FEATURE_GRAPH_PATH} missing; "
                    "build-visual-index requires graph/feature_graph.json — "
                    "run aieng recognize-features first"
                )
            if ANNOTATION_LAYERS_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{ANNOTATION_LAYERS_PATH} already exists; use --overwrite to replace it"
                )

            manifest = json.loads(package.read("manifest.json"))
            feature_graph = json.loads(package.read(_FEATURE_GRAPH_PATH))
            topology_map = _read_optional_json(package, _TOPOLOGY_MAP_PATH)
            protected_regions = _read_optional_json(package, _PROTECTED_REGIONS_PATH)
            simulation_setup = _read_optional_yaml(package, _SIMULATION_SETUP_PATH)
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    source_files = _build_source_files(names)
    layers = _build_layers(feature_graph, topology_map, protected_regions, simulation_setup)
    annotation_layers = {
        "format": ANNOTATION_FORMAT,
        "format_version": FORMAT_VERSION,
        "source_files": source_files,
        "layers": layers,
    }

    _rewrite_package_with_annotation_layers(path, existing_members, manifest, annotation_layers)
    return path


# ---------------------------------------------------------------------------
# Source file index
# ---------------------------------------------------------------------------

def _build_source_files(names: set[str]) -> list[str]:
    candidates = [
        _FEATURE_GRAPH_PATH,
        _TOPOLOGY_MAP_PATH,
        _PROTECTED_REGIONS_PATH,
        _CONSTRAINTS_PATH,
        _SIMULATION_SETUP_PATH,
    ]
    return [path for path in candidates if path in names]


# ---------------------------------------------------------------------------
# Layer builders
# ---------------------------------------------------------------------------

def _build_layers(
    feature_graph: dict[str, Any],
    topology_map: Any | None,
    protected_regions: Any | None,
    simulation_setup: Any | None,
) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []

    features_layer = _build_features_layer(feature_graph)
    if features_layer["items"]:
        layers.append(features_layer)

    protected_layer = _build_protected_layer(protected_regions)
    if protected_layer["items"]:
        layers.append(protected_layer)

    sim_layer = _build_simulation_targets_layer(simulation_setup)
    if sim_layer["items"]:
        layers.append(sim_layer)

    unknown_layer = _build_unknown_layer(feature_graph)
    if unknown_layer["items"]:
        layers.append(unknown_layer)

    return layers


def _annotation_id(prefix: str, feature_id: str) -> str:
    base = feature_id[5:] if feature_id.startswith("feat_") else feature_id
    return f"ann_{prefix}_{base}"


def _topology_refs_from_feature(feature: dict[str, Any]) -> dict[str, list[str]]:
    refs = feature.get("geometry_refs", {})
    if isinstance(refs, list):
        return {"faces": [r for r in refs if isinstance(r, str)], "edges": []}
    if isinstance(refs, dict):
        return {
            "faces": [r for r in refs.get("faces", []) if isinstance(r, str)],
            "edges": [r for r in refs.get("edges", []) if isinstance(r, str)],
        }
    return {"faces": [], "edges": []}


def _build_features_layer(feature_graph: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for feature in feature_graph.get("features", []):
        if not isinstance(feature, dict):
            continue
        feature_id = feature.get("id", "")
        feature_type = feature.get("type", "unknown_type")
        name = feature.get("name", "Unnamed feature")
        topology_refs = _topology_refs_from_feature(feature)

        item: dict[str, Any] = {
            "id": _annotation_id("feat", feature_id),
            "feature_id": feature_id,
            "label": name,
            "feature_type": feature_type,
            "topology_refs": topology_refs,
            "visual_role": "candidate_feature",
            "status": "candidate",
            "notes": ["Feature recognition is rule-based and candidate-only."],
        }
        items.append(item)

    return {"id": "features", "name": "Feature annotations", "items": items}


def _build_protected_layer(protected_regions: Any | None) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    if isinstance(protected_regions, dict):
        for region in protected_regions.get("protected_regions", []):
            if not isinstance(region, dict):
                continue
            feature_id = region.get("feature_id", "")
            item: dict[str, Any] = {
                "id": _annotation_id("prot", feature_id),
                "feature_id": feature_id,
                "label": f"Protected: {feature_id}",
                "visual_role": "protected_region",
                "status": "protected",
                "forbidden_operations": list(region.get("forbidden_operations", [])),
                "allowed_operations": list(region.get("allowed_operations", [])),
                "reason": region.get("reason", ""),
            }
            items.append(item)

    return {"id": "protected_regions", "name": "Protected region annotations", "items": items}


def _build_simulation_targets_layer(simulation_setup: Any | None) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    if isinstance(simulation_setup, dict):
        for index, bc in enumerate(simulation_setup.get("boundary_conditions", []) or []):
            if not isinstance(bc, dict):
                continue
            target_feature = bc.get("target_feature", "")
            if not target_feature:
                continue
            bc_id = bc.get("id", f"bc_{index}")
            item: dict[str, Any] = {
                "id": f"ann_sim_bc_{bc_id}",
                "feature_id": target_feature,
                "label": f"Fixed support candidate: {target_feature}",
                "visual_role": "simulation_context",
                "status": "candidate",
                "simulation_type": "boundary_condition",
                "simulation_id": bc_id,
            }
            items.append(item)

        for index, load in enumerate(simulation_setup.get("loads", []) or []):
            if not isinstance(load, dict):
                continue
            target_feature = load.get("target_feature", "")
            if not target_feature:
                continue
            load_id = load.get("id", f"load_{index}")
            load_type = load.get("type", "force")
            item = {
                "id": f"ann_sim_load_{load_id}",
                "feature_id": target_feature,
                "label": f"{load_type.capitalize()} load candidate: {target_feature}",
                "visual_role": "simulation_context",
                "status": "candidate",
                "simulation_type": "load",
                "simulation_id": load_id,
            }
            items.append(item)

    return {"id": "simulation_targets", "name": "Simulation target annotations", "items": items}


def _build_unknown_layer(feature_graph: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for feature in feature_graph.get("features", []):
        if not isinstance(feature, dict):
            continue
        if feature.get("type") != "unknown_feature":
            continue
        feature_id = feature.get("id", "")
        name = feature.get("name", "Unknown feature")
        topology_refs = _topology_refs_from_feature(feature)
        item: dict[str, Any] = {
            "id": _annotation_id("unk", feature_id),
            "feature_id": feature_id,
            "label": f"Unclassified geometry: {name}",
            "feature_type": "unknown_feature",
            "topology_refs": topology_refs,
            "visual_role": "unclassified_geometry",
            "status": "unknown",
            "notes": [
                "Engineering meaning is not known.",
                "Feature recognition is rule-based and candidate-only.",
            ],
        }
        items.append(item)

    return {
        "id": "unknown_or_unclassified",
        "name": "Unknown and unclassified geometry annotations",
        "items": items,
    }


# ---------------------------------------------------------------------------
# Zip helpers
# ---------------------------------------------------------------------------

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
    skip = {"manifest.json", ANNOTATION_LAYERS_PATH}
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_annotation_layers(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    annotation_layers: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    visual_resources = resources.setdefault("visual", {})
    if not isinstance(visual_resources, dict):
        raise ValueError("manifest resources.visual must be an object")
    visual_resources["annotation_layers"] = ANNOTATION_LAYERS_PATH

    annotation_json = json.dumps(annotation_layers, indent=2, sort_keys=True) + "\n"
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    existing_filenames = {info.filename for info, _ in existing_members}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            if VISUAL_DIR not in existing_filenames:
                out_package.writestr(VISUAL_DIR, b"")
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(ANNOTATION_LAYERS_PATH, annotation_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
