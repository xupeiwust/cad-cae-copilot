"""SQLite persistence layer for chat messages and user settings.

Uses the standard library sqlite3 module. Database file lives at
<data_root>/aieng.db. All functions accept a Path to the db file so
callers can pass ``settings.data_root / "aieng.db"``.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

CHAT_ROLES = {"user", "assistant", "system"}
_CONNECT_TIMEOUT_S = 30.0

_DB_INIT_SQL = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    project_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    mode TEXT,
    created_at TEXT NOT NULL,
    extra_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_chat_project ON chat_messages(project_id, created_at);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    active_run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_project ON chat_sessions(project_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS user_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    run_id TEXT,
    project_id TEXT,
    session_id TEXT,
    type TEXT NOT NULL,
    status TEXT,
    content TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_events_project_session ON agent_events(project_id, session_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_agent_events_run ON agent_events(run_id, created_at, id);
"""


def init_db(db_path: Path) -> None:
    """Create tables and indexes if they do not exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _conn(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_DB_INIT_SQL)
        _ensure_column(conn, "chat_messages", "session_id", "TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id, created_at, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_events_project_session ON agent_events(project_id, session_id, created_at, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_events_run ON agent_events(run_id, created_at, id)")
        conn.commit()
    finally:
        conn.close()


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=_CONNECT_TIMEOUT_S)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, spec: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if column not in {row[1] for row in rows}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")


# chat_sessions CRUD


def create_chat_session(
    db_path: Path,
    *,
    project_id: str,
    title: str | None = None,
) -> dict[str, Any]:
    """Create a project-scoped chat session."""
    from .config import now_iso

    project_id = project_id.strip()
    if not project_id:
        raise ValueError("project_id is required")
    clean_title = (title or "New session").strip() or "New session"
    now = now_iso()
    session_id = uuid.uuid4().hex[:12]
    conn = _conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO chat_sessions (id, project_id, title, status, active_run_id, created_at, updated_at)
            VALUES (?, ?, ?, 'idle', NULL, ?, ?)
            """,
            (session_id, project_id, clean_title, now, now),
        )
        conn.commit()
        return get_chat_session(db_path, session_id)  # type: ignore[return-value]
    finally:
        conn.close()


def ensure_default_chat_session(db_path: Path, project_id: str) -> dict[str, Any]:
    """Return the newest session for a project, creating one if needed."""
    conn = _conn(db_path)
    try:
        row = conn.execute(
            """
            SELECT id, project_id, title, status, active_run_id, created_at, updated_at
            FROM chat_sessions
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        if row is not None:
            return _session_row_to_dict(row)
    finally:
        conn.close()
    return create_chat_session(db_path, project_id=project_id, title="Default session")


def get_chat_session(db_path: Path, session_id: str) -> dict[str, Any] | None:
    conn = _conn(db_path)
    try:
        row = conn.execute(
            """
            SELECT id, project_id, title, status, active_run_id, created_at, updated_at
            FROM chat_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        return _session_row_to_dict(row) if row else None
    finally:
        conn.close()


def get_chat_sessions(db_path: Path, project_id: str) -> list[dict[str, Any]]:
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, project_id, title, status, active_run_id, created_at, updated_at
            FROM chat_sessions
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC
            """,
            (project_id,),
        ).fetchall()
        return [_session_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def update_chat_session(
    db_path: Path,
    session_id: str,
    *,
    title: str | None = None,
    status: str | None = None,
    active_run_id: str | None = None,
) -> dict[str, Any] | None:
    from .config import now_iso

    current = get_chat_session(db_path, session_id)
    if current is None:
        return None
    next_title = (title.strip() if isinstance(title, str) else current["title"]) or current["title"]
    next_status = (status.strip() if isinstance(status, str) else current["status"]) or current["status"]
    next_run_id = active_run_id if active_run_id is not None else current["active_run_id"]
    updated_at = now_iso()
    conn = _conn(db_path)
    try:
        conn.execute(
            """
            UPDATE chat_sessions
            SET title = ?, status = ?, active_run_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_title, next_status, next_run_id, updated_at, session_id),
        )
        conn.commit()
    finally:
        conn.close()
    return get_chat_session(db_path, session_id)


def delete_chat_session(db_path: Path, project_id: str, session_id: str) -> bool:
    conn = _conn(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM chat_sessions WHERE id = ? AND project_id = ?",
            (session_id, project_id),
        )
        conn.execute("DELETE FROM chat_messages WHERE session_id = ? AND project_id = ?", (session_id, project_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_project_chat(db_path: Path, project_id: str) -> int:
    """Delete all chat sessions and messages for a project; returns rows removed.

    Chat data lives in this sqlite db keyed by project_id, separate from the
    project directory — so deleting a project must purge these rows too or they
    are orphaned.
    """
    conn = _conn(db_path)
    try:
        c1 = conn.execute("DELETE FROM chat_messages WHERE project_id = ?", (project_id,))
        c2 = conn.execute("DELETE FROM chat_sessions WHERE project_id = ?", (project_id,))
        c3 = conn.execute("DELETE FROM agent_events WHERE project_id = ?", (project_id,))
        conn.commit()
        return (c1.rowcount or 0) + (c2.rowcount or 0) + (c3.rowcount or 0)
    finally:
        conn.close()


def _session_row_to_dict(row: sqlite3.Row | tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "project_id": row[1],
        "title": row[2],
        "status": row[3],
        "active_run_id": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }


# chat_messages CRUD


def add_chat_message(
    db_path: Path,
    *,
    project_id: str,
    role: str,
    content: str,
    session_id: str | None = None,
    mode: str | None = None,
    created_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert a chat message and return the created row."""
    from .config import now_iso

    project_id = project_id.strip()
    role = role.strip().lower()
    content = content.strip()
    if not project_id:
        raise ValueError("project_id is required")
    if role not in CHAT_ROLES:
        raise ValueError(f"Unsupported chat role: {role}")
    if not content:
        raise ValueError("content is required")

    if session_id:
        session = get_chat_session(db_path, session_id)
        if session is None or session["project_id"] != project_id:
            raise ValueError("chat session not found for project")

    created_at = created_at or now_iso()
    extra_json = json.dumps(extra, ensure_ascii=False) if extra is not None else None
    conn = _conn(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO chat_messages (session_id, project_id, role, content, mode, created_at, extra_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, project_id, role, content, mode, created_at, extra_json),
        )
        if session_id:
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (created_at, session_id),
            )
        conn.commit()
        row_id = cursor.lastrowid
        row = conn.execute(
            """
            SELECT id, session_id, project_id, role, content, mode, created_at, extra_json
            FROM chat_messages
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()
        return _message_row_to_dict(row)
    finally:
        conn.close()


def get_chat_messages(db_path: Path, project_id: str, session_id: str | None = None) -> list[dict[str, Any]]:
    """Return all chat messages for a project, oldest first."""
    conn = _conn(db_path)
    try:
        if session_id:
            rows = conn.execute(
                """
                SELECT id, session_id, project_id, role, content, mode, created_at, extra_json
                FROM chat_messages
                WHERE project_id = ? AND session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (project_id, session_id),
            ).fetchall()
            return [_message_row_to_dict(r) for r in rows]
        rows = conn.execute(
            """
            SELECT id, session_id, project_id, role, content, mode, created_at, extra_json
            FROM chat_messages
            WHERE project_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (project_id,),
        ).fetchall()
        return [_message_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def clear_chat_messages(db_path: Path, project_id: str, session_id: str | None = None) -> int:
    """Delete all chat messages for a project. Returns deleted row count."""
    conn = _conn(db_path)
    try:
        if session_id:
            cursor = conn.execute(
                "DELETE FROM chat_messages WHERE project_id = ? AND session_id = ?",
                (project_id, session_id),
            )
        else:
            cursor = conn.execute("DELETE FROM chat_messages WHERE project_id = ?", (project_id,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def delete_chat_message(db_path: Path, project_id: str, message_id: int) -> bool:
    """Delete a single chat message by id, scoped to project."""
    conn = _conn(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM chat_messages WHERE id = ? AND project_id = ?",
            (message_id, project_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def _message_row_to_dict(row: sqlite3.Row | tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "session_id": row[1],
        "project_id": row[2],
        "role": row[3],
        "content": row[4],
        "mode": row[5],
        "created_at": row[6],
        "extra": json.loads(row[7]) if row[7] else None,
    }


# agent_events CRUD


def add_agent_event(
    db_path: Path,
    *,
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
    run_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    status: str | None = None,
    content: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Insert an append-only agent transcript event idempotently."""
    from .config import now_iso

    event_id = event_id.strip()
    event_type = event_type.strip()
    if not event_id:
        raise ValueError("event_id is required")
    if not event_type:
        raise ValueError("event_type is required")
    created_at = created_at or now_iso()
    payload_json = json.dumps(payload, ensure_ascii=False)
    conn = _conn(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO agent_events
                (event_id, run_id, project_id, session_id, type, status, content, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, run_id, project_id, session_id, event_type, status, content, payload_json, created_at),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT id, event_id, run_id, project_id, session_id, type, status, content, payload_json, created_at
            FROM agent_events
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()
        return _agent_event_row_to_dict(row)
    finally:
        conn.close()


def get_agent_events(db_path: Path, project_id: str, session_id: str | None = None) -> list[dict[str, Any]]:
    conn = _conn(db_path)
    try:
        if session_id:
            rows = conn.execute(
                """
                SELECT id, event_id, run_id, project_id, session_id, type, status, content, payload_json, created_at
                FROM agent_events
                WHERE project_id = ? AND session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (project_id, session_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, event_id, run_id, project_id, session_id, type, status, content, payload_json, created_at
                FROM agent_events
                WHERE project_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (project_id,),
            ).fetchall()
        return [_agent_event_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def _agent_event_row_to_dict(row: sqlite3.Row | tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "event_id": row[1],
        "run_id": row[2],
        "project_id": row[3],
        "session_id": row[4],
        "type": row[5],
        "status": row[6],
        "content": row[7],
        "payload": json.loads(row[8]) if row[8] else {},
        "created_at": row[9],
    }


# user_settings CRUD


def set_setting(db_path: Path, key: str, value: Any) -> dict[str, Any]:
    """Upsert a setting value (any JSON-serialisable value)."""
    from .config import now_iso

    key = _normalize_setting_key(key)
    raw = json.dumps(value, ensure_ascii=False)
    updated_at = now_iso()
    conn = _conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO user_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, raw, updated_at),
        )
        conn.commit()
        return {"key": key, "value": value, "updated_at": updated_at}
    finally:
        conn.close()


def get_setting(db_path: Path, key: str) -> Any | None:
    """Return the parsed value for a setting key, or None if absent."""
    record = get_setting_record(db_path, key)
    return None if record is None else record["value"]


def get_setting_record(db_path: Path, key: str) -> dict[str, Any] | None:
    """Return a setting record, preserving JSON null as an existing value."""
    key = _normalize_setting_key(key)
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT key, value, updated_at FROM user_settings WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return {"key": row[0], "value": json.loads(row[1]), "updated_at": row[2]}
    finally:
        conn.close()


def get_all_settings(db_path: Path) -> dict[str, Any]:
    """Return all settings as a dict."""
    conn = _conn(db_path)
    try:
        rows = conn.execute("SELECT key, value FROM user_settings").fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}
    finally:
        conn.close()


def delete_setting(db_path: Path, key: str) -> bool:
    """Delete a setting by key. Returns True if a row was deleted."""
    key = _normalize_setting_key(key)
    conn = _conn(db_path)
    try:
        cursor = conn.execute("DELETE FROM user_settings WHERE key = ?", (key,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def _normalize_setting_key(key: str) -> str:
    key = key.strip()
    if not key:
        raise ValueError("setting key is required")
    return key
