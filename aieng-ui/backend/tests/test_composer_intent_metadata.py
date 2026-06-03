"""Composer slash-command intent is persisted as metadata only.

These cover the send-pipeline plumbing added for the composer slash commands:
the autopilot run create request accepts an optional `composer_intent` blob,
echoes it back, and preserves it across the background-worker state rebuild;
chat messages roundtrip `extra.composer_intent` (Chinese included). No agent
execution behavior changes — the metadata is recorded, never routed on.
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


def _wait_for_status(client: TestClient, run_id: str, statuses: set[str], timeout_s: float = 5.0) -> dict:
    deadline = time.time() + timeout_s
    last: dict | None = None
    while time.time() < deadline:
        resp = client.get(f"/api/agent/autopilot/runs/{run_id}")
        # The background worker may be mid-write; tolerate a transient read and
        # keep polling rather than failing the test on a momentary blip.
        if resp.status_code == 200:
            last = resp.json()
            if last.get("status") in statuses:
                return last
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never reached {statuses}; last={last}")


_INTENT = {
    "command": "build",
    "commandRaw": "/build",
    "text": "一个四旋翼无人机",
    "mentions": [{"kind": "face", "raw": "@face:f_top", "value": "f_top"}],
    "errors": [],
}


def test_autopilot_run_create_persists_composer_intent(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("composer-intent"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "/build 一个四旋翼无人机",
            "project_id": project["id"],
            "adapter_id": "fake",
            "composer_intent": _INTENT,
            "fake_actions": [{"action": {"type": "final", "message": "Built."}, "done": True}],
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    # Create response already echoes the intent (fast-path state).
    assert resp.json()["composer_intent"] == _INTENT

    # After the background worker rebuilds and overwrites the state, the metadata
    # must still be there — proving _new_state threads it through. Chinese text
    # and the mention survive the JSON roundtrip verbatim.
    final = _wait_for_status(client, run_id, {"completed", "failed"})
    assert final["composer_intent"] == _INTENT
    assert final["composer_intent"]["text"] == "一个四旋翼无人机"


def test_autopilot_run_without_composer_intent_is_backward_compatible(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("composer-intent-legacy"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "make a bracket",
            "project_id": project["id"],
            "adapter_id": "fake",
            "fake_actions": [{"action": {"type": "final", "message": "Done."}, "done": True}],
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("composer_intent") is None
    final = _wait_for_status(client, resp.json()["run_id"], {"completed", "failed"})
    assert final.get("composer_intent") is None


def test_autopilot_run_malformed_composer_intent_rejected(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("composer-intent-bad"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "/build drone",
            "project_id": project["id"],
            "adapter_id": "fake",
            "composer_intent": "not-a-dict",
        },
    )
    # Invalid request shape -> clear 400 (matches the endpoint's existing style).
    assert resp.status_code == 400


def test_chat_message_extra_composer_intent_roundtrip(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("composer-intent-chat"))
    client = TestClient(create_app(settings))

    created = client.post(
        f"/api/projects/{project['id']}/chat-messages",
        json={
            "role": "user",
            "content": "/build 一个四旋翼无人机",
            "mode": "runtime",
            "extra": {"client_id": "local-1", "composer_intent": _INTENT},
        },
    )
    assert created.status_code == 200
    assert created.json()["extra"]["composer_intent"] == _INTENT

    listed = client.get(f"/api/projects/{project['id']}/chat-messages").json()
    assert len(listed) == 1
    extra = listed[0]["extra"]
    assert extra["client_id"] == "local-1"
    assert extra["composer_intent"]["command"] == "build"
    assert extra["composer_intent"]["text"] == "一个四旋翼无人机"  # Chinese preserved
