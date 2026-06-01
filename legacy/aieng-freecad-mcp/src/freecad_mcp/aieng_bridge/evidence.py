"""Internal helpers to create .aieng-compatible evidence entries from StandardToolResult.

Rules:
- Importing or generating an artifact does not advance a claim.
- Mesh exists does not mean mesh acceptable.
- Solver ran does not mean design valid.
- Result file exists does not mean claim passed.
- Surrogate estimate is not solver evidence.
- Unsupported means insufficient evidence, not false.
- Claim status may only change via explicit claim update operation.
"""

from __future__ import annotations

from typing import Any

from freecad_mcp.tool_contracts import StandardToolResult


def build_evidence_entry(
    result: StandardToolResult,
    *,
    evidence_id: str | None = None,
    additional_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a .aieng-compatible evidence index entry from a StandardToolResult.

    The returned dict is intended to be appended to ``results/evidence_index.json``
    by a future persistence layer.  This function does NOT write to disk.
    """
    entry: dict[str, Any] = {
        "evidence_id": evidence_id or result.trace.tool_trace_id or "unknown",
        "evidence_type": result.evidence.evidence_type or "tool_execution",
        "producer_kind": result.evidence.producer_kind or result.trace.producer,
        "status": result.status,
        "operation": result.operation,
        "artifacts_written": result.artifacts_written,
        "claim_ids_possibly_supported": result.evidence.claim_ids_possibly_supported,
        "claims_advanced": result.claim_policy.claims_advanced,
    }
    if additional_metadata:
        entry["metadata"] = additional_metadata
    if result.warnings:
        entry["warnings"] = result.warnings
    if result.errors:
        entry["errors"] = result.errors
    return entry
