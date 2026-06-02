"""Regression: a blocked autopilot run keeps its chat session active.

Bug B-5 (audit): `_run_session_status` did not map "blocked" (the ask_user /
pause "waiting on the user" state), so it fell through to "idle". The session
then looked finished and the UI would not restore the active run / ask_user
card. Blocked is non-terminal and must map to an active session status.
"""

import time
from pathlib import Path

from fastapi.testclient import TestClient

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


def _session_status(client: TestClient, project_id: str, session_id: str) -> str | None:
    resp = client.get(f"/api/projects/{project_id}/chat-sessions")
    assert resp.status_code == 200
    for session in resp.json():
        if session["id"] == session_id:
            return session.get("status")
    raise AssertionError(f"session {session_id} not found")


def test_blocked_run_keeps_session_active_not_idle(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("blocked-status"))
    client = TestClient(create_app(settings))

    session_id = client.post(
        f"/api/projects/{project['id']}/chat-sessions", json={"title": "Ask"}
    ).json()["id"]

    # A run that asks the user a question parks in "blocked" (waiting on input).
    run_resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "inspect the active project",
            "project_id": project["id"],
            "session_id": session_id,
            "adapter_id": "fake",
            "fake_actions": [
                {"action": {"type": "ask_user", "question": "Which face?"}, "done": False}
            ],
        },
    )
    assert run_resp.status_code == 200
    run_id = run_resp.json()["run_id"]
    blocked = _wait_for_run_status(client, run_id, {"blocked"})
    assert blocked["status"] == "blocked"

    # The session must be active (not idle/terminal) while the run waits on input.
    deadline = time.time() + 5.0
    status = None
    while time.time() < deadline:
        status = _session_status(client, project["id"], session_id)
        if status == "running":
            break
        time.sleep(0.05)
    assert status == "running", f"blocked run left session status={status!r} (expected running, not idle)"
