"""Unified failure taxonomy for all MCP tools.

Every tool error should map to a standard FailureMode so that callers,
auditors, and orchestrators can reason about failures consistently.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FailureMode(str):
    """Standard failure mode taxonomy.

    This is intentionally a plain str subclass (not an Enum) so that
    new modes can be added without breaking schema consumers.
    """

    # Input / artifact problems
    MISSING_INPUT = "missing_input"
    MISSING_ARTIFACT = "missing_artifact"

    # Runtime problems
    MISSING_RUNTIME = "missing_runtime"
    SOLVER_UNAVAILABLE = "solver_unavailable"
    MESH_FAILED = "mesh_failed"

    # Guard / policy problems
    GUARD_REJECTED = "guard_rejected"
    SEMANTIC_ONLY_REJECTED = "semantic_only_rejected"
    PROTECTED_REGION_VIOLATED = "protected_region_violated"

    # CAD operation problems
    RECOMPUTE_FAILED = "recompute_failed"
    EXPORT_FAILED = "export_failed"

    # Data / lookup problems
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"

    # Review states
    NEEDS_REVIEW = "needs_review"

    # Catch-all
    UNKNOWN = "unknown"


class FailureDetail(BaseModel):
    """Structured failure detail with standard mode and human message."""

    model_config = ConfigDict(extra="forbid")

    mode: str = FailureMode.UNKNOWN
    message: str = ""
    context: dict[str, Any] = Field(default_factory=dict)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        return super().model_dump(**kwargs)


# ---------------------------------------------------------------------------
# Stable error codes for evidence / trace / claim update paths
# ---------------------------------------------------------------------------
# These codes are consumed by CI, orchestrators, and frontends.  They are
# intentionally plain strings (not an Enum) so new codes can be added without
# breaking schema consumers.

MISSING_PACKAGE_PATH = "MISSING_PACKAGE_PATH"
MISSING_EVIDENCE_IDS = "MISSING_EVIDENCE_IDS"
EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
CLAIM_NOT_FOUND = "CLAIM_NOT_FOUND"
MISSING_DECISION_CRITERIA = "MISSING_DECISION_CRITERIA"
MISSING_MANUAL_FIELDS = "MISSING_MANUAL_FIELDS"
UNKNOWN_MODE = "UNKNOWN_MODE"
PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
POLICY_VIOLATION = "POLICY_VIOLATION"

ERROR_CODE_DESCRIPTIONS: dict[str, str] = {
    MISSING_PACKAGE_PATH: "The provided package_path does not exist or is not a directory.",
    MISSING_EVIDENCE_IDS: "claim update requires at least one evidence_id.",
    EVIDENCE_NOT_FOUND: "One or more requested evidence_ids were not found in evidence_index.json.",
    CLAIM_NOT_FOUND: "The requested claim_id does not exist in claim_map.json.",
    MISSING_DECISION_CRITERIA: "evaluate mode requires at least one decision_criterion.",
    MISSING_MANUAL_FIELDS: "manual mode requires requested_status and rationale.",
    UNKNOWN_MODE: "The claim update mode is not recognized.",
    PERSISTENCE_FAILED: "Writing evidence_index, tool_trace, or claim_map failed (disk, permissions, or corrupt JSON).",
    POLICY_VIOLATION: "The operation violates a package-level policy (e.g., persist without package_path, guard rejection, protected region, semantic-only).",
}


# ---------------------------------------------------------------------------
# Unified primary_error_code constants (mapped from FailureMode + legacy codes)
# ---------------------------------------------------------------------------

INVALID_INPUT = "INVALID_INPUT"
MISSING_ARTIFACT = "MISSING_ARTIFACT"
MISSING_RUNTIME = "MISSING_RUNTIME"
SOLVER_UNAVAILABLE = "SOLVER_UNAVAILABLE"
MESH_FAILED = "MESH_FAILED"
EXECUTION_FAILED = "EXECUTION_FAILED"
EXPORT_FAILED = "EXPORT_FAILED"
NOT_FOUND = "NOT_FOUND"
AMBIGUOUS = "AMBIGUOUS"
NEEDS_REVIEW = "NEEDS_REVIEW"
INTERNAL_ERROR = "INTERNAL_ERROR"

_FAILURE_MODE_TO_CODE: dict[str, str] = {
    FailureMode.MISSING_INPUT: INVALID_INPUT,
    FailureMode.MISSING_ARTIFACT: MISSING_ARTIFACT,
    FailureMode.MISSING_RUNTIME: MISSING_RUNTIME,
    FailureMode.SOLVER_UNAVAILABLE: SOLVER_UNAVAILABLE,
    FailureMode.MESH_FAILED: MESH_FAILED,
    FailureMode.GUARD_REJECTED: POLICY_VIOLATION,
    FailureMode.SEMANTIC_ONLY_REJECTED: POLICY_VIOLATION,
    FailureMode.PROTECTED_REGION_VIOLATED: POLICY_VIOLATION,
    FailureMode.RECOMPUTE_FAILED: EXECUTION_FAILED,
    FailureMode.EXPORT_FAILED: EXPORT_FAILED,
    FailureMode.NOT_FOUND: NOT_FOUND,
    FailureMode.AMBIGUOUS: AMBIGUOUS,
    FailureMode.NEEDS_REVIEW: NEEDS_REVIEW,
    FailureMode.UNKNOWN: FailureMode.UNKNOWN,
}

_LEGACY_CODE_TO_CODE: dict[str, str] = {
    "validation_error": INVALID_INPUT,
    "backend_error": EXECUTION_FAILED,
    "internal_error": INTERNAL_ERROR,
    "PERSISTENCE_FAILED": PERSISTENCE_FAILED,
}


def map_failure_mode_to_error_code(failure_mode: str | FailureDetail | None) -> str | None:
    """Map a FailureMode value or FailureDetail to a primary_error_code.

    Returns ``None`` when *failure_mode* is ``None``.
    Unknown modes fall back to ``UNKNOWN``.
    """
    if failure_mode is None:
        return None
    mode = failure_mode.mode if isinstance(failure_mode, FailureDetail) else failure_mode
    return _FAILURE_MODE_TO_CODE.get(mode, FailureMode.UNKNOWN)


def derive_primary_error_code(
    *,
    primary_error_code: str | None = None,
    failure_mode: str | FailureDetail | None = None,
    legacy_error_code: str | None = None,
) -> str | None:
    """Return the most specific machine-decidable error code available.

    Resolution priority (highest first):
    1. ``primary_error_code`` — already normalized, use as-is.
    2. ``failure_mode`` — mapped via :func:`map_failure_mode_to_error_code`.
    3. ``legacy_error_code`` — mapped from CAE ``error_code`` strings or
       persistence dict ``error_code`` values.
    4. ``None`` — no error code applies.

    This function is the single source of truth for consumers that need a
    stable code regardless of which result model they are reading.
    """
    if primary_error_code is not None:
        return primary_error_code
    if failure_mode is not None:
        return map_failure_mode_to_error_code(failure_mode)
    if legacy_error_code is not None:
        return _LEGACY_CODE_TO_CODE.get(legacy_error_code, FailureMode.UNKNOWN)
    return None


# Human-readable descriptions for known modes
FAILURE_MODE_DESCRIPTIONS: dict[str, str] = {
    FailureMode.MISSING_INPUT: "A required input parameter was missing or empty.",
    FailureMode.MISSING_ARTIFACT: "An expected artifact (file, document, object) was not found.",
    FailureMode.MISSING_RUNTIME: "A required runtime (FreeCAD, FEM, mesher, solver) is not available.",
    FailureMode.SOLVER_UNAVAILABLE: "The solver backend is not installed or not reachable.",
    FailureMode.MESH_FAILED: "Mesh generation failed or produced invalid output.",
    FailureMode.GUARD_REJECTED: "The operation was rejected by .aieng guard checks.",
    FailureMode.SEMANTIC_ONLY_REJECTED: "The target feature is semantic-only and cannot be edited via CAD.",
    FailureMode.PROTECTED_REGION_VIOLATED: "The operation would modify a protected region.",
    FailureMode.RECOMPUTE_FAILED: "FreeCAD document recompute failed after modification.",
    FailureMode.EXPORT_FAILED: "Artifact export (STEP, FCStd, mesh, deck) failed.",
    FailureMode.NOT_FOUND: "The requested resource was not found.",
    FailureMode.AMBIGUOUS: "The request matched multiple resources; disambiguation required.",
    FailureMode.NEEDS_REVIEW: "Result or mapping requires human review before trust.",
    FailureMode.UNKNOWN: "An unclassified error occurred.",
}


def classify_exception(exc: Exception) -> FailureDetail:
    """Heuristic classifier mapping common exceptions to FailureMode."""
    msg = str(exc).lower()
    exc_type = type(exc).__name__

    if exc_type == "ValueError":
        if "not found" in msg or "missing" in msg:
            if "file" in msg or "path" in msg or "artifact" in msg or "object" in msg or "document" in msg:
                return FailureDetail(mode=FailureMode.MISSING_ARTIFACT, message=str(exc))
            return FailureDetail(mode=FailureMode.MISSING_INPUT, message=str(exc))
        if "guard" in msg or "rejected" in msg:
            return FailureDetail(mode=FailureMode.GUARD_REJECTED, message=str(exc))
        if "semantic" in msg:
            return FailureDetail(mode=FailureMode.SEMANTIC_ONLY_REJECTED, message=str(exc))
        if "protected" in msg:
            return FailureDetail(mode=FailureMode.PROTECTED_REGION_VIOLATED, message=str(exc))

    if exc_type in ("FileNotFoundError", "OSError"):
        return FailureDetail(mode=FailureMode.MISSING_ARTIFACT, message=str(exc))

    if "recompute" in msg:
        return FailureDetail(mode=FailureMode.RECOMPUTE_FAILED, message=str(exc))
    if "export" in msg:
        return FailureDetail(mode=FailureMode.EXPORT_FAILED, message=str(exc))
    if "mesh" in msg:
        return FailureDetail(mode=FailureMode.MESH_FAILED, message=str(exc))
    if "solver" in msg:
        return FailureDetail(mode=FailureMode.SOLVER_UNAVAILABLE, message=str(exc))
    if "runtime" in msg or "not available" in msg:
        return FailureDetail(mode=FailureMode.MISSING_RUNTIME, message=str(exc))

    return FailureDetail(mode=FailureMode.UNKNOWN, message=f"{exc_type}: {exc}")
