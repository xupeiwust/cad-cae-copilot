"""Regression: autopilot adapter step counters have a bounded lifecycle (B-14).

_SESSION_STEP_COUNTERS was a module-global keyed by "{session_id}:{adapter_id}"
that was never cleared — leaking memory, letting a new run on the same chat
session inherit the previous run's step index, and (with no lock) racing across
worker threads. Counters are now cleared when a run reaches a terminal state
(completed/failed/cancelled) and on chat-session delete; non-terminal states
(awaiting_approval/blocked/chatting) keep the counter so a resumed run continues.
"""

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent_autopilot import engine as engine_module
from app.main import Settings, create_app, default_project, save_project


def _make_runtime_settings(tmp_path: Path) -> Settings:
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=tmp_path / "workspace",
        data_root=tmp_path / "data",
        aieng_root=tmp_path / "workspace" / "aieng",
        sample_step=tmp_path / "workspace" / "sample.step",
    )


def _wait_for_run_status(client: TestClient, run_id: str, statuses: set[str], timeout_s: float = 5.0) -> dict:
    deadline = time.time() + timeout_s
    last: dict | None = None
    while time.time() < deadline:
        resp = client.get(f"/api/agent/autopilot/runs/{run_id}")
        assert resp.status_code == 200
        last = resp.json()
        if last.get("status") in statuses:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never reached {statuses}; last={last}")


def _key(session_id: str) -> str:
    return engine_module._step_counter_key(session_id, "fake")


def _has_counter(session_id: str) -> bool:
    return _key(session_id) in engine_module._SESSION_STEP_COUNTERS


# --------------------------------------------------------------------------- #
# Pure helper lifecycle
# --------------------------------------------------------------------------- #

def test_step_counter_helpers_increment_and_reset() -> None:
    engine_module._SESSION_STEP_COUNTERS.clear()
    # A single run's calls increment from 0.
    assert engine_module._session_step_index("s1", "fake") == 0
    assert engine_module._session_step_index("s1", "fake") == 1
    assert engine_module._session_step_index("s1", "fake") == 2
    # Terminal clear: the next run on the same session starts fresh, not at 3.
    engine_module._clear_step_counter("s1", "fake")
    assert engine_module._session_step_index("s1", "fake") == 0


def test_clear_session_step_counters_scopes_to_one_session() -> None:
    engine_module._SESSION_STEP_COUNTERS.clear()
    engine_module._session_step_index("s1", "fake")
    engine_module._session_step_index("s1", "claude-code")
    engine_module._session_step_index("s2", "fake")
    engine_module.clear_session_step_counters("s1")
    assert not _has_counter("s1")
    assert engine_module._step_counter_key("s1", "claude-code") not in engine_module._SESSION_STEP_COUNTERS
    assert _has_counter("s2")  # other sessions untouched


# --------------------------------------------------------------------------- #
# Lifecycle through the real engine (fake adapter; no CAD/LLM)
# --------------------------------------------------------------------------- #

def _run(client: TestClient, project_id: str, session_id: str, actions: list[dict]) -> str:
    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "inspect the active project",
            "project_id": project_id,
            "session_id": session_id,
            "adapter_id": "fake",
            "fake_actions": actions,
        },
    )
    assert resp.status_code == 200
    return resp.json()["run_id"]


def test_completed_run_clears_counter_and_next_run_does_not_inherit(tmp_path: Path) -> None:
    engine_module._SESSION_STEP_COUNTERS.clear()
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("step-counter"))
    client = TestClient(create_app(settings))
    session_id = client.post(
        f"/api/projects/{project['id']}/chat-sessions", json={"title": "S"}
    ).json()["id"]

    run1 = _run(client, project["id"], session_id, [
        {"action": {"type": "final", "message": "Done."}, "done": True},
    ])
    _wait_for_run_status(client, run1, {"completed"})
    assert not _has_counter(session_id), "completed run should clear its step counter"

    # Second run on the SAME session: because the counter was cleared, it starts a
    # fresh sequence rather than inheriting run 1's index.
    run2 = _run(client, project["id"], session_id, [
        {"action": {"type": "final", "message": "Done again."}, "done": True},
    ])
    _wait_for_run_status(client, run2, {"completed"})
    assert not _has_counter(session_id)


def test_blocked_run_keeps_counter(tmp_path: Path) -> None:
    engine_module._SESSION_STEP_COUNTERS.clear()
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("step-counter-blocked"))
    client = TestClient(create_app(settings))
    session_id = client.post(
        f"/api/projects/{project['id']}/chat-sessions", json={"title": "S"}
    ).json()["id"]

    run = _run(client, project["id"], session_id, [
        {"action": {"type": "ask_user", "question": "Which face?"}, "done": False},
    ])
    _wait_for_run_status(client, run, {"blocked"})
    # Non-terminal: the run will continue after the user replies, so its counter
    # must survive (the next adapter call should resume, not restart at 0).
    assert _has_counter(session_id), "blocked run must keep its step counter"
    assert engine_module._SESSION_STEP_COUNTERS[_key(session_id)] >= 1


def test_cancelled_run_clears_counter(tmp_path: Path) -> None:
    engine_module._SESSION_STEP_COUNTERS.clear()
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("step-counter-cancel"))
    client = TestClient(create_app(settings))
    session_id = client.post(
        f"/api/projects/{project['id']}/chat-sessions", json={"title": "S"}
    ).json()["id"]

    run = _run(client, project["id"], session_id, [
        {"action": {"type": "ask_user", "question": "Which face?"}, "done": False},
    ])
    _wait_for_run_status(client, run, {"blocked"})
    assert _has_counter(session_id)

    cancel = client.post(f"/api/agent/autopilot/runs/{run}/cancel")
    assert cancel.status_code == 200
    assert not _has_counter(session_id), "cancelled run should clear its step counter"


def test_session_delete_clears_counter(tmp_path: Path) -> None:
    engine_module._SESSION_STEP_COUNTERS.clear()
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("step-counter-delete"))
    client = TestClient(create_app(settings))
    session_id = client.post(
        f"/api/projects/{project['id']}/chat-sessions", json={"title": "S"}
    ).json()["id"]

    run = _run(client, project["id"], session_id, [
        {"action": {"type": "ask_user", "question": "Which face?"}, "done": False},
    ])
    _wait_for_run_status(client, run, {"blocked"})
    assert _has_counter(session_id)

    deleted = client.delete(f"/api/projects/{project['id']}/chat-sessions/{session_id}")
    assert deleted.status_code == 200
    assert not _has_counter(session_id), "deleting the session should clear its step counters"
