"""Mesh-to-CAD reconstruction status aggregator v0.

Aggregates scattered mesh-to-CAD pipeline diagnostics into one clear status report.
Tells an agent or engineer:
- What reconstruction level was achieved?
- Is a valid STEP available?
- Is this only partial analytic B-Rep?
- Are there freeform surfaces that are candidates but not stitched?
- What blocks full CAD reconstruction?
- What is the next recommended action?

This is a SUMMARY/DECISION layer — it does NOT create geometry, does NOT trigger
fitting/sewing/export, and does NOT change existing behavior. Pure read-only aggregation.

Output:
  diagnostics/mesh_to_cad_reconstruction_status.json
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.mesh_brep_solidification import (
    MESH_BREP_ROUNDTRIP_PATH,
    MESH_BREP_SEWING_PATH,
    MESH_BREP_STEP_EXPORT_PATH,
    RECONSTRUCTED_STEP_PATH,
    RECONSTRUCTED_TOPOLOGY_PATH,
)
from aieng.converters.mesh_brep_stitching import (
    MESH_BREP_STITCHING_PLAN_PATH,
    MESH_BREP_STITCHING_READINESS_PATH,
)
from aieng.converters.mesh_freeform_brep_face_generation import FREEFORM_BREP_FACES_PATH
from aieng.converters.mesh_freeform_face_trimming_readiness import TRIMMING_READINESS_PATH
from aieng.converters.mesh_freeform_surface_fitting import FREEFORM_SURFACE_FIT_PATH
from aieng.converters.mesh_freeform_surface_readiness import FREEFORM_READINESS_PATH
from aieng.converters.mesh_reconstruction_readiness import MESH_RECONSTRUCTION_READINESS_PATH
from aieng.converters.mesh_region_segmentation import MESH_REGION_GRAPH_PATH
from aieng.converters.mesh_surface_fitting import MESH_SURFACE_FIT_PATH
from aieng.converters.mesh_brep_face_generation import PARTIAL_BREP_FACES_PATH
from aieng.converters.mesh_brep_reconstruction import MESH_BREP_PLAN_PATH, PARTIAL_BREP_SURFACES_PATH

STATUS_PATH = "diagnostics/mesh_to_cad_reconstruction_status.json"


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name).decode("utf-8"))
        except Exception:
            return None
    return None


def _safe_float(val: Any, default: float | None = None) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _artifact_exists(package_path: Path, names: set[str], artifact: str) -> bool:
    if artifact in names:
        return True
    # Also check filesystem for STEP files (they may exist outside the zip)
    if artifact == RECONSTRUCTED_STEP_PATH:
        return (package_path.parent / artifact).exists() if package_path.exists() else False
    return False


def _build_coverage(inputs: dict[str, Any]) -> dict[str, Any]:
    """Build coverage summary from available artifacts."""
    region_graph = inputs.get("region_graph") or {}
    surface_fit = inputs.get("surface_fit") or {}
    freeform_fit = inputs.get("freeform_fit") or {}
    plan = inputs.get("brep_plan") or {}
    faces_doc = inputs.get("partial_brep_faces") or {}
    freeform_faces = inputs.get("freeform_faces") or {}

    regions = region_graph.get("regions") or []
    total_area = sum(_safe_float(r.get("area"), 0.0) or 0.0 for r in regions)

    fitted_surfaces = surface_fit.get("surfaces") or []
    freeform_surfaces = freeform_fit.get("surfaces") or []

    analytic_area = sum(
        _safe_float(r.get("area"), 0.0) or 0.0
        for r in regions
        if any(str(s.get("source_region_id")) == str(r.get("region_id")) for s in fitted_surfaces)
    )
    freeform_area = sum(
        _safe_float(r.get("area"), 0.0) or 0.0
        for r in regions
        if any(str(s.get("source_region_id")) == str(r.get("region_id")) for s in freeform_surfaces)
    )

    def frac(area: float) -> float | None:
        if total_area and total_area > 0:
            return round(area / total_area, 4)
        return None

    return {
        "analytic_fitted_area_fraction": frac(analytic_area),
        "freeform_fitted_area_fraction": frac(freeform_area),
        "unfit_area_fraction": frac(max(0.0, total_area - analytic_area - freeform_area)),
        "region_count": len(regions),
        "analytic_fitted_count": len(fitted_surfaces),
        "freeform_fitted_count": len(freeform_surfaces),
        "candidate_face_count": _safe_int((plan.get("summary") or {}).get("candidate_face_count")),
        "validated_face_count": _safe_int((faces_doc.get("summary") or {}).get("generated_face_count")),
        "freeform_candidate_face_count": _safe_int((freeform_faces.get("summary") or {}).get("generated_face_count")),
    }


def _build_readiness(inputs: dict[str, Any]) -> dict[str, Any]:
    """Build readiness flags from available artifacts."""
    rr = (inputs.get("reconstruction_readiness") or {}).get("readiness") or {}
    fr = inputs.get("freeform_readiness") or {}
    ff = inputs.get("freeform_faces") or {}
    ftr = inputs.get("freeform_trimming_readiness") or {}
    sp = inputs.get("stitching_plan") or {}
    sewing = inputs.get("sewing") or {}
    step_export = inputs.get("step_export") or {}

    freeform_ready = any(
        str(f.get("trimming_readiness")) == "ready"
        for f in (ftr.get("faces") or [])
    )

    return {
        "analytic_reconstruction_ready": bool(rr.get("partial_brep_candidate") or rr.get("full_brep_candidate")),
        "freeform_evidence_ready": bool(fr.get("status") in ("ready", "partial")),
        "freeform_face_candidates_ready": bool(
            (ff.get("summary") or {}).get("generated_face_count", 0) > 0
        ),
        "freeform_trimming_ready": freeform_ready,
        "closed_shell_possible": bool(
            (sp.get("summary") or {}).get("can_attempt_closed_shell")
        ),
        "step_export_possible": bool(
            step_export.get("step_exported")
            or (sewing.get("summary") or {}).get("shell_type") == "closed_shell"
        ),
    }


def _build_blockers(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract blockers from existing diagnostics."""
    blockers: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(btype: str, severity: str, reason: str, source: str) -> None:
        if btype in seen:
            return
        seen.add(btype)
        blockers.append({
            "type": btype,
            "severity": severity,
            "reason": reason,
            "source_artifact": source,
        })

    # Reconstruction readiness blockers
    rr = inputs.get("reconstruction_readiness") or {}
    for b in (rr.get("readiness") or {}).get("blocking_issues") or []:
        detail = b if isinstance(b, str) else str(b.get("issue", ""))
        if "unfit" in detail.lower():
            add("unfit_regions", "warning", detail, MESH_RECONSTRUCTION_READINESS_PATH)
        elif "noisy" in detail.lower():
            add("too_many_noisy_regions", "warning", detail, MESH_RECONSTRUCTION_READINESS_PATH)
        elif "boundary" in detail.lower():
            add("missing_boundaries", "warning", detail, MESH_RECONSTRUCTION_READINESS_PATH)
        else:
            add("insufficient_data", "info", detail, MESH_RECONSTRUCTION_READINESS_PATH)

    # Stitching blockers
    sp = inputs.get("stitching_plan") or {}
    sr = inputs.get("stitching_readiness") or {}
    for b in (sr.get("blocking_issues") or []) + (sp.get("blocking_issues") or []):
        detail = b if isinstance(b, str) else str(b.get("issue", ""))
        if "gap" in detail.lower():
            add("large_edge_gaps", "warning", detail, MESH_BREP_STITCHING_READINESS_PATH)
        elif "unreconstructed" in detail.lower():
            add("unreconstructed_neighbor_regions", "warning", detail, MESH_BREP_STITCHING_READINESS_PATH)
        elif "conflict" in detail.lower():
            add("conflicting_edge_matches", "warning", detail, MESH_BREP_STITCHING_READINESS_PATH)
        else:
            add("incomplete_stitching", "warning", detail, MESH_BREP_STITCHING_READINESS_PATH)

    # Sewing blockers
    sewing = inputs.get("sewing") or {}
    s_summary = sewing.get("summary") or {}
    if s_summary.get("shell_type") == "failed":
        add("sewing_failed", "critical", "OCC sewing produced no valid shell", MESH_BREP_SEWING_PATH)
    elif s_summary.get("shell_type") == "partial_shell":
        add("incomplete_stitching", "warning", "Sewing produced partial shell only", MESH_BREP_SEWING_PATH)

    # STEP export blockers
    step_export = inputs.get("step_export") or {}
    if not step_export.get("step_exported") and s_summary.get("shell_type") == "closed_shell":
        reason = step_export.get("reason") or "STEP export blocked despite closed shell"
        add("step_export_failed", "warning", reason, MESH_BREP_STEP_EXPORT_PATH)

    # Roundtrip blockers
    rt = inputs.get("roundtrip_verification") or {}
    if rt.get("status") == "failed":
        add("step_roundtrip_failed", "critical", "Roundtrip verification failed", MESH_BREP_ROUNDTRIP_PATH)
    elif rt.get("status") == "warning":
        add("step_roundtrip_warning", "warning", "Roundtrip verification produced warnings", MESH_BREP_ROUNDTRIP_PATH)

    # Freeform blockers
    ftr = inputs.get("freeform_trimming_readiness") or {}
    if ftr.get("status") in ("partial", "not_ready"):
        for f in (ftr.get("faces") or []):
            if f.get("trimming_readiness") == "not_ready":
                issues = f.get("blocking_issues") or []
                if "boundary_missing" in issues:
                    add("freeform_boundary_not_ready", "warning",
                        f"Freeform face {f.get('face_id')} missing boundary", TRIMMING_READINESS_PATH)
                elif "self_intersection_risk_high" in issues:
                    add("freeform_boundary_not_ready", "warning",
                        f"Freeform face {f.get('face_id')} self-intersecting boundary", TRIMMING_READINESS_PATH)
                else:
                    add("freeform_not_trimmed", "info",
                        f"Freeform face {f.get('face_id')} not ready for trimming", TRIMMING_READINESS_PATH)

    # Mesh-only / insufficient data
    region_graph = inputs.get("region_graph") or {}
    if not region_graph.get("regions"):
        add("insufficient_data", "info", "No region graph available", MESH_REGION_GRAPH_PATH)

    return blockers


def _classify_status(inputs: dict[str, Any]) -> tuple[str, str, str, bool, bool, str]:
    """Classify overall reconstruction status.

    Returns (status, geometry_kind, cad_editability, step_available, step_verified, next_action).
    """
    step_export = inputs.get("step_export") or {}
    rt = inputs.get("roundtrip_verification") or {}
    sewing = inputs.get("sewing") or {}
    faces_doc = inputs.get("partial_brep_faces") or {}
    freeform_faces = inputs.get("freeform_faces") or {}
    ftr = inputs.get("freeform_trimming_readiness") or {}
    sp = inputs.get("stitching_plan") or {}
    region_graph = inputs.get("region_graph") or {}

    step_exported = bool(step_export.get("step_exported"))
    roundtrip_passed = rt.get("status") in ("passed", "warning")
    roundtrip_failed = rt.get("status") == "failed"
    shell_type = (sewing.get("summary") or {}).get("shell_type")
    has_closed_shell = shell_type == "closed_shell"
    has_partial_shell = shell_type == "partial_shell"
    validated_faces = _safe_int((faces_doc.get("summary") or {}).get("generated_face_count"))
    freeform_gen = _safe_int((freeform_faces.get("summary") or {}).get("generated_face_count"))
    has_regions = bool(region_graph.get("regions"))

    # 1. step_exported — verified STEP
    if step_exported and not roundtrip_failed:
        return (
            "step_exported",
            "brep",
            "step_solid",
            True,
            roundtrip_passed,
            "use_reconstructed_step",
        )

    # 2. closed_brep_solid — valid closed shell but STEP missing/unverified
    if has_closed_shell and not step_exported:
        return (
            "closed_brep_solid",
            "brep",
            "partial_faces",
            False,
            False,
            "export_step_or_verify",
        )

    # 3. partial_brep — analytic faces exist but no closed solid
    if validated_faces > 0:
        return (
            "partial_brep",
            "brep",
            "partial_faces",
            False,
            False,
            "improve_stitching" if has_partial_shell else "use_partial_brep",
        )

    # 4. freeform_candidate_only — freeform faces exist but no analytic solid
    if freeform_gen > 0:
        face_list = ftr.get("faces") or []
        trimming_ready = any(str(f.get("trimming_readiness")) == "ready" for f in face_list)
        has_boundary_issue = any(
            any(issue in (f.get("blocking_issues") or [])
                for issue in ("boundary_missing", "boundary_poor", "self_intersection_risk_high"))
            for f in face_list
        )
        next_action = (
            "attempt_freeform_trimming" if trimming_ready
            else "improve_boundary" if has_boundary_issue
            else "improve_segmentation"
        )
        return (
            "freeform_candidate_only",
            "mixed",
            "candidate_faces_only",
            False,
            False,
            next_action,
        )

    # 5. mesh_only — mesh exists but no usable B-Rep/face evidence
    if has_regions:
        return (
            "mesh_only",
            "mesh",
            "mesh_only",
            False,
            False,
            "improve_segmentation",
        )

    # 6. insufficient_data
    return (
        "insufficient_data",
        "none",
        "none",
        False,
        False,
        "request_user_input",
    )


def build_mesh_to_cad_reconstruction_status(
    package_path: str | Path,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate mesh-to-CAD reconstruction status from a package.

    If ``inputs`` is provided, uses it directly (for testing). Otherwise reads
    all artifacts from the package. Pure aggregation — no geometry creation.
    """
    package_path = Path(package_path)

    if inputs is None:
        inputs = {}
        if package_path.exists():
            try:
                with zipfile.ZipFile(package_path, "r") as zf:
                    names = set(zf.namelist())
                    inputs["region_graph"] = _read_json(zf, MESH_REGION_GRAPH_PATH, names)
                    inputs["surface_fit"] = _read_json(zf, MESH_SURFACE_FIT_PATH, names)
                    inputs["freeform_fit"] = _read_json(zf, FREEFORM_SURFACE_FIT_PATH, names)
                    inputs["freeform_readiness"] = _read_json(zf, FREEFORM_READINESS_PATH, names)
                    inputs["freeform_faces"] = _read_json(zf, FREEFORM_BREP_FACES_PATH, names)
                    inputs["freeform_trimming_readiness"] = _read_json(zf, TRIMMING_READINESS_PATH, names)
                    inputs["reconstruction_readiness"] = _read_json(zf, MESH_RECONSTRUCTION_READINESS_PATH, names)
                    inputs["brep_plan"] = _read_json(zf, MESH_BREP_PLAN_PATH, names)
                    inputs["partial_brep_surfaces"] = _read_json(zf, PARTIAL_BREP_SURFACES_PATH, names)
                    inputs["partial_brep_faces"] = _read_json(zf, PARTIAL_BREP_FACES_PATH, names)
                    inputs["stitching_plan"] = _read_json(zf, MESH_BREP_STITCHING_PLAN_PATH, names)
                    inputs["stitching_readiness"] = _read_json(zf, MESH_BREP_STITCHING_READINESS_PATH, names)
                    inputs["sewing"] = _read_json(zf, MESH_BREP_SEWING_PATH, names)
                    inputs["step_export"] = _read_json(zf, MESH_BREP_STEP_EXPORT_PATH, names)
                    inputs["roundtrip_verification"] = _read_json(zf, MESH_BREP_ROUNDTRIP_PATH, names)
                    inputs["step_exists"] = RECONSTRUCTED_STEP_PATH in names
            except Exception:
                pass

    status, geometry_kind, cad_editability, step_available, step_verified, next_action = _classify_status(inputs)
    coverage = _build_coverage(inputs)
    readiness = _build_readiness(inputs)
    blockers = _build_blockers(inputs)

    # Override next_action if critical blockers exist for statuses that claim a solid
    critical_blockers = [b for b in blockers if b.get("severity") == "critical"]
    if critical_blockers and status in ("closed_brep_solid",):
        next_action = "request_user_input"

    # Warnings and errors from downstream artifacts
    warnings: list[str] = []
    errors: list[str] = []
    for key in ("sewing", "step_export", "roundtrip_verification", "reconstruction_readiness"):
        doc = inputs.get(key) or {}
        warnings.extend(doc.get("warnings") or [])
        errors.extend(doc.get("errors") or [])

    source_artifacts = [
        name for name, val in {
            MESH_REGION_GRAPH_PATH: inputs.get("region_graph"),
            MESH_SURFACE_FIT_PATH: inputs.get("surface_fit"),
            FREEFORM_SURFACE_FIT_PATH: inputs.get("freeform_fit"),
            FREEFORM_READINESS_PATH: inputs.get("freeform_readiness"),
            FREEFORM_BREP_FACES_PATH: inputs.get("freeform_faces"),
            TRIMMING_READINESS_PATH: inputs.get("freeform_trimming_readiness"),
            MESH_RECONSTRUCTION_READINESS_PATH: inputs.get("reconstruction_readiness"),
            MESH_BREP_PLAN_PATH: inputs.get("brep_plan"),
            PARTIAL_BREP_SURFACES_PATH: inputs.get("partial_brep_surfaces"),
            PARTIAL_BREP_FACES_PATH: inputs.get("partial_brep_faces"),
            MESH_BREP_STITCHING_PLAN_PATH: inputs.get("stitching_plan"),
            MESH_BREP_STITCHING_READINESS_PATH: inputs.get("stitching_readiness"),
            MESH_BREP_SEWING_PATH: inputs.get("sewing"),
            MESH_BREP_STEP_EXPORT_PATH: inputs.get("step_export"),
            MESH_BREP_ROUNDTRIP_PATH: inputs.get("roundtrip_verification"),
            RECONSTRUCTED_STEP_PATH: inputs.get("step_exists"),
            RECONSTRUCTED_TOPOLOGY_PATH: inputs.get("roundtrip_verification"),
        }.items()
        if val is not None
    ]

    return {
        "format": "aieng.mesh_to_cad.reconstruction_status.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": status,
        "geometry_kind": geometry_kind,
        "cad_editability": cad_editability,
        "step_available": step_available,
        "step_verified": step_verified,
        "main_artifacts": {
            "reconstructed_step": RECONSTRUCTED_STEP_PATH if step_available else None,
            "reconstructed_topology_map": RECONSTRUCTED_TOPOLOGY_PATH if step_available else None,
            "region_graph": MESH_REGION_GRAPH_PATH if inputs.get("region_graph") else None,
            "surface_fit": MESH_SURFACE_FIT_PATH if inputs.get("surface_fit") else None,
            "freeform_fit": FREEFORM_SURFACE_FIT_PATH if inputs.get("freeform_fit") else None,
            "freeform_faces": FREEFORM_BREP_FACES_PATH if inputs.get("freeform_faces") else None,
        },
        "coverage": coverage,
        "readiness": readiness,
        "blockers": blockers,
        "recommended_next_action": next_action,
        "honesty": {
            "mesh_is_not_brep": geometry_kind in ("mesh", "none"),
            "freeform_candidates_are_not_stitched": bool(
                coverage.get("freeform_candidate_face_count", 0) > 0 and status != "step_exported"
            ),
            "step_only_when_verified": True,
            "production_cad_certified": False,
        },
        "source_artifacts": source_artifacts,
        "warnings": warnings[:20],
        "errors": errors[:20],
        "claim_boundary": (
            "Mesh-to-CAD reconstruction STATUS AGGREGATOR — diagnostic summary only. "
            "Does NOT create geometry, does NOT stitch, does NOT sew, does NOT export STEP. "
            "Reads existing pipeline artifacts and classifies reconstruction level honestly."
        ),
    }


def write_mesh_to_cad_reconstruction_status(package_path: str | Path) -> dict[str, Any]:
    """Build + write diagnostics/mesh_to_cad_reconstruction_status.json.
    Best-effort; returns the status document."""
    package_path = Path(package_path)
    status_doc = build_mesh_to_cad_reconstruction_status(package_path)
    if not package_path.exists():
        return status_doc

    data = (json.dumps(status_doc, indent=2, sort_keys=True) + "\n").encode()
    tmp = package_path.with_suffix(".recon_status.tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename != STATUS_PATH:
                    dst.writestr(item, src.read(item.filename))
            dst.writestr(STATUS_PATH, data)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return status_doc
