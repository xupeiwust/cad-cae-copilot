"""Regression (B-12): deleting a chat session removes its autopilot run files.

delete_chat_session_endpoint used to only cancel active runs, leaving the run
JSON on disk as orphans (store.delete_runs existed but was unused). It now
sweeps the session's run files after the session row is deleted; other sessions'
runs are untouched.
"""

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent_autopilot.store import AutopilotStore
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


def _new_session(client: TestClient, project_id: str, title: str) -> str:
    return client.post(f"/api/projects/{project_id}/chat-sessions", json={"title": title}).json()["id"]


def _new_run(client: TestClient, project_id: str, session_id: str, actions: list[dict]) -> str:
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


def test_delete_session_removes_only_its_run_files(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("run-cleanup"))
    client = TestClient(create_app(settings))
    store = AutopilotStore(settings.data_root / "agent_autopilot" / "runs")

    session_a = _new_session(client, project["id"], "A")
    session_b = _new_session(client, project["id"], "B")

    # Session A: an active (blocked, ask_user) run — exercises cancel-then-delete.
    run_a = _new_run(client, project["id"], session_a, [
        {"action": {"type": "ask_user", "question": "Which face?"}, "done": False},
    ])
    _wait_for_run_status(client, run_a, {"blocked"})
    # Session B: a completed run that must survive A's deletion.
    run_b = _new_run(client, project["id"], session_b, [
        {"action": {"type": "final", "message": "Done."}, "done": True},
    ])
    _wait_for_run_status(client, run_b, {"completed"})

    assert store._path(run_a).exists(), "run A file should exist before delete"
    assert store._path(run_b).exists(), "run B file should exist before delete"

    # Delete session A.
    deleted = client.delete(f"/api/projects/{project['id']}/chat-sessions/{session_a}")
    assert deleted.status_code == 200
    body = deleted.json()
    assert body["deleted"] is True
    assert body["deleted_autopilot_run_files"] >= 1

    # Session A gone; its run file removed; run no longer loadable.
    sessions = {s["id"] for s in client.get(f"/api/projects/{project['id']}/chat-sessions").json()}
    assert session_a not in sessions
    assert session_b in sessions
    assert not store._path(run_a).exists(), "run A file should be deleted"
    assert client.get(f"/api/agent/autopilot/runs/{run_a}").status_code == 404
    assert store.list_runs(session_id=session_a) == []

    # Session B untouched.
    assert store._path(run_b).exists(), "run B file must survive A's deletion"
    assert client.get(f"/api/agent/autopilot/runs/{run_b}").status_code == 200
