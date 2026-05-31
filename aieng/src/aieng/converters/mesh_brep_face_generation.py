"""Analytic B-Rep FACE generation from partial B-Rep face candidates.

Turns plane/cylinder face candidates (geometry/partial_brep_surfaces.json) into REAL OCC
faces and validates them (closure, validity, area) — an intermediate artifact. It does NOT
stitch faces into a shell, does NOT build a watertight solid, and does NOT export STEP. The
generated OCC faces are validated in memory; only a NEUTRAL JSON status record is persisted.
NURBS/freeform fitting is out of scope.
"""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.mesh_brep_reconstruction import PARTIAL_BREP_SURFACES_PATH

PARTIAL_BREP_FACES_PATH = "geometry/partial_brep_faces.json"
PARTIAL_BREP_FACE_GEN_DIAG_PATH = "diagnostics/partial_brep_face_generation.json"

_AREA_TOL = 1e-6
_STITCH_MIN_FACES = 4


def _honesty() -> dict[str, Any]:
    return {
        "is_brep": False,                 # source is a mesh; these are candidate faces
        "full_solid": False,
        "watertight": False,
        "step_exported": False,
        "cad_editable": "candidate_faces_only",
        "faces_stitched": False,
    }


def _occ():
    """Import the OCC (OCP) symbols needed to build + validate faces, or None if absent."""
    try:
        from OCP.gp import gp_Pnt, gp_Dir, gp_Ax3
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
        from OCP.Geom import Geom_CylindricalSurface
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        from OCP.BRepCheck import BRepCheck_Analyzer
        return {
            "Pnt": gp_Pnt, "Dir": gp_Dir, "Ax3": gp_Ax3,
            "MakePolygon": BRepBuilderAPI_MakePolygon, "MakeFace": BRepBuilderAPI_MakeFace,
            "Cyl": Geom_CylindricalSurface, "GProps": GProp_GProps,
            "BRepGProp": BRepGProp, "Analyzer": BRepCheck_Analyzer,
        }
    except Exception:
        return None


def _face_area(occ, face) -> float:
    props = occ["GProps"]()
    occ["BRepGProp"].SurfaceProperties_s(face, props)
    return float(props.Mass())


def _dedup_loop(loop: list) -> list[list[float]]:
    out: list[list[float]] = []
    for p in loop:
        q = [float(p[0]), float(p[1]), float(p[2])]
        if not out or any(abs(q[k] - out[-1][k]) > 1e-9 for k in range(3)):
            out.append(q)
    # drop a repeated closing vertex
    if len(out) >= 2 and all(abs(out[0][k] - out[-1][k]) < 1e-9 for k in range(3)):
        out = out[:-1]
    return out


def _gen_plane(occ, cand: dict[str, Any]) -> dict[str, Any]:
    b = cand.get("boundary") or {}
    loop = _dedup_loop(b.get("loop_world") or [])
    if len(loop) < 3:
        return {"status": "skipped", "reason": "plane boundary has < 3 distinct points (degenerate)"}
    try:
        mp = occ["MakePolygon"]()
        for p in loop:
            mp.Add(occ["Pnt"](p[0], p[1], p[2]))
        mp.Close()
        if not mp.IsDone():
            return {"status": "failed", "reason": "could not build a closed boundary polygon"}
        wire = mp.Wire()
        mf = occ["MakeFace"](wire, True)        # OnlyPlane=True
        if not mf.IsDone():
            return {"status": "failed", "reason": "BRepBuilderAPI_MakeFace failed for the planar wire"}
        face = mf.Face()
        valid = bool(occ["Analyzer"](face).IsValid())
        area = _face_area(occ, face)
        if area <= _AREA_TOL:
            return {"status": "skipped", "reason": f"degenerate face (area {area:.3g} <= tol)",
                    "geometry_validation": {"area": round(area, 6), "valid": valid}}
        if not valid:
            return {"status": "skipped", "reason": "invalid face (self-intersection / non-planar loop)",
                    "geometry_validation": {"area": round(area, 6), "valid": False}}
        return {"status": "generated",
                "geometry_validation": {"area": round(area, 6), "valid": True,
                                        "loop_closed": True, "boundary_points": len(loop)}}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


def _gen_cylinder(occ, cand: dict[str, Any]) -> dict[str, Any]:
    a = cand.get("analytic") or {}
    b = cand.get("boundary") or {}
    axis_origin = a.get("axis_origin")
    axis_dir = a.get("axis_direction")
    radius = a.get("radius")
    axial = a.get("axial_range") or b.get("axial_range")
    angular = b.get("angular_range") or a.get("angular_range")
    if not (axis_origin and axis_dir and radius and axial):
        return {"status": "skipped", "reason": "skipped_cylinder_boundary_insufficient (missing axis/radius/axial)"}
    if angular is None:
        return {"status": "skipped",
                "reason": "skipped_cylinder_boundary_insufficient (no angular coverage derivable)"}
    try:
        u0, u1 = float(angular[0]), float(angular[1])
        v_len = float(axial[1]) - float(axial[0])
        if u1 <= u0 or v_len <= 0:
            return {"status": "skipped", "reason": "skipped_cylinder_boundary_insufficient (empty angular/axial span)"}
        ax = occ["Ax3"](occ["Pnt"](*[float(x) for x in axis_origin]),
                        occ["Dir"](*[float(x) for x in axis_dir]))
        cyl = occ["Cyl"](ax, float(radius))
        mf = occ["MakeFace"](cyl, u0, u1, 0.0, v_len, 1e-6)
        if not mf.IsDone():
            return {"status": "failed", "reason": "BRepBuilderAPI_MakeFace failed for the cylindrical patch"}
        face = mf.Face()
        valid = bool(occ["Analyzer"](face).IsValid())
        area = _face_area(occ, face)
        if area <= _AREA_TOL:
            return {"status": "skipped", "reason": f"degenerate cylindrical patch (area {area:.3g})",
                    "geometry_validation": {"area": round(area, 6), "valid": valid}}
        return {"status": "generated" if valid else "skipped",
                "reason": None if valid else "invalid cylindrical face",
                "geometry_validation": {"area": round(area, 6), "valid": valid,
                                        "angular_span": round(u1 - u0, 6), "axial_span": round(v_len, 6)}}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


def generate_brep_faces(surfaces_doc: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate + validate OCC faces from partial B-Rep face candidates.

    Returns ``(faces_doc, diagnostics)``. Pure w.r.t. the package (validates faces in
    memory; persists only neutral JSON). No stitching, no solid, no STEP. When OCC/OCP is
    unavailable every candidate is skipped honestly."""
    prov_src = (surfaces_doc or {}).get("provenance") or {}
    provenance = {
        "source_mesh_artifact": prov_src.get("source_mesh_artifact"),
        "source_ir_node": prov_src.get("source_ir_node"),
        "design_space_node": prov_src.get("design_space_node"),
        "runtime": prov_src.get("runtime"),
        "partial_brep_surfaces": PARTIAL_BREP_SURFACES_PATH,
        "representation_kind": "mesh",
        "geometry_kind": "mesh",
        **_honesty(),
        "limitations": [
            "OCC faces are generated + validated as an intermediate artifact only. They are "
            "NOT stitched, NOT a watertight solid, NOT exported to STEP, NOT production CAD.",
        ],
    }
    cands = (surfaces_doc or {}).get("face_candidates") or []
    occ = _occ()
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    if occ is None and cands:
        warnings.append("OCC/OCP (build123d kernel) unavailable; no faces generated")

    for c in cands:
        base = {
            "face_id": c.get("face_candidate_id"),
            "source_region_id": c.get("source_region_id"),
            "source_surface_id": c.get("source_surface_id"),
            "face_type": c.get("surface_type"),
            "fit_confidence": c.get("fit_confidence"),
        }
        if occ is None:
            records.append({**base, "status": "skipped", "reason": "OCC/OCP unavailable"})
            continue
        st = c.get("surface_type")
        if st == "plane":
            res = _gen_plane(occ, c)
        elif st == "cylinder":
            res = _gen_cylinder(occ, c)
        else:
            res = {"status": "skipped", "reason": f"unsupported surface_type ({st})"}
        records.append({**base, **res})

    gen = [r for r in records if r["status"] == "generated"]
    plane_gen = sum(1 for r in gen if r["face_type"] == "plane")
    cyl_gen = sum(1 for r in gen if r["face_type"] == "cylinder")
    summary = {
        "input_candidate_count": len(cands),
        "generated_face_count": len(gen),
        "generated_plane_count": plane_gen,
        "generated_cylinder_count": cyl_gen,
        "skipped_count": sum(1 for r in records if r["status"] == "skipped"),
        "failed_count": sum(1 for r in records if r["status"] == "failed"),
        "can_attempt_stitching": len(gen) >= _STITCH_MIN_FACES,
    }
    faces_doc = {
        "format": "aieng.partial_brep_faces",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "faces": records,
        "summary": summary,
        "provenance": provenance,
        "claim_boundary": "Validated analytic faces (intermediate) — NOT stitched, NOT a "
                          "watertight solid, NOT STEP, NOT production CAD.",
    }
    diagnostics = {
        "format": "aieng.partial_brep_face_generation",
        "schema_version": "0.1",
        "occ_available": occ is not None,
        "summary": summary,
        "faces": records,
        "warnings": warnings,
        "thresholds": {"area_tol": _AREA_TOL, "stitch_min_faces": _STITCH_MIN_FACES},
        "provenance": provenance,
    }
    return faces_doc, diagnostics


# ── package integration ──────────────────────────────────────────────────────

def build_brep_faces(package_path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read geometry/partial_brep_surfaces.json from a package, generate + validate OCC
    faces, and return ``(faces_doc, diagnostics)``. Missing input degrades honestly."""
    package_path = Path(package_path)
    surfaces_doc = None
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            if PARTIAL_BREP_SURFACES_PATH in zf.namelist():
                surfaces_doc = json.loads(zf.read(PARTIAL_BREP_SURFACES_PATH))
    except Exception:  # noqa: BLE001
        surfaces_doc = None
    return generate_brep_faces(surfaces_doc)


def write_brep_faces(package_path: str | Path) -> dict[str, Any]:
    """Build + write geometry/partial_brep_faces.json and
    diagnostics/partial_brep_face_generation.json. Best-effort. Never stitches / exports STEP."""
    package_path = Path(package_path)
    faces_doc, diagnostics = build_brep_faces(package_path)
    if not package_path.exists():
        return faces_doc
    members = {
        PARTIAL_BREP_FACES_PATH: (json.dumps(faces_doc, indent=2, sort_keys=True) + "\n").encode(),
        PARTIAL_BREP_FACE_GEN_DIAG_PATH: (json.dumps(diagnostics, indent=2, sort_keys=True) + "\n").encode(),
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
    return faces_doc
