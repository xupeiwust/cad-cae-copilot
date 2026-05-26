"""Revalidation status semantics for .aieng packages.

Pure functions with no I/O. Owns the revalidation status schema, path
conventions, and state-transition logic for geometry revision tracking.
Does not read from or write to any ZIP or filesystem.

Every revalidation status record carries ``claim_advancement: "none"`` —
these records are observational, not engineering claim decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

__all__ = [
    "REVALIDATION_STATUS_PATH",
    "default_revalidation_status",
    "record_geometry_edit_status",
    "record_solver_validation_status",
    "build_revalidation_response",
    "validate_revalidation_status",
]

# ── constants ────────────────────────────────────────────────────────────────

REVALIDATION_STATUS_PATH: str = "state/revalidation_status.json"

_AFFECTED_DOMAINS: list[str] = ["result_summary", "field_summaries", "solver_outputs"]

_REQUIRED_STATUS_FIELDS: tuple[str, ...] = (
    "schema_version",
    "requires_revalidation",
    "current_geometry_revision",
    "claim_advancement",
)


# ── internal builder ─────────────────────────────────────────────────────────

def _make_status(
    *,
    requires_revalidation: bool,
    reason: str | None,
    triggering_tool: str | None,
    affected_artifacts: list[str],
    current_geometry_revision: int,
    last_validated_geometry_revision: int | None,
    stale_since_geometry_revision: int | None,
    validated_by_run_id: str | None,
    recorded_at: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": "0.2",
        "geometry_modified": requires_revalidation,
        "requires_revalidation": requires_revalidation,
        "reason": reason,
        "triggering_tool": triggering_tool,
        "affected_artifacts": affected_artifacts,
        "affected_domains": list(_AFFECTED_DOMAINS),
        "claim_advancement": "none",
        "recorded_at": recorded_at or datetime.now(timezone.utc).isoformat(),
        "current_geometry_revision": current_geometry_revision,
        "last_validated_geometry_revision": last_validated_geometry_revision,
        "stale_since_geometry_revision": stale_since_geometry_revision,
        "validated_by_run_id": validated_by_run_id,
    }


# ── public API ───────────────────────────────────────────────────────────────

def default_revalidation_status() -> dict[str, Any]:
    """Return the logical default status when no record exists in the package.

    Returns:
        A status dict with ``requires_revalidation=False`` and revision
        counters initialised to their zero-state values.
    """
    return _make_status(
        requires_revalidation=False,
        reason=None,
        triggering_tool=None,
        affected_artifacts=[],
        current_geometry_revision=0,
        last_validated_geometry_revision=None,
        stale_since_geometry_revision=None,
        validated_by_run_id=None,
        recorded_at=None,
    )


def record_geometry_edit_status(
    current: dict[str, Any] | None,
    *,
    triggering_tool: str = "cad.edit_parameter",
    affected_artifacts: list[str] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Return a new revalidation status dict reflecting a geometry edit.

    Increments ``current_geometry_revision`` and marks the package stale.
    Preserves ``last_validated_geometry_revision`` from the previous status.

    Args:
        current: Existing revalidation status dict, or ``None`` if absent.
        triggering_tool: Tool identifier that caused the geometry change.
        affected_artifacts: Package-internal paths affected by the edit.
        timestamp: ISO 8601 timestamp; defaults to current UTC time.

    Returns:
        New revalidation status dict with ``requires_revalidation=True``.
    """
    prev_rev: int = (current or {}).get("current_geometry_revision") or 0
    prev_validated: int | None = (current or {}).get("last_validated_geometry_revision")
    new_rev = prev_rev + 1
    return _make_status(
        requires_revalidation=True,
        reason="geometry_changed",
        triggering_tool=triggering_tool,
        affected_artifacts=affected_artifacts or [],
        current_geometry_revision=new_rev,
        last_validated_geometry_revision=prev_validated,
        stale_since_geometry_revision=new_rev,
        validated_by_run_id=None,
        recorded_at=timestamp,
    )


def record_solver_validation_status(
    current: dict[str, Any] | None,
    *,
    run_id: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Return a new revalidation status dict reflecting a successful solver run.

    Clears stale state and records the current geometry revision as validated.

    Args:
        current: Existing revalidation status dict, or ``None`` if absent.
        run_id: Identifier of the solver run that performed validation.
        timestamp: ISO 8601 timestamp; defaults to current UTC time.

    Returns:
        New revalidation status dict with ``requires_revalidation=False``.
    """
    current_rev: int = (current or {}).get("current_geometry_revision") or 0
    return _make_status(
        requires_revalidation=False,
        reason="solver_rerun_completed",
        triggering_tool="cae.run_solver",
        affected_artifacts=[],
        current_geometry_revision=current_rev,
        last_validated_geometry_revision=current_rev,
        stale_since_geometry_revision=None,
        validated_by_run_id=run_id,
        recorded_at=timestamp,
    )


def build_revalidation_response(status: dict[str, Any] | None) -> dict[str, Any]:
    """Build the revalidation_status dict for injection into API responses.

    Args:
        status: Revalidation status dict read from the package, or ``None``
            when no record exists yet.

    Returns:
        A dict with all fields expected by the API response schema.
        ``claim_advancement`` is always ``"none"``.
    """
    rs = status
    return {
        "requires_revalidation": rs.get("requires_revalidation", False) if rs else False,
        "reason": rs.get("reason") if rs else None,
        "triggering_tool": rs.get("triggering_tool") if rs else None,
        "affected_domains": rs.get("affected_domains") if rs else None,
        "recorded_at": rs.get("recorded_at") if rs else None,
        "current_geometry_revision": rs.get("current_geometry_revision") if rs else 0,
        "last_validated_geometry_revision": (
            rs.get("last_validated_geometry_revision") if rs else None
        ),
        "stale_since_geometry_revision": (
            rs.get("stale_since_geometry_revision") if rs else None
        ),
        "validated_by_run_id": rs.get("validated_by_run_id") if rs else None,
        "claim_advancement": "none",
    }


def validate_revalidation_status(obj: dict[str, Any]) -> list[str]:
    """Validate a deserialised revalidation status dict against the core schema.

    Args:
        obj: A dict loaded from ``state/revalidation_status.json``.

    Returns:
        List of issue strings describing schema violations; empty = valid.
    """
    issues: list[str] = []
    for field in _REQUIRED_STATUS_FIELDS:
        if field not in obj:
            issues.append(f"missing required field: {field!r}")
    if obj.get("claim_advancement") != "none":
        issues.append("claim_advancement must be 'none'")
    return issues
