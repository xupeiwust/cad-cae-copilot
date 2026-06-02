from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from app import agent_activity
from app.main import Settings, create_app, default_project, save_project


def _make_settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=workspace / "aieng",
        sample_step=workspace / "sample.step",
    )


def test_settings_persist_json_null_without_404(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))

    put_response = client.put("/api/settings/example", json={"value": None})
    assert put_response.status_code == 200
    assert put_response.json()["value"] is None

    get_response = client.get("/api/settings/example")
    assert get_response.status_code == 200
    assert get_response.json()["value"] is None

    list_response = client.get("/api/settings")
    assert list_response.status_code == 200
    assert "example" in list_response.json()


def test_chat_message_persistence_validates_and_orders_rows(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    project = save_project(settings, default_project("persisted chat"))
    client = TestClient(create_app(settings))
    project_id = project["id"]

    empty_response = client.post(
        f"/api/projects/{project_id}/chat-messages",
        json={"role": "user", "content": "   "},
    )
    assert empty_response.status_code == 400

    bad_role_response = client.post(
        f"/api/projects/{project_id}/chat-messages",
        json={"role": "tool", "content": "hello"},
    )
    assert bad_role_response.status_code == 400

    first = client.post(
        f"/api/projects/{project_id}/chat-messages",
        json={"role": "USER", "content": "hello", "created_at": "2026-01-01T00:00:00+00:00"},
    )
    second = client.post(
        f"/api/projects/{project_id}/chat-messages",
        json={
            "role": "assistant",
            "content": "hi",
            "created_at": "2026-01-01T00:00:01+00:00",
            "extra": {"kind": "smoke"},
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200

    rows_response = client.get(f"/api/projects/{project_id}/chat-messages")
    assert rows_response.status_code == 200
    rows = rows_response.json()
    assert [row["role"] for row in rows] == ["user", "assistant"]
    assert [row["content"] for row in rows] == ["hello", "hi"]
    assert rows[1]["extra"] == {"kind": "smoke"}


def test_project_chat_sessions_scope_messages_and_track_active_run(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    project = save_project(settings, default_project("session chat"))
    client = TestClient(create_app(settings))
    project_id = project["id"]

    first = client.post(f"/api/projects/{project_id}/chat-sessions", json={"title": "First"})
    second = client.post(f"/api/projects/{project_id}/chat-sessions", json={"title": "Second"})
    assert first.status_code == 200
    assert second.status_code == 200
    first_id = first.json()["id"]
    second_id = second.json()["id"]
    assert first.json()["approval_mode"] == "balanced"
    assert first.json()["context_summary"] is None
    assert first.json()["context_summary_json"] is None
    assert first.json()["context_summary_updated_at"] is None

    patch_response = client.patch(
        f"/api/projects/{project_id}/chat-sessions/{first_id}",
        json={"active_run_id": "run-123", "status": "running", "approval_mode": "manual"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["active_run_id"] == "run-123"
    assert patch_response.json()["status"] == "running"
    assert patch_response.json()["approval_mode"] == "manual"

    bad_approval_mode = client.patch(
        f"/api/projects/{project_id}/chat-sessions/{first_id}",
        json={"approval_mode": "reckless"},
    )
    assert bad_approval_mode.status_code == 400

    client.post(
        f"/api/projects/{project_id}/chat-messages",
        json={"session_id": first_id, "role": "user", "content": "first session"},
    )
    client.post(
        f"/api/projects/{project_id}/chat-messages",
        json={"session_id": second_id, "role": "user", "content": "second session"},
    )

    first_rows = client.get(f"/api/projects/{project_id}/chat-messages?session_id={first_id}").json()
    second_rows = client.get(f"/api/projects/{project_id}/chat-messages?session_id={second_id}").json()
    assert [row["content"] for row in first_rows] == ["first session"]
    assert [row["session_id"] for row in first_rows] == [first_id]
    assert [row["content"] for row in second_rows] == ["second session"]

    sessions = client.get(f"/api/projects/{project_id}/chat-sessions").json()
    assert {session["id"] for session in sessions} == {first_id, second_id}


def test_chat_session_init_migrates_legacy_agent_session_fields(tmp_path: Path) -> None:
    from app import db

    db_path = tmp_path / "data" / "aieng.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE chat_sessions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'idle',
                active_run_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO chat_sessions (
                id, project_id, title, status, active_run_id, created_at, updated_at
            ) VALUES (
                'legacy-session', 'project-1', 'Legacy', 'idle', NULL,
                '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    db.init_db(db_path)
    session = db.get_chat_session(db_path, "legacy-session")

    assert session is not None
    assert session["approval_mode"] == "balanced"
    assert session["context_summary_json"] is None
    assert session["context_summary"] is None
    assert session["context_summary_updated_at"] is None


def test_chat_session_context_summary_storage_round_trip_and_clear(tmp_path: Path) -> None:
    from app import db

    settings = _make_settings(tmp_path)
    project = save_project(settings, default_project("summary storage"))
    client = TestClient(create_app(settings))
    project_id = project["id"]
    session = client.post(f"/api/projects/{project_id}/chat-sessions", json={"title": "Summary"}).json()
    summary = {
        "schema_version": 1,
        "session_id": session["id"],
        "project_id": project_id,
        "goal": "Keep context compact",
        "current_state": "Storage is being tested.",
        "important_decisions": ["Store summary in SQLite, not package artifacts."],
        "updated_at": "2026-06-02T00:00:00+00:00",
    }

    updated = db.update_chat_session_context_summary(
        settings.data_root / "aieng.db",
        session["id"],
        context_summary=summary,
    )

    assert updated is not None
    assert updated["context_summary"] == summary
    assert updated["context_summary_updated_at"] == summary["updated_at"]
    assert isinstance(updated["context_summary_json"], str)

    cleared = db.update_chat_session_context_summary(
        settings.data_root / "aieng.db",
        session["id"],
        context_summary=None,
    )
    assert cleared is not None
    assert cleared["context_summary"] is None
    assert cleared["context_summary_json"] is None
    assert cleared["context_summary_updated_at"] is None


def test_chat_session_context_summary_rejects_non_json_values(tmp_path: Path) -> None:
    from app import db

    settings = _make_settings(tmp_path)
    project = save_project(settings, default_project("summary invalid"))
    client = TestClient(create_app(settings))
    session = client.post(f"/api/projects/{project['id']}/chat-sessions", json={"title": "Summary"}).json()

    try:
        db.update_chat_session_context_summary(
            settings.data_root / "aieng.db",
            session["id"],
            context_summary={"bad": {1, 2, 3}},
        )
    except ValueError as exc:
        assert "JSON serializable" in str(exc)
    else:
        raise AssertionError("expected ValueError for non-JSON context summary")


def test_chat_session_and_message_changes_publish_sse_events(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    project = save_project(settings, default_project("session events"))
    client = TestClient(create_app(settings))
    project_id = project["id"]
    q = agent_activity.subscribe()
    try:
        created = client.post(f"/api/projects/{project_id}/chat-sessions", json={"title": "Events"})
        assert created.status_code == 200
        session = created.json()
        event = q.get(timeout=1)
        assert event["type"] == "chat_session_changed"
        assert event["action"] == "created"
        assert event["session"]["id"] == session["id"]

        message = client.post(
            f"/api/projects/{project_id}/chat-messages",
            json={"session_id": session["id"], "role": "user", "content": "hello stream"},
        )
        assert message.status_code == 200
        events = [q.get(timeout=1), q.get(timeout=1)]
        assert any(item["type"] == "chat_message" and item["chat_message"]["content"] == "hello stream" for item in events)
        assert any(item["type"] == "chat_session_changed" and item["session"]["id"] == session["id"] for item in events)
    finally:
        agent_activity.unsubscribe(q)


def test_agent_event_persistence_is_ordered_and_idempotent(tmp_path: Path) -> None:
    from app import db

    settings = _make_settings(tmp_path)
    project = save_project(settings, default_project("agent events"))
    client = TestClient(create_app(settings))
    project_id = project["id"]
    session = client.post(f"/api/projects/{project_id}/chat-sessions", json={"title": "Events"}).json()

    first = db.add_agent_event(
        settings.data_root / "aieng.db",
        event_id="evt-1",
        event_type="tool_started",
        project_id=project_id,
        session_id=session["id"],
        run_id="run-1",
        status="running",
        content="Starting",
        payload={"tool_name": "aieng.agent_context"},
        created_at="2026-01-01T00:00:00+00:00",
    )
    duplicate = db.add_agent_event(
        settings.data_root / "aieng.db",
        event_id="evt-1",
        event_type="tool_started",
        project_id=project_id,
        session_id=session["id"],
        run_id="run-1",
        payload={"tool_name": "changed"},
        created_at="2026-01-01T00:00:01+00:00",
    )
    db.add_agent_event(
        settings.data_root / "aieng.db",
        event_id="evt-2",
        event_type="tool_completed",
        project_id=project_id,
        session_id=session["id"],
        run_id="run-1",
        status="done",
        content="Done",
        payload={"tool_name": "aieng.agent_context"},
        created_at="2026-01-01T00:00:02+00:00",
    )

    assert duplicate["payload"] == first["payload"]
    response = client.get(f"/api/projects/{project_id}/agent-events?session_id={session['id']}")
    assert response.status_code == 200
    rows = response.json()
    assert [row["event_id"] for row in rows] == ["evt-1", "evt-2"]
    assert rows[0]["payload"]["tool_name"] == "aieng.agent_context"
