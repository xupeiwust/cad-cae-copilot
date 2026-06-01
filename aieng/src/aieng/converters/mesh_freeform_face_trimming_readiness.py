"""Freeform face trimming readiness v0 for mesh-to-CAD pipeline.

Assesses whether generated freeform face candidates have enough boundary and
adjacency information to attempt future trimming and mixed stitching. This is a
DIAGNOSTICS-ONLY milestone — it does NOT generate trimmed faces, does NOT stitch,
does NOT sew, and does NOT export STEP.

Output:
  diagnostics/freeform_face_trimming_readiness.json
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.mesh_freeform_brep_face_generation import FREEFORM_BREP_FACES_PATH
from aieng.converters.mesh_freeform_surface_fitting import FREEFORM_SURFACE_FIT_PATH
from aieng.converters.mesh_freeform_surface_readiness import FREEFORM_READINESS_PATH
from aieng.converters.mesh_region_segmentation import MESH_REGION_GRAPH_PATH

TRIMMING_READINESS_PATH = "diagnostics/freeform_face_trimming_readiness.json"

# Thresholds
_BOUNDARY_GOOD_MIN_POINTS = 4
_BOUNDARY_CLOSURE_TOL = 1e-3
_SELF_INTERSECTION_CHECK = True
_QUALITY_READY = 0.70
_QUALITY_PARTIAL = 0.40


def _boundary_closed(loop_uv: list[list[float]]) -> bool:
    """Check if first and last UV points are close."""
    if len(loop_uv) < 2:
        return False
    a, b = loop_uv[0], loop_uv[-1]
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 < _BOUNDARY_CLOSURE_TOL


def _self_intersection_risk(loop_uv: list[list[float]]) -> str:
    """Simple 2D segment intersection test for self-intersection risk.
    Returns 'low', 'medium', 'high', or 'unknown'."""
    if not _SELF_INTERSECTION_CHECK or len(loop_uv) < 4:
        return "unknown"
    n = len(loop_uv)
    for i in range(n):
        a1 = loop_uv[i]
        a2 = loop_uv[(i + 1) % n]
        for j in range(i + 2, n):
            if j == (i - 1) % n or j == (i + 1) % n:
                continue
            b1 = loop_uv[j]
            b2 = loop_uv[(j + 1) % n]
            if _segments_intersect(a1, a2, b1, b2):
                return "high"
    return "low"


def _segments_intersect(
    a1: list[float], a2: list[float], b1: list[float], b2: list[float]
) -> bool:
    """2D segment intersection (proper, excluding shared endpoints)."""
    # Exclude shared endpoints
    eps = 1e-9
    def same(p, q):
        return abs(p[0] - q[0]) < eps and abs(p[1] - q[1]) < eps
    if same(a1, b1) or same(a1, b2) or same(a2, b1) or same(a2, b2):
        return False
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
    return ccw(a1, b1, b2) != ccw(a2, b1, b2) and ccw(a1, a2, b1) != ccw(a1, a2, b2)


def _score_boundary(boundary: dict[str, Any] | None) -> tuple[float, str, dict[str, Any]]:
    """Score boundary quality. Returns (score, status, details)."""
    if not boundary or boundary.get("type") == "none":
        return 0.0, "missing", {"exists": False, "point_count": 0, "closed": False, "self_intersection_risk": "unknown", "status": "missing"}

    btype = str(boundary.get("type", ""))
    pts = int(boundary.get("point_count", 0))
    loop_uv = boundary.get("loop_uv") or []
    closed = _boundary_closed(loop_uv)
    si_risk = _self_intersection_risk(loop_uv)

    details = {
        "exists": True,
        "source": btype,
        "point_count": pts,
        "closed": closed,
        "self_intersection_risk": si_risk,
    }

    if si_risk == "high":
        return 0.1, "poor", {**details, "status": "poor"}
    if btype == "convex_hull":
        # Convex hull is always approximate
        if closed and pts >= _BOUNDARY_GOOD_MIN_POINTS:
            return 0.5, "approximate", {**details, "status": "approximate"}
        return 0.3, "poor", {**details, "status": "poor"}
    if btype == "approximate_uv_loop":
        if closed and pts >= _BOUNDARY_GOOD_MIN_POINTS:
            return 0.8, "good", {**details, "status": "good"}
        return 0.4, "approximate", {**details, "status": "approximate"}
    return 0.3, "approximate", {**details, "status": "approximate"}


def _neighbor_surface_type(
    region_id: str,
    fitted_by_region: dict[str, dict[str, Any]],
    freeform_by_region: dict[str, dict[str, Any]],
    region_graph: dict[str, Any],
) -> str:
    """Determine the surface type of a neighbor region."""
    # Check analytic fits first
    f = fitted_by_region.get(region_id)
    if f:
        return str(f.get("surface_type", "unknown"))
    # Check freeform fits
    ff = freeform_by_region.get(region_id)
    if ff and ff.get("status") == "fitted":
        return "bspline"
    # Check region graph class
    for reg in region_graph.get("regions", []):
        if str(reg.get("region_id")) == region_id:
            return str(reg.get("surface_class_candidate", "unknown"))
    return "unknown"


def _score_adjacency(
    source_region_id: str,
    region_graph: dict[str, Any] | None,
    fitted_by_region: dict[str, dict[str, Any]],
    freeform_by_region: dict[str, dict[str, Any]],
) -> tuple[float, str, list[dict[str, Any]]]:
    """Score adjacency compatibility. Returns (score, status, neighbor_details)."""
    if not region_graph:
        return 0.0, "unknown", []

    # Find neighbors
    neighbors: list[str] = []
    for edge in region_graph.get("adjacency", []):
        ra = str(edge.get("region_a", ""))
        rb = str(edge.get("region_b", ""))
        if ra == source_region_id:
            neighbors.append(rb)
        elif rb == source_region_id:
            neighbors.append(ra)

    if not neighbors:
        return 0.3, "unknown", []

    details: list[dict[str, Any]] = []
    matched = 0
    poor = 0

    for nid in neighbors:
        stype = _neighbor_surface_type(nid, fitted_by_region, freeform_by_region, region_graph)
        if stype in ("plane", "cylinder", "bspline"):
            compat = "good"
            matched += 1
        elif stype == "freeform_candidate":
            # Could be fitted or not
            if freeform_by_region.get(nid) and freeform_by_region[nid].get("status") == "fitted":
                compat = "good"
                matched += 1
            else:
                compat = "approximate"
        elif stype == "noisy_small_region":
            compat = "poor"
            poor += 1
        else:
            compat = "unknown"

        details.append({
            "region_id": nid,
            "surface_type": stype,
            "edge_compatibility": compat,
        })

    total = len(neighbors)
    if matched >= total:
        return 1.0, "good", details
    if poor > 0:
        return 0.3, "poor", details
    if matched + len([d for d in details if d["edge_compatibility"] == "approximate"]) >= total * 0.5:
        return 0.6, "partial", details
    return 0.4, "partial", details


def _face_readiness(
    face: dict[str, Any],
    surface: dict[str, Any] | None,
    readiness: dict[str, Any] | None,
    region_graph: dict[str, Any] | None,
    fitted_by_region: dict[str, dict[str, Any]],
    freeform_by_region: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Assess trimming readiness for a single freeform face candidate."""
    fid = str(face.get("face_id") or face.get("source_surface_id") or "")
    rid = str(face.get("source_region_id") or "")
    status = str(face.get("status") or "")

    if status != "generated":
        return {
            "face_id": fid,
            "source_surface_id": face.get("source_surface_id"),
            "source_region_id": rid,
            "trimming_readiness": "not_ready",
            "quality_score": 0.0,
            "boundary": {"exists": False, "status": "missing", "self_intersection_risk": "unknown"},
            "adjacency": {"status": "unknown", "neighbors": []},
            "blocking_issues": ["face_not_generated"],
            "warnings": [],
            "recommended_next_action": "keep_evidence_only",
        }

    # Boundary scoring
    boundary_info = (surface or {}).get("boundary") or {}
    b_score, b_status, b_details = _score_boundary(boundary_info)

    # Adjacency scoring
    a_score, a_status, a_details = _score_adjacency(rid, region_graph, fitted_by_region, freeform_by_region)

    # Base quality from original readiness
    q_score = 0.0
    if readiness:
        for s in readiness.get("surfaces") or []:
            if str(s.get("source_region_id")) == rid:
                q_score = float(s.get("quality_score") or 0.0)
                break

    # Weighted trimming readiness score
    trimming_score = round(b_score * 0.50 + a_score * 0.30 + min(q_score, 1.0) * 0.20, 4)

    blocking: list[str] = []
    warnings: list[str] = []

    if b_status == "missing":
        blocking.append("boundary_missing")
    if b_status == "poor":
        blocking.append("boundary_poor")
    if b_details.get("self_intersection_risk") == "high":
        blocking.append("self_intersection_risk_high")
    if a_status == "poor":
        blocking.append("adjacency_poor")
    if q_score < _QUALITY_PARTIAL:
        warnings.append("source surface quality_score below partial threshold")

    if trimming_score >= _QUALITY_READY and not blocking:
        t_readiness = "ready"
        action = "attempt_trimmed_face_generation"
    elif trimming_score >= _QUALITY_PARTIAL and "boundary_missing" not in blocking:
        t_readiness = "partial"
        if "boundary_poor" in blocking or b_details.get("self_intersection_risk") == "high":
            action = "improve_boundary"
        else:
            action = "improve_segmentation"
    else:
        t_readiness = "not_ready"
        if "boundary_missing" in blocking:
            action = "improve_boundary"
        else:
            action = "keep_evidence_only"

    return {
        "face_id": fid,
        "source_surface_id": face.get("source_surface_id"),
        "source_region_id": rid,
        "trimming_readiness": t_readiness,
        "quality_score": trimming_score,
        "boundary": b_details,
        "adjacency": {
            "neighbor_count": len(a_details),
            "matched_neighbor_count": sum(1 for n in a_details if n["edge_compatibility"] == "good"),
            "unmatched_neighbor_count": sum(1 for n in a_details if n["edge_compatibility"] in ("poor", "unknown")),
            "neighbors": a_details,
            "status": a_status,
        },
        "blocking_issues": blocking,
        "warnings": warnings,
        "recommended_next_action": action,
    }


def assess_freeform_trimming_readiness(
    freeform_faces: dict[str, Any] | None,
    freeform_fit: dict[str, Any] | None,
    freeform_readiness: dict[str, Any] | None,
    region_graph: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assess trimming readiness for all generated freeform face candidates.

    Returns a single readiness document. Pure. Diagnostic-only."""
    provenance = {
        "source_freeform_faces": FREEFORM_BREP_FACES_PATH,
        "source_freeform_fit": FREEFORM_SURFACE_FIT_PATH,
        "source_region_graph": MESH_REGION_GRAPH_PATH,
        "representation_kind": "mesh",
        "geometry_kind": "mesh",
        "trimmed_faces_generated": False,
        "faces_stitched": False,
        "step_exported": False,
        "cad_editable": False,
        "readiness_only": True,
        "limitations": [
            "Trimming readiness is diagnostic-only. It does NOT generate trimmed faces, "
            "does NOT stitch, does NOT sew, does NOT export STEP.",
        ],
    }

    if not isinstance(freeform_faces, dict):
        return _readiness_doc(
            provenance, status="skipped", reason="missing_freeform_face_candidates",
            faces=[], summary={
                "faces_total": 0, "faces_ready_for_trimming": 0,
                "faces_partial": 0, "faces_not_ready": 0,
                "recommended_next_action": "insufficient_data",
            })

    faces_in = [f for f in (freeform_faces.get("faces") or []) if f.get("status") == "generated"]

    if not faces_in:
        return _readiness_doc(
            provenance, status="skipped", reason="no_generated_freeform_faces",
            faces=[], summary={
                "faces_total": 0, "faces_ready_for_trimming": 0,
                "faces_partial": 0, "faces_not_ready": 0,
                "recommended_next_action": "insufficient_data",
            })

    # Build lookup dicts
    surface_by_region: dict[str, dict[str, Any]] = {}
    if isinstance(freeform_fit, dict):
        for s in freeform_fit.get("surfaces") or []:
            rid = str(s.get("source_region_id") or "")
            if rid:
                surface_by_region[rid] = s

    fitted_by_region: dict[str, dict[str, Any]] = {}
    freeform_by_region: dict[str, dict[str, Any]] = {}

    # Also try to read analytic fits from region_graph provenance hints if available
    # (mesh_brep_reconstruction.py already builds these lookups)

    face_scores: list[dict[str, Any]] = []
    for face in faces_in:
        face_scores.append(_face_readiness(
            face,
            surface_by_region.get(str(face.get("source_region_id"))),
            freeform_readiness,
            region_graph,
            fitted_by_region,
            freeform_by_region,
        ))

    ready_n = sum(1 for f in face_scores if f["trimming_readiness"] == "ready")
    partial_n = sum(1 for f in face_scores if f["trimming_readiness"] == "partial")
    not_ready_n = sum(1 for f in face_scores if f["trimming_readiness"] == "not_ready")
    total_n = len(face_scores)

    if ready_n >= 1:
        overall_status = "ready"
        action = "attempt_trimmed_face_generation"
        reason = f"{ready_n} face(s) ready for future trimming"
    elif partial_n >= 1:
        overall_status = "partial"
        action = "improve_boundary"
        reason = f"{partial_n} face(s) partial, {not_ready_n} not ready"
    else:
        overall_status = "not_ready"
        action = "keep_evidence_only"
        reason = f"{not_ready_n} of {total_n} face(s) not ready"

    summary = {
        "faces_total": total_n,
        "faces_ready_for_trimming": ready_n,
        "faces_partial": partial_n,
        "faces_not_ready": not_ready_n,
        "recommended_next_action": action,
    }

    return _readiness_doc(
        provenance, status=overall_status, reason=reason,
        faces=face_scores, summary=summary,
    )


def _readiness_doc(
    provenance: dict[str, Any],
    *,
    status: str,
    reason: str,
    faces: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "format": "aieng.mesh.freeform_face_trimming_readiness.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": status,
        "source_freeform_faces": FREEFORM_BREP_FACES_PATH,
        "source_freeform_fit": FREEFORM_SURFACE_FIT_PATH,
        "source_region_graph": MESH_REGION_GRAPH_PATH,
        "summary": summary,
        "faces": faces,
        "honesty": {
            "trimmed_faces_generated": False,
            "faces_stitched": False,
            "step_exported": False,
            "cad_editable": False,
            "readiness_only": True,
        },
        "limitations": [
            "Trimming readiness is diagnostic-only and does not generate trimmed faces.",
            "Boundaries are approximate evidence, not exact trimming curves.",
            "Adjacency assessments are advisory and may not reflect exact edge topology.",
            "No stitching, sewing, or STEP export is performed.",
        ],
        "provenance": provenance,
        "claim_boundary": "Advisory trimming readiness assessment for freeform face candidates. "
                          "Does NOT generate trimmed faces, stitch, sew, or export STEP.",
    }


def write_freeform_trimming_readiness(package_path: str | Path) -> dict[str, Any]:
    """Read freeform face candidates + fit + region graph, assess trimming readiness,
    and write diagnostics/freeform_face_trimming_readiness.json. Best-effort."""
    package_path = Path(package_path)
    freeform_faces = None
    freeform_fit = None
    freeform_readiness = None
    region_graph = None
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            if FREEFORM_BREP_FACES_PATH in names:
                freeform_faces = json.loads(zf.read(FREEFORM_BREP_FACES_PATH).decode("utf-8"))
            if FREEFORM_SURFACE_FIT_PATH in names:
                freeform_fit = json.loads(zf.read(FREEFORM_SURFACE_FIT_PATH).decode("utf-8"))
            if FREEFORM_READINESS_PATH in names:
                freeform_readiness = json.loads(zf.read(FREEFORM_READINESS_PATH).decode("utf-8"))
            if MESH_REGION_GRAPH_PATH in names:
                region_graph = json.loads(zf.read(MESH_REGION_GRAPH_PATH).decode("utf-8"))
    except FileNotFoundError:
        pass
    except Exception:
        pass

    readiness = assess_freeform_trimming_readiness(
        freeform_faces, freeform_fit, freeform_readiness, region_graph
    )
    if not package_path.exists():
        return readiness

    members = {
        TRIMMING_READINESS_PATH: (json.dumps(readiness, indent=2, sort_keys=True) + "\n").encode(),
    }
    tmp = package_path.with_suffix(".fftrim.tmp.aieng")
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
    return readiness
