"""Symbolic B-Rep graph and pointer index for AIENG packages.

This is a CAD-neutral, deterministic layer derived from
``geometry/topology_map.json``.  It borrows the useful idea behind Pointer-CAD
for agent workflows: downstream CAD/CAE actions should refer to explicit face
and edge pointers (``@face:face_001``) instead of vague natural language.

The module does not call CAD kernels or LLMs.  When exact edge topology is not
available, it emits face adjacency relations inferred from bounding boxes and
marks them as low-confidence/virtual rather than pretending they are kernel
edges.
"""
from __future__ import annotations

import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException

SCHEMA_VERSION = "0.1"

BREP_GRAPH_MEMBER = "graph/brep_graph.json"
ENTITY_INDEX_MEMBER = "graph/entity_index.json"
BREP_DIGEST_MEMBER = "ai/brep_digest.md"


def build_brep_graph_for_project(
    settings: Any,
    project_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the B-Rep graph layer for a project, optionally writing it back."""

    from .project_io import get_project, resolve_project_path

    p = payload or {}
    write_files = bool(p.get("write_files", True))
    digest_limit = int(p.get("digest_limit", 40))

    project = get_project(settings, project_id)
    package_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if package_path is None or not package_path.exists():
        raise HTTPException(status_code=404, detail=".aieng package not found")

    topo = _read_json_member(package_path, "geometry/topology_map.json")
    if not topo:
        raise HTTPException(status_code=422, detail="geometry/topology_map.json not found")

    feature_graph = _read_json_member(package_path, "graph/feature_graph.json") or {}
    result = build_brep_graph_from_topology(topo, feature_graph=feature_graph, digest_limit=digest_limit)
    written: list[str] = []
    if write_files:
        files = {
            BREP_GRAPH_MEMBER: json.dumps(result["brep_graph"], indent=2, ensure_ascii=False).encode(),
            ENTITY_INDEX_MEMBER: json.dumps(result["entity_index"], indent=2, ensure_ascii=False).encode(),
            BREP_DIGEST_MEMBER: result["digest"].encode("utf-8"),
        }
        _write_members_atomic(package_path, files)
        written = list(files.keys())

    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "write_files": write_files,
        "written_artifacts": written,
        **result,
    }


def get_brep_graph_for_project(settings: Any, project_id: str) -> dict[str, Any]:
    """Read existing B-Rep graph artifacts from a project package."""

    from .project_io import get_project, resolve_project_path

    project = get_project(settings, project_id)
    package_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if package_path is None or not package_path.exists():
        raise HTTPException(status_code=404, detail=".aieng package not found")

    graph = _read_json_member(package_path, BREP_GRAPH_MEMBER)
    index = _read_json_member(package_path, ENTITY_INDEX_MEMBER)
    digest_raw = _read_bytes_member(package_path, BREP_DIGEST_MEMBER)
    if graph is None or index is None:
        raise HTTPException(status_code=404, detail="B-Rep graph has not been built")
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "brep_graph": graph,
        "entity_index": index,
        "digest": digest_raw.decode("utf-8", errors="replace") if digest_raw else "",
    }


def build_brep_graph_from_topology(
    topology: dict[str, Any],
    *,
    feature_graph: dict[str, Any] | None = None,
    digest_limit: int = 40,
) -> dict[str, Any]:
    """Return ``{brep_graph, entity_index, digest}`` from topology data."""

    feature_graph = feature_graph or {}
    entities = topology.get("entities") or []
    solids_raw = [e for e in entities if isinstance(e, dict) and e.get("type") in {"solid", "body"}]
    faces_raw = [e for e in entities if isinstance(e, dict) and e.get("type") == "face"]
    edges_raw = [e for e in entities if isinstance(e, dict) and e.get("type") == "edge"]

    feature_roles = _feature_roles_by_face(feature_graph)
    bbox = _model_bbox(solids_raw, faces_raw)
    faces = [_normalise_face(f, feature_roles.get(str(f.get("id"))), bbox) for f in faces_raw]
    edges = [_normalise_edge(e) for e in edges_raw]
    relations = _explicit_relations(faces, edges) + _inferred_face_adjacency(faces)
    groups = _selection_groups(faces, feature_graph)
    entity_index = _build_entity_index(faces, edges, groups)

    graph = {
        "schema_version": SCHEMA_VERSION,
        "source": "geometry/topology_map.json",
        "representation": "symbolic_brep_graph",
        "pointer_syntax": {"face": "@face:<face_id>", "edge": "@edge:<edge_id>", "group": "@group:<group_id>"},
        "limitations": [
            "Exact edge/loop topology is included only when present in topology_map.json.",
            "Inferred face adjacency is bbox-based and should be treated as low-confidence.",
            "Pointers are stable only within the current topology snapshot; topology-changing edits require revalidation.",
        ],
        "entities": {
            "solids": solids_raw,
            "faces": faces,
            "edges": edges,
        },
        "relations": relations,
        "selection_groups": groups,
    }
    digest = build_brep_digest(graph, entity_index, max_items=digest_limit)
    return {"brep_graph": graph, "entity_index": entity_index, "digest": digest}


def build_brep_digest(
    brep_graph: dict[str, Any],
    entity_index: dict[str, Any],
    *,
    max_items: int = 40,
) -> str:
    """Compact markdown digest for LLM context windows."""

    faces = brep_graph.get("entities", {}).get("faces") or []
    edges = brep_graph.get("entities", {}).get("edges") or []
    groups = brep_graph.get("selection_groups") or []
    relations = brep_graph.get("relations") or []
    inferred_adj = [r for r in relations if r.get("type") == "face_adjacent_face"]

    lines = [
        "B-Rep Graph Digest",
        "",
        f"Entities: {len(faces)} faces, {len(edges)} explicit edges, {len(inferred_adj)} face-adjacency relations.",
        "Pointer syntax: @face:<id>, @edge:<id>, @group:<id>.",
        "",
    ]
    if groups:
        lines.append("Selection groups:")
        for group in groups[:10]:
            members = ", ".join(group.get("members") or [])
            lines.append(f"- @{group['kind']}:{group['id']}: {group['label']} -> {members}")
        lines.append("")

    lines.append("Important faces:")
    sorted_faces = sorted(
        faces,
        key=lambda f: (0 if f.get("roles") else 1, -(float(f.get("area_mm2") or 0))),
    )
    for face in sorted_faces[:max_items]:
        parts = [f"- @face:{face['id']}", str(face.get("surface_type") or "other")]
        if face.get("area_mm2") is not None:
            parts.append(f"area={float(face['area_mm2']):.1f}mm^2")
        if face.get("normal"):
            n = face["normal"]
            parts.append(f"normal=[{n[0]:.2f},{n[1]:.2f},{n[2]:.2f}]")
        if face.get("radius_mm") is not None:
            parts.append(f"radius={float(face['radius_mm']):.2f}mm")
        if face.get("roles"):
            parts.append("roles=" + ",".join(face["roles"]))
        parts.append(f"label=\"{entity_index.get(face['id'], {}).get('label', face['id'])}\"")
        lines.append("  ".join(parts))

    if inferred_adj:
        lines.append("")
        lines.append("Adjacency examples:")
        for rel in inferred_adj[: min(12, max_items)]:
            lines.append(
                f"- @face:{rel['from']} adjacent to @face:{rel['to']} "
                f"({rel.get('basis', 'unknown')}, confidence={rel.get('confidence', 'unknown')})"
            )

    lines.append("")
    lines.append("Use these pointers in CAD/CAE action proposals; re-build this graph after topology-changing CAD edits.")
    return "\n".join(lines)


def load_or_build_digest(package_path: Path, *, max_items: int = 30) -> str | None:
    """Read digest from package, or build a transient digest from topology."""

    digest_raw = _read_bytes_member(package_path, BREP_DIGEST_MEMBER)
    if digest_raw:
        return digest_raw.decode("utf-8", errors="replace")
    topo = _read_json_member(package_path, "geometry/topology_map.json")
    if not topo:
        return None
    feature_graph = _read_json_member(package_path, "graph/feature_graph.json") or {}
    return build_brep_graph_from_topology(topo, feature_graph=feature_graph, digest_limit=max_items)["digest"]


def _normalise_face(raw: dict[str, Any], feature_roles: list[str] | None, model_bbox: list[float]) -> dict[str, Any]:
    fid = str(raw.get("id") or "face_unknown")
    bbox = _bbox(raw.get("bounding_box"))
    center = raw.get("center") if isinstance(raw.get("center"), list) else _center(bbox)
    normal = _vector(raw.get("normal"))
    surface_type = str(raw.get("surface_type") or "other")
    roles = _roles_for_face(raw, feature_roles or [], model_bbox)
    signature = _entity_signature(surface_type, bbox, raw.get("area"), normal, raw.get("radius"))
    return {
        "id": fid,
        "pointer": f"@face:{fid}",
        "kind": "face",
        "surface_type": surface_type,
        "area_mm2": _float_or_none(raw.get("area")),
        "radius_mm": _float_or_none(raw.get("radius")),
        "normal": normal,
        "center": center,
        "bounding_box": bbox,
        "body_id": raw.get("body_id"),
        "roles": roles,
        "entity_signature": signature,
    }


def _normalise_edge(raw: dict[str, Any]) -> dict[str, Any]:
    eid = str(raw.get("id") or "edge_unknown")
    adj = raw.get("adjacent_faces") or raw.get("face_ids") or []
    return {
        "id": eid,
        "pointer": f"@edge:{eid}",
        "kind": "edge",
        "curve_type": str(raw.get("curve_type") or raw.get("geometry_type") or "unknown"),
        "length_mm": _float_or_none(raw.get("length") or raw.get("length_mm")),
        "bounding_box": _bbox(raw.get("bounding_box")),
        "adjacent_faces": [str(x) for x in adj],
        "entity_signature": _entity_signature(str(raw.get("curve_type") or "edge"), _bbox(raw.get("bounding_box")), raw.get("length"), None, None),
    }


def _explicit_relations(faces: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    face_ids = {f["id"] for f in faces}
    relations: list[dict[str, Any]] = []
    for edge in edges:
        eid = edge["id"]
        for fid in edge.get("adjacent_faces") or []:
            if fid in face_ids:
                relations.append({"type": "face_has_edge", "from": fid, "to": eid, "confidence": "explicit"})
        adj = [fid for fid in edge.get("adjacent_faces") or [] if fid in face_ids]
        if len(adj) >= 2:
            for i, left in enumerate(adj):
                for right in adj[i + 1:]:
                    relations.append({"type": "face_adjacent_face", "from": left, "to": right, "via": eid, "confidence": "explicit"})
    return relations


def _inferred_face_adjacency(faces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(faces):
        for b in faces[i + 1:]:
            if not _bbox_adjacent(a.get("bounding_box") or [], b.get("bounding_box") or []):
                continue
            key = tuple(sorted((a["id"], b["id"])))
            if key in seen:
                continue
            seen.add(key)
            relations.append({
                "type": "face_adjacent_face",
                "from": key[0],
                "to": key[1],
                "via": None,
                "basis": "bbox_touch_or_overlap",
                "confidence": "low",
                "virtual": True,
            })
    return relations


def _selection_groups(faces: list[dict[str, Any]], feature_graph: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    # Feature-backed groups first.
    for feat in feature_graph.get("features") or []:
        refs = feat.get("geometry_refs") or {}
        face_ids = [str(x) for x in refs.get("faces") or []]
        if not face_ids:
            continue
        ftype = str(feat.get("type") or "feature")
        gid = str(feat.get("id") or _safe_id(ftype))
        groups.append({
            "id": gid,
            "kind": "group",
            "pointer": f"@group:{gid}",
            "label": str(feat.get("name") or ftype),
            "role": _feature_type_to_role(ftype),
            "members": face_ids,
            "source": "feature_graph",
        })

    # Geometry-only cylindrical hole groups.
    cylinders = [f for f in faces if f.get("surface_type") == "cylinder" and f.get("radius_mm") is not None]
    by_radius: list[list[dict[str, Any]]] = []
    for face in cylinders:
        r = float(face["radius_mm"])
        target = None
        for group in by_radius:
            gr = float(group[0]["radius_mm"])
            if abs(r - gr) / max(r, gr, 1e-9) <= 0.08:
                target = group
                break
        if target is None:
            by_radius.append([face])
        else:
            target.append(face)
    for idx, group in enumerate(by_radius, 1):
        if len(group) < 2:
            continue
        gid = f"cylindrical_pattern_{idx:03d}"
        if any(g["id"] == gid for g in groups):
            continue
        groups.append({
            "id": gid,
            "kind": "group",
            "pointer": f"@group:{gid}",
            "label": f"{len(group)} cylindrical faces with radius {float(group[0]['radius_mm']):.2f} mm",
            "role": "mounting_candidate",
            "members": [f["id"] for f in group],
            "source": "geometry_heuristic",
        })
    return groups


def _build_entity_index(
    faces: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> dict[str, Any]:
    index: dict[str, Any] = {}
    for face in faces:
        label = _face_label(face)
        index[face["id"]] = {
            "kind": "face",
            "pointer": face["pointer"],
            "label": label,
            "roles": face.get("roles") or [],
            "entity_signature": face.get("entity_signature"),
        }
    for edge in edges:
        index[edge["id"]] = {
            "kind": "edge",
            "pointer": edge["pointer"],
            "label": _edge_label(edge),
            "roles": [],
            "entity_signature": edge.get("entity_signature"),
        }
    for group in groups:
        index[group["id"]] = {
            "kind": "group",
            "pointer": group["pointer"],
            "label": group["label"],
            "roles": [group.get("role")] if group.get("role") else [],
            "members": group.get("members") or [],
        }
    return index


def _roles_for_face(raw: dict[str, Any], feature_roles: list[str], model_bbox: list[float]) -> list[str]:
    roles = list(dict.fromkeys(feature_roles))
    surface = str(raw.get("surface_type") or "")
    normal = _vector(raw.get("normal"))
    center = raw.get("center") if isinstance(raw.get("center"), list) else _center(_bbox(raw.get("bounding_box")))
    if surface == "cylinder":
        roles.append("mounting_candidate")
    if len(model_bbox) == 6 and normal and center:
        zmin, zmax = model_bbox[2], model_bbox[5]
        span = max(zmax - zmin, 1e-9)
        if normal[2] < -0.85 and (center[2] - zmin) / span < 0.2:
            roles.append("support_candidate")
        if normal[2] > 0.85 and (zmax - center[2]) / span < 0.2:
            roles.append("load_candidate")
    return sorted(set(roles))


def _feature_roles_by_face(feature_graph: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for feat in feature_graph.get("features") or []:
        role = _feature_type_to_role(str(feat.get("type") or ""))
        refs = feat.get("geometry_refs") or {}
        for fid in refs.get("faces") or []:
            out.setdefault(str(fid), []).append(role)
    return out


def _feature_type_to_role(ftype: str) -> str:
    if "hole" in ftype or "mount" in ftype:
        return "mounting_candidate"
    if "base" in ftype:
        return "support_candidate"
    if "rib" in ftype or "stiff" in ftype:
        return "stiffener"
    if "fillet" in ftype or "chamfer" in ftype:
        return "stress_relief"
    return "feature_reference"


def _face_label(face: dict[str, Any]) -> str:
    roles = face.get("roles") or []
    prefix = ", ".join(roles) if roles else str(face.get("surface_type") or "face")
    if face.get("surface_type") == "cylinder" and face.get("radius_mm") is not None:
        return f"{prefix} cylindrical face r={float(face['radius_mm']):.2f} mm"
    if face.get("normal"):
        n = face["normal"]
        axis = _normal_axis_label(n)
        return f"{prefix} planar face normal {axis}"
    return prefix


def _edge_label(edge: dict[str, Any]) -> str:
    length = edge.get("length_mm")
    if length is not None:
        return f"{edge.get('curve_type', 'edge')} edge length {float(length):.2f} mm"
    return f"{edge.get('curve_type', 'edge')} edge"


def _normal_axis_label(n: list[float]) -> str:
    axes = [("+X", n[0]), ("-X", -n[0]), ("+Y", n[1]), ("-Y", -n[1]), ("+Z", n[2]), ("-Z", -n[2])]
    label, value = max(axes, key=lambda item: item[1])
    return label if value > 0.75 else f"[{n[0]:.2f},{n[1]:.2f},{n[2]:.2f}]"


def _bbox_adjacent(a: list[float], b: list[float]) -> bool:
    if len(a) != 6 or len(b) != 6:
        return False
    spans = [max(abs(a[3 + i] - a[i]), abs(b[3 + i] - b[i]), 1.0) for i in range(3)]
    tol = max(max(spans) * 1e-4, 1e-4)
    overlap_axes = 0
    touch_axes = 0
    for i in range(3):
        amin, amax, bmin, bmax = a[i], a[i + 3], b[i], b[i + 3]
        overlap = min(amax, bmax) - max(amin, bmin)
        if overlap > tol:
            overlap_axes += 1
        elif abs(amax - bmin) <= tol or abs(bmax - amin) <= tol or overlap >= -tol:
            touch_axes += 1
    # Topology maps from lightweight extractors often store planar faces with a
    # zero-thickness bbox on one axis, so true shared boundaries can show up as
    # "touch" on two axes plus overlap on the third.
    return (overlap_axes >= 2 and touch_axes >= 1) or (overlap_axes >= 1 and overlap_axes + touch_axes >= 3)


def _model_bbox(solids_raw: list[dict[str, Any]], faces_raw: list[dict[str, Any]]) -> list[float]:
    for solid in solids_raw:
        bbox = _bbox(solid.get("bounding_box"))
        if bbox:
            return bbox
    boxes = [_bbox(face.get("bounding_box")) for face in faces_raw]
    boxes = [b for b in boxes if b]
    if not boxes:
        return []
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        min(b[2] for b in boxes),
        max(b[3] for b in boxes),
        max(b[4] for b in boxes),
        max(b[5] for b in boxes),
    ]


def _entity_signature(surface_type: str, bbox: list[float], scalar: Any, normal: list[float] | None, radius: Any) -> str:
    payload = {
        "surface_type": surface_type,
        "bbox": [round(float(x), 3) for x in bbox] if len(bbox) == 6 else [],
        "scalar": round(float(scalar), 3) if _is_number(scalar) else None,
        "normal": [round(float(x), 3) for x in normal] if normal else None,
        "radius": round(float(radius), 3) if _is_number(radius) else None,
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    # Small deterministic non-cryptographic hash is enough for re-identification hints.
    h = 2166136261
    for ch in text:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return f"sig_{h:08x}"


def _bbox(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 6:
        return []
    try:
        return [float(x) for x in value]
    except (TypeError, ValueError):
        return []


def _center(bbox: list[float]) -> list[float] | None:
    if len(bbox) != 6:
        return None
    return [(bbox[0] + bbox[3]) / 2, (bbox[1] + bbox[4]) / 2, (bbox[2] + bbox[5]) / 2]


def _vector(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    try:
        vec = [float(x) for x in value]
    except (TypeError, ValueError):
        return None
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 1e-12:
        return None
    return [x / norm for x in vec]


def _float_or_none(value: Any) -> float | None:
    return float(value) if _is_number(value) else None


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _safe_id(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", text).strip("_") or "group"


def _read_json_member(package_path: Path, member: str) -> dict[str, Any] | None:
    raw = _read_bytes_member(package_path, member)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _read_bytes_member(package_path: Path, member: str) -> bytes | None:
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            if member in zf.namelist():
                return zf.read(member)
    except Exception:
        return None
    return None


def _write_members_atomic(package_path: Path, files: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".tmp.aieng")
    try:
        with zipfile.ZipFile(package_path, "r") as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename not in files:
                    dst.writestr(item, src.read(item.filename))
            for name, content in files.items():
                dst.writestr(name, content)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def pick_face_at_point(
    package_path: Path,
    px: float,
    py: float,
    pz: float,
) -> dict[str, Any] | None:
    """Find the B-Rep face that best matches a 3D pick point from the viewer.

    Scoring (lower is better):
    - Planar face: weighted sum of point-to-plane distance and distance to bbox center.
    - Cylindrical face: difference between radial distance and radius, plus Z-extent penalty.
    - Fallback: distance to face center.
    """
    graph = _read_json_member(package_path, BREP_GRAPH_MEMBER)
    if not graph:
        return None
    faces = (graph.get("entities") or {}).get("faces") or []
    if not faces:
        return None

    best: dict[str, Any] | None = None
    best_score = float("inf")

    for face in faces:
        bbox = _bbox(face.get("bounding_box"))
        if len(bbox) != 6:
            continue
        center = face.get("center") if isinstance(face.get("center"), list) else _center(bbox)
        if not center:
            continue

        cx, cy, cz = center
        dx = px - cx
        dy = py - cy
        dz = pz - cz
        dist_to_center = math.sqrt(dx * dx + dy * dy + dz * dz)

        surface_type = str(face.get("surface_type") or "other")
        score = dist_to_center

        if surface_type == "plane":
            normal = _vector(face.get("normal"))
            if normal and dist_to_center > 1e-9:
                # Point-to-plane distance
                nx, ny, nz = normal
                d = nx * cx + ny * cy + nz * cz
                plane_dist = abs(nx * px + ny * py + nz * pz - d)
                # Distance to bbox center (down-weighted)
                score = plane_dist * 0.7 + dist_to_center * 0.3
            # Penalize if point is far outside bbox
            tol = max(bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2], 1.0) * 0.3
            outside_penalty = 0.0
            for i, (amin, amax, coord) in enumerate(zip(bbox[:3], bbox[3:], [px, py, pz])):
                if coord < amin - tol:
                    outside_penalty += (amin - tol - coord) ** 2
                elif coord > amax + tol:
                    outside_penalty += (coord - amax - tol) ** 2
            score += math.sqrt(outside_penalty) * 2.0

        elif surface_type == "cylinder":
            radius = _float_or_none(face.get("radius_mm"))
            if radius is not None:
                # Distance from point to cylinder axis (assumed Z-aligned through center)
                radial_dist = math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
                score = abs(radial_dist - radius) * 0.8 + abs(dz) * 0.2
            # Penalize if outside Z-extent
            zmin, zmax = bbox[2], bbox[5]
            tol_z = max(zmax - zmin, 1.0) * 0.2
            if pz < zmin - tol_z:
                score += (zmin - tol_z - pz) ** 2
            elif pz > zmax + tol_z:
                score += (pz - zmax - tol_z) ** 2

        else:
            # Generic: distance to center, with bbox containment bonus
            tol = max(bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2], 1.0) * 0.2
            outside = False
            for amin, amax, coord in zip(bbox[:3], bbox[3:], [px, py, pz]):
                if coord < amin - tol or coord > amax + tol:
                    outside = True
                    break
            if outside:
                score *= 1.5

        if score < best_score:
            best_score = score
            best = face

    if best is None:
        return None

    # Build a rich result with pointer, label, and distance context
    label = _face_label(best)
    return {
        "pointer": best.get("pointer"),
        "face_id": best["id"],
        "surface_type": best.get("surface_type"),
        "area_mm2": best.get("area_mm2"),
        "radius_mm": best.get("radius_mm"),
        "normal": best.get("normal"),
        "center": best.get("center"),
        "roles": best.get("roles") or [],
        "label": label,
        "score": round(best_score, 4),
    }


__all__ = [
    "BREP_DIGEST_MEMBER",
    "BREP_GRAPH_MEMBER",
    "ENTITY_INDEX_MEMBER",
    "SCHEMA_VERSION",
    "build_brep_digest",
    "build_brep_graph_for_project",
    "build_brep_graph_from_topology",
    "get_brep_graph_for_project",
    "load_or_build_digest",
    "pick_face_at_point",
]
