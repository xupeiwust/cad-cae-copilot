"""Shape IR object registry.

Builds `registry/object_registry.json`: the cross-reference that ties each Shape
IR node to its generated artifacts and *selectable* entities — topology faces /
mesh regions / viewer ids — plus editable parameters and the verification record.
This is what makes node↔model selection (PR3) and CAE mapping (PR5) possible.

Linkage of a node to executed geometry, in priority order:
  1. ``source_ir_node`` field on a topology entity (projected topology) — exact.
  2. entity ``name`` matching the node's label/id — works for executed B-Rep,
     because the build123d compiler stamps each part's ``.label`` (= node id) and
     the topology extractor records it as the body ``name``.
  3. ``fused_mesh`` — mesh backends (SDF/Manifold) fuse all nodes into one body,
     so every node resolves to that single body/region (honestly flagged).
  4. ``none`` — executed B-Rep with no labels and no source_ir_node.

Like the verifier, this runs no CAD kernel; it only reads the package.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

from .shape_ir import _node_id, _node_kind, _shape_nodes
from .shape_ir_verification import VERIFICATION_PATH, verify_shape_ir_package

SHAPE_IR_OBJECT_REGISTRY_PATH = "registry/object_registry.json"

_SHAPE_IR_MEMBER = "geometry/shape_ir.json"
_TOPOLOGY_MEMBER = "geometry/topology_map.json"
_MESH_TOPOLOGY_MEMBER = "geometry/mesh_topology_map.json"
_ARTIFACT_REFS = {
    "source": "geometry/source.py",
    "sdf_source": "geometry/sdf_source.py",
    "manifold_source": "geometry/manifold_source.py",
    "step": "geometry/generated.step",
    "preview_glb": "geometry/preview.glb",
    "preview_stl": "geometry/preview.stl",
}


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name not in names:
        return None
    try:
        return json.loads(zf.read(name).decode("utf-8"))
    except Exception:
        return None


def _node_names(node: dict[str, Any], node_id: str) -> set[str]:
    """Candidate names a node may appear under in topology (label/id/name)."""
    out = {node_id}
    for key in ("label", "id", "name"):
        v = node.get(key)
        if v:
            out.add(str(v))
    return out


def build_shape_ir_object_registry(package_path: str | Path) -> dict[str, Any]:
    """Return the Shape IR object registry for a package (does not write it)."""
    package_path = Path(package_path)
    if not package_path.exists():
        return {"format": "aieng.shape_ir_object_registry", "format_version": FORMAT_VERSION,
                "error": f"package not found: {package_path}", "objects": []}

    report = verify_shape_ir_package(package_path)  # package-level facts (PR1)

    with zipfile.ZipFile(package_path, "r") as zf:
        names = set(zf.namelist())
        payload = _read_json(zf, _SHAPE_IR_MEMBER, names) or {}
        topology = _read_json(zf, _TOPOLOGY_MEMBER, names) or {}
        mesh_topology = _read_json(zf, _MESH_TOPOLOGY_MEMBER, names) or {}
        present_artifacts = {k: v for k, v in _ARTIFACT_REFS.items() if v in names}
        source_files = [m for m in (_SHAPE_IR_MEMBER, _TOPOLOGY_MEMBER, _MESH_TOPOLOGY_MEMBER) if m in names]

    nodes = _shape_nodes(payload) if isinstance(payload, dict) else []
    src_key = "parts" if isinstance(payload.get("parts"), list) else (
        "components" if isinstance(payload.get("components"), list) else "parts")

    entities = topology.get("entities") if isinstance(topology, dict) else []
    entities = entities if isinstance(entities, list) else []
    mesh_entities = mesh_topology.get("entities") if isinstance(mesh_topology, dict) else []
    mesh_entities = mesh_entities if isinstance(mesh_entities, list) else []

    solids = [e for e in entities if isinstance(e, dict) and e.get("type") == "solid"]
    faces = [e for e in entities if isinstance(e, dict) and e.get("type") == "face"]
    repr_kind = report.get("representation_kind", "unknown")
    geometry_kind = report.get("geometry_kind", "none")
    fused_mesh = geometry_kind == "mesh" and len(solids) <= 1 and bool(solids or faces)

    def _faces_of(solid_ids: set[str]) -> list[str]:
        out: list[str] = []
        for s in solids:
            if s["id"] in solid_ids:
                out.extend(str(fid) for fid in (s.get("face_ids") or []))
        out.extend(str(f["id"]) for f in faces if f.get("body_id") in solid_ids)
        return out

    objects: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        node_id = _node_id(node, index + 1)
        candidates = _node_names(node, node_id)

        # ── resolve node -> topology entities ──
        sin_solids = [s for s in solids if str(s.get("source_ir_node")) == node_id]
        sin_faces = [f for f in faces if str(f.get("source_ir_node")) == node_id]
        if sin_solids or sin_faces:
            linkage = "source_ir_node"
            solid_ids = {s["id"] for s in sin_solids}
            face_ids = sorted(set(_faces_of(solid_ids)) | {str(f["id"]) for f in sin_faces})
            topo_ids = sorted(solid_ids) + face_ids
        else:
            name_solids = [s for s in solids if str(s.get("name")) in candidates]
            if name_solids:
                linkage = "name_match"
                solid_ids = {s["id"] for s in name_solids}
                face_ids = sorted(set(_faces_of(solid_ids)))
                topo_ids = sorted(solid_ids) + face_ids
            elif fused_mesh:
                linkage = "fused_mesh"
                solid_ids = {s["id"] for s in solids}
                face_ids = sorted(str(f["id"]) for f in faces)
                topo_ids = sorted(solid_ids) + face_ids
            else:
                linkage = "none"
                face_ids = []
                topo_ids = []

        mesh_ids = [str(e.get("id")) for e in mesh_entities
                    if str(e.get("source_ir_node")) == node_id or str(e.get("name")) in candidates]

        params = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
        objects.append({
            "node_id": node_id,
            "source_pointer": f"/{src_key}/{index}",
            "node_type": _node_kind(node),
            "runtime": report.get("runtime"),
            "backend": report.get("backend"),
            "representation_kind": repr_kind,
            "capability_level": report.get("capability_level"),
            "lossiness": report.get("lossiness"),
            "cad_editable": report.get("cad_editable"),
            "editable_parameters": params,
            "artifacts": present_artifacts,
            "topology_entities": topo_ids,
            "mesh_entities": mesh_ids,
            "viewer_selectable_ids": face_ids,  # faces are what the viewer picks
            "linkage": linkage,
            "verification_status_ref": f"{VERIFICATION_PATH}#/nodes/{index}",
        })

    resolved = sum(1 for o in objects if o["linkage"] != "none")
    notes = [
        "Maps Shape IR nodes to generated artifacts and selectable entities.",
        "linkage: source_ir_node (projected) | name_match (executed B-Rep label) | "
        "fused_mesh (mesh backends fuse all nodes into one body) | none.",
    ]
    if fused_mesh:
        notes.append("Mesh backend fused all nodes into one body; per-node identity is not preserved.")

    return {
        "format": "aieng.shape_ir_object_registry",
        "format_version": FORMAT_VERSION,
        "representation": report.get("representation"),
        "representation_kind": repr_kind,
        "runtime": report.get("runtime"),
        "backend": report.get("backend"),
        "executed": report.get("executed"),
        "fallback": report.get("fallback"),
        "geometry_kind": geometry_kind,
        "verification": VERIFICATION_PATH,
        "source_files": source_files,
        "node_count": len(objects),
        "resolved_count": resolved,
        "objects": objects,
        "notes": notes,
    }


def write_shape_ir_object_registry(package_path: str | Path) -> dict[str, Any]:
    """Compute the registry and write it to ``registry/object_registry.json``.
    Returns the registry. Re-raises only if the package can't be rewritten."""
    package_path = Path(package_path)
    registry = build_shape_ir_object_registry(package_path)
    if not package_path.exists():
        return registry
    data = (json.dumps(registry, indent=2, sort_keys=True) + "\n").encode()
    tmp = package_path.with_suffix(".tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename != SHAPE_IR_OBJECT_REGISTRY_PATH:
                    dst.writestr(item, src.read(item.filename))
            dst.writestr(SHAPE_IR_OBJECT_REGISTRY_PATH, data)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return registry
