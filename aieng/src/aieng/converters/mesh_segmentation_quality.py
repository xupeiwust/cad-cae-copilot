"""Mesh region segmentation quality assessment and re-segmentation hints v0.

Assesses whether mesh region segmentation is good enough for downstream CAD
reconstruction, identifies fragmentation/undersegmentation/boundary problems,
and recommends conservative re-segmentation strategies. This is ADVISORY — it
does NOT rerun segmentation, does NOT modify geometry, and does NOT trigger
reconstruction.

Outputs:
  diagnostics/mesh_segmentation_quality.json
  analysis/mesh_resegmentation_hints.json
"""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.mesh_freeform_face_trimming_readiness import TRIMMING_READINESS_PATH
from aieng.converters.mesh_freeform_surface_fitting import FREEFORM_SURFACE_FIT_PATH
from aieng.converters.mesh_freeform_surface_readiness import FREEFORM_READINESS_PATH
from aieng.converters.mesh_reconstruction_readiness import MESH_RECONSTRUCTION_READINESS_PATH
from aieng.converters.mesh_region_segmentation import MESH_REGION_GRAPH_PATH, MESH_REGION_SEGMENTATION_DIAG_PATH
from aieng.converters.mesh_surface_fitting import MESH_SURFACE_FIT_PATH
from aieng.converters.mesh_to_cad_reconstruction_status import STATUS_PATH as RECONSTRUCTION_STATUS_PATH

SEGMENTATION_QUALITY_PATH = "diagnostics/mesh_segmentation_quality.json"
RESEGMENTATION_HINTS_PATH = "analysis/mesh_resegmentation_hints.json"

# Thresholds
_TINY_REGION_FACE_COUNT = 4
_TINY_REGION_AREA_FRAC = 0.005
_HIGH_FRAGMENTATION_RATIO = 0.4
_LARGE_UNFIT_AREA_FRAC = 0.15
_LOW_FIT_COVERAGE = 0.5
_HIGH_NOISY_FRAC = 0.3


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:
            return None
    return None


def _region_bbox_diag(bbox: list[float]) -> float:
    if len(bbox) >= 6:
        return math.sqrt(sum((bbox[i + 3] - bbox[i]) ** 2 for i in range(3)))
    return 0.0


def _compute_scores(
    region_graph: dict[str, Any] | None,
    surface_fit: dict[str, Any] | None,
    freeform_fit: dict[str, Any] | None,
    freeform_readiness: dict[str, Any] | None,
    trimming_readiness: dict[str, Any] | None,
    reconstruction_status: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute fragmentation, undersegmentation, fit coverage, boundary quality scores."""
    regions = (region_graph or {}).get("regions") or []
    total_area = sum(_safe_float(r.get("area")) for r in regions) or 1.0
    total_faces = sum(_safe_int(r.get("face_count")) for r in regions) or 1

    tiny_regions = [
        r for r in regions
        if _safe_int(r.get("face_count")) <= _TINY_REGION_FACE_COUNT
        or _safe_float(r.get("area")) / total_area < _TINY_REGION_AREA_FRAC
    ]
    noisy_regions = [r for r in regions if r.get("surface_class_candidate") == "noisy_small_region"]
    unfit_regions = [r for r in regions if r.get("surface_class_candidate") in ("freeform_candidate", "unknown")]
    large_regions = [r for r in regions if _safe_float(r.get("area")) / total_area > _LARGE_UNFIT_AREA_FRAC]

    fitted_surfaces = (surface_fit or {}).get("surfaces") or []
    fitted_rids = {str(s.get("source_region_id")) for s in fitted_surfaces}
    fitted_area = sum(
        _safe_float(r.get("area")) for r in regions
        if str(r.get("region_id")) in fitted_rids
    )

    freeform_surfaces = (freeform_fit or {}).get("surfaces") or []
    freeform_rids = {str(s.get("source_region_id")) for s in freeform_surfaces}
    freeform_fitted_area = sum(
        _safe_float(r.get("area")) for r in regions
        if str(r.get("region_id")) in freeform_rids
    )

    # Fragmentation: ratio of tiny/noisy regions to total
    tiny_frac = len(tiny_regions) / max(len(regions), 1)
    noisy_frac = len(noisy_regions) / max(len(regions), 1)
    fragmentation = min(1.0, (tiny_frac + noisy_frac) / _HIGH_FRAGMENTATION_RATIO)

    # Undersegmentation: large regions that are unfit or have high error
    large_unfit = [
        r for r in large_regions
        if str(r.get("region_id")) not in fitted_rids
        and str(r.get("region_id")) not in freeform_rids
    ]
    undersegmentation = min(1.0, len(large_unfit) / max(len(large_regions), 1))

    # If freeform readiness says improve_segmentation, boost undersegmentation
    fr_surfaces = (freeform_readiness or {}).get("surfaces") or []
    if any(str(s.get("recommended_next_action")) == "improve_segmentation" for s in fr_surfaces):
        undersegmentation = max(undersegmentation, 0.6)

    # Fit coverage
    fit_coverage = min(1.0, (fitted_area + freeform_fitted_area) / total_area)
    if fit_coverage < _LOW_FIT_COVERAGE:
        fit_coverage_score = fit_coverage / _LOW_FIT_COVERAGE
    else:
        fit_coverage_score = 0.5 + 0.5 * (fit_coverage - _LOW_FIT_COVERAGE) / (1.0 - _LOW_FIT_COVERAGE)

    # Boundary quality from trimming readiness
    boundary_score = 1.0
    tr_faces = (trimming_readiness or {}).get("faces") or []
    if tr_faces:
        not_ready = sum(1 for f in tr_faces if f.get("trimming_readiness") == "not_ready")
        partial = sum(1 for f in tr_faces if f.get("trimming_readiness") == "partial")
        total_tr = len(tr_faces)
        if total_tr > 0:
            boundary_score = 1.0 - (not_ready * 0.5 + partial * 0.2) / total_tr
    # Also degrade from reconstruction status blockers
    rs_blockers = (reconstruction_status or {}).get("blockers") or []
    if any(b.get("type") in ("missing_boundaries", "large_edge_gaps") for b in rs_blockers):
        boundary_score = min(boundary_score, 0.5)

    overall = round(
        max(0.0, 1.0 - fragmentation * 0.35 - undersegmentation * 0.30
            - (1.0 - fit_coverage_score) * 0.20 - (1.0 - boundary_score) * 0.15),
        4,
    )

    return {
        "fragmentation_score": round(max(0.0, 1.0 - fragmentation), 4),
        "undersegmentation_score": round(max(0.0, 1.0 - undersegmentation), 4),
        "fit_coverage_score": round(max(0.0, fit_coverage_score), 4),
        "boundary_quality_score": round(max(0.0, boundary_score), 4),
        "overall_quality_score": overall,
        "region_count": len(regions),
        "tiny_region_count": len(tiny_regions),
        "noisy_region_count": len(noisy_regions),
        "large_mixed_region_count": len(large_unfit),
        "unfit_region_count": len(unfit_regions),
        "fitted_area_fraction": round(fitted_area / total_area, 4),
        "freeform_fitted_area_fraction": round(freeform_fitted_area / total_area, 4),
    }


def _build_region_findings(
    region_graph: dict[str, Any] | None,
    surface_fit: dict[str, Any] | None,
    freeform_fit: dict[str, Any] | None,
    freeform_readiness: dict[str, Any] | None,
    trimming_readiness: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build per-region findings from available evidence."""
    findings: list[dict[str, Any]] = []
    regions = (region_graph or {}).get("regions") or []
    if not regions:
        return findings

    total_area = sum(_safe_float(r.get("area")) for r in regions) or 1.0

    fitted_by_rid: dict[str, dict[str, Any]] = {}
    for s in (surface_fit or {}).get("surfaces") or []:
        fitted_by_rid[str(s.get("source_region_id"))] = s

    freeform_by_rid: dict[str, dict[str, Any]] = {}
    for s in (freeform_fit or {}).get("surfaces") or []:
        freeform_by_rid[str(s.get("source_region_id"))] = s

    fr_by_rid: dict[str, dict[str, Any]] = {}
    for s in (freeform_readiness or {}).get("surfaces") or []:
        fr_by_rid[str(s.get("source_region_id"))] = s

    tr_by_rid: dict[str, dict[str, Any]] = {}
    for f in (trimming_readiness or {}).get("faces") or []:
        tr_by_rid[str(f.get("source_region_id"))] = f

    for r in regions:
        rid = str(r.get("region_id"))
        area = _safe_float(r.get("area"))
        area_frac = area / total_area
        face_count = _safe_int(r.get("face_count"))
        cls = str(r.get("surface_class_candidate"))
        planarity = _safe_float(r.get("planarity_score"))

        # Tiny fragment
        if face_count <= _TINY_REGION_FACE_COUNT or area_frac < _TINY_REGION_AREA_FRAC:
            findings.append({
                "region_id": rid,
                "finding_type": "tiny_fragment",
                "severity": "info" if area_frac < 0.001 else "warning",
                "evidence": {"face_count": face_count, "area_fraction": round(area_frac, 4)},
            })

        # Noisy region
        if cls == "noisy_small_region":
            findings.append({
                "region_id": rid,
                "finding_type": "noisy_region",
                "severity": "warning",
                "evidence": {"face_count": face_count, "area_fraction": round(area_frac, 4)},
            })

        # Large unfit region (potential undersegmentation)
        if area_frac > _LARGE_UNFIT_AREA_FRAC and rid not in fitted_by_rid and rid not in freeform_by_rid:
            findings.append({
                "region_id": rid,
                "finding_type": "large_mixed_surface",
                "severity": "warning",
                "evidence": {"area_fraction": round(area_frac, 4), "planarity_score": planarity},
            })

        # Freeform region with poor readiness
        fr = fr_by_rid.get(rid)
        if fr and fr.get("readiness") == "not_ready":
            findings.append({
                "region_id": rid,
                "finding_type": "unfit_region",
                "severity": "warning",
                "evidence": {"quality_score": fr.get("quality_score"), "recommended_action": fr.get("recommended_next_action")},
            })

        # Boundary problems from trimming readiness
        tr = tr_by_rid.get(rid)
        if tr and tr.get("trimming_readiness") == "not_ready":
            issues = tr.get("blocking_issues") or []
            if "boundary_missing" in issues or "boundary_poor" in issues:
                findings.append({
                    "region_id": rid,
                    "finding_type": "boundary_problem",
                    "severity": "warning",
                    "evidence": {"blocking_issues": issues},
                })

        # High fit error on fitted surface
        fitted = fitted_by_rid.get(rid)
        if fitted:
            rms = _safe_float(fitted.get("rms_distance") or fitted.get("rms_radial"))
            scale = _region_bbox_diag(r.get("bbox", [])) or 1.0
            if scale > 0 and rms / scale > 0.05:
                findings.append({
                    "region_id": rid,
                    "finding_type": "high_fit_error",
                    "severity": "info",
                    "evidence": {"rms": rms, "relative_rms": round(rms / scale, 4)},
                })

    return findings


def _build_hints(
    scores: dict[str, Any],
    findings: list[dict[str, Any]],
    reconstruction_status: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], str]:
    """Generate re-segmentation hints from quality findings and scores."""
    hints: list[dict[str, Any]] = []
    hint_id = 0

    def add_hint(htype: str, priority: str, confidence: str, reason: str,
                 affected: list[str], params: dict[str, Any] | None = None) -> None:
        nonlocal hint_id
        hint_id += 1
        hints.append({
            "id": f"hint_{hint_id:03d}",
            "type": htype,
            "priority": priority,
            "confidence": confidence,
            "reason": reason,
            "affected_regions": affected,
            "suggested_parameters": params or {},
        })

    # If STEP already verified, suggest keeping current segmentation
    rs_status = (reconstruction_status or {}).get("status")
    if rs_status == "step_exported":
        add_hint("keep_current_segmentation", "low", "high",
                 "Reconstruction produced verified STEP; segmentation is adequate",
                 [])
        return hints, "keep_current_segmentation"

    # Many tiny/noisy regions → fragmentation
    tiny_noisy = [f for f in findings if f["finding_type"] in ("tiny_fragment", "noisy_region")]
    if scores["tiny_region_count"] >= 3 or scores["fragmentation_score"] < 0.5:
        affected = [f["region_id"] for f in tiny_noisy[:10]]
        add_hint("merge_tiny_regions", "high" if scores["fragmentation_score"] < 0.3 else "medium", "medium",
                 f"{scores['tiny_region_count']} tiny/noisy regions indicate oversegmentation",
                 affected,
                 {"min_region_area_fraction": 0.02})
        add_hint("raise_normal_angle_threshold", "medium", "low",
                 "Larger normal-angle tolerance may merge adjacent planar fragments",
                 affected,
                 {"normal_angle_deg": 30.0})

    # Large unfit regions → undersegmentation
    large_unfit = [f for f in findings if f["finding_type"] == "large_mixed_surface"]
    if large_unfit or scores["undersegmentation_score"] < 0.5:
        affected = [f["region_id"] for f in large_unfit[:10]]
        add_hint("split_high_curvature_region", "high" if scores["undersegmentation_score"] < 0.3 else "medium", "medium",
                 "Large unfit regions may contain multiple surface types",
                 affected)
        add_hint("try_curvature_aware_segmentation", "medium", "low",
                 "Curvature-aware seeding may better separate distinct surfaces",
                 affected)

    # Boundary problems
    boundary_issues = [f for f in findings if f["finding_type"] == "boundary_problem"]
    if boundary_issues:
        add_hint("try_curvature_aware_segmentation", "medium", "medium",
                 "Boundary problems may improve with better region edge alignment",
                 [f["region_id"] for f in boundary_issues[:10]])

    # Freeform readiness says improve_segmentation
    ff_unfit = [f for f in findings if f["finding_type"] == "unfit_region"]
    if ff_unfit:
        add_hint("split_high_curvature_region", "medium", "medium",
                 "Freeform regions with poor readiness may be under-segmented",
                 [f["region_id"] for f in ff_unfit[:10]])

    # Low fit coverage
    if scores["fit_coverage_score"] < 0.5:
        add_hint("decrease_normal_angle_threshold", "medium", "low",
                 f"Low fit coverage ({scores['fit_coverage_score']}); stricter segmentation may help",
                 [],
                 {"normal_angle_deg": 10.0})

    # Determine overall next action
    if not hints:
        next_action = "keep_current_segmentation"
    elif any(h["type"] == "merge_tiny_regions" and h["priority"] == "high" for h in hints):
        next_action = "rerun_with_adjusted_thresholds"
    elif any(h["type"] in ("split_high_curvature_region", "try_curvature_aware_segmentation") and h["priority"] == "high" for h in hints):
        next_action = "try_curvature_aware_segmentation"
    else:
        next_action = "rerun_with_adjusted_thresholds"

    return hints, next_action


def assess_segmentation_quality(
    region_graph: dict[str, Any] | None,
    seg_diag: dict[str, Any] | None,
    surface_fit: dict[str, Any] | None,
    fit_diag: dict[str, Any] | None,
    freeform_fit: dict[str, Any] | None,
    freeform_readiness: dict[str, Any] | None,
    trimming_readiness: dict[str, Any] | None,
    reconstruction_status: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Assess segmentation quality and generate re-segmentation hints.

    Returns ``(quality_doc, hints_doc)``. Pure. Advisory only.
    """
    if not isinstance(region_graph, dict) or not region_graph.get("regions"):
        quality_doc = _quality_doc(
            status="insufficient_data",
            summary={"region_count": 0, "tiny_region_count": 0, "noisy_region_count": 0,
                     "large_mixed_region_count": 0, "unfit_region_count": 0,
                     "fragmentation_score": 0.0, "undersegmentation_score": 0.0,
                     "fit_coverage_score": 0.0, "overall_quality_score": 0.0},
            findings=[], blockers=[],
        )
        hints_doc = _hints_doc(
            status="insufficient_data",
            hints=[],
            next_action="insufficient_data",
        )
        return quality_doc, hints_doc

    scores = _compute_scores(region_graph, surface_fit, freeform_fit, freeform_readiness,
                             trimming_readiness, reconstruction_status)
    findings = _build_region_findings(region_graph, surface_fit, freeform_fit,
                                      freeform_readiness, trimming_readiness)
    hints, next_action = _build_hints(scores, findings, reconstruction_status)

    # Overall status
    overall = scores["overall_quality_score"]
    if overall >= 0.7:
        status = "good"
    elif overall >= 0.4:
        status = "warning"
    else:
        status = "poor"

    # Blockers
    blockers: list[dict[str, Any]] = []
    if scores["fragmentation_score"] < 0.3:
        blockers.append({"type": "high_fragmentation", "severity": "warning",
                         "reason": f"Fragmentation score {scores['fragmentation_score']}: many tiny/noisy regions"})
    if scores["undersegmentation_score"] < 0.3:
        blockers.append({"type": "undersegmentation", "severity": "warning",
                         "reason": f"Undersegmentation score {scores['undersegmentation_score']}: large unfit regions"})
    if scores["fit_coverage_score"] < 0.3:
        blockers.append({"type": "low_fit_coverage", "severity": "warning",
                         "reason": f"Fit coverage score {scores['fit_coverage_score']}: most regions unfit"})

    source_artifacts = [name for name, val in {
        MESH_REGION_GRAPH_PATH: region_graph,
        MESH_REGION_SEGMENTATION_DIAG_PATH: seg_diag,
        MESH_SURFACE_FIT_PATH: surface_fit,
        FREEFORM_SURFACE_FIT_PATH: freeform_fit,
        FREEFORM_READINESS_PATH: freeform_readiness,
        TRIMMING_READINESS_PATH: trimming_readiness,
        RECONSTRUCTION_STATUS_PATH: reconstruction_status,
    }.items() if val is not None]

    quality_doc = _quality_doc(
        status=status,
        summary=scores,
        findings=findings,
        blockers=blockers,
        source_artifacts=source_artifacts,
        warnings=(seg_diag or {}).get("warnings", [])[:10],
    )

    hints_status = "ready" if status == "good" else ("warning" if status == "warning" else "needs_user_input")
    hints_doc = _hints_doc(
        status=hints_status,
        hints=hints,
        next_action=next_action,
    )
    return quality_doc, hints_doc


def _quality_doc(
    *,
    status: str,
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
    blockers: list[dict[str, Any]] | None = None,
    source_artifacts: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "format": "aieng.mesh.segmentation_quality.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": status,
        "source_region_graph": MESH_REGION_GRAPH_PATH,
        "summary": summary,
        "region_findings": findings,
        "blockers": blockers or [],
        "source_artifacts": source_artifacts or [],
        "warnings": warnings or [],
        "errors": [],
        "claim_boundary": (
            "Segmentation quality assessment is ADVISORY ONLY. Does NOT rerun segmentation, "
            "does NOT modify geometry, does NOT trigger reconstruction."
        ),
    }


def _hints_doc(
    *,
    status: str,
    hints: list[dict[str, Any]],
    next_action: str,
) -> dict[str, Any]:
    return {
        "format": "aieng.mesh.resegmentation_hints.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": status,
        "hints": hints,
        "recommended_next_action": next_action,
        "limitations": [
            "Hints are advisory only. They do NOT automatically rerun segmentation.",
            "No mesh geometry is modified by this artifact.",
            "Downstream artifacts are not regenerated.",
        ],
        "claim_boundary": (
            "Resegmentation hints are ADVISORY ONLY. Does NOT rerun segmentation, "
            "does NOT modify geometry, does NOT trigger reconstruction."
        ),
    }


def write_segmentation_quality(package_path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read mesh pipeline artifacts, assess segmentation quality, generate hints,
    and write both diagnostics/mesh_segmentation_quality.json and
    analysis/mesh_resegmentation_hints.json. Best-effort."""
    package_path = Path(package_path)
    inputs: dict[str, Any] = {}
    if package_path.exists():
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                names = set(zf.namelist())
                inputs["region_graph"] = _read_json(zf, MESH_REGION_GRAPH_PATH, names)
                inputs["seg_diag"] = _read_json(zf, MESH_REGION_SEGMENTATION_DIAG_PATH, names)
                inputs["surface_fit"] = _read_json(zf, MESH_SURFACE_FIT_PATH, names)
                inputs["fit_diag"] = _read_json(zf, "diagnostics/mesh_surface_fitting.json", names)
                inputs["freeform_fit"] = _read_json(zf, FREEFORM_SURFACE_FIT_PATH, names)
                inputs["freeform_readiness"] = _read_json(zf, FREEFORM_READINESS_PATH, names)
                inputs["trimming_readiness"] = _read_json(zf, TRIMMING_READINESS_PATH, names)
                inputs["reconstruction_status"] = _read_json(zf, RECONSTRUCTION_STATUS_PATH, names)
        except Exception:
            pass

    quality_doc, hints_doc = assess_segmentation_quality(
        inputs.get("region_graph"),
        inputs.get("seg_diag"),
        inputs.get("surface_fit"),
        inputs.get("fit_diag"),
        inputs.get("freeform_fit"),
        inputs.get("freeform_readiness"),
        inputs.get("trimming_readiness"),
        inputs.get("reconstruction_status"),
    )
    if not package_path.exists():
        return quality_doc, hints_doc

    members = {
        SEGMENTATION_QUALITY_PATH: (json.dumps(quality_doc, indent=2, sort_keys=True) + "\n").encode(),
        RESEGMENTATION_HINTS_PATH: (json.dumps(hints_doc, indent=2, sort_keys=True) + "\n").encode(),
    }
    tmp = package_path.with_suffix(".segqual.tmp.aieng")
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
    return quality_doc, hints_doc
