from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.geometry.topology_extractor import TOPOLOGY_MAP_PATH

AAG_PATH = "graph/aag.json"


class AAGBuilder:
    """Deterministic attributed adjacency graph (AAG) builder.

    The AAG is a generated index derived from topology_map.json and is not the
    source of truth for topology entities.
    """

    def build(self, topology_map: dict[str, Any]) -> dict[str, Any]:
        entities = [entity for entity in topology_map.get("entities", []) if isinstance(entity, dict)]
        face_entities = [entity for entity in entities if entity.get("type") == "face" and isinstance(entity.get("id"), str)]
        edge_entities = [entity for entity in entities if entity.get("type") == "edge" and isinstance(entity.get("id"), str)]

        nodes = [self._node_from_face(face) for face in sorted(face_entities, key=lambda item: str(item["id"]))]
        face_ids = {str(face["id"]) for face in face_entities}

        edge_to_faces = self._edge_to_faces(edge_entities, face_ids)
        pair_to_edge_ids: dict[tuple[str, str], set[str]] = {}
        for edge_id, owning_faces in edge_to_faces.items():
            if len(owning_faces) < 2:
                continue
            ordered_faces = sorted(owning_faces)
            for index, source in enumerate(ordered_faces):
                for target in ordered_faces[index + 1:]:
                    pair = (source, target)
                    pair_to_edge_ids.setdefault(pair, set()).add(edge_id)

        # Fall back to explicit face-level adjacency if no shared-edge proof is available.
        adjacency_pairs: set[tuple[str, str]] = set(pair_to_edge_ids.keys())
        for face in face_entities:
            source = str(face["id"])
            adjacent = face.get("adjacent_entity_ids")
            if not isinstance(adjacent, list):
                continue
            for candidate in adjacent:
                if not isinstance(candidate, str) or candidate not in face_ids or candidate == source:
                    continue
                pair = tuple(sorted((source, candidate)))
                adjacency_pairs.add(pair)

        arcs: list[dict[str, Any]] = []
        edge_proven = 0
        inferred = 0
        for index, pair in enumerate(sorted(adjacency_pairs), start=1):
            source_face, target_face = pair
            source_node = self._node_id_for_face(source_face)
            target_node = self._node_id_for_face(target_face)
            shared_edges = sorted(pair_to_edge_ids.get(pair, set()))

            if shared_edges:
                adjacency_type = "edge_adjacent"
                confidence = "high"
                edge_proven += 1
            else:
                adjacency_type = "inferred_from_topology"
                confidence = "medium"
                inferred += 1

            arcs.append(
                {
                    "id": f"arc_{index:03d}",
                    "source_node": source_node,
                    "target_node": target_node,
                    "shared_edge_ids": shared_edges,
                    "adjacency_type": adjacency_type,
                    "edge_continuity": "unknown",
                    "confidence": confidence,
                }
            )

        metadata = topology_map.get("metadata") if isinstance(topology_map.get("metadata"), dict) else {}
        topology_backend = metadata.get("extraction_backend", "unknown")

        if arcs:
            if edge_proven > 0:
                adjacency_evidence = "real" if topology_backend == "occ" else "mock"
            else:
                adjacency_evidence = "inferred"
        else:
            adjacency_evidence = "unavailable"

        notes = [
            "AAG is a generated graph/index derived from geometry/topology_map.json.",
            "AAG is not the source of truth; topology_map remains the source for topology entities.",
            "Convexity/continuity and dihedral angle fields may be unknown unless backend evidence exists.",
        ]
        if adjacency_evidence == "unavailable":
            notes.append("Adjacency arcs are empty because sufficient adjacency evidence was unavailable in topology data.")

        return {
            "schema_version": FORMAT_VERSION,
            "source_topology_map": TOPOLOGY_MAP_PATH,
            "generation_method": {
                "builder": "AAGBuilder",
                "topology_backend": topology_backend,
                "adjacency_evidence": adjacency_evidence,
            },
            "nodes": nodes,
            "arcs": arcs,
            "notes": notes,
        }

    def _node_from_face(self, face: dict[str, Any]) -> dict[str, Any]:
        face_id = str(face["id"])
        node: dict[str, Any] = {
            "id": self._node_id_for_face(face_id),
            "topology_entity_id": face_id,
            "entity_type": "face",
            "surface_type": str(face.get("surface_type", "unknown")),
        }
        for optional in ("area", "bbox", "normal", "axis", "radius", "feature_hints"):
            if optional == "bbox":
                if isinstance(face.get("bounding_box"), list):
                    node["bbox"] = face["bounding_box"]
            elif optional in face:
                node[optional] = face[optional]
        return node

    def _edge_to_faces(self, edge_entities: list[dict[str, Any]], known_face_ids: set[str]) -> dict[str, set[str]]:
        edge_to_faces: dict[str, set[str]] = {}
        for edge in edge_entities:
            edge_id = str(edge["id"])
            owners: set[str] = set()
            for key in ("face_ids", "adjacent_entity_ids"):
                refs = edge.get(key)
                if isinstance(refs, list):
                    owners.update(ref for ref in refs if isinstance(ref, str) and ref in known_face_ids)
            if owners:
                edge_to_faces[edge_id] = owners
        return edge_to_faces

    @staticmethod
    def _node_id_for_face(face_id: str) -> str:
        return f"node_{face_id}"


def build_aag_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
    builder: AAGBuilder | None = None,
) -> Path:
    """Write graph/aag.json to an existing .aieng package."""
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    builder = builder or AAGBuilder()

    try:
        with zipfile.ZipFile(path, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if TOPOLOGY_MAP_PATH not in names:
                raise FileNotFoundError(f"{TOPOLOGY_MAP_PATH} missing")
            if AAG_PATH in names and not overwrite:
                raise FileExistsError(f"{AAG_PATH} already exists; use --overwrite to replace it")

            manifest = json.loads(package.read("manifest.json"))
            topology_map = json.loads(package.read(TOPOLOGY_MAP_PATH))
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    aag_data = builder.build(topology_map)
    _rewrite_package_with_aag(path, existing_members, manifest, aag_data)
    return path


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    seen: set[str] = set()
    for info in package.infolist():
        if info.filename in {"manifest.json", AAG_PATH} or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_aag(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    aag_data: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    graph_resources = resources.setdefault("graph", {})
    if not isinstance(graph_resources, dict):
        raise ValueError("manifest resources.graph must be an object")
    graph_resources["aag"] = AAG_PATH

    aag_json = json.dumps(aag_data, indent=2, sort_keys=True) + "\n"
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(AAG_PATH, aag_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
