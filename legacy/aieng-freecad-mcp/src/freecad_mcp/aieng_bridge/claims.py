"""Explicit evidence-backed claim update layer.

Rules:
- Evidence alone does not advance a claim.
- Only this module's update path may modify claim_map.json.
- All other tools remain claim-map immutable.
- Claim evaluation is deterministic; no LLM reasoning.
- Manual mode is supported but must be labeled as such.
- Every update leaves a trace record.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from freecad_mcp.aieng_bridge.persistence import (
    PersistenceError,
    _atomic_write_json,
)
from freecad_mcp.contracts.failure_mode import (
    CLAIM_NOT_FOUND,
    EVIDENCE_NOT_FOUND,
    MISSING_DECISION_CRITERIA,
    MISSING_EVIDENCE_IDS,
    MISSING_MANUAL_FIELDS,
    MISSING_PACKAGE_PATH,
    PERSISTENCE_FAILED,
    UNKNOWN_MODE,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ClaimDecisionCriterion(BaseModel):
    """A single deterministic criterion for evaluating a claim."""

    model_config = ConfigDict(extra="forbid")

    metric_name: str
    operator: Literal["<", "<=", ">", ">=", "==", "!="]
    threshold: float | int | str
    unit: str | None = None
    evidence_field: str | None = None  # e.g. "metadata.metrics", "outputs.result"


class ClaimUpdateRequest(BaseModel):
    """Request to update a claim status."""

    model_config = ConfigDict(extra="forbid")

    package_path: str
    claim_id: str
    evidence_ids: list[str]
    decision_criteria: list[ClaimDecisionCriterion] = []
    requested_status: Literal["pass", "fail", "unsupported"] | None = None
    mode: Literal["evaluate", "manual"] = "evaluate"
    rationale: str | None = None
    dry_run: bool = False


class CriterionResult(BaseModel):
    """Result of evaluating one criterion against evidence."""

    model_config = ConfigDict(extra="forbid")

    metric_name: str
    operator: str
    threshold: float | int | str
    actual_value: float | int | str | None = None
    status: Literal["pass", "fail", "not_found", "unsupported"]
    reason: str | None = None


class ClaimUpdateSummary(BaseModel):
    """Summary of a claim update operation."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "failed", "rejected", "unsupported"]
    claim_id: str
    old_status: str | None = None
    new_status: str | None = None
    evidence_ids: list[str] = []
    criteria_results: list[CriterionResult] = []
    claim_map_updated: bool = False
    trace_id: str | None = None
    primary_error_code: str | None = None
    warnings: list[str] = []
    errors: list[str] = []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def update_claim_status(request: ClaimUpdateRequest) -> ClaimUpdateSummary:
    """Update a claim status based on evidence and criteria.

    This is the only code path allowed to modify claim_map.json.

    Steps:
    1. Load claim_map and evidence_index.
    2. Validate inputs (claim exists, evidence exists, criteria valid).
    3. Evaluate criteria against evidence (evaluate mode) or validate manual inputs.
    4. If dry_run, return summary without writing.
    5. Update claim_map.json atomically and append trace.
    """
    package_path = Path(request.package_path)

    # Validation: package path
    if not package_path.is_dir():
        return ClaimUpdateSummary(
            status="rejected",
            claim_id=request.claim_id,
            primary_error_code=MISSING_PACKAGE_PATH,
            errors=[f"Package path is not a directory: {request.package_path}"],
        )

    # Load claim_map and evidence_index
    claim_map = load_claim_map(str(package_path))
    evidence_index = load_evidence_index(str(package_path))

    # Validation: claim exists
    claim = find_claim(claim_map, request.claim_id)
    if claim is None:
        return ClaimUpdateSummary(
            status="rejected",
            claim_id=request.claim_id,
            primary_error_code=CLAIM_NOT_FOUND,
            errors=[f"Claim not found: {request.claim_id}"],
        )

    # Validation: evidence_ids provided
    if not request.evidence_ids:
        return ClaimUpdateSummary(
            status="rejected",
            claim_id=request.claim_id,
            primary_error_code=MISSING_EVIDENCE_IDS,
            errors=["evidence_ids must not be empty."],
        )

    # Validation: evidence entries exist
    evidence_entries = find_evidence(evidence_index, request.evidence_ids)
    found_ids = {e.get("evidence_id") for e in evidence_entries}
    missing_ids = set(request.evidence_ids) - found_ids
    if missing_ids:
        return ClaimUpdateSummary(
            status="rejected",
            claim_id=request.claim_id,
            primary_error_code=EVIDENCE_NOT_FOUND,
            errors=[f"Evidence IDs not found: {sorted(missing_ids)}"],
        )

    old_status = claim.get("status", "unsupported")
    criteria_results: list[CriterionResult] = []
    new_status: str | None = None
    warnings: list[str] = []

    if request.mode == "evaluate":
        if not request.decision_criteria:
            return ClaimUpdateSummary(
                status="rejected",
                claim_id=request.claim_id,
                primary_error_code=MISSING_DECISION_CRITERIA,
                errors=["evaluate mode requires at least one decision_criterion."],
            )
        criteria_results = evaluate_claim_criteria(evidence_entries, request.decision_criteria)
        new_status = _determine_status_from_results(criteria_results)

    elif request.mode == "manual":
        if not request.rationale:
            return ClaimUpdateSummary(
                status="rejected",
                claim_id=request.claim_id,
                primary_error_code=MISSING_MANUAL_FIELDS,
                errors=["manual mode requires a rationale."],
            )
        if request.requested_status is None:
            return ClaimUpdateSummary(
                status="rejected",
                claim_id=request.claim_id,
                primary_error_code=MISSING_MANUAL_FIELDS,
                errors=["manual mode requires a requested_status."],
            )
        new_status = request.requested_status
        warnings.append("Claim status was set manually, not by deterministic evaluation.")

    else:
        return ClaimUpdateSummary(
            status="rejected",
            claim_id=request.claim_id,
            primary_error_code=UNKNOWN_MODE,
            errors=[f"Unknown mode: {request.mode}"],
        )

    # Dry run: evaluate but do not write
    if request.dry_run:
        return ClaimUpdateSummary(
            status="success",
            claim_id=request.claim_id,
            old_status=old_status,
            new_status=new_status,
            evidence_ids=request.evidence_ids,
            criteria_results=criteria_results,
            claim_map_updated=False,
            warnings=warnings,
        )

    # Update claim_map.json
    try:
        trace_id = _write_claim_update(
            package_path=str(package_path),
            claim=claim,
            claim_map=claim_map,
            request=request,
            new_status=new_status,
            criteria_results=criteria_results,
            old_status=old_status,
        )
    except PersistenceError as exc:
        return ClaimUpdateSummary(
            status="failed",
            claim_id=request.claim_id,
            old_status=old_status,
            primary_error_code=PERSISTENCE_FAILED,
            errors=[f"Failed to write claim update: {exc}"],
        )

    return ClaimUpdateSummary(
        status="success",
        claim_id=request.claim_id,
        old_status=old_status,
        new_status=new_status,
        evidence_ids=request.evidence_ids,
        criteria_results=criteria_results,
        claim_map_updated=True,
        trace_id=trace_id,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Evidence lookup
# ---------------------------------------------------------------------------

def load_claim_map(package_path: str) -> dict[str, Any]:
    """Load claim_map.json from package."""
    path = Path(package_path) / "results" / "claim_map.json"
    if not path.exists():
        return {"claims": []}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "claims" in data:
            return data
        return {"claims": []}
    except (json.JSONDecodeError, OSError):
        return {"claims": []}


def load_evidence_index(package_path: str) -> dict[str, Any]:
    """Load evidence_index.json from package."""
    path = Path(package_path) / "results" / "evidence_index.json"
    if not path.exists():
        return {"entries": []}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "entries" in data:
            return data
        if isinstance(data, list):
            return {"entries": data}
        return {"entries": []}
    except (json.JSONDecodeError, OSError):
        return {"entries": []}


def find_claim(claim_map: dict[str, Any], claim_id: str) -> dict[str, Any] | None:
    """Find a claim by ID in the claim map."""
    for claim in claim_map.get("claims", []):
        if claim.get("id") == claim_id:
            return claim
    return None


def find_evidence(evidence_index: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    """Find evidence entries by IDs."""
    ids_set = set(evidence_ids)
    return [
        entry for entry in evidence_index.get("entries", [])
        if entry.get("evidence_id") in ids_set
    ]


# ---------------------------------------------------------------------------
# Criteria evaluation
# ---------------------------------------------------------------------------

def evaluate_claim_criteria(
    evidence_entries: list[dict[str, Any]],
    criteria: list[ClaimDecisionCriterion],
) -> list[CriterionResult]:
    """Evaluate decision criteria against evidence entries.

    Searches for metric values in evidence entries in this order:
    1. metadata.metrics (list of ResultMetric-like dicts)
    2. outputs.metrics
    3. result.metrics
    4. metadata (direct key lookup)
    5. outputs (direct key lookup)
    6. root level of evidence entry (direct key lookup)
    """
    results: list[CriterionResult] = []

    for criterion in criteria:
        metric_value, found_in = _find_metric_in_evidence(evidence_entries, criterion.metric_name)

        if metric_value is None and not found_in:
            results.append(
                CriterionResult(
                    metric_name=criterion.metric_name,
                    operator=criterion.operator,
                    threshold=criterion.threshold,
                    status="not_found",
                    reason=f"Metric '{criterion.metric_name}' not found in evidence.",
                )
            )
            continue

        try:
            comparison_result = _compare_value(metric_value, criterion.operator, criterion.threshold)
            status: Literal["pass", "fail", "not_found", "unsupported"] = (
                "pass" if comparison_result else "fail"
            )
            results.append(
                CriterionResult(
                    metric_name=criterion.metric_name,
                    operator=criterion.operator,
                    threshold=criterion.threshold,
                    actual_value=metric_value,
                    status=status,
                    reason=None,
                )
            )
        except (TypeError, ValueError) as exc:
            results.append(
                CriterionResult(
                    metric_name=criterion.metric_name,
                    operator=criterion.operator,
                    threshold=criterion.threshold,
                    actual_value=metric_value,
                    status="unsupported",
                    reason=f"Type mismatch during comparison: {exc}",
                )
            )

    return results


def _find_metric_in_evidence(
    evidence_entries: list[dict[str, Any]], metric_name: str
) -> tuple[Any, bool]:
    """Search all evidence entries for a metric by name.

    Returns (value, found) where found is True if the metric was located.
    """
    for entry in evidence_entries:
        # Search paths in priority order
        for path in ("metadata.metrics", "outputs.metrics", "result.metrics"):
            value = _get_nested(entry, path)
            if isinstance(value, list):
                for metric in value:
                    if isinstance(metric, dict) and metric.get("name") == metric_name:
                        return metric.get("value"), True

        # Direct key lookups
        for prefix in ("metadata", "outputs", ""):
            container = _get_nested(entry, prefix) if prefix else entry
            if isinstance(container, dict):
                if metric_name in container:
                    return container[metric_name], True

    return None, False


def _get_nested(data: dict[str, Any], path: str) -> Any:
    """Get a nested value from a dict using dot-separated path."""
    if not path:
        return data
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _compare_value(value: Any, operator: str, threshold: float | int | str) -> bool:
    """Compare a value against a threshold using the given operator."""
    # Try numeric comparison first
    try:
        num_value = float(value)  # type: ignore[arg-type]
        num_threshold = float(threshold)  # type: ignore[arg-type]
        if operator == "<":
            return num_value < num_threshold
        if operator == "<=":
            return num_value <= num_threshold
        if operator == ">":
            return num_value > num_threshold
        if operator == ">=":
            return num_value >= num_threshold
        if operator == "==":
            return num_value == num_threshold
        if operator == "!=":
            return num_value != num_threshold
    except (TypeError, ValueError):
        pass

    # Fall back to string comparison
    str_value = str(value) if value is not None else ""
    str_threshold = str(threshold) if threshold is not None else ""
    if operator == "==":
        return str_value == str_threshold
    if operator == "!=":
        return str_value != str_threshold

    raise TypeError(f"Cannot compare {type(value).__name__} with {type(threshold).__name__} using '{operator}'")


def _determine_status_from_results(results: list[CriterionResult]) -> str:
    """Determine overall claim status from criterion results.

    Rules:
    - If any result is 'fail' → 'fail'
    - If any result is 'not_found' or 'unsupported' and none fail → 'unsupported'
    - If all results are 'pass' → 'pass'
    """
    statuses = {r.status for r in results}
    if "fail" in statuses:
        return "fail"
    if "not_found" in statuses or "unsupported" in statuses:
        return "unsupported"
    return "pass"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _write_claim_update(
    package_path: str,
    claim: dict[str, Any],
    claim_map: dict[str, Any],
    request: ClaimUpdateRequest,
    new_status: str,
    criteria_results: list[CriterionResult],
    old_status: str,
) -> str:
    """Write updated claim_map and append trace entry.

    Returns the trace_id.
    """
    path = Path(package_path)
    now = datetime.now(timezone.utc).isoformat()

    # Update the target claim in-place within claim_map
    for c in claim_map.get("claims", []):
        if c.get("id") == request.claim_id:
            c["status"] = new_status
            c["evidence_ids"] = list(request.evidence_ids)
            c["last_updated"] = now
            c["update_mode"] = request.mode
            if request.rationale:
                c["rationale"] = request.rationale
            if criteria_results:
                c["criteria_results"] = [r.model_dump(mode="json") for r in criteria_results]
            break

    # Write claim_map atomically
    claim_map_path = path / "results" / "claim_map.json"
    _atomic_write_json(claim_map_path, claim_map)

    # Build and append trace entry
    trace_entry: dict[str, Any] = {
        "trace_id": f"claim-update-{now}",
        "producer": "freecad_mcp",
        "operation": "aieng_update_claim",
        "status": "success",
        "claim_id": request.claim_id,
        "old_status": old_status,
        "new_status": new_status,
        "evidence_ids": request.evidence_ids,
        "mode": request.mode,
        "updated_at": now,
    }
    if request.rationale:
        trace_entry["rationale"] = request.rationale
    if criteria_results:
        trace_entry["criteria_results"] = [r.model_dump(mode="json") for r in criteria_results]

    # Append to tool_trace.json
    trace_path = path / "provenance" / "tool_trace.json"
    existing_traces: list[dict[str, Any]] = []
    if trace_path.exists():
        try:
            with trace_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "entries" in data:
                existing_traces = list(data["entries"])
            elif isinstance(data, list):
                existing_traces = data
        except (json.JSONDecodeError, OSError):
            pass

    trace_id = f"trace-{len(existing_traces):04d}"
    trace_entry["trace_id"] = trace_id
    existing_traces.append(trace_entry)
    _atomic_write_json(trace_path, {"entries": existing_traces})

    return trace_id
