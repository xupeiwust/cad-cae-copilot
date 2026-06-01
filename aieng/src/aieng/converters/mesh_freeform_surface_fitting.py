"""Freeform/NURBS surface fitting evidence v0 for mesh-to-CAD reconstruction.

Fits approximate BSpline-like surfaces to ``freeform_candidate`` mesh regions.
This is BACKEND-ONLY EVIDENCE — it does NOT create B-Rep faces, does NOT stitch
into solids, does NOT export STEP, and does NOT claim CAD editability.

Output:
  graph/mesh_freeform_surface_fit.json      — fitted surface evidence
  diagnostics/mesh_freeform_surface_fitting.json — fitting diagnostics

Honesty flags (all false):
  is_brep, cad_editable, reconstructed_face, step_exported, stitching_ready
"""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from aieng import FORMAT_VERSION
from aieng.converters.mesh_region_segmentation import (
    MESH_REGION_GRAPH_PATH,
    assign_face_regions,
    read_package_mesh,
)
from aieng.converters.mesh_surface_fitting import MESH_SURFACE_FIT_PATH

FREEFORM_SURFACE_FIT_PATH = "graph/mesh_freeform_surface_fit.json"
FREEFORM_SURFACE_FITTING_DIAG_PATH = "diagnostics/mesh_freeform_surface_fitting.json"

# Fitting parameters
_DEFAULT_DEGREE = 3
_MIN_CONTROL_POINTS = 4          # per direction
_MAX_CONTROL_POINTS = 8          # per direction
_MIN_VERTICES_FOR_FIT = 9        # need at least 3x3 sample grid worth
_MIN_REGION_FACES = 2
_MAX_REL_RMS_ERROR = 0.10        # reject if RMS / scale > this
_MIN_HIGH_CONFIDENCE_SAMPLES = 50
_MIN_MEDIUM_CONFIDENCE_SAMPLES = 15


def _bbox_diag(bbox: list) -> float:
    if not (isinstance(bbox, list) and len(bbox) >= 6):
        return 0.0
    d = [bbox[k + 3] - bbox[k] for k in range(3)]
    return float(np.sqrt(sum(x * x for x in d)))


def _parameterize_region(verts: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project region vertices onto a 2D plane via PCA for UV parameterization.
    Returns (uv_coords, centroid, basis) where basis = (u_axis, v_axis, normal)."""
    pts = np.asarray(verts, dtype=float)
    centroid = pts.mean(axis=0)
    centered = pts - centroid
    cov = centered.T @ centered
    evals, evecs = np.linalg.eigh(cov)
    # largest spread -> u, second -> v, smallest -> normal
    u_axis = evecs[:, 2]
    v_axis = evecs[:, 1]
    normal = evecs[:, 0]
    uv = np.column_stack([centered @ u_axis, centered @ v_axis])
    # normalize to [0, 1]
    uv_min = uv.min(axis=0)
    uv_max = uv.max(axis=0)
    span = uv_max - uv_min
    safe_span = np.where(span > 1e-12, span, 1.0)
    uv_norm = (uv - uv_min) / safe_span
    return uv_norm, centroid, np.column_stack([u_axis, v_axis, normal])


def _bspline_basis_1d(t: np.ndarray, degree: int, n_ctrl: int) -> np.ndarray:
    """Build uniform-clamped B-spline basis matrix B where B[i,j] = basis_j(t_i).
    Uses Cox-de Boor recursion.  t in [0,1]."""
    n = n_ctrl
    p = degree
    # knot vector: p+1 zeros, uniform interior, p+1 ones
    m = n + p + 1
    knots = np.concatenate([
        np.zeros(p),
        np.linspace(0.0, 1.0, m - 2 * p),
        np.ones(p),
    ])
    nt = len(t)
    B = np.zeros((nt, n))
    for i in range(nt):
        ti = float(t[i])
        # find span
        if ti >= 1.0:
            span = n - 1
        elif ti <= 0.0:
            span = p
        else:
            span = int(np.searchsorted(knots[p:m - p], ti, side="right")) - 1
            span = max(p, min(span, n - 1))
        # initialize degree-0 basis
        N = np.zeros(m - 1)
        N[span] = 1.0
        for deg in range(1, p + 1):
            Nnew = np.zeros(m - 1)
            for j in range(m - deg - 1):
                left = knots[j + deg] - knots[j]
                right = knots[j + deg + 1] - knots[j + 1]
                a = (ti - knots[j]) / left if left > 1e-12 else 0.0
                b = (knots[j + deg + 1] - ti) / right if right > 1e-12 else 0.0
                Nnew[j] = a * N[j] + b * N[j + 1]
            N = Nnew
        B[i, :] = N[:n]
    return B


def _fit_bspline_surface(
    pts_world: np.ndarray,
    uv: np.ndarray,
    *,
    degree_u: int = _DEFAULT_DEGREE,
    degree_v: int = _DEFAULT_DEGREE,
    n_ctrl_u: int | None = None,
    n_ctrl_v: int | None = None,
) -> dict[str, Any] | None:
    """Approximate a BSpline surface via least-squares.
    Returns a dict with control_net, knot_summary, fit_error, etc., or None if fit fails."""
    n_pts = len(pts_world)
    if n_pts < _MIN_VERTICES_FOR_FIT:
        return None

    # adaptive control point count
    ncu = n_ctrl_u or max(_MIN_CONTROL_POINTS, min(_MAX_CONTROL_POINTS, int(np.sqrt(n_pts) // 2) + 2))
    ncv = n_ctrl_v or ncu

    try:
        Bu = _bspline_basis_1d(uv[:, 0], degree_u, ncu)
        Bv = _bspline_basis_1d(uv[:, 1], degree_v, ncv)
        # Kronecker product for 2D surface: B = np.kron(Bv, Bu) is huge; solve per coordinate
        # Instead: for each point i, the tensor product basis value for ctrl (j,k) is Bu[i,j]*Bv[i,k]
        # We reshape control_net to ncu*ncv x 3 and solve a least-squares system.
        B = np.zeros((n_pts, ncu, ncv))
        for i in range(n_pts):
            B[i] = np.outer(Bu[i], Bv[i])
        Bmat = B.reshape(n_pts, ncu * ncv)
        ctrl_flat, *_ = np.linalg.lstsq(Bmat, pts_world, rcond=None)
        ctrl = ctrl_flat.reshape(ncu, ncv, 3)

        # Evaluate fitted surface at sample points
        fitted = Bmat @ ctrl_flat
        deltas = pts_world - fitted
        dists = np.linalg.norm(deltas, axis=1)
        rms = float(np.sqrt((dists ** 2).mean()))
        max_err = float(dists.max())
        mean_err = float(dists.mean())

        control_net = [[[round(float(ctrl[j][k][d]), 6) for d in range(3)]
                        for k in range(ncv)] for j in range(ncu)]

        return {
            "degree_u": degree_u,
            "degree_v": degree_v,
            "control_points_u": ncu,
            "control_points_v": ncv,
            "control_net": control_net,
            "knot_summary": {
                "type": "uniform_clamped",
                "degree_u": degree_u,
                "degree_v": degree_v,
                "knots_u_count": ncu + degree_u + 1,
                "knots_v_count": ncv + degree_v + 1,
                "domain_u": [0.0, 1.0],
                "domain_v": [0.0, 1.0],
            },
            "fit_error": {
                "rms": round(rms, 6),
                "max": round(max_err, 6),
                "mean": round(mean_err, 6),
                "unit": "model_unit",
            },
        }
    except Exception:
        return None


def _fit_confidence_freeform(rms: float, scale: float, n_samples: int) -> str:
    """Classify fit confidence for freeform surfaces."""
    rel = rms / scale if scale else rms
    if n_samples >= _MIN_HIGH_CONFIDENCE_SAMPLES and rel <= 0.02:
        return "high"
    if n_samples >= _MIN_MEDIUM_CONFIDENCE_SAMPLES and rel <= 0.08:
        return "medium"
    if n_samples >= _MIN_VERTICES_FOR_FIT:
        return "low"
    return "reject"


def _boundary_loop_freeform(uv: np.ndarray) -> dict[str, Any]:
    """Approximate boundary from the UV parameterization convex hull."""
    try:
        # 2D convex hull of UV points
        from aieng.converters.mesh_surface_fitting import _convex_hull_2d
        hull = _convex_hull_2d(uv)
        loop_uv = [[round(float(uv[i][0]), 6), round(float(uv[i][1]), 6)] for i in hull]
        return {
            "type": "approximate_uv_loop",
            "loop_uv": loop_uv,
            "boundary_source": "projected_region_boundary",
            "approximate": True,
            "point_count": len(hull),
        }
    except Exception:
        return {
            "type": "none",
            "loop_uv": None,
            "boundary_source": "none",
            "approximate": True,
            "point_count": 0,
        }


def fit_freeform_surfaces(package_path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fit approximate BSpline surfaces to freeform_candidate regions.

    Returns ``(freeform_surface_fit, diagnostics)``. Pure numpy. Evidence-only:
    no B-Rep faces, no STEP, no CAD editability claimed."""
    package_path = Path(package_path)
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            graph = _read_json(zf, MESH_REGION_GRAPH_PATH, names)
    except FileNotFoundError:
        return _degraded("package not found")
    except Exception as exc:
        return _degraded(f"could not read package: {type(exc).__name__}: {exc}")

    if not isinstance(graph, dict) or not graph.get("regions"):
        return _degraded("no graph/mesh_region_graph.json (or it has no regions)")

    mesh = read_package_mesh(package_path)
    if not mesh["available"]:
        return _degraded(mesh["reason"] or "no source mesh available")

    V = np.asarray(mesh["vertices"], dtype=float)
    F = np.asarray(mesh["faces"], dtype=int)
    region_of, unit, area = assign_face_regions(V, F)

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
        "limitations": [
            "Freeform surface fits are approximate BSpline-like evidence only. "
            "NOT B-Rep faces, NOT stitched, NOT STEP-exported, NOT CAD-editable.",
        ],
    }

    surfaces: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    considered = fitted = 0
    confidence_dist: dict[str, int] = {}

    for reg in graph.get("regions") or []:
        rid = str(reg.get("region_id") or "")
        cls = reg.get("surface_class_candidate")
        try:
            ridx = int(rid.split("_")[1])
        except (IndexError, ValueError):
            skipped.append({"region_id": rid, "reason": "unparseable region id"})
            continue

        fid = np.where(region_of == ridx)[0]
        if len(fid) == 0:
            skipped.append({"region_id": rid, "reason": "no faces recovered"})
            continue

        verts_idx = np.unique(F[fid].reshape(-1))
        pts = V[verts_idx]
        bbox = reg.get("bbox") or []
        scale = _bbox_diag(bbox) or 1.0
        n_verts = len(verts_idx)

        # Region selection rules
        if cls == "noisy_small_region":
            skipped.append({"region_id": rid, "surface_class_candidate": cls,
                            "reason": "noisy/small region: skipped"})
            continue
        if cls not in ("freeform_candidate", "unknown"):
            # Already analytic-fit (plane/cylinder) — skip unless explicitly asked
            skipped.append({"region_id": rid, "surface_class_candidate": cls,
                            "reason": "already fit as analytic surface (plane/cylinder)"})
            continue
        if n_verts < _MIN_VERTICES_FOR_FIT:
            skipped.append({"region_id": rid, "surface_class_candidate": cls,
                            "reason": f"too few vertices ({n_verts} < {_MIN_VERTICES_FOR_FIT})"})
            continue

        considered += 1
        uv, centroid, basis = _parameterize_region(pts)
        fit = _fit_bspline_surface(pts, uv)
        if fit is None:
            skipped.append({"region_id": rid, "surface_class_candidate": cls,
                            "reason": "BSpline least-squares fit failed"})
            continue

        rms = fit["fit_error"]["rms"]
        conf = _fit_confidence_freeform(rms, scale, n_verts)
        confidence_dist[conf] = confidence_dist.get(conf, 0) + 1

        if conf == "reject" or (scale and rms / scale > _MAX_REL_RMS_ERROR):
            skipped.append({"region_id": rid, "surface_class_candidate": cls,
                            "reason": f"fit rejected (rms={rms:.4g}, rel={rms/scale:.3f})"})
            continue

        fitted += 1
        boundary = _boundary_loop_freeform(uv)
        surfaces.append({
            "surface_id": f"freeform_surface_{ridx:03d}",
            "source_region_id": rid,
            "surface_type": "bspline_surface_candidate",
            "status": "fitted",
            "degree_u": fit["degree_u"],
            "degree_v": fit["degree_v"],
            "control_points_u": fit["control_points_u"],
            "control_points_v": fit["control_points_v"],
            "control_net": fit["control_net"],
            "knot_summary": fit["knot_summary"],
            "uv_domain": {"u": [0.0, 1.0], "v": [0.0, 1.0]},
            "fit_error": fit["fit_error"],
            "confidence": conf,
            "boundary": boundary,
            "sample_count": n_verts,
            "centroid": [round(float(centroid[d]), 6) for d in range(3)],
            "basis_u": [round(float(basis[:, 0][d]), 6) for d in range(3)],
            "basis_v": [round(float(basis[:, 1][d]), 6) for d in range(3)],
            "normal": [round(float(basis[:, 2][d]), 6) for d in range(3)],
            "is_brep": False,
            "cad_editable": False,
            "reconstructed_face": False,
            "step_exported": False,
            "stitching_ready": False,
            "candidate_only": True,
            "approximate": True,
            "limitations": [
                "Approximate BSpline-like surface fit from mesh vertices. NOT an exact NURBS.",
                "Boundary is approximate; not a valid B-Rep trimming curve.",
                "No STEP export, no stitching, no solid reconstruction from this evidence.",
            ],
        })

    fit_doc = {
        "format": "aieng.mesh.freeform_surface_fit.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "surfaces": surfaces,
        "provenance": provenance,
        "claim_boundary": "Approximate BSpline-like surface fits for freeform mesh regions. "
                          "Evidence-only; NOT B-Rep faces, NOT STEP, NOT CAD-editable.",
    }
    diagnostics = {
        "format": "aieng.mesh_freeform_surface_fitting",
        "schema_version": "0.1",
        "regions_considered": considered,
        "regions_fitted": fitted,
        "regions_skipped": len(skipped),
        "skipped_detail": skipped,
        "confidence_distribution": confidence_dist,
        "thresholds": {
            "min_vertices_for_fit": _MIN_VERTICES_FOR_FIT,
            "min_region_faces": _MIN_REGION_FACES,
            "max_rel_rms_error": _MAX_REL_RMS_ERROR,
            "degree": _DEFAULT_DEGREE,
            "min_control_points": _MIN_CONTROL_POINTS,
            "max_control_points": _MAX_CONTROL_POINTS,
            "high_confidence": f">= {_MIN_HIGH_CONFIDENCE_SAMPLES} samples & rel_rms <= 0.02",
            "medium_confidence": f">= {_MIN_MEDIUM_CONFIDENCE_SAMPLES} samples & rel_rms <= 0.08",
        },
        "source_artifacts": [MESH_REGION_GRAPH_PATH, MESH_SURFACE_FIT_PATH],
        "warnings": [] if considered > 0 else ["no freeform_candidate or unknown regions found"],
        "provenance": provenance,
    }
    return fit_doc, diagnostics


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:
            return None
    return None


def _degraded(reason: str) -> tuple[dict[str, Any], dict[str, Any]]:
    fit_doc = {
        "format": "aieng.mesh.freeform_surface_fit.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "surfaces": [],
        "provenance": {"representation_kind": "mesh", "geometry_kind": "mesh",
                       "is_brep": False, "cad_editable": False, "available": False},
        "claim_boundary": "No region graph / mesh available for freeform fitting.",
    }
    diagnostics = {
        "format": "aieng.mesh_freeform_surface_fitting",
        "schema_version": "0.1",
        "regions_considered": 0,
        "regions_fitted": 0,
        "regions_skipped": 0,
        "available": False,
        "status": "skipped",
        "reason": reason,
        "warnings": [reason],
        "thresholds": {},
    }
    return fit_doc, diagnostics


def write_freeform_surface_fit(package_path: str | Path) -> dict[str, Any]:
    """Build + write graph/mesh_freeform_surface_fit.json and
    diagnostics/mesh_freeform_surface_fitting.json. Best-effort."""
    package_path = Path(package_path)
    fit_doc, diagnostics = fit_freeform_surfaces(package_path)
    if not package_path.exists():
        return fit_doc
    members = {
        FREEFORM_SURFACE_FIT_PATH: (json.dumps(fit_doc, indent=2, sort_keys=True) + "\n").encode(),
        FREEFORM_SURFACE_FITTING_DIAG_PATH: (json.dumps(diagnostics, indent=2, sort_keys=True) + "\n").encode(),
    }
    tmp = package_path.with_suffix(".fftmp.aieng")
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
