from __future__ import annotations

from pathlib import Path

from app import db
from app.agent_autopilot.engine import AutopilotEngine
from app.agent_autopilot.event_contract import apply_event_metadata, is_public_terminal_event
from app.agent_autopilot.schema import AdapterInvocationResult, AutopilotAgentAction, AutopilotRunRequest
from app.agent_autopilot.store import AutopilotStore


RUNTIME_TOOLS = [
    {"name": "aieng.agent_context", "description": "context", "input_schema": {"type": "object"}},
]


def _public_terminal_events(events: list[dict]) -> list[dict]:
    return [event for event in events if is_public_terminal_event(event)]


def test_event_metadata_covers_public_agent_event_types() -> None:
    samples = [
        ("run_status_changed", "completed", {"status": "completed"}, "terminal", "public", True),
        ("run_cancelled", "cancelled", {}, "terminal", "public", True),
        ("agent_phase_changed", "running", {"progress_event": True}, "progress", "diagnostic", False),
        ("agent_plan_step_updated", "running", {}, "progress", "public", True),
        ("tool_started", "running", {}, "tool", "public", True),
        ("tool_completed", "completed", {}, "tool", "public", True),
        ("tool_failed", "failed", {}, "tool", "public", True),
        ("approval_requested", "awaiting_approval", {}, "approval", "public", True),
        ("ask_user_requested", "blocked", {}, "user_input", "public", True),
        ("artifact_ready", "completed", {}, "artifact", "public", True),
        ("agent_message", "completed", {"kind": "final"}, "status", "public", True),
    ]
    for event_type, status, payload, category, visibility, user_visible in samples:
        event = apply_event_metadata({"type": event_type, "status": status, "payload": payload})
        assert event["category"] == category
        assert event["visibility"] == visibility
        assert event["user_visible"] is user_visible
        assert event["payload"]["category"] == category
        assert event["payload"]["visibility"] == visibility
        assert event["payload"]["user_visible"] is user_visible


def test_progress_phase_duplicate_is_diagnostic_while_status_progress_is_public() -> None:
    phase = apply_event_metadata({
        "type": "agent_phase_changed",
        "status": "running",
        "content": "Waiting for model",
        "payload": {"phase": "waiting_for_model", "progress_event": True},
    })
    status = apply_event_metadata({
        "type": "run_status_changed",
        "status": "running",
        "content": "Waiting for model",
        "payload": {"phase": "waiting_for_model", "progress_event": True},
    })

    assert phase["category"] == "progress"
    assert phase["visibility"] == "diagnostic"
    assert phase["user_visible"] is False
    assert status["category"] == "progress"
    assert status["visibility"] == "public"
    assert status["user_visible"] is True
    assert len([event for event in (phase, status) if event["category"] == "progress" and event["user_visible"]]) == 1


def test_completed_run_has_single_public_terminal_status_event_and_no_running_after_terminal(tmp_path: Path) -> None:
    events: list[dict] = []
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        on_event=events.append,
    )

    state = engine.start(
        AutopilotRunRequest(
            message="hello",
            project_id="p1",
            fake_actions=[{"action": {"type": "final", "message": "done"}, "done": True}],
        )
    )

    assert state.status == "completed"
    terminals = _public_terminal_events(events)
    assert [(event["type"], event["status"]) for event in terminals] == [("run_status_changed", "completed")]
    terminal_index = events.index(terminals[0])
    assert not any(event.get("status") == "running" for event in events[terminal_index + 1 :])
    final_message = next(event for event in events if event["type"] == "agent_message" and event.get("status") == "completed")
    assert final_message["category"] == "status"
    assert final_message["user_visible"] is True


def test_cancel_and_adapter_failure_terminal_semantics_are_distinct(tmp_path: Path) -> None:
    class FailingAdapter:
        adapter_id = "failing"
        label = "Failing"

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            return AdapterInvocationResult(status="error", diagnostic="adapter exploded")

    cancel_events: list[dict] = []
    cancel_engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "cancel-runs"),
        runtime_tools=RUNTIME_TOOLS,
        on_event=cancel_events.append,
    )
    cancel_state = cancel_engine.start(
        AutopilotRunRequest(
            message="wait",
            project_id="p1",
            fake_actions=[{"action": {"type": "pause", "reason": "waiting"}}],
        )
    )
    cancel_engine.cancel_run(cancel_state.run_id)
    assert [(event["type"], event["status"]) for event in _public_terminal_events(cancel_events)] == [("run_cancelled", "cancelled")]

    fail_events: list[dict] = []
    fail_engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "fail-runs"),
        runtime_tools=RUNTIME_TOOLS,
        adapters={"failing": FailingAdapter()},
        on_event=fail_events.append,
    )
    fail_state = fail_engine.start(AutopilotRunRequest(message="hello", project_id="p1", adapter_id="failing"))

    assert fail_state.status == "failed"
    assert not any(event["type"] == "run_cancelled" for event in fail_events)
    tool_failed = next(event for event in fail_events if event["type"] == "tool_failed")
    assert tool_failed["category"] == "tool"
    assert tool_failed["visibility"] == "public"
    assert _public_terminal_events(fail_events) == []


def test_persisted_event_metadata_is_returned_top_level_and_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "aieng.db"
    db.init_db(db_path)
    event = apply_event_metadata({
        "event_id": "run1-completed",
        "type": "run_status_changed",
        "run_id": "run1",
        "project_id": "p1",
        "session_id": "s1",
        "status": "completed",
        "content": "Autopilot run completed.",
        "payload": {"status": "completed"},
        "created_at": "2026-06-03T00:00:00+00:00",
    })

    row = db.add_agent_event(
        db_path,
        event_id=event["event_id"],
        event_type=event["type"],
        payload=event["payload"],
        run_id=event["run_id"],
        project_id=event["project_id"],
        session_id=event["session_id"],
        status=event["status"],
        content=event["content"],
        created_at=event["created_at"],
    )
    events = db.get_agent_events(db_path, "p1", session_id="s1")

    assert row["category"] == "terminal"
    assert events[0]["category"] == "terminal"
    assert events[0]["visibility"] == "public"
    assert events[0]["user_visible"] is True
    assert events[0]["payload"]["category"] == "terminal"
