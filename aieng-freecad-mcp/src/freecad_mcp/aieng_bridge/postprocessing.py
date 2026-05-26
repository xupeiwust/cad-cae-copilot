"""Post-processing evidence layer for CAE results.

Extracts deterministic result metrics and exports structured artifacts
(CSV, VTK) while preserving claim discipline.

Rules:
- Post-processing evidence improves AI readability; it does not validate claims.
- Result file exists != claim passed.
- Metric extracted != design safe.
- CSV/VTK exported != validation complete.
- Surrogate outputs are not solver evidence.
- Never modify claim_map.json.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from freecad_mcp.aieng_bridge.context import load_aieng_context
from freecad_mcp.aieng_bridge.persistence import (
    PersistenceError,
    persist_standard_result_to_aieng,
)
from freecad_mcp.tool_contracts import ClaimPolicy, EvidenceBlock, StandardToolResult, TraceBlock


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PostprocessRequest(BaseModel):
    """Request to post-process CAE results."""

    model_config = ConfigDict(extra="forbid")

    package_path: str | None = None
    result_source: str | None = None
    persist_to_aieng: bool = False
    export_csv: bool = True
    export_vtk: bool = False
    output_dir: str | None = None
    producer_kind: Literal["surrogate", "freecad_fem", "external_solver"] = "surrogate"
    analysis_type: Literal["static_structural", "thermal", "modal", "buckling"] = "static_structural"


class ResultMetric(BaseModel):
    """A single extracted or estimated metric."""

    model_config = ConfigDict(extra="forbid")

    name: str
    value: float | int | str | None = None
    unit: str | None = None
    source: str | None = None
    status: Literal["found", "not_found", "estimated"] = "found"


class PostprocessArtifact(BaseModel):
    """A written post-processing artifact."""

    model_config = ConfigDict(extra="forbid")

    path: str
    artifact_type: Literal["csv", "vtk", "json", "screenshot", "summary"]
    quantity: str | None = None
    source_artifact: str | None = None


class PostprocessSummary(BaseModel):
    """Summary of a post-processing run."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "partial", "failed", "unsupported", "rejected"]
    analysis_type: str
    producer_kind: str
    metrics: list[ResultMetric] = []
    artifacts_written: list[PostprocessArtifact] = []
    evidence_ids: list[str] = []
    trace_ids: list[str] = []
    claim_policy: ClaimPolicy = Field(default_factory=ClaimPolicy)
    warnings: list[str] = []
    errors: list[str] = []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def postprocess_results(request: PostprocessRequest) -> PostprocessSummary:
    """Run post-processing on CAE results.

    Steps:
    1. Validate inputs (package_path required if persist_to_aieng).
    2. Extract metrics from result_source or generate conservative surrogate summary.
    3. Export CSV if requested.
    4. Handle VTK if requested (currently unsupported without field data).
    5. Build evidence and optionally persist to .aieng.
    """
    context = load_aieng_context(request.package_path)

    if request.persist_to_aieng and not request.package_path:
        return PostprocessSummary(
            status="rejected",
            analysis_type=request.analysis_type,
            producer_kind=request.producer_kind,
            claim_policy=ClaimPolicy(),
            errors=["persist_to_aieng=true requires a valid package_path."],
        )

    # Determine output directory
    output_dir = _resolve_output_dir(request)

    # Extract metrics
    metrics = extract_result_metrics(
        request.result_source, request.analysis_type, request.producer_kind
    )

    artifacts: list[PostprocessArtifact] = []
    warnings: list[str] = []
    unsupported: list[str] = []

    # CSV export
    if request.export_csv:
        csv_artifacts = export_postprocess_csv(metrics, str(output_dir))
        artifacts.extend(csv_artifacts)

    # VTK export
    if request.export_vtk:
        vtk_artifacts = export_postprocess_vtk(metrics, str(output_dir))
        artifacts.extend(vtk_artifacts)
        if not vtk_artifacts:
            unsupported.append(
                "VTK export is unsupported: no nodal/element field data available."
            )

    summary = PostprocessSummary(
        status="success",
        analysis_type=request.analysis_type,
        producer_kind=request.producer_kind,
        metrics=metrics,
        artifacts_written=artifacts,
        claim_policy=ClaimPolicy(claims_advanced=False, requires_explicit_update_claim=True),
        warnings=warnings,
        errors=[],
    )

    if unsupported:
        summary.unsupported = unsupported  # type: ignore[attr-defined]
        summary.status = "partial"

    # Persistence
    _maybe_persist_postprocess(summary, request, str(output_dir))
    return summary


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------

def extract_result_metrics(
    result_source: str | None,
    analysis_type: str,
    producer_kind: str,
) -> list[ResultMetric]:
    """Extract or estimate result metrics from a result source.

    If result_source is a JSON file path, parse deterministic fields.
    If result_source is None and producer_kind is surrogate, return conservative estimates.
    Missing metrics are reported as not_found.
    """
    raw: dict[str, Any] | None = None
    if result_source and Path(result_source).is_file():
        try:
            with Path(result_source).open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            raw = None

    if raw is not None:
        return _extract_from_dict(raw, analysis_type, result_source)

    if producer_kind == "surrogate" and result_source is None:
        return _extract_surrogate_defaults(analysis_type)

    return [
        ResultMetric(
            name="result_source",
            value=result_source,
            status="not_found",
            source="extract_result_metrics",
        )
    ]


def _extract_from_dict(
    raw: dict[str, Any], analysis_type: str, source_path: str
) -> list[ResultMetric]:
    metrics: list[ResultMetric] = []

    if analysis_type == "static_structural":
        _add_if_present(metrics, raw, "max_von_mises_stress_mpa", "MPa", source_path)
        _add_if_present(metrics, raw, "max_displacement_mm", "mm", source_path)
        _add_if_present(metrics, raw, "factor_of_safety", "dimensionless", source_path)
        _add_if_present(metrics, raw, "meets_stress_limit", "bool", source_path)
        _add_if_present(metrics, raw, "meets_displacement_limit", "bool", source_path)
        _add_if_present(metrics, raw, "reaction_force_n", "N", source_path)

    elif analysis_type == "thermal":
        _add_if_present(metrics, raw, "max_temperature_c", "C", source_path)
        _add_if_present(metrics, raw, "min_temperature_c", "C", source_path)
        _add_if_present(metrics, raw, "max_heat_flux_w_m2", "W/m^2", source_path)

    elif analysis_type == "modal":
        freqs = raw.get("natural_frequencies_hz")
        if isinstance(freqs, list) and freqs:
            metrics.append(
                ResultMetric(
                    name="first_natural_frequency_hz",
                    value=freqs[0],
                    unit="Hz",
                    source=source_path,
                    status="found",
                )
            )
            metrics.append(
                ResultMetric(
                    name="natural_frequencies_hz",
                    value=str(freqs),
                    unit="Hz",
                    source=source_path,
                    status="found",
                )
            )
        else:
            metrics.append(
                ResultMetric(
                    name="first_natural_frequency_hz",
                    value=None,
                    unit="Hz",
                    source=source_path,
                    status="not_found",
                )
            )
        _add_if_present(metrics, raw, "mode_shapes_available", "bool", source_path)

    elif analysis_type == "buckling":
        _add_if_present(metrics, raw, "critical_load_factor", "dimensionless", source_path)
        _add_if_present(metrics, raw, "is_stable", "bool", source_path)

    # Common fields
    _add_if_present(metrics, raw, "solver_executed", "bool", source_path)
    _add_if_present(metrics, raw, "mesh_generated", "bool", source_path)

    return metrics


def _add_if_present(
    metrics: list[ResultMetric],
    raw: dict[str, Any],
    key: str,
    unit: str,
    source: str,
) -> None:
    if key in raw:
        metrics.append(
            ResultMetric(
                name=key,
                value=raw[key],
                unit=unit,
                source=source,
                status="found",
            )
        )
    else:
        metrics.append(
            ResultMetric(
                name=key,
                value=None,
                unit=unit,
                source=source,
                status="not_found",
            )
        )


def _extract_surrogate_defaults(analysis_type: str) -> list[ResultMetric]:
    """Return conservative default metrics for surrogate mode when no result source exists."""
    metrics: list[ResultMetric] = []

    if analysis_type == "static_structural":
        metrics.append(
            ResultMetric(
                name="max_von_mises_stress_mpa",
                value=None,
                unit="MPa",
                source="surrogate_default",
                status="not_found",
            )
        )
        metrics.append(
            ResultMetric(
                name="max_displacement_mm",
                value=None,
                unit="mm",
                source="surrogate_default",
                status="not_found",
            )
        )
        metrics.append(
            ResultMetric(
                name="factor_of_safety",
                value=None,
                unit="dimensionless",
                source="surrogate_default",
                status="not_found",
            )
        )

    elif analysis_type == "thermal":
        metrics.append(
            ResultMetric(
                name="max_temperature_c",
                value=None,
                unit="C",
                source="surrogate_default",
                status="not_found",
            )
        )

    elif analysis_type == "modal":
        metrics.append(
            ResultMetric(
                name="first_natural_frequency_hz",
                value=None,
                unit="Hz",
                source="surrogate_default",
                status="not_found",
            )
        )

    elif analysis_type == "buckling":
        metrics.append(
            ResultMetric(
                name="critical_load_factor",
                value=None,
                unit="dimensionless",
                source="surrogate_default",
                status="not_found",
            )
        )

    return metrics


# ---------------------------------------------------------------------------
# Artifact export
# ---------------------------------------------------------------------------

def export_postprocess_csv(
    metrics: list[ResultMetric], output_dir: str
) -> list[PostprocessArtifact]:
    """Export metrics to a CSV file."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    csv_path = out_path / "postprocess_metrics.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "value", "unit", "status", "source"])
        for m in metrics:
            writer.writerow([m.name, m.value, m.unit or "", m.status, m.source or ""])

    return [
        PostprocessArtifact(
            path=str(csv_path),
            artifact_type="csv",
            quantity="metrics",
        )
    ]


def export_postprocess_vtk(
    metrics: list[ResultMetric], output_dir: str
) -> list[PostprocessArtifact]:
    """Export metrics to VTK format.

    Currently unsupported because metrics are scalar summaries, not nodal/element fields.
    Returns empty list; caller is expected to record unsupported warning.
    """
    # VTK export requires actual nodal/element field data, which is not available
    # from scalar metric summaries. Future implementation could accept a field_data
    # parameter and write a .vtu or .vtk file.
    return []


# ---------------------------------------------------------------------------
# Evidence helpers
# ---------------------------------------------------------------------------

def build_postprocess_evidence(summary: PostprocessSummary) -> dict[str, Any]:
    """Build evidence metadata dict for a post-processing run."""
    not_found = [m.name for m in summary.metrics if m.status == "not_found"]
    metadata: dict[str, Any] = {
        "analysis_type": summary.analysis_type,
        "producer_kind": summary.producer_kind,
        "metrics": [m.model_dump(mode="json") for m in summary.metrics],
        "not_found_metrics": not_found,
        "artifacts_written": [a.model_dump(mode="json") for a in summary.artifacts_written],
        "engineering_validation": False,
        "claims_advanced": False,
    }
    if summary.producer_kind == "surrogate":
        metadata["warning"] = "Surrogate post-processing output is not solver validation evidence."
    if summary.warnings:
        metadata.setdefault("warnings", []).extend(summary.warnings)
    if summary.errors:
        metadata.setdefault("errors", []).extend(summary.errors)
    return metadata


def _maybe_persist_postprocess(
    summary: PostprocessSummary,
    request: PostprocessRequest,
    output_dir: str,
) -> None:
    """Optionally persist post-process evidence and trace to .aieng."""
    if not request.persist_to_aieng or not request.package_path:
        return

    package_path = request.package_path

    try:
        metadata = build_postprocess_evidence(summary)
        result = StandardToolResult(
            status=summary.status,
            operation="aieng_postprocess_results",
            inputs={
                "analysis_type": request.analysis_type,
                "producer_kind": request.producer_kind,
                "result_source": request.result_source,
                "export_csv": request.export_csv,
                "export_vtk": request.export_vtk,
            },
            outputs={
                "metric_count": len(summary.metrics),
                "artifacts_written": [a.path for a in summary.artifacts_written],
            },
            artifacts_written=[a.path for a in summary.artifacts_written],
            evidence=EvidenceBlock(producer_kind=request.producer_kind),
            claim_policy=summary.claim_policy,
            trace=TraceBlock(),
            warnings=summary.warnings,
            errors=summary.errors,
        )
        meta = persist_standard_result_to_aieng(
            package_path, result, additional_metadata=metadata
        )
        if "evidence_id" in meta:
            summary.evidence_ids.append(meta["evidence_id"])
        if "trace_id" in meta:
            summary.trace_ids.append(meta["trace_id"])
    except PersistenceError as exc:
        summary.errors.append(f"Post-process persistence failed: {exc}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_output_dir(request: PostprocessRequest) -> Path:
    if request.output_dir:
        return Path(request.output_dir)
    if request.package_path:
        return Path(request.package_path) / "postprocess"
    return Path(tempfile.mkdtemp()) / "postprocess"
