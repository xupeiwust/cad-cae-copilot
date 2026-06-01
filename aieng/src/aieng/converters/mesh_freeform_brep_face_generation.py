"""Freeform B-Rep FACE candidate generation v0 from BSpline surface fits.

Turns high-quality freeform fitting evidence into validated OCC face candidates.
This is BACKEND-ONLY and CANDIDATE-ONLY — faces are NOT stitched into shells,
NOT sewn into solids, and NOT exported to STEP. Every face carries explicit
honesty flags stating it is a candidate only.

Output:
  geometry/partial_freeform_brep_faces.json      — face candidate records
  diagnostics/freeform_brep_face_generation.json — generation diagnostics
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.mesh_freeform_surface_fitting import FREEFORM_SURFACE_FIT_PATH
from aieng.converters.mesh_freeform_surface_readiness import FREEFORM_READINESS_PATH

FREEFORM_BREP_FACES_PATH = "geometry/partial_freeform_brep_faces.json"
FREEFORM_BREP_FACE_GEN_DIAG_PATH = "diagnostics/freeform_brep_face_generation.json"

# Eligibility thresholds
_MIN_QUALITY_SCORE = 0.70
_ALLOW_PARTIAL = False  # v0: only "ready" surfaces become face candidates


def _occ() -> dict[str, Any] | None:
    """Import OCP symbols needed for BSpline face creation, or None if unavailable."""
    try:
        from OCP.TColgp import TColgp_Array2OfPnt
        from OCP.gp import gp_Pnt
        from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        return {
            "ArrPnt": TColgp_Array2OfPnt,
            "Pnt": gp_Pnt,
            "FitSurf": GeomAPI_PointsToBSplineSurface,
            "MakeFace": BRepBuilderAPI_MakeFace,
            "Analyzer": BRepCheck_Analyzer,
            "GProps": GProp_GProps,
            "BRepGProp": BRepGProp,
        }
    except Exception:
        return None


def _face_area(occ: dict[str, Any], face) -> float:
    props = occ["GProps"]()
    occ["BRepGProp"].SurfaceProperties_s(face, props)
    return float(props.Mass())


def _build_bspline_face(occ: dict[str, Any], control_net: list[list[list[float]]]) -> tuple[Any | None, str | None]:
    """Build a TopoDS_Face from a control-net grid using GeomAPI_PointsToBSplineSurface.

    Returns (face, reason).  This is a best-effort approximation: the fitted surface
    in mesh_freeform_surface_fit.json was created by least-squares B-spline basis
    evaluation, while GeomAPI_PointsToBSplineSurface interpolates/fits the same
    control points into a new OCC surface — the resulting geometry is a close
    approximation, not an exact reproduction of the original fit.
    """
    rows = len(control_net)
    cols = len(control_net[0]) if rows else 0
    if rows < 2 or cols < 2:
        return None, "control_net too small for surface (need at least 2x2)"

    try:
        arr = occ["ArrPnt"](1, rows, 1, cols)
        for i in range(rows):
            for j in range(cols):
                p = control_net[i][j]
                arr.SetValue(i + 1, j + 1, occ["Pnt"](float(p[0]), float(p[1]), float(p[2])))

        fitter = occ["FitSurf"](arr)
        if not fitter.IsDone():
            return None, "GeomAPI_PointsToBSplineSurface failed to build surface"

        surface = fitter.Surface()
        mf = occ["MakeFace"](surface, 1e-6)
        if not mf.IsDone():
            return None, "BRepBuilderAPI_MakeFace failed for BSpline surface"

        face = mf.Face()
        valid = bool(occ["Analyzer"](face).IsValid())
        area = _face_area(occ, face)
        return face, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _eligibility(surface: dict[str, Any], readiness: dict[str, Any] | None) -> tuple[bool, str]:
    """Check if a surface is eligible for face generation."""
    if surface.get("status") != "fitted":
        return False, "surface_status_not_fitted"

    rid = str(surface.get("source_region_id") or "")
    # Find matching readiness entry
    r_entry = None
    if readiness:
        for s in readiness.get("surfaces") or []:
            if str(s.get("source_region_id")) == rid:
                r_entry = s
                break

    if r_entry is None:
        return False, "no_readiness_entry_for_surface"

    r_status = str(r_entry.get("readiness") or "")
    q_score = float(r_entry.get("quality_score") or 0.0)

    if r_status == "not_ready":
        return False, "readiness_not_ready"
    if r_status == "partial" and not _ALLOW_PARTIAL:
        return False, "readiness_partial_not_allowed_in_v0"
    if r_status == "partial" and q_score < _MIN_QUALITY_SCORE:
        return False, "partial_quality_score_below_threshold"
    if q_score < _MIN_QUALITY_SCORE:
        return False, "quality_score_below_threshold"

    ctrl_u = int(surface.get("control_points_u", 0))
    ctrl_v = int(surface.get("control_points_v", 0))
    if ctrl_u < 2 or ctrl_v < 2:
        return False, "control_net_too_small"

    net = surface.get("control_net")
    if not isinstance(net, list) or len(net) < 2:
        return False, "control_net_missing_or_degenerate"

    return True, ""


def generate_freeform_brep_faces(
    freeform_fit: dict[str, Any] | None,
    freeform_readiness: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate validated OCC face candidates from ready freeform surfaces.

    Returns ``(faces_doc, diagnostics)``. Pure. Candidate-only: no stitching, no
    solid, no STEP. Degrades honestly when OCP is unavailable or no surfaces are ready."""
    prov_src = (freeform_fit or {}).get("provenance") or {}
    provenance = {
        "source_mesh_artifact": prov_src.get("source_mesh_artifact"),
        "source_ir_node": prov_src.get("source_ir_node"),
        "design_space_node": prov_src.get("design_space_node"),
        "runtime": prov_src.get("runtime"),
        "freeform_surface_fit": FREEFORM_SURFACE_FIT_PATH,
        "freeform_readiness": FREEFORM_READINESS_PATH,
        "representation_kind": "mesh",
        "geometry_kind": "mesh",
        "is_brep": False,
        "cad_editable": False,
        "step_exported": False,
        "limitations": [
            "Freeform face candidates are intermediate OCC artifacts only. NOT stitched, "
            "NOT a watertight solid, NOT exported to STEP, NOT production CAD.",
        ],
    }

    occ = _occ()
    surfaces_in = (freeform_fit or {}).get("surfaces") or []
    records: list[dict[str, Any]] = []
    warnings: list[str] = []

    if occ is None:
        warnings.append("OCP/OCC (build123d kernel) unavailable; no freeform faces generated")
        for surf in surfaces_in:
            records.append(_record_skipped(surf, "OCC/OCP unavailable"))
    elif not surfaces_in:
        warnings.append("no freeform surfaces in fit artifact")
    else:
        for surf in surfaces_in:
            eligible, reason = _eligibility(surf, freeform_readiness)
            if not eligible:
                records.append(_record_skipped(surf, reason))
                continue

            face, err = _build_bspline_face(occ, surf.get("control_net", []))
            if face is None:
                records.append(_record_failed(surf, err or "unknown"))
                continue

            area = _face_area(occ, face)
            valid = bool(occ["Analyzer"](face).IsValid())
            rid = str(surf.get("source_region_id") or "")
            r_entry = None
            if freeform_readiness:
                for s in freeform_readiness.get("surfaces") or []:
                    if str(s.get("source_region_id")) == rid:
                        r_entry = s
                        break

            records.append({
                "face_id": f"freeform_face_{len(records):03d}",
                "source_surface_id": surf.get("surface_id"),
                "source_region_id": rid,
                "surface_type": "bspline",
                "status": "generated",
                "skip_reason": None,
                "quality_score": r_entry.get("quality_score") if r_entry else None,
                "readiness": r_entry.get("readiness") if r_entry else None,
                "degree_u": surf.get("degree_u"),
                "degree_v": surf.get("degree_v"),
                "control_net_shape": [surf.get("control_points_u"), surf.get("control_points_v")],
                "boundary_status": (surf.get("boundary") or {}).get("type", "none"),
                "occ_validation": {
                    "occ_available": True,
                    "face_created": True,
                    "valid": valid,
                    "area": round(area, 6),
                    "warnings": [] if valid else ["BRepCheck_Analyzer reports invalid face"],
                },
                "honesty": {
                    "is_brep_face_candidate": True,
                    "faces_stitched": False,
                    "watertight": False,
                    "full_solid": False,
                    "step_exported": False,
                    "cad_editable": "candidate_face_only",
                    "production_ready": False,
                },
            })

    gen = [r for r in records if r["status"] == "generated"]
    skipped = [r for r in records if r["status"] == "skipped"]
    failed = [r for r in records if r["status"] == "failed"]

    summary = {
        "input_surface_count": len(surfaces_in),
        "generated_face_count": len(gen),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "can_attempt_future_freeform_stitching": len(gen) >= 2 and occ is not None,
    }

    faces_doc = {
        "format": "aieng.mesh.freeform_brep_faces.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "faces": records,
        "summary": summary,
        "provenance": provenance,
        "claim_boundary": "Validated freeform BSpline face CANDIDATES — NOT stitched, "
                          "NOT a watertight solid, NOT STEP, NOT production CAD.",
    }
    diagnostics = {
        "format": "aieng.freeform_brep_face_generation",
        "schema_version": "0.1",
        "occ_available": occ is not None,
        "summary": summary,
        "thresholds": {
            "min_quality_score": _MIN_QUALITY_SCORE,
            "allow_partial": _ALLOW_PARTIAL,
        },
        "faces": records,
        "warnings": warnings,
        "provenance": provenance,
    }
    return faces_doc, diagnostics


def _record_skipped(surf: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "face_id": None,
        "source_surface_id": surf.get("surface_id"),
        "source_region_id": surf.get("source_region_id"),
        "surface_type": "bspline",
        "status": "skipped",
        "skip_reason": reason,
        "quality_score": None,
        "readiness": None,
        "occ_validation": {"occ_available": None, "face_created": False, "valid": False},
        "honesty": {
            "is_brep_face_candidate": False,
            "faces_stitched": False,
            "watertight": False,
            "full_solid": False,
            "step_exported": False,
            "cad_editable": "candidate_face_only",
            "production_ready": False,
        },
    }


def _record_failed(surf: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "face_id": None,
        "source_surface_id": surf.get("surface_id"),
        "source_region_id": surf.get("source_region_id"),
        "surface_type": "bspline",
        "status": "failed",
        "skip_reason": reason,
        "quality_score": None,
        "readiness": None,
        "occ_validation": {"occ_available": True, "face_created": False, "valid": False},
        "honesty": {
            "is_brep_face_candidate": False,
            "faces_stitched": False,
            "watertight": False,
            "full_solid": False,
            "step_exported": False,
            "cad_editable": "candidate_face_only",
            "production_ready": False,
        },
    }


def write_freeform_brep_faces(package_path: str | Path) -> dict[str, Any]:
    """Read freeform fit + readiness artifacts, generate face candidates, and write
    geometry/partial_freeform_brep_faces.json and diagnostics/freeform_brep_face_generation.json.
    Best-effort; never raises."""
    package_path = Path(package_path)
    freeform_fit = None
    freeform_readiness = None
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            if FREEFORM_SURFACE_FIT_PATH in names:
                freeform_fit = json.loads(zf.read(FREEFORM_SURFACE_FIT_PATH).decode("utf-8"))
            if FREEFORM_READINESS_PATH in names:
                freeform_readiness = json.loads(zf.read(FREEFORM_READINESS_PATH).decode("utf-8"))
    except FileNotFoundError:
        pass
    except Exception:
        pass

    faces_doc, diagnostics = generate_freeform_brep_faces(freeform_fit, freeform_readiness)
    if not package_path.exists():
        return faces_doc

    members = {
        FREEFORM_BREP_FACES_PATH: (json.dumps(faces_doc, indent=2, sort_keys=True) + "\n").encode(),
        FREEFORM_BREP_FACE_GEN_DIAG_PATH: (json.dumps(diagnostics, indent=2, sort_keys=True) + "\n").encode(),
    }
    tmp = package_path.with_suffix(".ffbrep.tmp.aieng")
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
    return faces_doc
