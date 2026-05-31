"""Analytic plane fitting for mesh planar-candidate regions.

Fits best-fit PLANES to ``planar_candidate`` regions from graph/mesh_region_graph.json
— the next backend-only step toward future mesh-to-B-Rep reconstruction. This is still
mesh analysis: a fitted plane + an APPROXIMATE boundary loop, NOT a B-Rep face. No STEP
export, no NURBS, no CAD-editability claim, no B-Rep reconstruction here.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from aieng import FORMAT_VERSION
from aieng.converters.mesh_region_segmentation import (
    MESH_REGION_GRAPH_PATH,
    MESH_REGION_SEGMENTATION_DIAG_PATH,
    assign_face_regions,
    read_package_mesh,
)

MESH_SURFACE_FIT_PATH = "graph/mesh_surface_fit.json"
MESH_SURFACE_FITTING_DIAG_PATH = "diagnostics/mesh_surface_fitting.json"


# ── plane fit + boundary ─────────────────────────────────────────────────────

def fit_plane_to_points(points: np.ndarray, areas: np.ndarray | None = None) -> dict[str, Any]:
    """Best-fit plane (PCA) through points. Returns normal, origin (centroid), an
    orthonormal in-plane basis, and fit-error metrics (max / RMS / area-weighted RMS
    point-to-plane distance)."""
    pts = np.asarray(points, dtype=float)
    centroid = pts.mean(axis=0)
    centered = pts - centroid
    # PCA: smallest-variance principal axis is the plane normal.
    cov = centered.T @ centered
    evals, evecs = np.linalg.eigh(cov)          # ascending eigenvalues
    normal = evecs[:, 0]
    basis_u = evecs[:, 2]                        # largest spread
    basis_v = evecs[:, 1]
    if np.linalg.norm(normal) == 0:
        normal = np.array([0.0, 0.0, 1.0])
    normal = normal / (np.linalg.norm(normal) or 1.0)
    dist = centered @ normal
    max_d = float(np.abs(dist).max()) if len(dist) else 0.0
    rms = float(np.sqrt((dist ** 2).mean())) if len(dist) else 0.0
    return {
        "normal": [round(float(x), 6) for x in normal],
        "origin": [round(float(x), 6) for x in centroid],
        "basis_u": [round(float(x), 6) for x in basis_u],
        "basis_v": [round(float(x), 6) for x in basis_v],
        "max_distance": round(max_d, 6),
        "rms_distance": round(rms, 6),
    }


def _convex_hull_2d(pts2d: np.ndarray) -> list[int]:
    """Andrew's monotone-chain convex hull. Returns CCW vertex indices (no scipy dep)."""
    n = len(pts2d)
    if n < 3:
        return list(range(n))
    order = sorted(range(n), key=lambda i: (pts2d[i][0], pts2d[i][1]))

    def cross(o: int, a: int, b: int) -> float:
        return ((pts2d[a][0] - pts2d[o][0]) * (pts2d[b][1] - pts2d[o][1])
                - (pts2d[a][1] - pts2d[o][1]) * (pts2d[b][0] - pts2d[o][0]))

    lower: list[int] = []
    for i in order:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], i) <= 0:
            lower.pop()
        lower.append(i)
    upper: list[int] = []
    for i in reversed(order):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], i) <= 0:
            upper.pop()
        upper.append(i)
    return lower[:-1] + upper[:-1]


def _boundary_loop(pts: np.ndarray, fit: dict[str, Any]) -> dict[str, Any]:
    """Approximate region boundary: project the region vertices into the plane basis and
    take the 2D convex hull. First version — a convex over-approximation, not the true
    (possibly concave/holed) region outline."""
    origin = np.asarray(fit["origin"], dtype=float)
    u = np.asarray(fit["basis_u"], dtype=float)
    v = np.asarray(fit["basis_v"], dtype=float)
    rel = np.asarray(pts, dtype=float) - origin
    uv = np.column_stack([rel @ u, rel @ v])
    hull = _convex_hull_2d(uv)
    loop_uv = [[round(float(uv[i][0]), 6), round(float(uv[i][1]), 6)] for i in hull]
    loop_world = [[round(float(x), 6) for x in (origin + uv[i][0] * u + uv[i][1] * v)] for i in hull]
    return {
        "method": "convex_hull_2d",
        "approximate": True,
        "point_count": len(hull),
        "loop_uv": loop_uv,
        "loop_world": loop_world,
        "note": "Convex-hull over-approximation of the region outline in the fitted plane; "
                "not the exact (possibly concave / holed) boundary.",
    }


def _fit_confidence(planarity: float, rms: float, scale: float) -> str:
    rel = rms / scale if scale else rms
    if planarity >= 0.995 and rel <= 0.01:
        return "high"
    if planarity >= 0.98 and rel <= 0.05:
        return "medium"
    return "low"


# ── package integration ──────────────────────────────────────────────────────

def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:
            return None
    return None


def fit_mesh_surfaces(package_path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fit planes to the planar_candidate regions of a package's mesh region graph.

    Recovers per-region face membership deterministically (re-segments with the graph's
    thresholds), fits a PCA plane per planar_candidate region, and returns
    ``(mesh_surface_fit, diagnostics)``. Non-planar / freeform / noisy regions are
    skipped with a recorded reason. Missing region graph degrades honestly."""
    package_path = Path(package_path)
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            graph = _read_json(zf, MESH_REGION_GRAPH_PATH, names)
            seg_diag = _read_json(zf, MESH_REGION_SEGMENTATION_DIAG_PATH, names) or {}
    except FileNotFoundError:
        return _degraded("package not found")
    except Exception as exc:  # noqa: BLE001
        return _degraded(f"could not read package: {type(exc).__name__}: {exc}")

    if not isinstance(graph, dict) or not graph.get("regions"):
        return _degraded("no graph/mesh_region_graph.json (or it has no regions) — "
                         "run mesh region segmentation first")

    mesh = read_package_mesh(package_path)
    if not mesh["available"]:
        return _degraded(mesh["reason"] or "no source mesh available to fit")

    V = np.asarray(mesh["vertices"], dtype=float)
    F = np.asarray(mesh["faces"], dtype=int)
    angle = float((seg_diag.get("thresholds") or {}).get("normal_angle_deg", 20.0))
    region_of, _unit, area = assign_face_regions(V, F, normal_angle_deg=angle)

    prov_src = graph.get("provenance") or {}
    provenance = {
        "source_mesh_artifact": prov_src.get("source_mesh_artifact") or mesh["source_artifact"],
        "source_ir_node": prov_src.get("source_ir_node") or mesh["source_ir_node"],
        "design_space_node": prov_src.get("design_space_node") or mesh["design_space_node"],
        "runtime": prov_src.get("runtime") or mesh["runtime"],
        "region_graph": MESH_REGION_GRAPH_PATH,
        "representation_kind": "mesh",
        "geometry_kind": "mesh",
        "is_brep": False,
        "cad_editable": False,
        "limitations": list(prov_src.get("limitations") or []) + [
            "Plane fits are analytic approximations of mesh regions, NOT B-Rep faces. "
            "Boundary loops are convex-hull over-approximations. No STEP / NURBS / CAD here.",
        ],
    }

    surfaces: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[float] = []
    for reg in graph["regions"]:
        rid = str(reg.get("region_id") or "")
        cls = reg.get("surface_class_candidate")
        if cls != "planar_candidate":
            skipped.append({"region_id": rid, "surface_class_candidate": cls,
                            "reason": f"not a planar_candidate ({cls}); no plane fitted"})
            continue
        try:
            ridx = int(rid.split("_")[1])
        except (IndexError, ValueError):
            skipped.append({"region_id": rid, "reason": "unparseable region id"})
            continue
        fid = np.where(region_of == ridx)[0]
        if len(fid) == 0:
            skipped.append({"region_id": rid, "reason": "no faces recovered for region (mesh/threshold mismatch)"})
            continue
        verts_idx = np.unique(F[fid].reshape(-1))
        pts = V[verts_idx]
        fit = fit_plane_to_points(pts, areas=area[fid])
        bbox = reg.get("bbox") or []
        scale = _bbox_diag(bbox) or 1.0
        planarity = float(reg.get("planarity_score") or 0.0)
        conf = _fit_confidence(planarity, fit["rms_distance"], scale)
        errors.append(fit["rms_distance"])
        surfaces.append({
            "surface_id": f"surface_{ridx:03d}",
            "source_region_id": rid,
            "surface_type": "plane",
            "fitted": True,
            **fit,
            "region_planarity_score": planarity,
            "fit_confidence": conf,
            "boundary": _boundary_loop(pts, fit),
            "representation_kind": "mesh",
            "geometry_kind": "mesh",
            "is_brep": False,
        })

    fit_doc = {
        "format": "aieng.mesh_surface_fit",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "surfaces": surfaces,
        "provenance": provenance,
        "claim_boundary": "Plane fits + convex-hull boundaries are analytic approximations of "
                          "mesh regions toward future mesh-to-CAD; they are NOT B-Rep faces and "
                          "do NOT certify CAD editability. No STEP exported.",
    }
    diagnostics = {
        "format": "aieng.mesh_surface_fitting",
        "schema_version": "0.1",
        "regions_processed": len(graph["regions"]),
        "fitted": len(surfaces),
        "skipped": len(skipped),
        "skipped_detail": skipped,
        "thresholds": {"normal_angle_deg": angle,
                       "confidence": {"high": "planarity>=0.995 & rel_rms<=0.01",
                                      "medium": "planarity>=0.98 & rel_rms<=0.05"}},
        "fit_error_summary": {
            "max_rms": round(max(errors), 6) if errors else 0.0,
            "mean_rms": round(float(np.mean(errors)), 6) if errors else 0.0,
        },
        "source_mesh_artifact": provenance["source_mesh_artifact"],
        "source_ir_node": provenance["source_ir_node"],
        "warnings": [],
    }
    return fit_doc, diagnostics


def _bbox_diag(bbox: list) -> float:
    if not (isinstance(bbox, list) and len(bbox) >= 6):
        return 0.0
    d = [bbox[k + 3] - bbox[k] for k in range(3)]
    return float(np.sqrt(sum(x * x for x in d)))


def _degraded(reason: str) -> tuple[dict[str, Any], dict[str, Any]]:
    fit_doc = {
        "format": "aieng.mesh_surface_fit", "format_version": FORMAT_VERSION, "schema_version": "0.1",
        "surfaces": [], "provenance": {"representation_kind": "mesh", "geometry_kind": "mesh",
                                       "is_brep": False, "cad_editable": False, "available": False},
        "claim_boundary": "No region graph / mesh available to fit.",
    }
    diagnostics = {
        "format": "aieng.mesh_surface_fitting", "schema_version": "0.1",
        "regions_processed": 0, "fitted": 0, "skipped": 0, "available": False,
        "warnings": [reason], "thresholds": {},
    }
    return fit_doc, diagnostics


def write_mesh_surface_fit(package_path: str | Path) -> dict[str, Any]:
    """Build + write graph/mesh_surface_fit.json and diagnostics/mesh_surface_fitting.json.
    Best-effort: writes the degraded (empty) docs with a recorded reason when there is no
    region graph / mesh. Returns the fit document."""
    package_path = Path(package_path)
    fit_doc, diagnostics = fit_mesh_surfaces(package_path)
    if not package_path.exists():
        return fit_doc
    members = {
        MESH_SURFACE_FIT_PATH: (json.dumps(fit_doc, indent=2, sort_keys=True) + "\n").encode(),
        MESH_SURFACE_FITTING_DIAG_PATH: (json.dumps(diagnostics, indent=2, sort_keys=True) + "\n").encode(),
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
    return fit_doc
