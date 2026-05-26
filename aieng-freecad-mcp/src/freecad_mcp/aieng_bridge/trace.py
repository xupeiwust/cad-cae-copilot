"""Internal helpers to create .aieng-compatible provenance trace entries from StandardToolResult.

Rules:
- Every mutating operation must leave a trace record.
- The trace record must include inputs, outputs, exit status, and artifacts.
- Trace records must not auto-advance claims.
"""

from __future__ import annotations

from typing import Any

from freecad_mcp.tool_contracts import StandardToolResult


def build_trace_entry(
    result: StandardToolResult,
    *,
    trace_id: str | None = None,
    additional_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a .aieng-compatible provenance trace entry from a StandardToolResult.

    The returned dict is intended to be appended to ``provenance/tool_trace.json``
    by a future persistence layer.  This function does NOT write to disk.
    """
    entry: dict[str, Any] = {
        "trace_id": trace_id or result.trace.tool_trace_id or "unknown",
        "producer": result.trace.producer,
        "operation": result.operation,
        "status": result.status,
        "exit_status": result.trace.exit_status,
        "inputs": result.inputs,
        "outputs": result.outputs,
        "artifacts_written": result.artifacts_written,
    }
    if additional_metadata:
        entry["metadata"] = additional_metadata
    if result.warnings:
        entry["warnings"] = result.warnings
    if result.errors:
        entry["errors"] = result.errors
    return entry
