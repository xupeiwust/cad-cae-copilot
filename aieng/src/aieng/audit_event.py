"""Audit event artifact semantics for .aieng packages.

Pure functions with no I/O. Owns the audit event schema, path conventions,
vocabulary, and construction/validation/serialisation logic. Does not
append events to any ZIP (that is the caller's responsibility).

Every audit event carries ``claim_advancement: "none"`` — audit events are
observational records, not engineering claims.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

__all__ = [
    "AUDIT_EVENTS_PATH",
    "AUDIT_EVENT_TYPES",
    "build_audit_event",
    "validate_audit_event",
    "parse_audit_events_jsonl",
    "serialize_audit_events_jsonl",
]

# ── constants ────────────────────────────────────────────────────────────────

# Path inside the .aieng ZIP where the append-only event log is stored.
AUDIT_EVENTS_PATH: str = "audit/events.jsonl"

# Known event types emitted by the reference runtime.
AUDIT_EVENT_TYPES: frozenset[str] = frozenset({
    "geometry_modified",
    "solver_run_completed",
    "cae_summary_refreshed",
    "claim_proposal_created",
    "optimization_artifact_written",
    "optimization_candidates_proposed",
})

# Required fields in every serialised audit event artifact.
_REQUIRED_EVENT_FIELDS: tuple[str, ...] = (
    "schema_version", "event_id", "timestamp", "tool", "event_type",
    "status", "artifacts_written", "evidence_created", "claim_advancement",
)


# ── builder ──────────────────────────────────────────────────────────────────

def build_audit_event(
    *,
    tool: str,
    event_type: str,
    status: str,
    artifacts_written: list[str],
    evidence_created: list[str],
    state_changes: dict[str, Any],
    geometry_revision: int | None,
    revalidation_status: str | None,
    event_id: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build a single audit event dict ready for appending to the event log.

    ``claim_advancement`` is always ``"none"`` — audit events record what
    happened; they do not accept or advance engineering claims.

    Args:
        tool: The tool name that produced the event (e.g. ``"cae.run_solver"``).
        event_type: Semantic type of the event (e.g. ``"solver_run_completed"``).
        status: Completion status of the tool run (e.g. ``"completed"``).
        artifacts_written: Package-internal paths written by the tool.
        evidence_created: Package-internal paths that constitute new evidence.
        state_changes: Key/value pairs describing state transitions.
        geometry_revision: Geometry revision counter at the time of the event,
            or ``None`` when geometry revision is not applicable.
        revalidation_status: Revalidation state string at event time, or
            ``None`` when not applicable.
        event_id: Optional fixed event ID; auto-generated (32-hex UUID) when
            absent.
        timestamp: Optional ISO 8601 timestamp; defaults to current UTC time.

    Returns:
        A dict with all required event fields.
    """
    return {
        "schema_version": "0.1",
        "event_id": event_id or uuid.uuid4().hex,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "event_type": event_type,
        "status": status,
        "artifacts_written": artifacts_written,
        "evidence_created": evidence_created,
        "state_changes": state_changes,
        "geometry_revision": geometry_revision,
        "revalidation_status": revalidation_status,
        "claim_advancement": "none",
    }


# ── validation ───────────────────────────────────────────────────────────────

def validate_audit_event(obj: dict[str, Any]) -> list[str]:
    """Validate a deserialised audit event dict against the core schema.

    Args:
        obj: A dict loaded from a line of ``audit/events.jsonl``.

    Returns:
        List of issue strings describing schema violations; empty = valid.
    """
    issues: list[str] = []
    for field in _REQUIRED_EVENT_FIELDS:
        if field not in obj:
            issues.append(f"missing required field: {field!r}")
    if obj.get("claim_advancement") != "none":
        issues.append("claim_advancement must be 'none'")
    if not isinstance(obj.get("artifacts_written"), list):
        issues.append("artifacts_written must be a list")
    if not isinstance(obj.get("evidence_created"), list):
        issues.append("evidence_created must be a list")
    return issues


# ── JSONL helpers ────────────────────────────────────────────────────────────

def parse_audit_events_jsonl(text: str) -> list[dict[str, Any]]:
    """Parse a JSONL string into a list of audit event dicts.

    Silently skips blank lines and malformed JSON lines, matching the
    read-time behaviour in the reference runtime.

    Args:
        text: Contents of ``audit/events.jsonl`` as a string.

    Returns:
        Ordered list of successfully parsed event dicts.
    """
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            pass
    return events


def serialize_audit_events_jsonl(events: Iterable[dict[str, Any]]) -> str:
    """Serialise audit event dicts to compact JSONL.

    Each event is written as a single compact JSON line (no extra spaces)
    followed by a newline, matching the append behaviour in the reference
    runtime.

    Args:
        events: Iterable of audit event dicts to serialise.

    Returns:
        JSONL string with one event per line.
    """
    return "".join(
        json.dumps(e, separators=(",", ":")) + "\n" for e in events
    )
