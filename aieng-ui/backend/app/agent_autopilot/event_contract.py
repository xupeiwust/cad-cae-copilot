"""Backward-compatible public contract metadata for autopilot events."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypedDict

EventCategory = Literal["status", "progress", "terminal", "tool", "approval", "user_input", "artifact", "diagnostic"]
EventVisibility = Literal["public", "diagnostic"]

TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
WAITING_RUN_STATUSES = {"awaiting_approval", "blocked", "chatting"}


class EventContractMetadata(TypedDict):
    category: EventCategory
    visibility: EventVisibility
    user_visible: bool


def _payload_dict(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, Mapping) else {}


def _status(event: Mapping[str, Any], payload: Mapping[str, Any]) -> str | None:
    value = event.get("status") or payload.get("status")
    return str(value) if value is not None else None


def derive_event_metadata(event: Mapping[str, Any]) -> EventContractMetadata:
    """Derive category/visibility/user-visible hints without changing event type.

    This is intentionally advisory metadata: existing consumers can keep using
    ``type`` and ``status`` while newer UI code can suppress diagnostic progress
    duplicates or distinguish terminal run-status rows from tool failures.
    """
    event_type = str(event.get("type") or "")
    payload = _payload_dict(event.get("payload"))
    status = _status(event, payload)

    if event_type == "run_cancelled":
        return {"category": "terminal", "visibility": "public", "user_visible": True}

    if event_type == "run_status_changed":
        if status in TERMINAL_RUN_STATUSES:
            return {"category": "terminal", "visibility": "public", "user_visible": True}
        if payload.get("progress_event") is True:
            return {"category": "progress", "visibility": "public", "user_visible": True}
        return {"category": "status", "visibility": "public", "user_visible": True}

    if event_type == "agent_phase_changed":
        return {"category": "progress", "visibility": "diagnostic", "user_visible": False}

    if event_type in {"agent_plan_created", "agent_plan_step_updated"}:
        return {"category": "progress", "visibility": "public", "user_visible": True}

    if event_type in {"tool_started", "tool_completed", "tool_failed"}:
        return {"category": "tool", "visibility": "public", "user_visible": True}

    if event_type in {"approval_requested", "approval_resolved"}:
        return {"category": "approval", "visibility": "public", "user_visible": True}

    if event_type == "ask_user_requested":
        return {"category": "user_input", "visibility": "public", "user_visible": True}

    if event_type in {"artifact_ready", "viewer_asset_changed"}:
        return {"category": "artifact", "visibility": "public", "user_visible": True}

    if event_type == "agent_message":
        if payload.get("kind") == "thought_summary":
            return {"category": "diagnostic", "visibility": "diagnostic", "user_visible": False}
        return {"category": "status", "visibility": "public", "user_visible": True}

    return {"category": "diagnostic", "visibility": "diagnostic", "user_visible": False}


def apply_event_metadata(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return an event copy with contract metadata mirrored into payload.

    Top-level fields make live SSE events easy to inspect. Mirroring into the
    payload keeps the metadata durable for the current SQLite schema, which
    stores payload_json but has no dedicated metadata columns.
    """
    normalized = dict(event)
    payload = _payload_dict(normalized.get("payload"))
    normalized["payload"] = payload
    metadata = derive_event_metadata(normalized)
    for key, value in metadata.items():
        normalized.setdefault(key, value)
        payload.setdefault(key, value)
    return normalized


def is_public_terminal_event(event: Mapping[str, Any]) -> bool:
    normalized = apply_event_metadata(event)
    return (
        normalized.get("category") == "terminal"
        and normalized.get("visibility") == "public"
        and bool(normalized.get("user_visible"))
    )
