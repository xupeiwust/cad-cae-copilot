"""Mesh reconstruction readiness analysis.

Reads the mesh region graph + analytic surface fits and judges how ready a smooth mesh
is for FUTURE partial/full mesh-to-B-Rep/NURBS reconstruction. Pure analysis — it does
NOT reconstruct anything, export STEP, or create B-Rep/NURBS geometry. Outputs honest
coverage/quality metrics, a readiness classification, blocking issues, and an optional
per-region plan.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.mesh_region_segmentation import (
    MESH_REGION_GRAPH_PATH,
    MESH_REGION_SEGMENTATION_DIAG_PATH,
)
from aieng.converters.mesh_surface_fitting import (
    MESH_SURFACE_FIT_PATH,
    MESH_SURFACE_FITTING_DIAG_PATH,
)

MESH_RECONSTRUCTION_READINESS_PATH = "diagnostics/mesh_reconstruction_readiness.json"
MESH_RECONSTRUCTION_PLAN_PATH = "graph/mesh_reconstruction_plan.json"
_MANIFEST_PATH = "provenance/conversion_manifest.json"

# Readiness thresholds (area fractions / counts). Conservative on purpose.
_PARTIAL_MIN_FITTED_AREA = 0.5
_FULL_MIN_FITTED_AREA = 0.9
_FULL_MIN_FITTED_REGIONS = 4          # a closed B-Rep solid needs >= 4 faces
_FULL_MIN_ADJ_COVERAGE = 0.8
_FULL_MAX_UNFIT_AREA = 0.1
_NOISY_CLEANUP_AREA = 0.3
_LARGE_UNFIT_REGION_AREA = 0.1        # a single unfit region this large is a blocker


def assess_reconstruction_readiness(
    region_graph: dict[str, Any] | None,
    surface_fit: dict[str, Any] | None,
    seg_diag: dict[str, Any] | None = None,
    fit_diag: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Judge reconstruction readiness from the region graph + surface fits.

    Returns ``(readiness, plan)``. Pure. Honest: this is an analysis of mesh evidence,
    never a B-Rep — ``is_brep``/``cad_editable`` stay false. Missing inputs degrade to
    ``recommended_next_action = insufficient_data``."""
    missing: list[str] = []
    if not isinstance(region_graph, dict) or not region_graph.get("regions"):
        missing.append(MESH_REGION_GRAPH_PATH)
    if not isinstance(surface_fit, dict):
        missing.append(MESH_SURFACE_FIT_PATH)

    prov_src = (region_graph or {}).get("provenance") or {}
    provenance = {
        "source_mesh_artifact": prov_src.get("source_mesh_artifact"),
        "source_ir_node": prov_src.get("source_ir_node"),
        "design_space_node": prov_src.get("design_space_node"),
        "runtime": prov_src.get("runtime"),
        "region_graph": MESH_REGION_GRAPH_PATH,
        "surface_fit": MESH_SURFACE_FIT_PATH,
        "representation_kind": "mesh",
        "geometry_kind": "mesh",
        "is_brep": False,
        "cad_editable": False,
        "limitations": [
            "Reconstruction readiness is an analysis of mesh fit evidence, NOT a B-Rep. "
            "No geometry is reconstructed, no STEP/NURBS produced, nothing is CAD-editable.",
        ],
    }

    if missing:
        readiness = _readiness_doc(
            provenance, partial=False, full=False, action="insufficient_data",
            coverage={}, quality={}, blocking=[{"issue": "missing_inputs", "detail": missing}],
            reasoning=[f"required inputs missing: {', '.join(missing)}"], available=False)
        plan = _plan_doc(provenance, [])
        return readiness, plan

    regions = region_graph["regions"]
    adjacency = region_graph.get("adjacency") or []
    surfaces = surface_fit.get("surfaces") or []

    # region area + class
    area_of: dict[str, float] = {}
    class_of: dict[str, str] = {}
    for r in regions:
        rid = str(r.get("region_id"))
        area_of[rid] = float(r.get("area") or 0.0)
        class_of[rid] = str(r.get("surface_class_candidate") or "unknown")
    total_area = sum(area_of.values()) or 1.0

    # fitted regions (by source_region_id)
    fitted: dict[str, dict[str, Any]] = {}
    for s in surfaces:
        rid = str(s.get("source_region_id"))
        fitted[rid] = {
            "surface_type": s.get("surface_type"),
            "confidence": s.get("fit_confidence"),
            "has_boundary": bool(s.get("boundary")),
        }

    fitted_area = sum(area_of.get(rid, 0.0) for rid in fitted)
    plane_area = sum(area_of.get(rid, 0.0) for rid, f in fitted.items() if f["surface_type"] == "plane")
    cyl_area = sum(area_of.get(rid, 0.0) for rid, f in fitted.items() if f["surface_type"] == "cylinder")
    noisy_area = sum(a for rid, a in area_of.items() if class_of.get(rid) == "noisy_small_region")
    unfit_area = total_area - fitted_area

    # adjacency coverage among fitted regions
    total_pairs = len(adjacency)
    fitted_pairs = sum(1 for e in adjacency
                       if str(e.get("region_a")) in fitted and str(e.get("region_b")) in fitted)
    if len(fitted) <= 1:
        adj_coverage = 1.0 if total_pairs == 0 else float(fitted_pairs) / total_pairs
    else:
        adj_coverage = (float(fitted_pairs) / total_pairs) if total_pairs else 0.0

    conf_dist: dict[str, int] = {}
    for f in fitted.values():
        c = str(f.get("confidence") or "unknown")
        conf_dist[c] = conf_dist.get(c, 0) + 1
    boundaries_available = sum(1 for f in fitted.values() if f["has_boundary"])

    coverage = {
        "total_region_count": len(regions),
        "fitted_region_count": len(fitted),
        "fitted_area_fraction": round(fitted_area / total_area, 4),
        "plane_area_fraction": round(plane_area / total_area, 4),
        "cylinder_area_fraction": round(cyl_area / total_area, 4),
        "unfit_area_fraction": round(unfit_area / total_area, 4),
        "noisy_small_area_fraction": round(noisy_area / total_area, 4),
    }
    quality = {
        "fit_error_summary": (fit_diag or {}).get("fit_error_summary", {}),
        "confidence_distribution": conf_dist,
        "adjacency_coverage_fitted": round(adj_coverage, 4),
        "boundaries_available": boundaries_available,
        "boundary_coverage": round(boundaries_available / len(fitted), 4) if fitted else 0.0,
    }

    fitted_frac = fitted_area / total_area
    noisy_frac = noisy_area / total_area
    unfit_frac = unfit_area / total_area

    partial = (len(fitted) >= 1 and fitted_frac >= _PARTIAL_MIN_FITTED_AREA
               and noisy_frac < _NOISY_CLEANUP_AREA)
    full = (partial and fitted_frac >= _FULL_MIN_FITTED_AREA
            and len(fitted) >= _FULL_MIN_FITTED_REGIONS
            and adj_coverage >= _FULL_MIN_ADJ_COVERAGE
            and unfit_frac <= _FULL_MAX_UNFIT_AREA)

    # blocking issues
    blocking: list[dict[str, Any]] = []
    large_unfit = [str(rid) for rid, a in area_of.items()
                   if rid not in fitted and (a / total_area) > _LARGE_UNFIT_REGION_AREA]
    if large_unfit:
        blocking.append({"issue": "large_unfit_regions", "detail": large_unfit})
    if noisy_frac >= _NOISY_CLEANUP_AREA:
        blocking.append({"issue": "too_many_noisy_regions",
                         "detail": f"noisy area fraction {noisy_frac:.2f}"})
    if conf_dist.get("medium", 0) and not conf_dist.get("high", 0):
        blocking.append({"issue": "only_medium_confidence_fits", "detail": conf_dist})
    if fitted and boundaries_available < len(fitted):
        blocking.append({"issue": "missing_boundaries",
                         "detail": f"{len(fitted) - boundaries_available} fitted surface(s) without a boundary loop"})
    if len(fitted) > 1 and total_pairs == 0:
        blocking.append({"issue": "missing_adjacency", "detail": "no region adjacency available"})

    # recommended next action + reasoning
    reasoning: list[str] = []
    if len(regions) == 0:
        action = "insufficient_data"
        reasoning.append("no regions to assess")
    elif noisy_frac >= _NOISY_CLEANUP_AREA:
        action = "mesh_cleanup"
        reasoning.append(f"noisy/small regions cover {noisy_frac:.0%} of area (>= "
                         f"{_NOISY_CLEANUP_AREA:.0%}); clean the mesh before fitting/reconstruction")
    elif partial:
        if unfit_frac > _FULL_MAX_UNFIT_AREA:
            action = "freeform_surface_fitting"
            reasoning.append(f"{fitted_frac:.0%} of area is fitted but {unfit_frac:.0%} is still "
                             "unfit (freeform); fit the remaining regions before reconstruction")
        else:
            action = "partial_brep_reconstruction"
            reasoning.append(f"{fitted_frac:.0%} of area fitted to analytic surfaces with little "
                             "unfit area; ready to attempt (partial) reconstruction in a future step")
        if full:
            reasoning.append("coverage + adjacency + face count meet the full-candidate bar")
    else:
        action = "freeform_surface_fitting"
        reasoning.append(f"only {fitted_frac:.0%} of area fitted to analytic surfaces; most of the "
                         "body is freeform — fit freeform surfaces before any reconstruction")

    readiness = _readiness_doc(provenance, partial=partial, full=full, action=action,
                               coverage=coverage, quality=quality, blocking=blocking,
                               reasoning=reasoning, available=True,
                               thresholds=_thresholds())
    plan = _plan_doc(provenance, _region_plan(regions, fitted, area_of, total_area))
    return readiness, plan


def _thresholds() -> dict[str, Any]:
    return {
        "partial_min_fitted_area_fraction": _PARTIAL_MIN_FITTED_AREA,
        "full_min_fitted_area_fraction": _FULL_MIN_FITTED_AREA,
        "full_min_fitted_regions": _FULL_MIN_FITTED_REGIONS,
        "full_min_adjacency_coverage": _FULL_MIN_ADJ_COVERAGE,
        "full_max_unfit_area_fraction": _FULL_MAX_UNFIT_AREA,
        "noisy_cleanup_area_fraction": _NOISY_CLEANUP_AREA,
        "large_unfit_region_area_fraction": _LARGE_UNFIT_REGION_AREA,
    }


def _region_plan(regions, fitted, area_of, total_area) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for r in regions:
        rid = str(r.get("region_id"))
        cls = str(r.get("surface_class_candidate") or "unknown")
        frac = round(area_of.get(rid, 0.0) / total_area, 4)
        if rid in fitted:
            action = "reconstruct_face_candidate"
            st = fitted[rid]["surface_type"]
        elif cls == "noisy_small_region":
            action = "cleanup"
            st = None
        else:
            action = "fit_freeform_surface"
            st = None
        plan.append({"region_id": rid, "surface_class_candidate": cls,
                     "fitted_surface_type": st, "area_fraction": frac, "action": action})
    return plan


def _readiness_doc(provenance, *, partial, full, action, coverage, quality, blocking,
                   reasoning, available, thresholds=None) -> dict[str, Any]:
    return {
        "format": "aieng.mesh_reconstruction_readiness",
        "schema_version": "0.1",
        "available": available,
        "coverage": coverage,
        "quality": quality,
        "readiness": {
            "partial_brep_candidate": bool(partial),
            "full_brep_candidate": bool(full),
            "recommended_next_action": action,
        },
        "blocking_issues": blocking,
        "reasoning": reasoning,
        "thresholds": thresholds or {},
        "provenance": provenance,
        "claim_boundary": "Readiness reflects analytic-fit COVERAGE of a mesh; it does NOT "
                          "reconstruct B-Rep, export STEP, or certify CAD editability.",
    }


def _plan_doc(provenance, region_plan) -> dict[str, Any]:
    return {
        "format": "aieng.mesh_reconstruction_plan",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "region_plan": region_plan,
        "provenance": provenance,
        "claim_boundary": "A planning aid for FUTURE mesh-to-CAD work; no geometry is created here.",
    }


# ── package integration ──────────────────────────────────────────────────────

def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:
            return None
    return None


def build_mesh_reconstruction_readiness(package_path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the region graph + surface fits (+ diagnostics + manifest) from a package and
    return ``(readiness, plan)``. Missing artifacts degrade honestly to insufficient_data."""
    package_path = Path(package_path)
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            region_graph = _read_json(zf, MESH_REGION_GRAPH_PATH, names)
            surface_fit = _read_json(zf, MESH_SURFACE_FIT_PATH, names)
            seg_diag = _read_json(zf, MESH_REGION_SEGMENTATION_DIAG_PATH, names) or {}
            fit_diag = _read_json(zf, MESH_SURFACE_FITTING_DIAG_PATH, names) or {}
            manifest = _read_json(zf, _MANIFEST_PATH, names) or {}
    except FileNotFoundError:
        return assess_reconstruction_readiness(None, None)
    except Exception:  # noqa: BLE001
        return assess_reconstruction_readiness(None, None)

    readiness, plan = assess_reconstruction_readiness(region_graph, surface_fit, seg_diag, fit_diag)
    # backfill runtime provenance from the manifest if the graph didn't carry it
    ge = manifest.get("geometry_execution") if isinstance(manifest, dict) else None
    if isinstance(ge, dict):
        for doc in (readiness, plan):
            if not doc["provenance"].get("runtime"):
                doc["provenance"]["runtime"] = ge.get("actual_runtime") or ge.get("backend")
    return readiness, plan


def write_mesh_reconstruction_readiness(package_path: str | Path) -> dict[str, Any]:
    """Build + write diagnostics/mesh_reconstruction_readiness.json and
    graph/mesh_reconstruction_plan.json. Best-effort; returns the readiness doc."""
    package_path = Path(package_path)
    readiness, plan = build_mesh_reconstruction_readiness(package_path)
    if not package_path.exists():
        return readiness
    members = {
        MESH_RECONSTRUCTION_READINESS_PATH: (json.dumps(readiness, indent=2, sort_keys=True) + "\n").encode(),
        MESH_RECONSTRUCTION_PLAN_PATH: (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode(),
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
    return readiness
