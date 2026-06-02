from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from .schema import AutopilotRunState


DEFAULT_STALE_RUN_THRESHOLD_SECONDS = 300
RecoveryState = Literal["active", "needs_resume", "waiting", "terminal"]
WAITING_RUN_STATUSES = frozenset({"awaiting_approval", "blocked", "chatting"})
TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})


def _parse_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def classify_run_recovery(
    state: AutopilotRunState,
    *,
    live_run_ids: set[str] | frozenset[str] | None = None,
    now: datetime | None = None,
    stale_threshold_seconds: int = DEFAULT_STALE_RUN_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    """Return backward-compatible stale/recovery metadata for an autopilot run.

    The backend intentionally does not rewrite old persisted ``running`` runs to
    failed: clients need to distinguish "currently active" from "needs user
    recovery/cancel" without losing the original run evidence.
    """
    live_run_ids = live_run_ids or set()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    if state.status in TERMINAL_RUN_STATUSES:
        return {"stale": False, "recovery_state": "terminal"}
    if state.status in WAITING_RUN_STATUSES:
        return {"stale": False, "recovery_state": "waiting"}
    if state.status != "running":
        return {"stale": False, "recovery_state": "active"}
    if state.run_id in live_run_ids:
        return {"stale": False, "recovery_state": "active"}

    updated_at = _parse_iso(state.updated_at)
    if updated_at is None:
        return {
            "stale": True,
            "recovery_state": "needs_resume",
            "stale_reason": "running run has an invalid updated_at timestamp and no live worker is registered",
        }
    age_seconds = max(0.0, (now - updated_at).total_seconds())
    if age_seconds >= stale_threshold_seconds:
        return {
            "stale": True,
            "recovery_state": "needs_resume",
            "stale_reason": (
                f"running run has no live worker and has not updated for "
                f"{int(age_seconds)}s (threshold {stale_threshold_seconds}s)"
            ),
        }
    return {"stale": False, "recovery_state": "active"}


def enrich_run_response(
    state: AutopilotRunState,
    *,
    live_run_ids: set[str] | frozenset[str] | None = None,
    stale_threshold_seconds: int = DEFAULT_STALE_RUN_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    data = state.model_dump()
    data.update(
        classify_run_recovery(
            state,
            live_run_ids=live_run_ids,
            stale_threshold_seconds=stale_threshold_seconds,
        )
    )
    return data

