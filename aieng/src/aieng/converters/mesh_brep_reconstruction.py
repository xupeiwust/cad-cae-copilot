"""Partial B-Rep reconstruction PLANNING from accepted mesh surface fits.

Converts accepted analytic surface fits (planes/cylinders) into backend-neutral B-Rep
FACE CANDIDATES — the first generative step of mesh-to-CAD. It does NOT stitch faces
into a shell, does NOT build a watertight solid, does NOT export STEP, and does NOT do
NURBS/freeform fitting. Every face is a `candidate`; honesty flags say so explicitly.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.mesh_region_segmentation import MESH_REGION_GRAPH_PATH
from aieng.converters.mesh_surface_fitting import MESH_SURFACE_FIT_PATH
from aieng.converters.mesh_reconstruction_readiness import MESH_RECONSTRUCTION_READINESS_PATH
from aieng.converters.mesh_freeform_surface_fitting import FREEFORM_SURFACE_FIT_PATH
from aieng.converters.mesh_freeform_surface_readiness import FREEFORM_READINESS_PATH

MESH_BREP_PLAN_PATH = "graph/mesh_brep_reconstruction_plan.json"
PARTIAL_BREP_SURFACES_PATH = "geometry/partial_brep_surfaces.json"
PARTIAL_BREP_DIAG_PATH = "diagnostics/partial_brep_reconstruction.json"

_ACCEPT_CONFIDENCE = {"high", "medium"}
_MAX_REL_FIT_ERROR = 0.05            # skip a fit whose error/scale exceeds this
_FULL_MIN_FACES = 4
# readiness next-actions that gate OUT candidate creation
_BLOCK_ACTIONS = {"insufficient_data", "mesh_cleanup"}


def _honesty() -> dict[str, Any]:
    return {
        "is_brep": False,                         # the source is a mesh, not a B-Rep
        "reconstructed_faces_are_candidates": True,
        "full_solid": False,
        "watertight": False,
        "cad_editable": "candidate_only",
        "step_exported": False,
    }


def _scale(region: dict[str, Any]) -> float:
    bb = region.get("bbox") or []
    if isinstance(bb, list) and len(bb) >= 6:
        d = [bb[k + 3] - bb[k] for k in range(3)]
        s = (d[0] ** 2 + d[1] ** 2 + d[2] ** 2) ** 0.5
        if s > 0:
            return float(s)
    return 1.0


def _face_candidate(idx: int, region: dict[str, Any], s: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Build a B-Rep face candidate from an accepted surface fit, or return (None, reason)."""
    rid = str(region.get("region_id"))
    stype = s.get("surface_type")
    conf = str(s.get("fit_confidence") or "")
    if conf not in _ACCEPT_CONFIDENCE:
        return None, f"low-confidence fit ({conf or 'none'})"
    scale = _scale(region)

    if stype == "plane":
        b = s.get("boundary") or {}
        loop_world = b.get("loop_world")
        if not loop_world:
            return None, "plane fit has no boundary loop"
        rms = float(s.get("rms_distance") or 0.0)
        if scale and rms / scale > _MAX_REL_FIT_ERROR:
            return None, f"excessive plane fit error (rel_rms={rms / scale:.3f})"
        analytic = {"origin": s.get("origin"), "normal": s.get("normal"),
                    "basis_u": s.get("basis_u"), "basis_v": s.get("basis_v")}
        boundary = {"boundary_source": b.get("method") or "convex_hull",
                    "approximate": True, "loop_uv": b.get("loop_uv"), "loop_world": loop_world}
        fit_error = {"rms": rms, "max": float(s.get("max_distance") or 0.0)}
    elif stype == "cylinder":
        axial = s.get("axial_range")
        if not axial:
            return None, "cylinder fit has no axial range (no boundary evidence)"
        rms = float(s.get("rms_radial") or 0.0)
        r = float(s.get("radius") or 0.0) or 1.0
        if rms / r > _MAX_REL_FIT_ERROR:
            return None, f"excessive cylinder fit error (rel_rms={rms / r:.3f})"
        analytic = {"axis_origin": s.get("origin"), "axis_direction": s.get("axis"),
                    "radius": s.get("radius"), "axial_range": axial}
        boundary = {"boundary_source": "axial_range", "approximate": True,
                    "loop_uv": None, "loop_world": None, "axial_range": axial}
        fit_error = {"rms": rms, "max": float(s.get("max_radial") or 0.0),
                     "normal_consistency": s.get("normal_consistency")}
    else:
        return None, f"unsupported surface_type for partial reconstruction ({stype})"

    return {
        "face_candidate_id": f"face_cand_{idx:03d}",
        "source_region_id": rid,
        "source_surface_id": s.get("surface_id"),
        "surface_type": stype,
        "analytic": analytic,
        "boundary": boundary,
        "fit_confidence": conf,
        "fit_error": fit_error,
        "reconstruction_status": "candidate",
        "is_brep": False,
        "cad_editable": "candidate_only",
    }, None


def plan_partial_brep(
    region_graph: dict[str, Any] | None,
    surface_fit: dict[str, Any] | None,
    readiness: dict[str, Any] | None,
    freeform_fit: dict[str, Any] | None = None,
    freeform_readiness: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Plan partial B-Rep reconstruction from accepted fits. Returns
    ``(plan, surfaces, diagnostics)``. Pure. Produces FACE CANDIDATES only — no shell,
    no solid, no STEP. Gated out (no candidates + warning) when readiness says the mesh
    needs cleanup or is insufficient. Freeform fits are included as evidence-only entries
    optionally annotated with readiness quality scores."""
    prov_src = (surface_fit or {}).get("provenance") or (region_graph or {}).get("provenance") or {}
    provenance = {
        "source_mesh_artifact": prov_src.get("source_mesh_artifact"),
        "source_ir_node": prov_src.get("source_ir_node"),
        "design_space_node": prov_src.get("design_space_node"),
        "runtime": prov_src.get("runtime"),
        "region_graph": MESH_REGION_GRAPH_PATH,
        "surface_fit": MESH_SURFACE_FIT_PATH,
        "freeform_surface_fit": FREEFORM_SURFACE_FIT_PATH,
        "freeform_readiness": FREEFORM_READINESS_PATH,
        "readiness": MESH_RECONSTRUCTION_READINESS_PATH,
        "representation_kind": "mesh",
        "geometry_kind": "mesh",
        **_honesty(),
        "limitations": [
            "Face candidates are analytic approximations of mesh regions. NOT stitched, "
            "NOT a watertight solid, NOT STEP, NOT NURBS, NOT production CAD. Boundaries are "
            "approximate (convex-hull for planes, axial range for cylinders). "
            "Freeform fits are evidence-only; no B-Rep faces generated from them.",
        ],
    }
    warnings: list[str] = []
    missing: list[str] = []
    if not isinstance(region_graph, dict) or not region_graph.get("regions"):
        missing.append(MESH_REGION_GRAPH_PATH)
    if not isinstance(surface_fit, dict):
        missing.append(MESH_SURFACE_FIT_PATH)

    rd = (readiness or {}).get("readiness") or {}
    action = rd.get("recommended_next_action")
    gated = bool(missing) or (action in _BLOCK_ACTIONS)
    if missing:
        warnings.append(f"missing inputs: {', '.join(missing)}")
    if action in _BLOCK_ACTIONS:
        warnings.append(f"readiness recommends '{action}'; no face candidates produced "
                        "until that is addressed")

    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    plan_rows: list[dict[str, Any]] = []
    total_area = 0.0
    candidate_area = 0.0

    freeform_by_region: dict[str, dict[str, Any]] = {}
    if isinstance(freeform_fit, dict):
        freeform_by_region = {
            str(s.get("source_region_id")): s for s in (freeform_fit.get("surfaces") or [])}

    readiness_by_surface: dict[str, dict[str, Any]] = {}
    if isinstance(freeform_readiness, dict):
        readiness_by_surface = {
            str(s.get("source_region_id")): s for s in (freeform_readiness.get("surfaces") or [])}

    if not gated:
        fitted_by_region: dict[str, dict[str, Any]] = {
            str(s.get("source_region_id")): s for s in (surface_fit.get("surfaces") or [])}
        for region in region_graph["regions"]:
            rid = str(region.get("region_id"))
            cls = str(region.get("surface_class_candidate") or "unknown")
            area = float(region.get("area") or 0.0)
            total_area += area
            s = fitted_by_region.get(rid)
            if s is None:
                # Check for freeform evidence
                ff = freeform_by_region.get(rid)
                if ff is not None and ff.get("status") == "fitted":
                    skipped.append({"region_id": rid, "surface_class_candidate": cls,
                                    "reason": "freeform_brep_not_implemented"})
                    row: dict[str, Any] = {"region_id": rid, "eligible": False,
                                           "face_candidate_id": None,
                                           "reconstruction_status": "evidence_only",
                                           "source_freeform_surface_id": ff.get("surface_id"),
                                           "reason": "freeform_brep_not_implemented"}
                    # Optional readiness annotation (low-risk advisory)
                    fr = readiness_by_surface.get(rid)
                    if fr:
                        row["freeform_readiness"] = fr.get("readiness")
                        row["freeform_quality_score"] = fr.get("quality_score")
                        row["freeform_recommended_next_action"] = fr.get("recommended_next_action")
                    plan_rows.append(row)
                    continue
                reason = ("freeform region (no analytic fit)" if cls == "freeform_candidate"
                          else "noisy/small region" if cls == "noisy_small_region"
                          else f"region not fitted ({cls})")
                skipped.append({"region_id": rid, "surface_class_candidate": cls, "reason": reason})
                plan_rows.append({"region_id": rid, "eligible": False, "face_candidate_id": None, "reason": reason})
                continue
            cand, why = _face_candidate(len(candidates), region, s)
            if cand is None:
                skipped.append({"region_id": rid, "surface_class_candidate": cls,
                                "source_surface_id": s.get("surface_id"), "reason": why})
                plan_rows.append({"region_id": rid, "eligible": False, "face_candidate_id": None, "reason": why})
                continue
            candidates.append(cand)
            candidate_area += area
            plan_rows.append({"region_id": rid, "eligible": True,
                              "face_candidate_id": cand["face_candidate_id"],
                              "surface_type": cand["surface_type"]})
    else:
        for region in (region_graph or {}).get("regions") or []:
            total_area += float(region.get("area") or 0.0)

    plane_n = sum(1 for c in candidates if c["surface_type"] == "plane")
    cyl_n = sum(1 for c in candidates if c["surface_type"] == "cylinder")
    freeform_evidence_n = sum(1 for row in plan_rows if row.get("reconstruction_status") == "evidence_only")
    all_have_boundary = all(c["boundary"].get("loop_world") or c["boundary"].get("axial_range")
                            for c in candidates)
    can_partial = (not gated) and len(candidates) >= 1 and (
        readiness is None or bool(rd.get("partial_brep_candidate")) or action == "partial_brep_reconstruction")
    can_full = bool(rd.get("full_brep_candidate")) and len(candidates) >= _FULL_MIN_FACES and all_have_boundary

    summary = {
        "candidate_face_count": len(candidates),
        "plane_candidate_count": plane_n,
        "cylinder_candidate_count": cyl_n,
        "freeform_evidence_count": freeform_evidence_n,
        "skipped_region_count": len(skipped),
        "area_coverage": round(candidate_area / total_area, 4) if total_area else 0.0,
        "can_attempt_partial_brep": bool(can_partial),
        "can_attempt_full_brep": bool(can_full),
    }

    surfaces_doc = {
        "format": "aieng.partial_brep_surfaces",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "face_candidates": candidates,
        "summary": summary,
        "provenance": provenance,
        "claim_boundary": "Analytic face CANDIDATES from mesh fits — not stitched, not a "
                          "watertight solid, not STEP, not production CAD.",
    }
    plan_doc = {
        "format": "aieng.mesh_brep_reconstruction_plan",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "summary": summary,
        "region_plan": plan_rows,
        "readiness_action": action,
        "provenance": provenance,
        "claim_boundary": surfaces_doc["claim_boundary"],
    }
    diagnostics = {
        "format": "aieng.partial_brep_reconstruction",
        "schema_version": "0.1",
        "available": not bool(missing),
        "gated": gated,
        "summary": summary,
        "accepted": [{"region_id": c["source_region_id"], "surface_type": c["surface_type"],
                      "fit_confidence": c["fit_confidence"]} for c in candidates],
        "skipped": skipped,
        "warnings": warnings,
        "thresholds": {"accept_confidence": sorted(_ACCEPT_CONFIDENCE),
                       "max_rel_fit_error": _MAX_REL_FIT_ERROR, "full_min_faces": _FULL_MIN_FACES},
        "provenance": provenance,
    }
    return plan_doc, surfaces_doc, diagnostics


# ── package integration ──────────────────────────────────────────────────────

def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:
            return None
    return None


def build_partial_brep_plan(package_path: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Read the region graph + surface fits + freeform fits + readiness from a package and return
    ``(plan, surfaces, diagnostics)``. Missing inputs degrade honestly (no candidates)."""
    package_path = Path(package_path)
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            region_graph = _read_json(zf, MESH_REGION_GRAPH_PATH, names)
            surface_fit = _read_json(zf, MESH_SURFACE_FIT_PATH, names)
            freeform_fit = _read_json(zf, FREEFORM_SURFACE_FIT_PATH, names)
            freeform_readiness = _read_json(zf, FREEFORM_READINESS_PATH, names)
            readiness = _read_json(zf, MESH_RECONSTRUCTION_READINESS_PATH, names)
    except FileNotFoundError:
        return plan_partial_brep(None, None, None)
    except Exception:  # noqa: BLE001
        return plan_partial_brep(None, None, None)
    return plan_partial_brep(region_graph, surface_fit, readiness, freeform_fit, freeform_readiness)


def write_partial_brep_plan(package_path: str | Path) -> dict[str, Any]:
    """Build + write graph/mesh_brep_reconstruction_plan.json,
    geometry/partial_brep_surfaces.json, diagnostics/partial_brep_reconstruction.json.
    Best-effort; returns the plan document. Never exports STEP / builds geometry."""
    package_path = Path(package_path)
    plan_doc, surfaces_doc, diagnostics = build_partial_brep_plan(package_path)
    if not package_path.exists():
        return plan_doc
    members = {
        MESH_BREP_PLAN_PATH: (json.dumps(plan_doc, indent=2, sort_keys=True) + "\n").encode(),
        PARTIAL_BREP_SURFACES_PATH: (json.dumps(surfaces_doc, indent=2, sort_keys=True) + "\n").encode(),
        PARTIAL_BREP_DIAG_PATH: (json.dumps(diagnostics, indent=2, sort_keys=True) + "\n").encode(),
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
    return plan_doc
