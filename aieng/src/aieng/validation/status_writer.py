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

STATUS_PATH = "validation/status.yaml"
VALIDATION_DIR = "validation/"

_SIMULATION_SETUP_PATH = "simulation/setup.yaml"
_TOPOLOGY_MAP_PATH = "geometry/topology_map.json"
_AAG_PATH = "graph/aag.json"
_FEATURE_GRAPH_PATH = "graph/feature_graph.json"
_CONSTRAINTS_PATH = "graph/constraints.json"
_PROTECTED_REGIONS_PATH = "ai/protected_regions.json"
_CAE_MAPPING_PATH = "simulation/cae_mapping.json"
_CAE_PARSED_BCS_PATH = "simulation/cae_imports/parsed_boundary_conditions.json"
_CAE_PARSED_LOADS_PATH = "simulation/cae_imports/parsed_loads.json"
_INTERFACE_GRAPH_PATH = "objects/interface_graph.json"

ALLOWED_CLAIMS = [
    "The package contains structured engineering context.",
    "The package contains candidate feature graph data.",
    "The package contains simulation intent.",
    "Patch proposals are unexecuted suggestions.",
    "Solver deck is a scaffold if present.",
    "Topology was parsed from STEP by an experimental backend, if topology metadata confirms real_step_parsing.",
]

FORBIDDEN_CLAIMS = [
    "The design is safe.",
    "The stress target is satisfied.",
    "A mesh has been generated.",
    "A solver has been run.",
    "The patch has been applied.",
    "Manufacturing feasibility has been validated.",
    "Feature labels are confirmed engineering truth.",
]


def update_validation_status_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
    extra_status: dict[str, Any] | None = None,
) -> Path:
    """Generate validation/status.yaml for an existing .aieng package."""
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
            if STATUS_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{STATUS_PATH} already exists; use --overwrite to replace it"
                )
            manifest = json.loads(package.read("manifest.json"))
            existing_members = _read_existing_members(package)
            topology_metadata = _read_topology_metadata(package, names)
            aag_data = _read_optional_json(package, _AAG_PATH)
            cae_mapping = _read_optional_json(package, _CAE_MAPPING_PATH)
            interface_graph = _read_optional_json(package, _INTERFACE_GRAPH_PATH)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {package_file}") from exc

    status = _build_status(
        manifest,
        names,
        topology_metadata=topology_metadata,
        aag_data=aag_data,
        cae_mapping=cae_mapping,
        interface_graph=interface_graph,
        extra_status=extra_status,
    )
    status_yaml = yaml.safe_dump(status, sort_keys=False, allow_unicode=True)
    _rewrite_package_with_status(package_file, existing_members, manifest, status_yaml)
    return package_file


def _build_status(
    manifest: dict[str, Any],
    names: set[str],
    *,
    topology_metadata: dict[str, Any] | None = None,
    aag_data: dict[str, Any] | None = None,
    cae_mapping: dict[str, Any] | None = None,
    interface_graph: dict[str, Any] | None = None,
    extra_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model_id = manifest.get("model_id", "unknown_model")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # Determine what resources are present
    has_source_step = "geometry/source.step" in names
    has_normalized_step = "geometry/normalized.step" in names
    has_topology = _TOPOLOGY_MAP_PATH in names
    has_aag = _AAG_PATH in names
    has_feature_graph = _FEATURE_GRAPH_PATH in names
    has_constraints = _CONSTRAINTS_PATH in names
    has_setup = _SIMULATION_SETUP_PATH in names
    has_protected_regions = _PROTECTED_REGIONS_PATH in names
    has_solver_deck = "simulation/solver_deck.inp" in names

    # Detect patch proposals from manifest resources
    manifest_resource_paths = _resource_paths(manifest.get("resources", {}))
    patch_paths = [p for p in manifest_resource_paths if p.startswith("ai/patches/") and p.endswith(".json")]
    has_patches = len(patch_paths) > 0 and any(p in names for p in patch_paths)

    has_any_context = has_constraints or has_setup or has_protected_regions
    has_visual_index = "visual/annotation_layers.json" in names
    has_visual_manifest = "visual/model_manifest.json" in names
    has_object_registry = "objects/object_registry.json" in names
    has_interface_graph = "objects/interface_graph.json" in names
    has_cae_source_deck = "simulation/cae_imports/source_solver_deck.inp" in names
    has_cae_mapping = _CAE_MAPPING_PATH in names

    cae_mapping_status = "not_imported"
    cae_mapping_method = "none"
    if has_cae_mapping:
        try:
            mapping_doc = cae_mapping if isinstance(cae_mapping, dict) else {}
            mapped_count = int(mapping_doc.get("mapping_summary", {}).get("mapped_count", 0))
            unmapped_count = int(mapping_doc.get("mapping_summary", {}).get("unmapped_count", 0))
            if mapped_count > 0 and unmapped_count > 0:
                cae_mapping_status = "imported_partially_mapped"
            elif mapped_count > 0:
                cae_mapping_status = "imported_mapped"
            else:
                cae_mapping_status = "imported_unmapped"

            mappings = mapping_doc.get("mappings")
            methods = {
                item.get("mapping_method")
                for item in mappings
                if isinstance(item, dict) and item.get("mapping_status") in {"mapped", "partially_mapped"}
            } if isinstance(mappings, list) else set()
            if methods == {"user_provided"} and methods:
                cae_mapping_method = "user_provided"
            elif methods:
                cae_mapping_method = "mixed"
        except Exception:
            cae_mapping_status = "imported_unmapped"

    interface_graph_has_cae_refs = _interface_graph_has_cae_refs(interface_graph)
    cae_interface_mapping_status = "none"
    if has_cae_mapping and interface_graph_has_cae_refs:
        cae_interface_mapping_status = "mapped"
    elif has_cae_mapping and cae_mapping_status == "imported_partially_mapped":
        cae_interface_mapping_status = "partially_mapped"

    status = {
        "generated_by": f"aieng {__version__}",
        "model_id": model_id,
        "package_format_version": FORMAT_VERSION,
        "generated_at": now,
        "package_validation": {
            "package_resources_present": True,
            "manifest_present": True,
            "structured_resources_validated": "structurally_checked",
        },
        "geometry_status": {
            "source_geometry_present": has_source_step,
            "normalized_geometry_present": has_normalized_step,
            "real_geometry_parsing": "not_run",
            "real_geometry_validity": "not_run",
            "reason": (
                "No real CAD kernel validation in current phase. "
                "STEP content is not parsed."
            ),
        },
        "topology_status": _build_topology_status(has_topology, topology_metadata, has_aag, aag_data),
        "feature_status": {
            "feature_graph_present": has_feature_graph,
            "recognition_mode": "rule_based" if has_feature_graph else "none",
            "status": "candidate_only" if has_feature_graph else "not_generated",
            "warning": (
                "Feature labels are candidates, not confirmed engineering truth."
                if has_feature_graph
                else "Feature graph has not been generated."
            ),
        },
        "engineering_context_status": {
            "context_source": "user_provided" if has_any_context else "not_provided",
            "status": "structured_context_present" if has_any_context else "not_present",
            "protected_regions_present": has_protected_regions,
            "simulation_intent_present": has_setup,
            "solver_deck_scaffold_present": has_solver_deck,
        },
        "solver_mesh_status": {
            "mesh_generation": "not_run",
            "solver_execution": "not_run",
            "stress_validation": "not_validated",
            "displacement_validation": "not_validated",
            "manufacturing_validation": "not_run",
        },
        "cae_import_status": {
            "cae_import_present": has_cae_source_deck,
            "cae_mapping_status": cae_mapping_status,
            "cae_mapping_method": cae_mapping_method,
            "cae_solver_execution": "not_run",
            "cae_results_imported": False,
            "parsed_boundary_conditions_present": _CAE_PARSED_BCS_PATH in names,
            "parsed_loads_present": _CAE_PARSED_LOADS_PATH in names,
            "updated_deck_exported": "simulation/updated_deck.inp" in names,
            "updated_deck_path": "simulation/updated_deck.inp" if "simulation/updated_deck.inp" in names else None,
        },
        "patch_status": {
            "patch_proposals_present": has_patches,
            "patch_execution": "not_run",
            "geometry_modified_by_patch": False,
            "solver_run_for_patch": False,
            "patch_validation_required": has_patches,
        },
        "visual_status": {
            "visual_index_present": has_visual_index,
            "annotation_layers_present": has_visual_index,
            "visual_manifest_present": has_visual_manifest,
            "rendered_geometry_present": False,
            "visual_rendering": "not_generated",
            "reason": (
                "Visual resources are scaffolds only in Phase 8B. "
                "No rendering, glTF, image, or 3D geometry visualization has been performed."
            ),
        },
        "object_registry_status": {
            "object_registry_present": has_object_registry,
            "registry_is_source_of_truth": False,
            "reason": (
                "Object registry is a generated navigation index only. "
                "Structured source JSON/YAML files remain authoritative."
            ),
        },
        "interface_graph_status": {
            "interface_graph_present": has_interface_graph,
            "interface_graph_source_of_truth": False,
            "interface_graph_has_cae_refs": interface_graph_has_cae_refs,
            "cae_interface_mapping_status": cae_interface_mapping_status,
            "reason": (
                "Interface graph is a generated index derived from structured context. "
                "Feature graph, constraints, protected regions, simulation setup, visual annotations, and explicit CAE mappings remain authoritative."
            ),
        },
        "claim_policy": {
            "allowed_claims": list(ALLOWED_CLAIMS),
            "forbidden_claims": list(FORBIDDEN_CLAIMS),
        },
    }
    if extra_status:
        status.update(extra_status)
    return status


def _interface_graph_has_cae_refs(interface_graph: Any | None) -> bool:
    if not isinstance(interface_graph, dict):
        return False
    interfaces = interface_graph.get("interfaces")
    if not isinstance(interfaces, list):
        return False
    for interface in interfaces:
        if not isinstance(interface, dict):
            continue
        refs = interface.get("cae_refs")
        if isinstance(refs, list) and any(isinstance(ref, dict) for ref in refs):
            return True
    return False


def _read_topology_metadata(
    package: zipfile.ZipFile, names: set[str]
) -> dict[str, Any] | None:
    """Read metadata from topology_map.json without raising on malformed content."""
    if _TOPOLOGY_MAP_PATH not in names:
        return None
    try:
        data = json.loads(package.read(_TOPOLOGY_MAP_PATH))
        if isinstance(data, dict):
            meta = data.get("metadata")
            return meta if isinstance(meta, dict) else None
    except Exception:
        pass
    return None


def _read_optional_json(package: zipfile.ZipFile, member: str) -> dict[str, Any] | None:
    if member not in set(package.namelist()):
        return None
    try:
        data = json.loads(package.read(member))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _build_topology_status(
    has_topology: bool,
    metadata: dict[str, Any] | None,
    has_aag: bool,
    aag_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the topology_status section, branching on real vs mock extraction."""
    if not has_topology:
        return {
            "topology_map_present": False,
            "aag_present": has_aag,
            "extraction_mode": "none",
            "status": "not_generated",
            "warning": "Topology map has not been generated.",
        }

    aag_evidence = "not_generated"
    if has_aag and isinstance(aag_data, dict):
        generation_method = aag_data.get("generation_method")
        if isinstance(generation_method, dict) and isinstance(generation_method.get("adjacency_evidence"), str):
            aag_evidence = generation_method["adjacency_evidence"]
        else:
            aag_evidence = "unknown"

    # Detect experimental real extraction: occ backend + real_step_parsing: true
    if (
        isinstance(metadata, dict)
        and metadata.get("extraction_backend") == "occ"
        and metadata.get("real_step_parsing") is True
    ):
        result: dict[str, Any] = {
            "topology_map_present": True,
            "aag_present": has_aag,
            "aag_adjacency_evidence": aag_evidence,
            "extraction_mode": "parsed_from_step",
            "extraction_backend": "occ",
            "real_step_parsing": True,
            "status": "experimental_real_extraction",
            "warning": (
                "Topology was parsed from STEP using an experimental OCP backend. "
                "Geometry fidelity has not been independently established and remains review-required. "
                "Feature recognition remains separate and rule-based."
            ),
        }
        if isinstance(metadata.get("runtime_provider"), str):
            result["runtime_provider"] = metadata["runtime_provider"]
        return result

    # Default: mock (or any unrecognised backend without real_step_parsing)
    return {
        "topology_map_present": True,
        "aag_present": has_aag,
        "aag_adjacency_evidence": aag_evidence,
        "extraction_mode": "mock",
        "status": "mock_generated",
        "warning": "Topology map is deterministic mock data and not parsed from STEP content.",
    }


def _resource_paths(resources: Any) -> list[str]:
    paths: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            paths.append(value)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(resources)
    return paths


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    skip = {"manifest.json", STATUS_PATH}
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_status(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    status_yaml: str,
) -> None:
    resources = manifest.setdefault("resources", {})
    validation_resources = resources.setdefault("validation", {})
    if not isinstance(validation_resources, dict):
        raise ValueError("manifest resources.validation must be an object")
    validation_resources["status"] = STATUS_PATH

    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    # Ensure validation/ directory entry is present in the archive
    existing_filenames = {info.filename for info, _ in existing_members}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            if VALIDATION_DIR not in existing_filenames:
                out_package.writestr(VALIDATION_DIR, b"")
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(STATUS_PATH, status_yaml)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
