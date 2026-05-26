from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION, __version__

ALLOWED_OPERATIONS_CATALOG_PATH = "graph/allowed_operations_catalog.json"
FEATURE_GRAPH_PATH = "graph/feature_graph.json"
PROTECTED_REGIONS_PATH = "ai/protected_regions.json"
CONSTRAINTS_PATH = "graph/constraints.json"
INTERFACE_GRAPH_PATH = "objects/interface_graph.json"

_OPERATION_TYPES = (
    "modify_parameter",
    "add_feature",
    "remove_feature",
    "protect_feature",
    "assign_material",
    "assign_boundary_condition",
    "assign_load",
)


def build_allowed_operations_catalog_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
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
            if FEATURE_GRAPH_PATH not in names:
                raise FileNotFoundError(
                    "graph/feature_graph.json missing; build-allowed-operations-catalog requires feature graph"
                )
            if ALLOWED_OPERATIONS_CATALOG_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{ALLOWED_OPERATIONS_CATALOG_PATH} already exists; use --overwrite to replace it"
                )

            manifest = json.loads(package.read("manifest.json"))
            feature_graph = json.loads(package.read(FEATURE_GRAPH_PATH))
            protected_regions = _read_optional_json(package, PROTECTED_REGIONS_PATH)
            constraints = _read_optional_json(package, CONSTRAINTS_PATH)
            interface_graph = _read_optional_json(package, INTERFACE_GRAPH_PATH)
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    catalog = _build_catalog(
        names=names,
        feature_graph=feature_graph,
        protected_regions=protected_regions,
        constraints=constraints,
        interface_graph=interface_graph,
    )
    _rewrite_package_with_catalog(path, existing_members, manifest, catalog)
    return path


def _build_catalog(
    *,
    names: set[str],
    feature_graph: dict[str, Any],
    protected_regions: Any | None,
    constraints: Any | None,
    interface_graph: Any | None,
) -> dict[str, Any]:
    features = feature_graph.get("features") if isinstance(feature_graph, dict) else None
    if not isinstance(features, list):
        raise ValueError("graph/feature_graph.json features must be an array")

    protected_ids = _protected_feature_ids(protected_regions)
    constraint_refs = _constraint_ids_by_feature(constraints)
    interface_roles = _interface_roles_by_feature(interface_graph)

    entries: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("id"), str):
            continue
        feature_id = feature["id"]
        feature_type = str(feature.get("type") or "unknown_feature")
        protected = feature_id in protected_ids
        blocked_constraints = sorted(constraint_refs.get(feature_id, set()))
        feature_interface_roles = sorted(interface_roles.get(feature_id, set()))
        editability = feature.get("editability")

        operations: list[dict[str, Any]] = []
        for op_type in _OPERATION_TYPES:
            status, reason = _operation_status(op_type, protected)
            preconditions: list[str] = []
            if op_type == "modify_parameter" and status != "forbidden":
                if editability == "executable_by_regeneration":
                    preconditions.append("requires regeneration-backed writeback flow")
                else:
                    preconditions.append("semantic-only update; does not imply CAD geometry writeback")
            if op_type == "assign_boundary_condition":
                if "fixed_support_interface" in feature_interface_roles:
                    preconditions.append("feature appears in fixed_support_interface role")
                else:
                    preconditions.append("define explicit target mapping for boundary-condition assignment")
            if op_type == "assign_load":
                if "load_application_interface" in feature_interface_roles:
                    preconditions.append("feature appears in load_application_interface role")
                else:
                    preconditions.append("define explicit target mapping for load assignment")
            operations.append(
                {
                    "operation_type": op_type,
                    "status": status,
                    "reason": reason,
                    "preconditions": preconditions,
                    "blocked_by_constraints": blocked_constraints,
                }
            )

        entries.append(
            {
                "feature_id": feature_id,
                "feature_type": feature_type,
                "protected": protected,
                "interface_roles": feature_interface_roles,
                "operations": operations,
            }
        )

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "format_version": FORMAT_VERSION,
        "catalog_id": "allowed_operations_catalog_001",
        "generated_by": f"aieng {__version__}",
        "generated_at_utc": now,
        "source_files": [
            path
            for path in (FEATURE_GRAPH_PATH, PROTECTED_REGIONS_PATH, CONSTRAINTS_PATH, INTERFACE_GRAPH_PATH)
            if path in names
        ],
        "feature_operations": sorted(entries, key=lambda item: item["feature_id"]),
        "notes": [
            "Catalog is generated from structured resources and is policy guidance for patch planning.",
            "Catalog does not execute CAD/CAE operations by itself.",
        ],
    }


def _operation_status(operation_type: str, protected: bool) -> tuple[str, str]:
    if operation_type == "protect_feature":
        return "allowed", "Protection metadata updates are always admissible."
    if protected and operation_type in {"modify_parameter", "remove_feature"}:
        return "forbidden", "Protected regions block geometry-affecting operations on this feature."
    if operation_type in {"assign_material", "assign_boundary_condition", "assign_load", "add_feature", "remove_feature"}:
        return "conditional", "Requires explicit engineering context, constraint checks, and validation plan."
    return "allowed", "Operation is admissible subject to normal schema and policy checks."


def _protected_feature_ids(protected_regions: Any | None) -> set[str]:
    if not isinstance(protected_regions, dict):
        return set()
    regions = protected_regions.get("protected_regions")
    if not isinstance(regions, list):
        return set()
    return {
        region["feature_id"]
        for region in regions
        if isinstance(region, dict) and isinstance(region.get("feature_id"), str)
    }


def _constraint_ids_by_feature(constraints: Any | None) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    if not isinstance(constraints, dict):
        return result
    constraint_items = constraints.get("constraints")
    if not isinstance(constraint_items, list):
        return result
    for item in constraint_items:
        if not isinstance(item, dict):
            continue
        target = item.get("target")
        cid = item.get("id")
        if isinstance(target, str) and isinstance(cid, str):
            result.setdefault(target, set()).add(cid)
    return result


def _interface_roles_by_feature(interface_graph: Any | None) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    if not isinstance(interface_graph, dict):
        return result
    interfaces = interface_graph.get("interfaces")
    if not isinstance(interfaces, list):
        return result

    for interface in interfaces:
        if not isinstance(interface, dict):
            continue
        feature_ids = interface.get("feature_ids")
        roles = interface.get("roles")
        if not isinstance(feature_ids, list) or not isinstance(roles, list):
            continue
        role_set = {role for role in roles if isinstance(role, str) and role}
        if not role_set:
            continue
        for feature_id in feature_ids:
            if isinstance(feature_id, str) and feature_id:
                result.setdefault(feature_id, set()).update(role_set)
    return result


def _read_optional_json(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    try:
        return json.loads(package.read(member))
    except Exception:
        return None


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    seen: set[str] = set()
    for info in package.infolist():
        if info.filename in {"manifest.json", ALLOWED_OPERATIONS_CATALOG_PATH} or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_catalog(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    catalog: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    graph_resources = resources.setdefault("graph", {})
    if not isinstance(graph_resources, dict):
        raise ValueError("manifest resources.graph must be an object")
    graph_resources["allowed_operations_catalog"] = ALLOWED_OPERATIONS_CATALOG_PATH

    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    catalog_json = json.dumps(catalog, indent=2, sort_keys=True) + "\n"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as handle:
        tmp_path = Path(handle.name)

    try:
        with zipfile.ZipFile(tmp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out:
            for info, data in existing_members:
                out.writestr(info, data)
            out.writestr("manifest.json", manifest_json)
            out.writestr(ALLOWED_OPERATIONS_CATALOG_PATH, catalog_json)
        shutil.move(str(tmp_path), path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
