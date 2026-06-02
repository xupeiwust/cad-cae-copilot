from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.agent_autopilot.local_agent_preflight import local_agent_preflight
from app.agent_autopilot.run_recovery import DEFAULT_STALE_RUN_THRESHOLD_SECONDS, classify_run_recovery
from app.agent_autopilot.schema import LocalAgentCapability, AutopilotRunRequest
from app.agent_autopilot.engine import AutopilotEngine
from app.agent_autopilot.store import AutopilotStore
from app.main import Settings, create_app


class FakeProbeAdapter:
    label = "Fake"

    def __init__(self, capability: LocalAgentCapability) -> None:
        self.adapter_id = capability.adapter_id
        self.command = capability.command
        self._capability = capability

    def probe(self, timeout_seconds: int = 3) -> LocalAgentCapability:
        return self._capability

    def invoke(self, **kwargs: Any):  # pragma: no cover - not used in preflight tests
        raise AssertionError("invoke should not be called by preflight")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=tmp_path / "workspace",
        data_root=tmp_path / "data",
        aieng_root=tmp_path / "workspace" / "aieng",
        sample_step=tmp_path / "workspace" / "sample.step",
    )


def _capability(
    adapter_id: str,
    *,
    status: str = "available",
    diagnostic: str = "ok",
    command: str = "fake-agent",
) -> LocalAgentCapability:
    return LocalAgentCapability(
        adapter_id=adapter_id,
        label="Claude Code CLI" if adapter_id == "claude-code" else "Codex CLI",
        status=status,  # type: ignore[arg-type]
        command=command,
        command_path=f"/tmp/{command}" if status != "missing" else None,
        version="1.0.0",
        supports_non_interactive=status == "available",
        supports_json=status == "available",
        supports_json_schema=status == "available",
        supports_tool_disable=status == "available",
        supports_session_continuation=adapter_id == "claude-code" and status == "available",
        diagnostic=diagnostic,
        probe_duration_ms=1,
    )


def _run_state(tmp_path: Path, status: str, *, updated_delta_s: int = 0):
    store = AutopilotStore(tmp_path / "runs")
    engine = AutopilotEngine(store=store, runtime_tools=[])
    state = engine.start(
        AutopilotRunRequest(
            message="hello",
            fake_actions=[{"action": {"type": "final", "message": "done"}, "done": True}],
        ),
        run_id="run1",
    )
    state.status = status  # type: ignore[assignment]
    state.updated_at = (datetime.now(timezone.utc) - timedelta(seconds=updated_delta_s)).isoformat()
    return state


def test_recovery_classification_for_stale_fresh_waiting_and_terminal(tmp_path: Path) -> None:
    stale = classify_run_recovery(
        _run_state(tmp_path, "running", updated_delta_s=DEFAULT_STALE_RUN_THRESHOLD_SECONDS + 5),
        live_run_ids=set(),
    )
    assert stale["stale"] is True
    assert stale["recovery_state"] == "needs_resume"
    assert "stale_reason" in stale

    fresh = classify_run_recovery(_run_state(tmp_path, "running", updated_delta_s=10), live_run_ids=set())
    assert fresh == {"stale": False, "recovery_state": "active"}

    live_old = classify_run_recovery(
        _run_state(tmp_path, "running", updated_delta_s=DEFAULT_STALE_RUN_THRESHOLD_SECONDS + 5),
        live_run_ids={"run1"},
    )
    assert live_old == {"stale": False, "recovery_state": "active"}

    assert classify_run_recovery(_run_state(tmp_path, "awaiting_approval"))["recovery_state"] == "waiting"
    assert classify_run_recovery(_run_state(tmp_path, "blocked"))["recovery_state"] == "waiting"
    for status in ("completed", "failed", "cancelled"):
        assert classify_run_recovery(_run_state(tmp_path, status))["recovery_state"] == "terminal"


def test_run_endpoint_returns_recovery_metadata_and_existing_fields(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = AutopilotStore(settings.data_root / "agent_autopilot" / "runs")
    engine = AutopilotEngine(store=store, runtime_tools=[])
    state = engine.start(
        AutopilotRunRequest(
            message="hello",
            fake_actions=[{"action": {"type": "final", "message": "done"}, "done": True}],
        ),
        run_id="stalerun",
    )
    state.status = "running"
    state.updated_at = (datetime.now(timezone.utc) - timedelta(seconds=DEFAULT_STALE_RUN_THRESHOLD_SECONDS + 10)).isoformat()
    store.save(state)

    client = TestClient(create_app(settings))
    response = client.get(f"/api/agent/autopilot/runs/{state.run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == state.run_id
    assert data["message"] == "hello"
    assert data["status"] == "running"
    assert data["stale"] is True
    assert data["recovery_state"] == "needs_resume"
    assert "stale_reason" in data


def test_cancel_stale_running_run_persists_cancelled_and_emits_once(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = AutopilotStore(settings.data_root / "agent_autopilot" / "runs")
    engine = AutopilotEngine(store=store, runtime_tools=[])
    state = engine.start(
        AutopilotRunRequest(
            message="long task",
            project_id="p1",
            fake_actions=[{"action": {"type": "final", "message": "done"}, "done": True}],
        ),
        run_id="cancelme",
    )
    state.status = "running"
    state.updated_at = (datetime.now(timezone.utc) - timedelta(seconds=DEFAULT_STALE_RUN_THRESHOLD_SECONDS + 10)).isoformat()
    store.save(state)

    client = TestClient(create_app(settings))
    response = client.post(f"/api/agent/autopilot/runs/{state.run_id}/cancel")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"
    assert data["recovery_state"] == "terminal"
    assert store.load(state.run_id).status == "cancelled"

    from app import db

    events = db.get_agent_events(settings.data_root / "aieng.db", "p1")
    events = [event for event in events if event.get("run_id") == state.run_id]
    assert [event["type"] for event in events].count("run_cancelled") == 1

    second = client.post(f"/api/agent/autopilot/runs/{state.run_id}/cancel")
    assert second.status_code == 200
    events_after = db.get_agent_events(settings.data_root / "aieng.db", "p1")
    events_after = [event for event in events_after if event.get("run_id") == state.run_id]
    assert [event["type"] for event in events_after].count("run_cancelled") == 1


def test_local_agent_preflight_all_and_filter(monkeypatch) -> None:
    adapters = {
        "claude-code": FakeProbeAdapter(_capability("claude-code")),
        "codex-cli": FakeProbeAdapter(_capability("codex-cli", status="missing", diagnostic="Command not found on PATH: codex", command="codex")),
    }
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter.run_claude_preflight",
        lambda **kwargs: {
            "ok": True,
            "stdout_parsed_result": {"is_error": False},
            "stderr": "",
            "rc": 0,
            "env_summary": {
                "USERPROFILE": "C:/Users/SecretUser",
                "APPDATA": "C:/Users/SecretUser/AppData/Roaming",
                "LOCALAPPDATA": "C:/Users/SecretUser/AppData/Local",
                "HOME": "C:/Users/SecretUser",
                "PATH_first_entries": ["C:/secret/bin", "D:/tools"],
                "claude_dir_in_PATH": True,
                "ANTHROPIC_env_names": ["ANTHROPIC_API_KEY"],
                "CLAUDE_env_names": [],
            },
        },
    )
    result = local_agent_preflight(adapters=adapters)
    assert [item["adapter_id"] for item in result["adapters"]] == ["claude-code", "codex-cli"]
    assert result["adapters"][0]["status"] == "ready"
    assert result["adapters"][0]["features"]["session_resume"] is True
    assert result["adapters"][1]["status"] == "missing_binary"
    assert "Install Codex CLI" in result["adapters"][1]["actionable_fix"]

    filtered = local_agent_preflight(adapter="codex-cli", adapters=adapters)
    assert [item["adapter_id"] for item in filtered["adapters"]] == ["codex-cli"]


def test_local_agent_preflight_classifies_claude_timeout_and_auth(monkeypatch) -> None:
    adapters = {"claude-code": FakeProbeAdapter(_capability("claude-code"))}
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter.run_claude_preflight",
        lambda **kwargs: {"ok": False, "error": "timeout after 20s", "stderr": "", "rc": None},
    )
    assert local_agent_preflight(adapters=adapters)["adapters"][0]["status"] == "timeout"

    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter.run_claude_preflight",
        lambda **kwargs: {"ok": False, "stdout_parsed_result": {"is_error": True, "result": "Not logged in · Please run /login"}, "stderr": "", "rc": 1},
    )
    assert local_agent_preflight(adapters=adapters)["adapters"][0]["status"] == "auth_error"


def test_local_agent_preflight_endpoint_is_safe_and_backward_compatible(monkeypatch, tmp_path: Path) -> None:
    secret = "sk-test-should-not-leak"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    adapters = {
        "claude-code": FakeProbeAdapter(_capability("claude-code")),
        "codex-cli": FakeProbeAdapter(_capability("codex-cli", status="missing", diagnostic="Command not found on PATH: codex", command="codex")),
    }
    monkeypatch.setattr("app.agent_autopilot.local_agent_preflight.adapter_registry", lambda: adapters)
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter.run_claude_preflight",
        lambda **kwargs: {
            "ok": True,
            "stdout_parsed_result": {"is_error": False},
            "stderr": "",
            "rc": 0,
            "env_summary": {
                "USERPROFILE": "C:/Users/SecretUser",
                "APPDATA": "C:/Users/SecretUser/AppData/Roaming",
                "LOCALAPPDATA": "C:/Users/SecretUser/AppData/Local",
                "HOME": "C:/Users/SecretUser",
                "PATH_first_entries": ["C:/secret/bin", "D:/tools"],
                "claude_dir_in_PATH": True,
                "ANTHROPIC_env_names": ["ANTHROPIC_API_KEY"],
                "CLAUDE_env_names": [],
            },
        },
    )
    client = TestClient(create_app(_settings(tmp_path)))

    preflight = client.get("/api/local-agents/preflight")
    assert preflight.status_code == 200
    data = preflight.json()
    assert len(data["adapters"]) == 2
    claude_diag = data["adapters"][0]["diagnostic"]
    assert claude_diag["env_summary"]["ANTHROPIC_env_names"] == ["ANTHROPIC_API_KEY"]
    assert claude_diag["plain_cli_preflight"]["env_summary"]["ANTHROPIC_env_names"] == ["ANTHROPIC_API_KEY"]
    assert claude_diag["plain_cli_preflight"]["env_summary"]["PATH_entry_count"] == 2
    assert secret not in str(data)
    assert "SecretUser" not in str(data)
    assert "C:/secret/bin" not in str(data)

    filtered = client.get("/api/local-agents/preflight?adapter=codex-cli")
    assert filtered.status_code == 200
    assert [item["adapter_id"] for item in filtered.json()["adapters"]] == ["codex-cli"]

    capabilities = client.get("/api/local-agents/capabilities")
    assert capabilities.status_code == 200
    assert "adapters" in capabilities.json()
