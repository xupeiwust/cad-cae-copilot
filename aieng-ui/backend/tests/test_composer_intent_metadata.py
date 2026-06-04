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


_INTENT = {
    "command": "build",
    "commandRaw": "/build",
    "text": "一个四旋翼无人机",
    "mentions": [{"kind": "face", "raw": "@face:f_top", "value": "f_top"}],
    "errors": [],
}


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
