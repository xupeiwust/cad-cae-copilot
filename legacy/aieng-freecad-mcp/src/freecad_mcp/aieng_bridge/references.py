"""Geometry reference and CAE target mapping scaffold.

Rules:
- Reference mapping is traceability evidence, not engineering validation.
- Mappings may need review after geometry changes.
- BC/load transfer is not guaranteed after geometry modification.
- No claims are advanced by reference mapping.
- Never modify claim_map.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from freecad_mcp.aieng_bridge.context import load_aieng_context
from freecad_mcp.aieng_bridge.persistence import _atomic_write_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class GeometryReference(BaseModel):
    """Mapping between a semantic feature/interface and geometric entities."""

    model_config = ConfigDict(extra="forbid")

    ref_id: str
    feature_id: str | None = None
    interface_id: str | None = None
    freecad_object_name: str | None = None
    freecad_subshape_ref: str | None = None
    step_entity_ref: str | None = None
    topology_id: str | None = None
    role: str | None = None
    mapping_method: Literal[
        "user_provided", "freecad_object_name", "freecad_subshape",
        "step_entity", "heuristic", "unresolved"
    ] = "unresolved"
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
    status: Literal["valid", "needs_review", "unresolved", "unsupported"] = "unresolved"
    warnings: list[str] = []


class CaeTargetReference(BaseModel):
    """Mapping between a CAE target and geometric/feature references."""

    model_config = ConfigDict(extra="forbid")

    target_id: str
    target_name: str | None = None
    target_type: Literal["boundary_condition", "load", "mesh_region", "result_region", "unknown"] = "unknown"
    feature_id: str | None = None
    interface_id: str | None = None
    geometry_ref_id: str | None = None
    source: str | None = None
    mapping_method: str = "unresolved"
    confidence: str = "unknown"
    status: str = "unresolved"
    warnings: list[str] = []


class ReferenceMap(BaseModel):
    """Collection of geometry and CAE target references."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    package_path: str | None = None
    geometry_references: list[GeometryReference] = []
    cae_targets: list[CaeTargetReference] = []
    generated_at: str = Field(default_factory=utc_now_iso)
    producer: str = "freecad_mcp"
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_reference_map(package_path: str) -> ReferenceMap:
    """Build a reference map from available .aieng resources.

    Sources (in order of preference):
    - feature_graph.json → geometry references via freecad_object_name
    - constraints.json → protected region / interface references
    - simulation/setup.yaml → CAE targets (BCs, loads, mesh regions)
    - simulation/cae_mapping.json → explicit user_provided mappings
    - objects/interface_graph.json → interface definitions
    - visual/annotation_layers.json → annotation references
    """
    context = load_aieng_context(package_path)
    warnings: list[str] = []
    geometry_refs: list[GeometryReference] = []
    cae_targets: list[CaeTargetReference] = []

    # Geometry references from feature_graph
    if context.feature_graph:
        graph_refs = _build_geometry_refs_from_feature_graph(context.feature_graph)
        geometry_refs.extend(graph_refs)
    else:
        warnings.append("feature_graph.json not found; no feature-to-geometry mappings.")

    # Geometry references from constraints (protected regions)
    if context.constraints:
        constraint_refs = _build_geometry_refs_from_constraints(context.constraints)
        geometry_refs.extend(constraint_refs)

    # Geometry references from interface_graph
    interface_graph = _try_load_json(Path(package_path) / "objects" / "interface_graph.json")
    if interface_graph:
        interface_refs = _build_geometry_refs_from_interface_graph(interface_graph)
        geometry_refs.extend(interface_refs)

    # CAE targets from simulation setup
    if context.simulation_setup:
        setup_targets = _build_cae_targets_from_simulation_setup(context.simulation_setup)
        cae_targets.extend(setup_targets)
    else:
        warnings.append("simulation/setup.yaml not found; no CAE target mappings.")

    # Explicit CAE mappings override heuristic targets
    cae_mapping = _try_load_json(Path(package_path) / "simulation" / "cae_mapping.json")
    if cae_mapping:
        explicit_targets = _build_cae_targets_from_cae_mapping(cae_mapping)
        # Merge: explicit targets replace heuristic ones by target_id
        explicit_ids = {t.target_id for t in explicit_targets}
        cae_targets = [t for t in cae_targets if t.target_id not in explicit_ids]
        cae_targets.extend(explicit_targets)

    # Annotation references
    annotation_layers = _try_load_json(Path(package_path) / "visual" / "annotation_layers.json")
    if annotation_layers:
        anno_refs = _build_geometry_refs_from_annotations(annotation_layers)
        geometry_refs.extend(anno_refs)

    return ReferenceMap(
        package_path=package_path,
        geometry_references=geometry_refs,
        cae_targets=cae_targets,
        warnings=warnings,
    )


def write_reference_map(package_path: str, reference_map: ReferenceMap) -> str:
    """Write a reference map to objects/reference_map.json atomically.

    Returns the written file path.
    """
    path = Path(package_path)
    objects_dir = path / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)
    ref_map_path = objects_dir / "reference_map.json"
    _atomic_write_json(ref_map_path, reference_map.model_dump(mode="json"))
    return str(ref_map_path)


def load_reference_map(package_path: str) -> ReferenceMap | None:
    """Load a reference map from objects/reference_map.json if present."""
    path = Path(package_path) / "objects" / "reference_map.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return ReferenceMap.model_validate(data)
    except (json.JSONDecodeError, Exception):
        return None


def mark_references_needing_review(
    package_path: str,
    affected_feature_ids: list[str],
    reason: str = "Geometry modified; mapping stability not guaranteed.",
) -> ReferenceMap:
    """Mark geometry references and linked CAE targets as needing review.

    Loads existing reference map or builds one if absent.
    Persists updated reference_map.json.
    """
    ref_map = load_reference_map(package_path)
    if ref_map is None:
        ref_map = build_reference_map(package_path)

    affected_set = set(affected_feature_ids)
    affected_geo_ref_ids: set[str] = set()

    # Mark geometry references
    for geo_ref in ref_map.geometry_references:
        if geo_ref.feature_id in affected_set:
            geo_ref.status = "needs_review"
            geo_ref.warnings.append(reason)
            affected_geo_ref_ids.add(geo_ref.ref_id)

    # Mark linked CAE targets
    for cae_target in ref_map.cae_targets:
        if cae_target.feature_id in affected_set:
            cae_target.status = "needs_review"
            cae_target.warnings.append(reason)
        elif cae_target.geometry_ref_id in affected_geo_ref_ids:
            cae_target.status = "needs_review"
            cae_target.warnings.append(
                f"Linked geometry reference marked needs_review: {reason}"
            )

    write_reference_map(package_path, ref_map)
    return ref_map


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _build_geometry_refs_from_feature_graph(feature_graph: dict[str, Any]) -> list[GeometryReference]:
    refs: list[GeometryReference] = []
    features = feature_graph.get("features", {})
    for feature_id, feature in features.items():
        if not isinstance(feature, dict):
            continue
        freecad_name = feature.get("freecad_object_name")
        ref = GeometryReference(
            ref_id=f"geom_{feature_id}",
            feature_id=feature_id,
            freecad_object_name=freecad_name,
            role=feature.get("name"),
            mapping_method="freecad_object_name" if freecad_name else "unresolved",
            confidence="medium" if freecad_name else "unknown",
            status="valid" if freecad_name else "unresolved",
        )
        if not freecad_name:
            ref.warnings.append("No freecad_object_name in feature graph.")
        refs.append(ref)
    return refs


def _build_geometry_refs_from_constraints(constraints: dict[str, Any]) -> list[GeometryReference]:
    refs: list[GeometryReference] = []
    protected = constraints.get("protected_regions", [])
    for region in protected:
        if not isinstance(region, dict):
            continue
        region_name = region.get("name", "unknown")
        for feature_id in region.get("features", []):
            refs.append(
                GeometryReference(
                    ref_id=f"geom_constraint_{region_name}_{feature_id}",
                    feature_id=feature_id,
                    role=f"protected_region:{region_name}",
                    mapping_method="heuristic",
                    confidence="low",
                    status="valid",
                )
            )
    return refs


def _build_geometry_refs_from_interface_graph(interface_graph: dict[str, Any]) -> list[GeometryReference]:
    refs: list[GeometryReference] = []
    interfaces = interface_graph.get("interfaces", [])
    for iface in interfaces:
        if not isinstance(iface, dict):
            continue
        interface_id = iface.get("interface_id")
        if not interface_id:
            continue
        refs.append(
            GeometryReference(
                ref_id=f"geom_iface_{interface_id}",
                interface_id=interface_id,
                role=iface.get("role"),
                mapping_method="user_provided",
                confidence="high",
                status="valid",
            )
        )
    return refs


def _build_geometry_refs_from_annotations(annotation_layers: dict[str, Any]) -> list[GeometryReference]:
    refs: list[GeometryReference] = []
    layers = annotation_layers.get("layers", [])
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        layer_id = layer.get("layer_id")
        if not layer_id:
            continue
        refs.append(
            GeometryReference(
                ref_id=f"geom_anno_{layer_id}",
                interface_id=layer.get("target"),
                role=layer.get("name"),
                mapping_method="user_provided",
                confidence="high",
                status="valid",
            )
        )
    return refs


def _build_cae_targets_from_simulation_setup(sim_setup: dict[str, Any]) -> list[CaeTargetReference]:
    targets: list[CaeTargetReference] = []

    # Boundary conditions
    for bc in sim_setup.get("boundary_conditions", []):
        if isinstance(bc, dict):
            target_id = f"bc_{bc.get('name', 'unknown')}"
            targets.append(
                CaeTargetReference(
                    target_id=target_id,
                    target_name=bc.get("name"),
                    target_type="boundary_condition",
                    source="simulation/setup.yaml",
                    mapping_method="heuristic",
                    confidence="low",
                    status="unresolved",
                )
            )

    # Loads
    for load in sim_setup.get("loads", []):
        if isinstance(load, dict):
            target_id = f"load_{load.get('name', 'unknown')}"
            targets.append(
                CaeTargetReference(
                    target_id=target_id,
                    target_name=load.get("name"),
                    target_type="load",
                    source="simulation/setup.yaml",
                    mapping_method="heuristic",
                    confidence="low",
                    status="unresolved",
                )
            )

    # Mesh refinement regions
    mesh = sim_setup.get("mesh", {})
    if isinstance(mesh, dict):
        for region in mesh.get("refinement_regions", []):
            target_id = f"mesh_region_{region}"
            targets.append(
                CaeTargetReference(
                    target_id=target_id,
                    target_name=str(region),
                    target_type="mesh_region",
                    source="simulation/setup.yaml",
                    mapping_method="heuristic",
                    confidence="low",
                    status="unresolved",
                )
            )

    return targets


def _build_cae_targets_from_cae_mapping(cae_mapping: dict[str, Any]) -> list[CaeTargetReference]:
    targets: list[CaeTargetReference] = []
    mappings = cae_mapping.get("mappings", [])
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        target_id = mapping.get("target_id")
        if not target_id:
            continue
        targets.append(
            CaeTargetReference(
                target_id=target_id,
                target_name=mapping.get("target_name"),
                target_type=mapping.get("target_type", "unknown"),
                feature_id=mapping.get("feature_id"),
                interface_id=mapping.get("interface_id"),
                geometry_ref_id=mapping.get("geometry_ref_id"),
                source="simulation/cae_mapping.json",
                mapping_method=mapping.get("mapping_method", "user_provided"),
                confidence=mapping.get("confidence", "high"),
                status="valid",
            )
        )
    return targets


# ---------------------------------------------------------------------------
# JSON helper
# ---------------------------------------------------------------------------

def _try_load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
