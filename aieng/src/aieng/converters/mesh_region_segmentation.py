"""Mesh region segmentation for smooth topology-optimization mesh outputs.

Analyzes a ``smooth_mesh_proxy`` / mesh-preview body and builds a SOLVER-NEUTRAL mesh
region graph — adjacent faces clustered into regions by normal similarity, each tagged
with a *candidate* surface class (planar / freeform / noisy). This is the first step
toward future mesh-to-B-Rep/NURBS reconstruction; it is observational mesh analysis only.

HONEST SCOPE: the output is a mesh region graph, NOT B-Rep topology. Regions are
``*_candidate`` guesses with confidence, never analytic faces. No STEP export, no
CAD-editability claim, no B-Rep reconstruction here.
"""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from aieng import FORMAT_VERSION

MESH_REGION_GRAPH_PATH = "graph/mesh_region_graph.json"
MESH_REGION_SEGMENTATION_DIAG_PATH = "diagnostics/mesh_region_segmentation.json"
_SHAPE_IR_PATH = "geometry/shape_ir.json"
_MESH_TOPOLOGY_PATH = "geometry/mesh_topology_map.json"
_MANIFEST_PATH = "provenance/conversion_manifest.json"
_PREVIEW_STL = "geometry/preview.stl"

# Shape IR node kinds that carry a ready triangle mesh (vertices/faces).
_MESH_NODE_KINDS = {"smooth_mesh_proxy", "surface_mesh", "mesh_proxy", "triangle_mesh"}


# ── pure segmentation ────────────────────────────────────────────────────────

def _face_normals_areas(V: np.ndarray, F: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tri = V[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    mag = np.linalg.norm(n, axis=1)
    area = 0.5 * mag
    safe = np.where(mag > 0, mag, 1.0)
    unit = n / safe[:, None]
    return unit, area


def _edge_face_map(F: np.ndarray) -> dict[tuple[int, int], list[int]]:
    edges: dict[tuple[int, int], list[int]] = {}
    for fi, (a, b, c) in enumerate(F):
        for u, v in ((a, b), (b, c), (c, a)):
            key = (int(min(u, v)), int(max(u, v)))
            edges.setdefault(key, []).append(fi)
    return edges


def _grow_regions(V: np.ndarray, F: np.ndarray, normal_angle_deg: float):
    """Flood-fill faces into regions across shared edges while adjacent normals stay
    within ``normal_angle_deg``. Returns (region_of, unit_normals, areas, edges,
    non_manifold_count, region_count). Deterministic (seed = ascending face index),
    so region ids are stable across re-runs — surface fitting relies on this."""
    unit, area = _face_normals_areas(V, F)
    edges = _edge_face_map(F)
    nfaces = len(F)
    adj: list[set[int]] = [set() for _ in range(nfaces)]
    non_manifold = 0
    for fl in edges.values():
        if len(fl) > 2:
            non_manifold += 1
        for i in range(len(fl)):
            for j in range(i + 1, len(fl)):
                adj[fl[i]].add(fl[j])
                adj[fl[j]].add(fl[i])
    cos_thresh = math.cos(math.radians(normal_angle_deg))
    region_of = np.full(nfaces, -1, dtype=int)
    rid = 0
    for seed in range(nfaces):
        if region_of[seed] >= 0:
            continue
        region_of[seed] = rid
        stack = [seed]
        while stack:
            f = stack.pop()
            nf = unit[f]
            for nb in adj[f]:
                if region_of[nb] < 0 and float(np.dot(nf, unit[nb])) >= cos_thresh:
                    region_of[nb] = rid
                    stack.append(nb)
        rid += 1
    return region_of, unit, area, edges, non_manifold, rid


def assign_face_regions(vertices: list | np.ndarray, faces: list | np.ndarray, *,
                        normal_angle_deg: float = 20.0):
    """Recover the per-face region assignment (and face normals/areas) for a mesh —
    the deterministic membership behind ``segment_mesh_regions``. Downstream steps
    (e.g. surface fitting) use this to collect the faces of a given ``region_NNN``.
    Returns (region_of, unit_normals, areas)."""
    V = np.asarray(vertices, dtype=float)
    F = np.asarray(faces, dtype=int)
    if V.ndim != 2 or V.shape[1] != 3 or F.ndim != 2 or F.shape[1] != 3 or len(F) == 0:
        return np.zeros(0, dtype=int), np.zeros((0, 3)), np.zeros(0)
    region_of, unit, area, _edges, _nm, _rid = _grow_regions(V, F, normal_angle_deg)
    return region_of, unit, area


def segment_mesh_regions(
    vertices: list | np.ndarray,
    faces: list | np.ndarray,
    *,
    normal_angle_deg: float = 20.0,
    min_region_faces: int = 2,
    small_area_frac: float = 0.01,
    planar_threshold: float = 0.98,
    freeform_threshold: float = 0.9,
) -> dict[str, Any]:
    """Cluster a triangle mesh into regions by normal similarity + edge connectivity.

    Returns ``{regions, adjacency, diagnostics}``. Pure numpy. A region grows across
    shared edges while adjacent face normals stay within ``normal_angle_deg`` — so a
    cube splits into 6 planar regions and a smooth blob stays a few low-planarity
    (freeform) regions. Each region carries a *candidate* surface class + confidence;
    nothing is asserted as a real B-Rep face."""
    V = np.asarray(vertices, dtype=float)
    F = np.asarray(faces, dtype=int)
    warnings: list[str] = []
    if V.ndim != 2 or V.shape[1] != 3 or F.ndim != 2 or F.shape[1] != 3 or len(F) == 0:
        return {"regions": [], "adjacency": [],
                "diagnostics": {"total_faces": 0, "total_regions": 0, "small_regions": 0,
                                "warnings": ["empty or malformed mesh (need Nx3 vertices + Mx3 faces)"],
                                "thresholds": {}}}

    region_of, unit, area, edges, non_manifold, rid = _grow_regions(V, F, normal_angle_deg)
    nfaces = len(F)
    if non_manifold:
        warnings.append(f"{non_manifold} non-manifold edge(s) (>2 incident faces); adjacency is approximate")

    total_area = float(area.sum()) or 1.0
    regions: list[dict[str, Any]] = []
    small_count = 0
    for r in range(rid):
        fid = np.where(region_of == r)[0]
        ar = float(area[fid].sum())
        an = (unit[fid] * area[fid, None]).sum(axis=0)
        ann = float(np.linalg.norm(an))
        avg_n = (an / ann) if ann > 0 else unit[fid[0]]
        planarity = float((np.abs(unit[fid] @ avg_n) * area[fid]).sum() / (ar or 1.0))
        pts = V[F[fid].reshape(-1)]
        bbox = [round(float(pts[:, k].min()), 6) for k in range(3)] + \
               [round(float(pts[:, k].max()), 6) for k in range(3)]
        is_small = len(fid) < min_region_faces or ar < small_area_frac * total_area
        if is_small:
            cls, conf = "noisy_small_region", "low"
            small_count += 1
        elif planarity >= planar_threshold:
            cls = "planar_candidate"
            conf = "high" if planarity >= 0.995 else "medium"
        elif planarity < freeform_threshold:
            cls = "freeform_candidate"
            conf = "medium"
        else:
            cls, conf = "unknown", "low"
        regions.append({
            "region_id": f"region_{r:03d}",
            "face_count": int(len(fid)),
            "area": round(ar, 6),
            "bbox": bbox,
            "average_normal": [round(float(v), 6) for v in avg_n],
            "planarity_score": round(planarity, 4),
            "surface_class_candidate": cls,
            "confidence": conf,
        })

    # region adjacency via edges whose incident faces span >1 region
    pair_edges: dict[tuple[int, int], int] = {}
    for fl in edges.values():
        rs = sorted({int(region_of[f]) for f in fl})
        if len(rs) > 1:
            for i in range(len(rs)):
                for j in range(i + 1, len(rs)):
                    pair_edges[(rs[i], rs[j])] = pair_edges.get((rs[i], rs[j]), 0) + 1
    adjacency = [{"region_a": f"region_{a:03d}", "region_b": f"region_{b:03d}",
                  "shared_boundary_edges": n} for (a, b), n in sorted(pair_edges.items())]
    for reg in regions:
        rn = int(reg["region_id"].split("_")[1])
        reg["neighbors"] = sorted(
            {e["region_b"] for e in adjacency if e["region_a"] == f"region_{rn:03d}"}
            | {e["region_a"] for e in adjacency if e["region_b"] == f"region_{rn:03d}"})

    diagnostics = {
        "total_faces": int(nfaces),
        "total_regions": int(rid),
        "small_regions": int(small_count),
        "class_counts": _class_counts(regions),
        "thresholds": {
            "normal_angle_deg": normal_angle_deg, "min_region_faces": min_region_faces,
            "small_area_frac": small_area_frac, "planar_threshold": planar_threshold,
            "freeform_threshold": freeform_threshold,
        },
        "warnings": warnings,
    }
    return {"regions": regions, "adjacency": adjacency, "diagnostics": diagnostics}


def _class_counts(regions: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in regions:
        c = r["surface_class_candidate"]
        out[c] = out.get(c, 0) + 1
    return out


# ── package integration ──────────────────────────────────────────────────────

def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:
            return None
    return None


def _mesh_node(shape_ir: dict[str, Any]) -> dict[str, Any] | None:
    parts = shape_ir.get("parts") or shape_ir.get("components") or []
    for n in parts:
        if not isinstance(n, dict):
            continue
        kind = str(n.get("type") or n.get("kind") or "").lower()
        if kind in _MESH_NODE_KINDS and n.get("vertices") and n.get("faces"):
            return n
    return None


def _mesh_from_stl(data: bytes) -> tuple[list, list] | None:
    try:
        import io
        import trimesh
        m = trimesh.load(io.BytesIO(data), file_type="stl")
        if hasattr(m, "vertices") and hasattr(m, "faces") and len(m.faces):
            return np.asarray(m.vertices).tolist(), np.asarray(m.faces).tolist()
    except Exception:
        return None
    return None


def read_package_mesh(package_path: str | Path) -> dict[str, Any]:
    """Read the mesh + provenance for a package (the single source of truth for mesh
    analysis steps). Prefers a Shape IR mesh node's inline vertices/faces, else
    geometry/preview.stl. Returns a dict with vertices/faces (or None), source_artifact,
    source_ir_node, design_space_node, runtime, limitations, available, reason."""
    package_path = Path(package_path)
    out: dict[str, Any] = {
        "vertices": None, "faces": None, "source_artifact": None, "source_ir_node": None,
        "design_space_node": None, "runtime": None, "limitations": [], "available": False,
        "reason": None,
    }
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            shape_ir = _read_json(zf, _SHAPE_IR_PATH, names) or {}
            manifest = _read_json(zf, _MANIFEST_PATH, names) or {}
            node = _mesh_node(shape_ir) if isinstance(shape_ir, dict) else None
            if node is not None:
                out["vertices"], out["faces"] = node.get("vertices"), node.get("faces")
                out["source_artifact"] = f"{_SHAPE_IR_PATH}#{node.get('id')}"
                so = node.get("source_optimization") or {}
                out["source_ir_node"] = so.get("source_ir_node") or node.get("id")
                out["design_space_node"] = so.get("design_space_node")
                out["limitations"] = list(so.get("limitations") or [])
            elif _PREVIEW_STL in names:
                got = _mesh_from_stl(zf.read(_PREVIEW_STL))
                if got is not None:
                    out["vertices"], out["faces"] = got
                    out["source_artifact"] = _PREVIEW_STL
            ge = manifest.get("geometry_execution") if isinstance(manifest, dict) else None
            if isinstance(ge, dict):
                out["runtime"] = ge.get("actual_runtime") or ge.get("backend")
                out["source_ir_node"] = out["source_ir_node"] or (manifest.get("topopt_inputs") or {}).get("source_ir_node")
    except FileNotFoundError:
        out["reason"] = "package not found"
        return out
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"could not read package: {type(exc).__name__}: {exc}"
        return out
    if not out["vertices"] or not out["faces"]:
        out["reason"] = ("no mesh available (no smooth_mesh_proxy/mesh_proxy node with "
                         "vertices/faces and no readable geometry/preview.stl)")
        return out
    out["available"] = True
    return out


def build_mesh_region_graph(
    package_path: str | Path, *, normal_angle_deg: float = 20.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a package's mesh (from a Shape IR mesh node, else preview.stl), segment it,
    and return ``(mesh_region_graph, diagnostics)``. Missing mesh degrades honestly
    (empty graph + a recorded reason); never raises."""
    package_path = Path(package_path)
    mesh = read_package_mesh(package_path)
    source_artifact = mesh["source_artifact"]
    if not mesh["available"]:
        return _degraded(mesh["reason"] or "no mesh available", source_artifact)
    vertices, faces = mesh["vertices"], mesh["faces"]
    source_ir_node = mesh["source_ir_node"]
    design_space_node = mesh["design_space_node"]
    runtime = mesh["runtime"]
    limitations = mesh["limitations"]

    seg = segment_mesh_regions(vertices, faces, normal_angle_deg=normal_angle_deg)
    provenance = {
        "source_mesh_artifact": source_artifact,
        "source_ir_node": source_ir_node,
        "design_space_node": design_space_node,
        "runtime": runtime,
        "representation_kind": "mesh",
        "geometry_kind": "mesh",
        "cad_editable": False,
        "is_brep": False,
        "limitations": limitations + [
            "Mesh region graph is observational mesh analysis, not B-Rep topology. Regions "
            "are *_candidate guesses (normal-similarity clustering), not analytic faces.",
        ],
    }
    graph = {
        "format": "aieng.mesh_region_graph",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "regions": seg["regions"],
        "adjacency": seg["adjacency"],
        "provenance": provenance,
        "claim_boundary": "Mesh regions are candidate clusters for future mesh-to-CAD "
                          "reconstruction; this graph does NOT certify B-Rep faces or CAD editability.",
    }
    diagnostics = {
        "format": "aieng.mesh_region_segmentation",
        "schema_version": "0.1",
        "source_mesh_artifact": source_artifact,
        "source_ir_node": source_ir_node,
        "design_space_node": design_space_node,
        **seg["diagnostics"],
        "fallbacks": [] if source_artifact and source_artifact.startswith(_SHAPE_IR_PATH)
        else ["read mesh from preview.stl (no Shape IR mesh node with inline vertices/faces)"]
        if source_artifact else [],
    }
    return graph, diagnostics


def _degraded(reason: str, source_artifact: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = {
        "format": "aieng.mesh_region_graph", "format_version": FORMAT_VERSION, "schema_version": "0.1",
        "regions": [], "adjacency": [],
        "provenance": {"source_mesh_artifact": source_artifact, "representation_kind": "mesh",
                       "geometry_kind": "mesh", "cad_editable": False, "is_brep": False, "available": False},
        "claim_boundary": "No mesh available to segment.",
    }
    diagnostics = {
        "format": "aieng.mesh_region_segmentation", "schema_version": "0.1",
        "total_faces": 0, "total_regions": 0, "small_regions": 0,
        "source_mesh_artifact": source_artifact, "available": False,
        "warnings": [reason], "fallbacks": [reason], "thresholds": {},
    }
    return graph, diagnostics


def write_mesh_region_graph(package_path: str | Path, *, normal_angle_deg: float = 20.0) -> dict[str, Any]:
    """Build + write graph/mesh_region_graph.json and diagnostics/mesh_region_segmentation.json
    into the package. Returns the graph. Best-effort: writes the degraded graph (with a
    recorded reason) when no mesh is available."""
    package_path = Path(package_path)
    graph, diagnostics = build_mesh_region_graph(package_path, normal_angle_deg=normal_angle_deg)
    if not package_path.exists():
        return graph
    members = {
        MESH_REGION_GRAPH_PATH: (json.dumps(graph, indent=2, sort_keys=True) + "\n").encode(),
        MESH_REGION_SEGMENTATION_DIAG_PATH: (json.dumps(diagnostics, indent=2, sort_keys=True) + "\n").encode(),
    }
    tmp = package_path.with_suffix(".tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename not in members:
                    dst.writestr(item, src.read(item.filename))
            for name, data in members.items():
                dst.writestr(name, data)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return graph
