"""CAE field, audit, manifest, consistency, claim, and evidence routes."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from ..legacy_app_symbols import sync_main_symbols
from ..logging_utils import log_exception

LOGGER = logging.getLogger("app.app_factory")

# Synthetic fallback metadata for every selectable CAE result field.
# Real FRD data overrides these min/max values; this map only ensures
# honest units and colormaps when no solver result is present yet.
_FIELD_SYNTHETIC_DEFAULTS: dict[str, dict[str, Any]] = {
    # Von Mises stress and legacy alias
    "von_mises": {"min_value": 0.0, "max_value": 250.0, "unit": "MPa", "colormap": "thermal"},
    "stress": {"min_value": 0.0, "max_value": 250.0, "unit": "MPa", "colormap": "thermal"},
    # Stress tensor components (signed)
    "sxx": {"min_value": -250.0, "max_value": 250.0, "unit": "MPa", "colormap": "coolwarm"},
    "syy": {"min_value": -250.0, "max_value": 250.0, "unit": "MPa", "colormap": "coolwarm"},
    "szz": {"min_value": -250.0, "max_value": 250.0, "unit": "MPa", "colormap": "coolwarm"},
    "sxy": {"min_value": -250.0, "max_value": 250.0, "unit": "MPa", "colormap": "coolwarm"},
    "sxz": {"min_value": -250.0, "max_value": 250.0, "unit": "MPa", "colormap": "coolwarm"},
    "syz": {"min_value": -250.0, "max_value": 250.0, "unit": "MPa", "colormap": "coolwarm"},
    # Principal stresses and derived scalar stress measures
    "s1": {"min_value": -250.0, "max_value": 250.0, "unit": "MPa", "colormap": "thermal"},
    "s2": {"min_value": -250.0, "max_value": 250.0, "unit": "MPa", "colormap": "thermal"},
    "s3": {"min_value": -250.0, "max_value": 250.0, "unit": "MPa", "colormap": "thermal"},
    "tresca": {"min_value": 0.0, "max_value": 250.0, "unit": "MPa", "colormap": "thermal"},
    "max_shear": {"min_value": 0.0, "max_value": 250.0, "unit": "MPa", "colormap": "thermal"},
    # Displacement magnitude and legacy alias
    "disp_magnitude": {"min_value": 0.0, "max_value": 5.0, "unit": "mm", "colormap": "coolwarm"},
    "displacement": {"min_value": 0.0, "max_value": 5.0, "unit": "mm", "colormap": "coolwarm"},
    # Per-axis displacement components (signed)
    "ux": {"min_value": -5.0, "max_value": 5.0, "unit": "mm", "colormap": "coolwarm"},
    "uy": {"min_value": -5.0, "max_value": 5.0, "unit": "mm", "colormap": "coolwarm"},
    "uz": {"min_value": -5.0, "max_value": 5.0, "unit": "mm", "colormap": "coolwarm"},
    # Safety factor (yield / von Mises)
    "safety_factor": {"min_value": 0.0, "max_value": 10.0, "unit": "", "colormap": "thermal"},
}


def _field_credibility(source: str, aieng_root: Path) -> dict[str, Any]:
    """Return the V&V-40 credibility stamp for a field descriptor response.

    FRD-backed fields are stamped as ``executed_solver_result``; synthetic
    fallbacks are downgraded to ``unverified`` so they cannot be mistaken for
    solver evidence.
    """
    aieng_src = aieng_root / "src"
    injected = False
    if str(aieng_src) not in sys.path:
        sys.path.insert(0, str(aieng_src))
        injected = True
    try:
        from aieng.converters.credibility import classify_credibility  # type: ignore[import]

        if source == "frd":
            return classify_credibility(
                "solver",
                solver_executed=True,
                is_solver_evidence=True,
                notes="Per-node FRD data extracted from an executed solver run.",
            )
        return classify_credibility(
            "solver",
            solver_executed=False,
            notes="Synthetic fallback; no solver result available for this field.",
        )
    finally:
        if injected:
            try:
                sys.path.remove(str(aieng_src))
            except ValueError:
                pass


def _sync_main_symbols() -> None:
    sync_main_symbols(globals())


def register_evidence_routes(app: FastAPI, *, active_settings: Any) -> None:
    _sync_main_symbols()

    @app.get("/api/projects/{project_id}/fields/{field_name}")
    def get_field_descriptor(project_id: str, field_name: str) -> dict[str, Any]:
        project = get_project(active_settings, project_id)
        meta = _FIELD_SYNTHETIC_DEFAULTS.get(
            field_name, {"min_value": 0.0, "max_value": 1.0, "unit": "", "colormap": "thermal"}
        )

        # Attempt real FRD extraction
        pkg = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        frd_data: dict[str, Any] | None = None
        if pkg is not None and pkg.exists():
            try:
                frd_data = _extract_frd_field_data(pkg, field_name, active_settings.aieng_root)
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to extract FRD field data; using synthetic field descriptor fallback.",
                    subsystem="app_factory.field_descriptor.read_frd",
                    context={"project_id": project_id, "field_name": field_name},
                )
                frd_data = None

        if frd_data is not None:
            return {
                "field_name": field_name,
                "project_id": project_id,
                "format": "vertex_json",
                "basis": "frd_nearest_node",
                "min_value": frd_data["min_value"],
                "max_value": frd_data["max_value"],
                "unit": frd_data["unit"],
                "colormap": meta["colormap"],
                "source": "frd",
                "values": frd_data["values"],
                "node_coords": frd_data["node_coords"],
                "warnings": frd_data["warnings"],
                "credibility": _field_credibility("frd", active_settings.aieng_root),
            }

        # Fallback to synthetic
        return {
            "field_name": field_name,
            "project_id": project_id,
            "format": "vertex_synthetic",
            "basis": "y_normalized",
            "min_value": meta["min_value"],
            "max_value": meta["max_value"],
            "unit": meta["unit"],
            "colormap": meta["colormap"],
            "source": "synthetic_mock",
            "credibility": _field_credibility("synthetic", active_settings.aieng_root),
        }

    @app.get("/api/projects/{project_id}/cae-result-fields")
    def list_cae_result_fields(project_id: str) -> dict[str, Any]:
        """List available CAE result fields from computed_metrics.json.

        Read-only. Does not execute solvers or advance claims.
        Returns compact metadata only; full per-node arrays are not served here.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        frd_source: str | None = _resolve_frd_in_package(package_path)
        available_fields: list[dict[str, Any]] = []
        warnings: list[str] = []

        computed_raw: dict[str, Any] | None = None
        try:
            with zipfile.ZipFile(package_path, "r") as _zf:
                if "results/computed_metrics.json" in _zf.namelist():
                    import json as _json
                    computed_raw = _json.loads(_zf.read("results/computed_metrics.json"))
        except Exception:
            log_exception(
                LOGGER,
                "Failed to read computed metrics while building field descriptor.",
                subsystem="app_factory.field_descriptor.read_computed_metrics",
                context={"project_id": project_id, "field_name": field_name},
            )
            warnings.append("Could not read results/computed_metrics.json.")

        if computed_raw and isinstance(computed_raw, dict):
            first_metrics: dict[str, Any] = {}
            for lc in (computed_raw.get("load_cases") or []):
                if isinstance(lc, dict) and lc.get("metrics"):
                    first_metrics = lc["metrics"]
                    break
            for _fname, _fmeta in _CAE_RESULT_FIELDS.items():
                metric = first_metrics.get(_fmeta["metric_key"])
                if metric and isinstance(metric, dict) and metric.get("value") is not None:
                    available_fields.append({
                        "field_name": _fname,
                        "unit": metric.get("unit") or _fmeta["unit"],
                        "max_value": metric["value"],
                        "source_type": "computed_metrics",
                        "source_artifact": "results/computed_metrics.json",
                    })
        elif frd_source:
            for _fname, _fmeta in _CAE_RESULT_FIELDS.items():
                available_fields.append({
                    "field_name": _fname,
                    "unit": _fmeta["unit"],
                    "max_value": None,
                    "source_type": "frd",
                    "source_artifact": frd_source,
                })
            warnings.append("computed_metrics.json absent; field availability inferred from FRD presence.")

        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "available_fields": available_fields,
            "frd_source": frd_source,
            "claim_advancement": "none",
            "revalidation_status": _build_revalidation_response(
                _read_revalidation_status(package_path)
            ),
            "warnings": warnings,
        }

    @app.get("/api/projects/{project_id}/cae-result-fields/{field_name}")
    def get_cae_result_field_summary(project_id: str, field_name: str) -> dict[str, Any]:
        """Compact summary statistics for a named CAE result field.

        Read-only. Does not serve full per-node arrays, execute solvers,
        or advance engineering claims.
        """
        if field_name not in _CAE_RESULT_FIELDS:
            raise HTTPException(
                status_code=404,
                detail=f"Field '{field_name}' not supported. Available: {sorted(_CAE_RESULT_FIELDS)}",
            )

        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        _fmeta = _CAE_RESULT_FIELDS[field_name]
        frd_path_in_pkg = _resolve_frd_in_package(package_path)
        warnings: list[str] = []

        frd_stats: dict[str, Any] | None = None
        if frd_path_in_pkg is not None:
            try:
                _raw = _extract_frd_field_data(package_path, field_name, active_settings.aieng_root)
                if _raw is not None:
                    import math as _math
                    frd_stats = {
                        "min_value": _raw["min_value"],
                        "max_value": _raw["max_value"],
                        "node_count": len(_raw["values"]),
                        "values_finite": all(_math.isfinite(v) for v in _raw["values"]),
                    }
                    warnings.extend(_raw.get("warnings") or [])
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to extract FRD statistics for field endpoint.",
                    subsystem="app_factory.field_descriptor.extract_frd_stats",
                    context={"project_id": project_id, "field_name": field_name},
                )
                warnings.append(f"FRD extraction failed for '{field_name}'.")

        cm_max_value: float | None = None
        cm_unit: str | None = None
        try:
            with zipfile.ZipFile(package_path, "r") as _zf:
                if "results/computed_metrics.json" in _zf.namelist():
                    import json as _json
                    _cm = _json.loads(_zf.read("results/computed_metrics.json"))
                    for _lc in (_cm.get("load_cases") or []):
                        _m = (_lc.get("metrics") or {}).get(_fmeta["metric_key"])
                        if _m and isinstance(_m, dict) and _m.get("value") is not None:
                            cm_max_value = _m["value"]
                            cm_unit = _m.get("unit") or _fmeta["unit"]
                            break
        except Exception:
            log_exception(
                LOGGER,
                "Failed to derive field descriptor values from computed metrics.",
                subsystem="app_factory.field_descriptor.computed_metric_lookup",
                context={"project_id": project_id, "field_name": field_name},
            )

        if frd_stats is None and cm_max_value is None:
            raise HTTPException(
                status_code=404,
                detail=f"No result data for '{field_name}'. Run solver and extract results first.",
            )

        if frd_stats is not None:
            stats = frd_stats
            unit = _fmeta["unit"]
            source_type = "frd"
        else:
            stats = {"min_value": None, "max_value": cm_max_value, "node_count": None, "values_finite": None}
            unit = cm_unit or _fmeta["unit"]
            source_type = "computed_metrics"

        return {
            "schema_version": "0.1",
            "field_name": field_name,
            "unit": unit,
            "source": {
                "frd_path": frd_path_in_pkg,
                "source_type": source_type,
                "computed_metrics_path": "results/computed_metrics.json" if cm_max_value is not None else None,
            },
            "stats": stats,
            "evidence_role": _fmeta["evidence_role"],
            "claim_advancement": "none",
            "revalidation_status": _build_revalidation_response(
                _read_revalidation_status(package_path)
            ),
            "warnings": warnings,
        }

    @app.get("/api/projects/{project_id}/audit-events")
    def get_project_audit_events(project_id: str) -> dict[str, Any]:
        """Read the package runtime audit event log.

        Read-only. Returns events in append order (oldest first). Returns an
        empty list rather than 404 when no audit log exists yet. Does not
        execute solvers or advance claims.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        events = _read_audit_events_from_package(package_path)
        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "events": events,
            "count": len(events),
            "claim_advancement": "none",
        }

    @app.get("/api/projects/{project_id}/artifact-manifest")
    def get_project_artifact_manifest(project_id: str) -> dict[str, Any]:
        """Return a read-only manifest of all artifacts in the .aieng package.

        Classifies each artifact by kind and category. Annotates CAE result
        artifacts with revalidation/freshness context from the revalidation
        status artifact when present. Does not write to the package or advance
        any engineering claim.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        return _generate_artifact_manifest(package_path)

    @app.get("/api/projects/{project_id}/package-consistency")
    def get_package_consistency(project_id: str) -> dict[str, Any]:
        """Run read-only consistency checks on the .aieng package metadata layers.

        Checks: (A) evidence index path coverage, (B) audit event artifact
        references, (C) field summary source traceability, (D) revalidation
        status consistency, (E) claim non-advancement. Does not mutate the
        package, execute solvers, or advance engineering claims.

        Stale state (requires_revalidation=True) is reported as 'warning', not
        'error' — stale state is valid while geometry edits are pending.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        checks = _run_package_consistency_checks(package_path)
        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "status": _rollup_check_status(checks),
            "claim_advancement": "none",
            "checks": checks,
        }

    @app.post("/api/projects/{project_id}/claim-proposals")
    def create_claim_proposal(
        project_id: str,
        body: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Create a claim proposal artifact in the .aieng package.

        Records a proposed claim update as an auditable artifact at
        claims/proposals/{proposal_id}.json. Does not accept the claim, does
        not create or modify claim maps, and does not advance any engineering
        claim. Supporting evidence must exist in the package or evidence index.

        Request: claim_id, proposed_status, supporting_evidence, rationale.
        proposed_status must be one of: supported, not_supported, needs_review.
        """
        data = body or {}
        claim_id = str(data.get("claim_id") or "").strip()
        proposed_status = str(data.get("proposed_status") or "").strip()
        supporting_evidence = data.get("supporting_evidence") or []
        rationale = str(data.get("rationale") or "").strip()

        errors = _validate_claim_proposal_request(
            claim_id=claim_id,
            proposed_status=proposed_status,
            supporting_evidence=supporting_evidence,
            rationale=rationale,
        )
        if errors:
            raise HTTPException(status_code=400, detail=errors[0])

        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        with zipfile.ZipFile(package_path, "r") as zf:
            pkg_names: set[str] = set(zf.namelist())
            ei_raw = (
                zf.read("results/evidence_index.json")
                if "results/evidence_index.json" in pkg_names
                else None
            )

        evidence_entries: list[dict[str, Any]] = []
        if ei_raw:
            try:
                evidence_entries = json.loads(ei_raw).get("entries") or []
            except json.JSONDecodeError:
                pass

        rs = _read_revalidation_status(package_path)
        missing = [
            p for p in supporting_evidence
            if not _resolve_evidence_reference(
                path=p,
                pkg_names=pkg_names,
                evidence_entries=evidence_entries,
                revalidation_status=rs,
            )["usable_for_claim_proposal"]
        ]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"supporting_evidence path(s) not found in package or evidence index: {missing}",
            )

        proposal = _build_claim_proposal(
            claim_id=claim_id,
            proposed_status=proposed_status,
            supporting_evidence=supporting_evidence,
            rationale=rationale,
        )
        proposal_path = _write_claim_proposal_to_package(package_path, proposal)

        try:
            _append_audit_event_to_package(
                package_path,
                _build_audit_event(
                    tool="claims.propose_update",
                    event_type="claim_proposal_created",
                    status="completed",
                    artifacts_written=[proposal_path],
                    evidence_created=[],
                    state_changes={
                        "claim_id": claim_id,
                        "proposed_status": proposed_status,
                    },
                    geometry_revision=None,
                    revalidation_status=None,
                ),
            )
        except Exception:
            log_exception(
                LOGGER,
                "Failed to write claim proposal audit artifact.",
                subsystem="app_factory.audit.claim_proposal",
                context={"project_id": project_id},
            )

        return {
            "schema_version": "0.1",
            "proposal": proposal,
            "proposal_path": proposal_path,
            "claim_advancement": "none",
        }

    @app.get("/api/projects/{project_id}/claim-proposals")
    def list_claim_proposals(project_id: str) -> dict[str, Any]:
        """List all claim proposal artifacts in the package.

        Read-only. Returns proposals sorted by created_at then proposal_id.
        Returns an empty list when no proposals exist.
        Never mutates the package or creates claim maps.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        proposals = _read_claim_proposals_from_package(package_path)
        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "count": len(proposals),
            "proposals": proposals,
            "claim_advancement": "none",
        }

    @app.get("/api/projects/{project_id}/claim-proposals/{proposal_id}")
    def get_claim_proposal(project_id: str, proposal_id: str) -> dict[str, Any]:
        """Read a single claim proposal by proposal_id.

        Read-only. Returns 404 if the proposal does not exist.
        Never mutates the package or creates claim maps.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        internal_path = f"{CLAIM_PROPOSALS_DIR}/{proposal_id}.json"
        with zipfile.ZipFile(package_path, "r") as zf:
            if internal_path not in zf.namelist():
                raise HTTPException(
                    status_code=404,
                    detail=f"claim proposal '{proposal_id}' not found",
                )
            try:
                proposal = json.loads(zf.read(internal_path))
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"proposal artifact is not valid JSON: {exc}",
                )

        return {
            "schema_version": "0.1",
            "proposal_path": internal_path,
            "proposal": proposal,
            "claim_advancement": "none",
        }

    @app.get("/api/projects/{project_id}/claim-proposals/{proposal_id}/support-packet")
    def get_claim_support_packet(project_id: str, proposal_id: str) -> dict[str, Any]:
        """Return a read-only support packet aggregating proposal + evidence + audit data.

        Assembles the proposal metadata, resolver outputs for each supporting
        evidence path, flattened warnings, stale/missing evidence counts, and
        the related audit events. Read-only — does not mutate the package,
        execute solvers, or advance any engineering claim.

        Returns 404 when the package or the proposal does not exist.
        Always returns claim_advancement: 'none'.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        internal_path = f"{CLAIM_PROPOSALS_DIR}/{proposal_id}.json"
        with zipfile.ZipFile(package_path, "r") as zf:
            pkg_names: set[str] = set(zf.namelist())
            if internal_path not in pkg_names:
                raise HTTPException(
                    status_code=404,
                    detail=f"claim proposal '{proposal_id}' not found",
                )
            try:
                proposal = json.loads(zf.read(internal_path))
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"proposal artifact is not valid JSON: {exc}",
                )
            ei_raw = (
                zf.read("results/evidence_index.json")
                if "results/evidence_index.json" in pkg_names
                else None
            )

        evidence_entries: list[dict[str, Any]] = []
        if ei_raw:
            try:
                evidence_entries = json.loads(ei_raw).get("entries") or []
            except json.JSONDecodeError:
                pass

        rs = _read_revalidation_status(package_path)
        audit_events = _read_audit_events_from_package(package_path)

        packet = _build_claim_support_packet(
            proposal=proposal,
            proposal_path=internal_path,
            pkg_names=pkg_names,
            evidence_entries=evidence_entries,
            revalidation_status=rs,
            audit_events=audit_events,
        )
        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "support_packet": packet,
            "claim_advancement": "none",
        }

    @app.get("/api/projects/{project_id}/evidence-references/resolve")
    def resolve_evidence_reference(
        project_id: str,
        path: str = Query(..., description="Package-internal artifact path to resolve"),
    ) -> dict[str, Any]:
        """Resolve a single package artifact path against the current package state.

        Read-only. Returns classification, evidence-index membership, revalidation
        freshness, and whether the path is usable as supporting evidence for a
        claim proposal. Does not mutate the package, execute solvers, or advance
        any engineering claim.

        Returns 404 when the package does not exist.
        Returns 400 when path is empty or not a valid internal package path.
        Always returns claim_advancement: 'none'.
        A path that is absent from the package still returns 200 with exists=false.
        """
        path = path.strip()
        if not path or not _is_internal_package_path(path):
            raise HTTPException(
                status_code=400,
                detail="path must be a non-empty relative package-internal path (no leading '/', no backslashes)",
            )

        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        with zipfile.ZipFile(package_path, "r") as zf:
            pkg_names: set[str] = set(zf.namelist())
            ei_raw = (
                zf.read("results/evidence_index.json")
                if "results/evidence_index.json" in pkg_names
                else None
            )

        evidence_entries: list[dict[str, Any]] = []
        if ei_raw:
            try:
                evidence_entries = json.loads(ei_raw).get("entries") or []
            except json.JSONDecodeError:
                pass

        rs = _read_revalidation_status(package_path)
        resolved = _resolve_evidence_reference(
            path=path,
            pkg_names=pkg_names,
            evidence_entries=evidence_entries,
            revalidation_status=rs,
        )
        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "resolved": resolved,
            "claim_advancement": "none",
        }
