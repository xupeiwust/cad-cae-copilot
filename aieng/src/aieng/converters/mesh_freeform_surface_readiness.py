"""Freeform surface fit readiness and quality scoring v0.

Scores approximate BSpline-like surface fits from graph/mesh_freeform_surface_fit.json
and produces a readiness assessment per surface + overall summary. This is ADVISORY ONLY:
it does NOT generate B-Rep faces, does NOT stitch, does NOT export STEP, and does NOT
claim CAD editability.

Output:
  diagnostics/mesh_freeform_reconstruction_readiness.json
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.mesh_freeform_surface_fitting import FREEFORM_SURFACE_FIT_PATH

FREEFORM_READINESS_PATH = "diagnostics/mesh_freeform_reconstruction_readiness.json"

# ── thresholds ────────────────────────────────────────────────────────────────

# Fit error thresholds (normalized by bbox diagonal / region scale)
_FIT_RMS_GOOD = 0.02
_FIT_RMS_ACCEPTABLE = 0.08
_FIT_MAX_GOOD = 0.10
_FIT_MAX_ACCEPTABLE = 0.25

# Boundary thresholds
_BOUNDARY_MIN_POINTS = 3

# Sample thresholds
_SAMPLE_GOOD = 50
_SAMPLE_ACCEPTABLE = 15

# Control net thresholds
_CTRL_MIN_POINTS = 4           # per direction
_CTRL_MAX_POINTS = 12          # per direction (excessive = poor)

# Overall readiness thresholds
_QUALITY_READY = 0.75
_QUALITY_PARTIAL = 0.40


def _score_fit_error(rms: float, max_err: float, scale: float) -> tuple[float, str]:
    """Return (score 0-1, status)."""
    rel_rms = rms / scale if scale else rms
    rel_max = max_err / scale if scale else max_err
    if rel_rms <= _FIT_RMS_GOOD and rel_max <= _FIT_MAX_GOOD:
        return 1.0, "good"
    if rel_rms <= _FIT_RMS_ACCEPTABLE and rel_max <= _FIT_MAX_ACCEPTABLE:
        return 0.6, "acceptable"
    return 0.2, "poor"


def _score_boundary(boundary: dict[str, Any] | None) -> tuple[float, str]:
    """Return (score 0-1, status)."""
    if not boundary:
        return 0.0, "missing"
    btype = boundary.get("type", "none")
    if btype == "none":
        return 0.0, "missing"
    pts = int(boundary.get("point_count", 0))
    approx = bool(boundary.get("approximate", True))
    if pts >= _BOUNDARY_MIN_POINTS and not approx:
        return 1.0, "good"
    if pts >= _BOUNDARY_MIN_POINTS:
        return 0.5, "approximate"
    return 0.2, "poor"


def _score_control_net(ctrl_u: int, ctrl_v: int) -> tuple[float, str]:
    """Return (score 0-1, status)."""
    total = ctrl_u * ctrl_v
    if total < _CTRL_MIN_POINTS * _CTRL_MIN_POINTS:
        return 0.3, "poor"
    if ctrl_u > _CTRL_MAX_POINTS or ctrl_v > _CTRL_MAX_POINTS:
        return 0.4, "excessive"
    return 1.0, "good"


def _score_sample(n_samples: int) -> tuple[float, str]:
    """Return (score 0-1, status)."""
    if n_samples >= _SAMPLE_GOOD:
        return 1.0, "good"
    if n_samples >= _SAMPLE_ACCEPTABLE:
        return 0.6, "sparse"
    return 0.2, "sparse"


def _bbox_diag(bbox: list) -> float:
    if not (isinstance(bbox, list) and len(bbox) >= 6):
        return 0.0
    d = [bbox[k + 3] - bbox[k] for k in range(3)]
    return float((sum(x * x for x in d)) ** 0.5)


def _surface_readiness(surface: dict[str, Any]) -> dict[str, Any]:
    """Assess readiness for a single freeform surface."""
    sid = str(surface.get("surface_id") or "")
    rid = str(surface.get("source_region_id") or "")
    status = str(surface.get("status") or "")
    fit_err = surface.get("fit_error") or {}
    boundary = surface.get("boundary") or {}
    n_samples = int(surface.get("sample_count", 0))
    ctrl_u = int(surface.get("control_points_u", 0))
    ctrl_v = int(surface.get("control_points_v", 0))
    bbox = surface.get("bbox") or []
    scale = _bbox_diag(bbox) or 1.0

    blocking: list[str] = []
    warnings: list[str] = []

    if status != "fitted":
        blocking.append("surface_status_not_fitted")
        return {
            "surface_id": sid,
            "source_region_id": rid,
            "readiness": "not_ready",
            "quality_score": 0.0,
            "confidence": "low",
            "fit_error_quality": {"status": "unknown", "score": 0.0},
            "boundary_quality": {"status": "unknown", "score": 0.0},
            "control_net_quality": {"status": "unknown", "score": 0.0},
            "sample_quality": {"status": "unknown", "score": 0.0},
            "blocking_issues": blocking,
            "warnings": warnings,
            "recommended_next_action": "keep_mesh_only",
        }

    # Sub-scores
    rms = float(fit_err.get("rms", 0.0))
    max_err = float(fit_err.get("max", 0.0))
    fit_score, fit_status = _score_fit_error(rms, max_err, scale)
    bound_score, bound_status = _score_boundary(boundary)
    ctrl_score, ctrl_status = _score_control_net(ctrl_u, ctrl_v)
    sample_score, sample_status = _score_sample(n_samples)

    if fit_status == "poor":
        blocking.append("fit_error_too_high")
        warnings.append(f"fit error poor (rms={rms:.4g}, rel={rms/scale:.3f})")
    if bound_status == "missing":
        blocking.append("boundary_missing")
        warnings.append("no approximate boundary available")
    if sample_status == "sparse":
        blocking.append("too_few_samples")
        warnings.append(f"sample count {n_samples} is below {_SAMPLE_ACCEPTABLE}")
    if ctrl_status == "excessive":
        warnings.append(f"control net {ctrl_u}x{ctrl_v} may be excessive")

    # Weighted quality score
    quality_score = round(
        fit_score * 0.40 + bound_score * 0.25 + ctrl_score * 0.20 + sample_score * 0.15, 4
    )

    # Confidence from original fit + quality
    orig_conf = str(surface.get("confidence") or "low")
    if orig_conf == "high" and quality_score >= _QUALITY_READY:
        confidence = "high"
    elif quality_score >= _QUALITY_PARTIAL:
        confidence = "medium"
    else:
        confidence = "low"

    # Readiness
    if quality_score >= _QUALITY_READY and not blocking:
        readiness = "ready"
        action = "attempt_freeform_face_generation"
    elif quality_score >= _QUALITY_PARTIAL and "fit_error_too_high" not in blocking:
        readiness = "partial"
        if "boundary_missing" in blocking:
            action = "improve_boundary"
        elif "too_few_samples" in blocking:
            action = "refit_with_more_samples"
        else:
            action = "refit_with_more_samples"
    else:
        readiness = "not_ready"
        if "too_few_samples" in blocking or "fit_error_too_high" in blocking:
            action = "improve_segmentation"
        else:
            action = "keep_mesh_only"

    return {
        "surface_id": sid,
        "source_region_id": rid,
        "readiness": readiness,
        "quality_score": quality_score,
        "confidence": confidence,
        "fit_error_quality": {
            "rms": round(rms, 6),
            "max": round(max_err, 6),
            "normalized_rms": round(rms / scale, 6) if scale else None,
            "normalized_max": round(max_err / scale, 6) if scale else None,
            "status": fit_status,
            "score": round(fit_score, 4),
        },
        "boundary_quality": {
            "type": boundary.get("type", "none"),
            "point_count": boundary.get("point_count", 0),
            "approximate": boundary.get("approximate", True),
            "status": bound_status,
            "score": round(bound_score, 4),
        },
        "control_net_quality": {
            "control_points_u": ctrl_u,
            "control_points_v": ctrl_v,
            "status": ctrl_status,
            "score": round(ctrl_score, 4),
        },
        "sample_quality": {
            "sample_count": n_samples,
            "status": sample_status,
            "score": round(sample_score, 4),
        },
        "blocking_issues": blocking,
        "warnings": warnings,
        "recommended_next_action": action,
    }


def assess_freeform_readiness(
    freeform_fit: dict[str, Any] | None,
) -> dict[str, Any]:
    """Score freeform surface fits and produce readiness diagnostics.

    Returns a single readiness document. Pure. Advisory only."""
    surfaces_in = (freeform_fit or {}).get("surfaces") or []
    prov_src = (freeform_fit or {}).get("provenance") or {}

    provenance = {
        "source_mesh_artifact": prov_src.get("source_mesh_artifact"),
        "source_ir_node": prov_src.get("source_ir_node"),
        "design_space_node": prov_src.get("design_space_node"),
        "runtime": prov_src.get("runtime"),
        "freeform_surface_fit": FREEFORM_SURFACE_FIT_PATH,
        "representation_kind": "mesh",
        "geometry_kind": "mesh",
        "is_brep": False,
        "cad_editable": False,
        "step_exported": False,
        "readiness_only": True,
        "limitations": [
            "Freeform readiness scoring is advisory only. It does NOT generate B-Rep faces, "
            "does NOT stitch, does NOT export STEP, and does NOT claim CAD editability.",
        ],
    }

    if not isinstance(freeform_fit, dict):
        return _readiness_doc(
            provenance, status="skipped", reason="no freeform fit artifact",
            surfaces=[], summary={"surfaces_total": 0, "surfaces_ready": 0, "surfaces_partial": 0,
                                  "surfaces_not_ready": 0, "area_ready_fraction": 0.0,
                                  "recommended_next_action": "insufficient_data"})

    surface_scores: list[dict[str, Any]] = []
    for surf in surfaces_in:
        surface_scores.append(_surface_readiness(surf))

    ready_n = sum(1 for s in surface_scores if s["readiness"] == "ready")
    partial_n = sum(1 for s in surface_scores if s["readiness"] == "partial")
    not_ready_n = sum(1 for s in surface_scores if s["readiness"] == "not_ready")
    total_n = len(surface_scores)

    # Overall recommended next action
    if total_n == 0:
        overall_status = "skipped"
        overall_action = "insufficient_data"
        reason = "no freeform surfaces to assess"
    elif ready_n >= 1 and not_ready_n <= ready_n:
        overall_status = "ready"
        overall_action = "attempt_freeform_face_generation"
        reason = f"{ready_n} surface(s) ready for future freeform B-Rep generation"
    elif partial_n >= 1 and not_ready_n <= partial_n + ready_n:
        overall_status = "partial"
        overall_action = "improve_segmentation" if not_ready_n > partial_n + ready_n else "refit_with_more_samples"
        reason = f"{partial_n} surface(s) partial, {not_ready_n} not ready"
    else:
        overall_status = "not_ready"
        overall_action = "keep_mesh_only"
        reason = f"{not_ready_n} of {total_n} surface(s) not ready"

    summary = {
        "surfaces_total": total_n,
        "surfaces_ready": ready_n,
        "surfaces_partial": partial_n,
        "surfaces_not_ready": not_ready_n,
        "area_ready_fraction": round(ready_n / total_n, 4) if total_n else 0.0,
        "recommended_next_action": overall_action,
    }

    return _readiness_doc(
        provenance, status=overall_status, reason=reason,
        surfaces=surface_scores, summary=summary,
        thresholds=_thresholds(),
    )


def _thresholds() -> dict[str, Any]:
    return {
        "fit_error": {
            "rms_good": _FIT_RMS_GOOD,
            "rms_acceptable": _FIT_RMS_ACCEPTABLE,
            "max_good": _FIT_MAX_GOOD,
            "max_acceptable": _FIT_MAX_ACCEPTABLE,
        },
        "boundary": {"min_points": _BOUNDARY_MIN_POINTS},
        "sample": {"good": _SAMPLE_GOOD, "acceptable": _SAMPLE_ACCEPTABLE},
        "control_net": {"min_points": _CTRL_MIN_POINTS, "max_points": _CTRL_MAX_POINTS},
        "quality_score": {"ready": _QUALITY_READY, "partial": _QUALITY_PARTIAL},
    }


def _readiness_doc(
    provenance: dict[str, Any],
    *,
    status: str,
    reason: str,
    surfaces: list[dict[str, Any]],
    summary: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "format": "aieng.mesh.freeform_reconstruction_readiness.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": status,
        "source_freeform_fit": FREEFORM_SURFACE_FIT_PATH,
        "summary": summary,
        "surfaces": surfaces,
        "thresholds": thresholds or {},
        "honesty": {
            "is_brep": False,
            "cad_editable": False,
            "step_exported": False,
            "readiness_only": True,
        },
        "limitations": [
            "Readiness scoring is advisory and does not guarantee B-Rep generation success.",
            "Freeform surfaces are NOT yet converted to OCC faces, NOT stitched, NOT exported to STEP.",
            "Thresholds are conservative; partial scores may improve with better segmentation or sampling.",
        ],
        "provenance": provenance,
        "claim_boundary": "Advisory readiness assessment for freeform surface fits. "
                          "Does NOT reconstruct geometry, export STEP, or certify CAD editability.",
    }


def write_freeform_readiness(package_path: str | Path) -> dict[str, Any]:
    """Read freeform fit artifact, score readiness, and write
    diagnostics/mesh_freeform_reconstruction_readiness.json."""
    package_path = Path(package_path)
    freeform_fit = None
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            if FREEFORM_SURFACE_FIT_PATH in names:
                freeform_fit = json.loads(zf.read(FREEFORM_SURFACE_FIT_PATH).decode("utf-8"))
    except FileNotFoundError:
        return assess_freeform_readiness(None)
    except Exception:
        return assess_freeform_readiness(None)

    readiness = assess_freeform_readiness(freeform_fit)
    if not package_path.exists():
        return readiness

    members = {
        FREEFORM_READINESS_PATH: (json.dumps(readiness, indent=2, sort_keys=True) + "\n").encode(),
    }
    tmp = package_path.with_suffix(".ffread.tmp.aieng")
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
