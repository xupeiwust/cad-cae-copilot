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

OBJECT_REGISTRY_PATH = "objects/object_registry.json"
OBJECTS_DIR = "objects/"
OBJECT_REGISTRY_FORMAT = "aieng.object_registry"

_TOPOLOGY_MAP_PATH = "geometry/topology_map.json"
_FEATURE_GRAPH_PATH = "graph/feature_graph.json"
_CONSTRAINTS_PATH = "graph/constraints.json"
_SIMULATION_SETUP_PATH = "simulation/setup.yaml"
_PROTECTED_REGIONS_PATH = "ai/protected_regions.json"
_VISUAL_ANNOTATION_PATH = "visual/annotation_layers.json"
_VISUAL_MODEL_MANIFEST_PATH = "visual/model_manifest.json"
_INTERFACE_GRAPH_PATH = "objects/interface_graph.json"
_VALIDATION_STATUS_PATH = "validation/status.yaml"
_CAE_PARSED_MATERIALS_PATH = "simulation/cae_imports/parsed_materials.json"
_CAE_PARSED_BCS_PATH = "simulation/cae_imports/parsed_boundary_conditions.json"
_CAE_PARSED_LOADS_PATH = "simulation/cae_imports/parsed_loads.json"
_CAE_MAPPING_PATH = "simulation/cae_mapping.json"
_PATCH_DIR = "ai/patches/"

_BASE_SOURCE_ORDER = [
    _TOPOLOGY_MAP_PATH,
    _FEATURE_GRAPH_PATH,
    _CONSTRAINTS_PATH,
    _SIMULATION_SETUP_PATH,
    _PROTECTED_REGIONS_PATH,
    _VISUAL_ANNOTATION_PATH,
    _VISUAL_MODEL_MANIFEST_PATH,
    _INTERFACE_GRAPH_PATH,
    _VALIDATION_STATUS_PATH,
    _CAE_PARSED_MATERIALS_PATH,
    _CAE_PARSED_BCS_PATH,
    _CAE_PARSED_LOADS_PATH,
    _CAE_MAPPING_PATH,
]


class _RegistryBuilder:
    def __init__(self, names: set[str]) -> None:
        self.names = names
        self.objects: dict[str, dict[str, Any]] = {}
        self._seen_relationships: set[tuple[str, str, str, str]] = set()
        self.relationships: list[dict[str, str]] = []

    def register_object(
        self,
        *,
        object_id: str,
        kind: str,
        object_type: str | None = None,
        name: str | None = None,
        defined_in: str | None = None,
        status: str | None = None,
        roles: list[str] | None = None,
    ) -> None:
        if not object_id:
            return
        current = self.objects.get(object_id)
        if current is None:
            current = {
                "id": object_id,
                "kind": kind,
                "referenced_by": set(),
                "roles": set(),
                "status": status or "defined",
            }
            self.objects[object_id] = current

        if current["kind"] == "unresolved_reference" and kind != "unresolved_reference":
            current["kind"] = kind
            current["status"] = status or "defined"

        if object_type is not None:
            current["type"] = object_type
        if name is not None:
            current["name"] = name
        if defined_in is not None:
            current["defined_in"] = defined_in
            current["referenced_by"].add(defined_in)
        if status is not None:
            current["status"] = status
        if roles:
            for role in roles:
                if isinstance(role, str) and role:
                    current["roles"].add(role)

    def record_reference(self, object_id: str, source_file: str, *, role: str | None = None) -> None:
        if not object_id:
            return
        if object_id not in self.objects:
            self.objects[object_id] = {
                "id": object_id,
                "kind": "unresolved_reference",
                "referenced_by": {source_file},
                "roles": set([role] if role else []),
                "status": "unresolved",
            }
            return

        current = self.objects[object_id]
        current["referenced_by"].add(source_file)
        if role:
            current["roles"].add(role)

    def add_relationship(self, *, from_id: str, to_id: str, rel_type: str, source_file: str) -> None:
        if not from_id or not to_id:
            return
        key = (from_id, to_id, rel_type, source_file)
        if key in self._seen_relationships:
            return
        self._seen_relationships.add(key)

        self.record_reference(from_id, source_file)
        self.record_reference(to_id, source_file)
        self.relationships.append(
            {
                "from": from_id,
                "to": to_id,
                "type": rel_type,
                "source_file": source_file,
            }
        )

    def finalize(self) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        objects: list[dict[str, Any]] = []
        for object_id in sorted(self.objects.keys()):
            item = dict(self.objects[object_id])
            referenced_by = sorted(item.pop("referenced_by", set()))
            roles = sorted(item.pop("roles", set()))
            item["referenced_by"] = referenced_by
            item["roles"] = roles
            objects.append(item)

        relationships = sorted(
            self.relationships,
            key=lambda rel: (rel["source_file"], rel["type"], rel["from"], rel["to"]),
        )
        return objects, relationships


def build_object_registry_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write objects/object_registry.json to an existing .aieng package."""
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
            if OBJECT_REGISTRY_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{OBJECT_REGISTRY_PATH} already exists; use --overwrite to replace it"
                )

            manifest = json.loads(package.read("manifest.json"))
            topology_map = _read_optional_json(package, _TOPOLOGY_MAP_PATH)
            feature_graph = _read_optional_json(package, _FEATURE_GRAPH_PATH)
            constraints = _read_optional_json(package, _CONSTRAINTS_PATH)
            simulation_setup = _read_optional_yaml(package, _SIMULATION_SETUP_PATH)
            protected_regions = _read_optional_json(package, _PROTECTED_REGIONS_PATH)
            annotation_layers = _read_optional_json(package, _VISUAL_ANNOTATION_PATH)
            visual_model_manifest = _read_optional_json(package, _VISUAL_MODEL_MANIFEST_PATH)
            interface_graph = _read_optional_json(package, _INTERFACE_GRAPH_PATH)
            validation_status = _read_optional_yaml(package, _VALIDATION_STATUS_PATH)
            parsed_cae_materials = _read_optional_json(package, _CAE_PARSED_MATERIALS_PATH)
            parsed_cae_bcs = _read_optional_json(package, _CAE_PARSED_BCS_PATH)
            parsed_cae_loads = _read_optional_json(package, _CAE_PARSED_LOADS_PATH)
            cae_mapping = _read_optional_json(package, _CAE_MAPPING_PATH)
            patch_docs = _read_patch_docs(package, names)
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    object_registry = _build_object_registry(
        names=names,
        topology_map=topology_map,
        feature_graph=feature_graph,
        constraints=constraints,
        simulation_setup=simulation_setup,
        protected_regions=protected_regions,
        annotation_layers=annotation_layers,
        visual_model_manifest=visual_model_manifest,
        interface_graph=interface_graph,
        validation_status=validation_status,
        parsed_cae_materials=parsed_cae_materials,
        parsed_cae_bcs=parsed_cae_bcs,
        parsed_cae_loads=parsed_cae_loads,
        cae_mapping=cae_mapping,
        patch_docs=patch_docs,
    )

    _rewrite_package_with_object_registry(path, existing_members, manifest, object_registry)
    return path


def _build_object_registry(
    *,
    names: set[str],
    topology_map: Any | None,
    feature_graph: Any | None,
    constraints: Any | None,
    simulation_setup: Any | None,
    protected_regions: Any | None,
    annotation_layers: Any | None,
    visual_model_manifest: Any | None,
    interface_graph: Any | None,
    validation_status: Any | None,
    parsed_cae_materials: Any | None,
    parsed_cae_bcs: Any | None,
    parsed_cae_loads: Any | None,
    cae_mapping: Any | None,
    patch_docs: list[tuple[str, Any | None]],
) -> dict[str, Any]:
    builder = _RegistryBuilder(names)

    # Topology entities
    if isinstance(topology_map, dict) and isinstance(topology_map.get("entities"), list):
        for entity in topology_map["entities"]:
            if not isinstance(entity, dict) or not isinstance(entity.get("id"), str):
                continue
            entity_id = entity["id"]
            builder.register_object(
                object_id=entity_id,
                kind="topology_entity",
                object_type=str(entity.get("type", "unknown")),
                name=_string_or_none(entity.get("name")) or entity_id,
                defined_in=_TOPOLOGY_MAP_PATH,
                status="defined",
                roles=["topology_entity"],
            )

    # Features + feature relationships
    if isinstance(feature_graph, dict) and isinstance(feature_graph.get("features"), list):
        for feature in feature_graph["features"]:
            if not isinstance(feature, dict) or not isinstance(feature.get("id"), str):
                continue
            feature_id = feature["id"]
            feature_type = _string_or_none(feature.get("type")) or "unknown_feature"
            roles = ["feature_candidate"]
            if feature_type == "mounting_hole_pattern":
                roles.append("mounting_interface_candidate")

            builder.register_object(
                object_id=feature_id,
                kind="feature",
                object_type=feature_type,
                name=_string_or_none(feature.get("name")) or feature_id,
                defined_in=_FEATURE_GRAPH_PATH,
                status="candidate",
                roles=roles,
            )

            for child_id in _string_list(feature.get("children", [])):
                builder.add_relationship(
                    from_id=feature_id,
                    to_id=child_id,
                    rel_type="parent_child",
                    source_file=_FEATURE_GRAPH_PATH,
                )

            refs = feature.get("geometry_refs")
            for topology_id in _feature_ref_ids(refs):
                builder.add_relationship(
                    from_id=feature_id,
                    to_id=topology_id,
                    rel_type="feature_to_topology",
                    source_file=_FEATURE_GRAPH_PATH,
                )

            for relationship in feature.get("relationships", []):
                if not isinstance(relationship, dict):
                    continue
                rel_type = _string_or_none(relationship.get("type")) or "feature_relationship"
                rel_from = _first_string(
                    relationship,
                    keys=("source", "source_feature_id", "feature_id"),
                )
                rel_to = _first_string(
                    relationship,
                    keys=("target", "target_feature_id"),
                )
                if rel_from and rel_to:
                    builder.add_relationship(
                        from_id=rel_from,
                        to_id=rel_to,
                        rel_type=rel_type,
                        source_file=_FEATURE_GRAPH_PATH,
                    )

    # Constraints
    if isinstance(constraints, dict) and isinstance(constraints.get("constraints"), list):
        for constraint in constraints["constraints"]:
            if not isinstance(constraint, dict) or not isinstance(constraint.get("id"), str):
                continue
            constraint_id = constraint["id"]
            constraint_type = _string_or_none(constraint.get("type")) or "constraint"
            target = _string_or_none(constraint.get("target"))
            roles = ["constraint"]
            if constraint_type in {
                "protect_geometry",
                "protect_position",
                "protect_dimension",
                "preserve_interface",
            }:
                roles.append("protection_constraint")

            builder.register_object(
                object_id=constraint_id,
                kind="constraint",
                object_type=constraint_type,
                name=_string_or_none(constraint.get("reason")) or constraint_id,
                defined_in=_CONSTRAINTS_PATH,
                status="declared",
                roles=roles,
            )

            if target:
                builder.add_relationship(
                    from_id=constraint_id,
                    to_id=target,
                    rel_type="constraint_target",
                    source_file=_CONSTRAINTS_PATH,
                )

    # Simulation setup
    if isinstance(simulation_setup, dict):
        simulation_id = _string_or_none(simulation_setup.get("simulation_id"))
        if simulation_id:
            builder.register_object(
                object_id=simulation_id,
                kind="simulation",
                object_type=_string_or_none(simulation_setup.get("simulation_type")) or "simulation",
                name=simulation_id,
                defined_in=_SIMULATION_SETUP_PATH,
                status="intent",
                roles=["simulation_intent"],
            )

        materials = simulation_setup.get("materials")
        if isinstance(materials, dict):
            for material_name in sorted(materials.keys()):
                material_id = _material_object_id(material_name)
                builder.register_object(
                    object_id=material_id,
                    kind="material",
                    object_type="material",
                    name=material_name,
                    defined_in=_SIMULATION_SETUP_PATH,
                    status="declared",
                    roles=["simulation_material"],
                )
                if simulation_id:
                    builder.add_relationship(
                        from_id=simulation_id,
                        to_id=material_id,
                        rel_type="simulation_uses_material",
                        source_file=_SIMULATION_SETUP_PATH,
                    )

        for bc in simulation_setup.get("boundary_conditions", []) or []:
            if not isinstance(bc, dict):
                continue
            bc_id = _string_or_none(bc.get("id"))
            if not bc_id:
                continue
            bc_type = _string_or_none(bc.get("type")) or "boundary_condition"
            builder.register_object(
                object_id=bc_id,
                kind="boundary_condition",
                object_type=bc_type,
                name=bc_id,
                defined_in=_SIMULATION_SETUP_PATH,
                status="candidate",
                roles=["simulation_boundary_condition"],
            )
            if simulation_id:
                builder.add_relationship(
                    from_id=simulation_id,
                    to_id=bc_id,
                    rel_type="simulation_has_boundary_condition",
                    source_file=_SIMULATION_SETUP_PATH,
                )
            target_feature = _string_or_none(bc.get("target_feature"))
            if target_feature:
                builder.add_relationship(
                    from_id=bc_id,
                    to_id=target_feature,
                    rel_type="boundary_condition_targets_feature",
                    source_file=_SIMULATION_SETUP_PATH,
                )
                if bc_type == "fixed":
                    builder.record_reference(
                        target_feature,
                        _SIMULATION_SETUP_PATH,
                        role="fixed_boundary_condition_target",
                    )

        for load in simulation_setup.get("loads", []) or []:
            if not isinstance(load, dict):
                continue
            load_id = _string_or_none(load.get("id"))
            if not load_id:
                continue
            load_type = _string_or_none(load.get("type")) or "load"
            builder.register_object(
                object_id=load_id,
                kind="load",
                object_type=load_type,
                name=load_id,
                defined_in=_SIMULATION_SETUP_PATH,
                status="candidate",
                roles=["simulation_load"],
            )
            if simulation_id:
                builder.add_relationship(
                    from_id=simulation_id,
                    to_id=load_id,
                    rel_type="simulation_has_load",
                    source_file=_SIMULATION_SETUP_PATH,
                )
            target_feature = _string_or_none(load.get("target_feature"))
            if target_feature:
                builder.add_relationship(
                    from_id=load_id,
                    to_id=target_feature,
                    rel_type="load_targets_feature",
                    source_file=_SIMULATION_SETUP_PATH,
                )

    # Protected regions
    if isinstance(protected_regions, dict) and isinstance(protected_regions.get("protected_regions"), list):
        for index, region in enumerate(protected_regions["protected_regions"], start=1):
            if not isinstance(region, dict):
                continue
            feature_id = _string_or_none(region.get("feature_id"))
            if not feature_id:
                continue
            region_id = f"protreg_{index:03d}_{feature_id}"
            builder.register_object(
                object_id=region_id,
                kind="protected_region",
                object_type="protected_region",
                name=f"Protected region: {feature_id}",
                defined_in=_PROTECTED_REGIONS_PATH,
                status="protected",
                roles=["protected_region"],
            )
            builder.add_relationship(
                from_id=region_id,
                to_id=feature_id,
                rel_type="protected_feature",
                source_file=_PROTECTED_REGIONS_PATH,
            )
            builder.record_reference(feature_id, _PROTECTED_REGIONS_PATH, role="protected_region")

    # Patch proposals + operations
    for patch_path, patch_doc in patch_docs:
        if not isinstance(patch_doc, dict):
            continue
        patch_id = _string_or_none(patch_doc.get("patch_id")) or Path(patch_path).stem
        patch_status = _string_or_none(patch_doc.get("status")) or "proposed"
        builder.register_object(
            object_id=patch_id,
            kind="patch",
            object_type="patch_proposal",
            name=_string_or_none(patch_doc.get("summary")) or patch_id,
            defined_in=patch_path,
            status=patch_status,
            roles=["patch_proposal"],
        )

        for index, operation in enumerate(patch_doc.get("operations", []) or [], start=1):
            if not isinstance(operation, dict):
                continue
            operation_id = f"patchop_{patch_id}_{index:03d}"
            operation_type = (
                _string_or_none(operation.get("op"))
                or _string_or_none(operation.get("type"))
                or "patch_operation"
            )
            builder.register_object(
                object_id=operation_id,
                kind="patch_operation",
                object_type=operation_type,
                name=operation_id,
                defined_in=patch_path,
                status=patch_status,
                roles=["patch_operation"],
            )
            builder.add_relationship(
                from_id=patch_id,
                to_id=operation_id,
                rel_type="patch_has_operation",
                source_file=patch_path,
            )

            target = _string_or_none(operation.get("target")) or _string_or_none(operation.get("target_feature_id"))
            if target:
                builder.add_relationship(
                    from_id=operation_id,
                    to_id=target,
                    rel_type="patch_targets_feature",
                    source_file=patch_path,
                )

        for target_feature in _string_list(patch_doc.get("target_feature_ids", [])):
            builder.add_relationship(
                from_id=patch_id,
                to_id=target_feature,
                rel_type="patch_targets_feature",
                source_file=patch_path,
            )

    # Visual annotation layers
    if isinstance(annotation_layers, dict) and isinstance(annotation_layers.get("layers"), list):
        for layer in annotation_layers["layers"]:
            if not isinstance(layer, dict):
                continue
            layer_id = _string_or_none(layer.get("id")) or "layer"
            for item in layer.get("items", []) or []:
                if not isinstance(item, dict):
                    continue
                annotation_id = _string_or_none(item.get("id"))
                if not annotation_id:
                    continue
                visual_role = _string_or_none(item.get("visual_role"))
                roles = [visual_role] if visual_role else ["visual_annotation"]
                builder.register_object(
                    object_id=annotation_id,
                    kind="visual_annotation",
                    object_type=layer_id,
                    name=_string_or_none(item.get("label")) or annotation_id,
                    defined_in=_VISUAL_ANNOTATION_PATH,
                    status=_string_or_none(item.get("status")) or "candidate",
                    roles=roles,
                )

                feature_id = _string_or_none(item.get("feature_id"))
                if feature_id:
                    builder.add_relationship(
                        from_id=annotation_id,
                        to_id=feature_id,
                        rel_type="annotation_targets_feature",
                        source_file=_VISUAL_ANNOTATION_PATH,
                    )

                refs = item.get("topology_refs")
                if isinstance(refs, dict):
                    for ref_id in _string_list(refs.get("faces", [])) + _string_list(refs.get("edges", [])):
                        builder.add_relationship(
                            from_id=annotation_id,
                            to_id=ref_id,
                            rel_type="annotation_targets_topology",
                            source_file=_VISUAL_ANNOTATION_PATH,
                        )

    # Visual resource manifest
    if isinstance(visual_model_manifest, dict):
        visual_resources = visual_model_manifest.get("visual_resources")
        if isinstance(visual_resources, dict):
            for resource_name in sorted(visual_resources.keys()):
                resource = visual_resources[resource_name]
                if not isinstance(resource, dict):
                    continue
                resource_id = f"visres_{resource_name}"
                builder.register_object(
                    object_id=resource_id,
                    kind="visual_resource",
                    object_type=_string_or_none(resource.get("type")) or "visual_resource",
                    name=resource_name,
                    defined_in=_VISUAL_MODEL_MANIFEST_PATH,
                    status=_string_or_none(resource.get("status")) or "unknown",
                    roles=["visual_resource"],
                )

    # Validation status
    if isinstance(validation_status, dict):
        builder.register_object(
            object_id="validation_status",
            kind="validation_status",
            object_type="validation_status",
            name="validation/status.yaml",
            defined_in=_VALIDATION_STATUS_PATH,
            status="generated",
            roles=["validation_status"],
        )

    # Imported CAE deck resources (Phase 10A scaffold)
    if isinstance(parsed_cae_materials, dict) and isinstance(parsed_cae_materials.get("materials"), list):
        for material in parsed_cae_materials["materials"]:
            if not isinstance(material, dict):
                continue
            name = _string_or_none(material.get("name"))
            if not name:
                continue
            material_id = f"cae_mat_{_slug(name)}"
            builder.register_object(
                object_id=material_id,
                kind="cae_material",
                object_type="cae_material",
                name=name,
                defined_in=_CAE_PARSED_MATERIALS_PATH,
                status="parsed",
                roles=["cae_import_material"],
            )

    if isinstance(parsed_cae_bcs, dict) and isinstance(parsed_cae_bcs.get("boundary_conditions"), list):
        for bc in parsed_cae_bcs["boundary_conditions"]:
            if not isinstance(bc, dict):
                continue
            bc_id = _string_or_none(bc.get("id"))
            if not bc_id:
                continue
            builder.register_object(
                object_id=bc_id,
                kind="cae_boundary_condition",
                object_type="cae_boundary_condition",
                name=bc_id,
                defined_in=_CAE_PARSED_BCS_PATH,
                status="parsed",
                roles=["cae_import_boundary_condition"],
            )

    if isinstance(parsed_cae_loads, dict) and isinstance(parsed_cae_loads.get("loads"), list):
        for load in parsed_cae_loads["loads"]:
            if not isinstance(load, dict):
                continue
            load_id = _string_or_none(load.get("id"))
            if not load_id:
                continue
            builder.register_object(
                object_id=load_id,
                kind="cae_load",
                object_type="cae_load",
                name=load_id,
                defined_in=_CAE_PARSED_LOADS_PATH,
                status="parsed",
                roles=["cae_import_load"],
            )

    if isinstance(cae_mapping, dict) and isinstance(cae_mapping.get("mappings"), list):
        for index, mapping in enumerate(cae_mapping["mappings"], start=1):
            if not isinstance(mapping, dict):
                continue
            mapping_id = f"cae_map_{index:03d}"
            cae_entity = _string_or_none(mapping.get("cae_entity")) or mapping_id
            builder.register_object(
                object_id=mapping_id,
                kind="cae_mapping",
                object_type=_string_or_none(mapping.get("cae_type")) or "cae_mapping",
                name=cae_entity,
                defined_in=_CAE_MAPPING_PATH,
                status=_string_or_none(mapping.get("mapping_status")) or "unmapped",
                roles=["cae_mapping"],
            )

            target_entity = _cae_entity_to_parsed_object_id(cae_entity, parsed_cae_bcs, parsed_cae_loads)
            if target_entity:
                builder.add_relationship(
                    from_id=mapping_id,
                    to_id=target_entity,
                    rel_type="cae_mapping_for_entity",
                    source_file=_CAE_MAPPING_PATH,
                )

            maps_to = mapping.get("maps_to")
            if isinstance(maps_to, dict):
                feature_id = _string_or_none(maps_to.get("feature_id"))
                if feature_id:
                    builder.add_relationship(
                        from_id=mapping_id,
                        to_id=feature_id,
                        rel_type="cae_entity_to_feature",
                        source_file=_CAE_MAPPING_PATH,
                    )
                interface_id = _string_or_none(maps_to.get("interface_id"))
                if interface_id:
                    builder.add_relationship(
                        from_id=mapping_id,
                        to_id=interface_id,
                        rel_type="cae_entity_to_interface",
                        source_file=_CAE_MAPPING_PATH,
                    )

    # Interface graph
    if isinstance(interface_graph, dict) and isinstance(interface_graph.get("interfaces"), list):
        for interface in interface_graph["interfaces"]:
            if not isinstance(interface, dict):
                continue
            interface_id = _string_or_none(interface.get("id"))
            if not interface_id:
                continue

            builder.register_object(
                object_id=interface_id,
                kind="interface",
                object_type=_string_or_none(interface.get("type")) or "interface",
                name=interface_id,
                defined_in=_INTERFACE_GRAPH_PATH,
                status=_string_or_none(interface.get("status")) or "candidate",
                roles=_string_list(interface.get("roles", [])) or ["interface"],
            )

            for feature_id in _string_list(interface.get("feature_ids", [])):
                builder.add_relationship(
                    from_id=interface_id,
                    to_id=feature_id,
                    rel_type="interface_targets_feature",
                    source_file=_INTERFACE_GRAPH_PATH,
                )

            topology_refs = interface.get("topology_refs")
            if isinstance(topology_refs, dict):
                for ref_id in _string_list(topology_refs.get("faces", [])) + _string_list(topology_refs.get("edges", [])):
                    builder.add_relationship(
                        from_id=interface_id,
                        to_id=ref_id,
                        rel_type="interface_refs_topology",
                        source_file=_INTERFACE_GRAPH_PATH,
                    )

            for constraint_id in _string_list(interface.get("constraint_refs", [])):
                builder.add_relationship(
                    from_id=interface_id,
                    to_id=constraint_id,
                    rel_type="interface_refs_constraint",
                    source_file=_INTERFACE_GRAPH_PATH,
                )

            for simulation_id in _string_list(interface.get("simulation_refs", [])):
                builder.add_relationship(
                    from_id=interface_id,
                    to_id=simulation_id,
                    rel_type="interface_refs_simulation",
                    source_file=_INTERFACE_GRAPH_PATH,
                )

            for visual_id in _string_list(interface.get("visual_refs", [])):
                builder.add_relationship(
                    from_id=interface_id,
                    to_id=visual_id,
                    rel_type="interface_refs_visual",
                    source_file=_INTERFACE_GRAPH_PATH,
                )

            for cae_ref in interface.get("cae_refs", []) or []:
                if not isinstance(cae_ref, dict):
                    continue
                cae_entity = _string_or_none(cae_ref.get("cae_entity"))
                if not cae_entity:
                    continue
                parsed_entity_id = _cae_entity_to_parsed_object_id(cae_entity, parsed_cae_bcs, parsed_cae_loads)
                cae_object_id = parsed_entity_id or cae_entity
                builder.record_reference(
                    cae_object_id,
                    _INTERFACE_GRAPH_PATH,
                    role="interface_mapped_cae_entity",
                )
                builder.add_relationship(
                    from_id=cae_object_id,
                    to_id=interface_id,
                    rel_type="cae_entity_to_interface",
                    source_file=_INTERFACE_GRAPH_PATH,
                )
                maps_to = cae_ref.get("maps_to")
                if isinstance(maps_to, dict):
                    feature_id = _string_or_none(maps_to.get("feature_id"))
                    if feature_id:
                        builder.add_relationship(
                            from_id=cae_object_id,
                            to_id=feature_id,
                            rel_type="cae_entity_to_feature",
                            source_file=_INTERFACE_GRAPH_PATH,
                        )

    objects, relationships = builder.finalize()
    source_files = _source_files(names, patch_docs)

    return {
        "format": OBJECT_REGISTRY_FORMAT,
        "format_version": FORMAT_VERSION,
        "source_files": source_files,
        "objects": objects,
        "relationships": relationships,
        "notes": [
            "This registry is generated from package resources.",
            "It is an index, not the source of truth.",
            "Structured source files remain authoritative.",
        ],
    }


def _source_files(names: set[str], patch_docs: list[tuple[str, Any | None]]) -> list[str]:
    files = [path for path in _BASE_SOURCE_ORDER if path in names]
    files.extend(sorted(path for path, _ in patch_docs if path in names))
    return files


def _read_patch_docs(package: zipfile.ZipFile, names: set[str]) -> list[tuple[str, Any | None]]:
    patch_paths = sorted(name for name in names if name.startswith(_PATCH_DIR) and name.endswith(".json"))
    docs: list[tuple[str, Any | None]] = []
    for patch_path in patch_paths:
        docs.append((patch_path, _read_optional_json(package, patch_path)))
    return docs


def _feature_ref_ids(refs: Any) -> list[str]:
    if isinstance(refs, list):
        return _string_list(refs)
    if isinstance(refs, dict):
        values: list[str] = []
        values.extend(_string_list(refs.get("faces", [])))
        values.extend(_string_list(refs.get("edges", [])))
        values.extend(_string_list(refs.get("entities", [])))
        return values
    return []


def _material_object_id(material_name: str) -> str:
    return f"mat_{_slug(material_name)}"


def _cae_entity_to_parsed_object_id(
    cae_entity: str,
    parsed_cae_bcs: Any | None,
    parsed_cae_loads: Any | None,
) -> str | None:
    if isinstance(parsed_cae_bcs, dict) and isinstance(parsed_cae_bcs.get("boundary_conditions"), list):
        for bc in parsed_cae_bcs["boundary_conditions"]:
            if isinstance(bc, dict) and _string_or_none(bc.get("target")) == cae_entity:
                return _string_or_none(bc.get("id"))

    if isinstance(parsed_cae_loads, dict) and isinstance(parsed_cae_loads.get("loads"), list):
        for load in parsed_cae_loads["loads"]:
            if isinstance(load, dict) and _string_or_none(load.get("target")) == cae_entity:
                return _string_or_none(load.get("id"))

    return None


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return slug or "unknown"


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _first_string(data: dict[str, Any], *, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


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
    skip = {"manifest.json", OBJECT_REGISTRY_PATH}
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_object_registry(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    object_registry: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    object_resources = resources.setdefault("objects", {})
    if not isinstance(object_resources, dict):
        raise ValueError("manifest resources.objects must be an object")
    object_resources["object_registry"] = OBJECT_REGISTRY_PATH

    object_registry_json = json.dumps(object_registry, indent=2, sort_keys=True) + "\n"
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
            out_package.writestr(OBJECT_REGISTRY_PATH, object_registry_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
