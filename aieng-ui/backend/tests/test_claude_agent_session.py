"""Phase 1 coverage for the VSCode-parity agentic session path (Approach A).

Pure-function tests only — no live nested claude process required. See
``aieng-ui/docs/web-chat-agentic-parity-plan.md``.
"""

from __future__ import annotations

from pathlib import Path

from app.agent_autopilot.claude_agent_session import (
    build_agent_command,
    build_run_mcp_config,
    permission_prompt_tool_name,
    translate_stream_event,
)


ROOT = Path("/repo")


def _cmd(**overrides):
    kwargs = dict(
        command_path="/usr/bin/claude",
        prompt="model a 40mm flange",
        session_id="11111111-1111-1111-1111-111111111111",
        resume=False,
        root=ROOT,
        mcp_config="/repo/.mcp.json",
        permission_prompt_tool="mcp__aieng-workbench__request_approval",
        model=None,
        extra_dirs=None,
    )
    kwargs.update(overrides)
    return build_agent_command(**kwargs)


# --- command construction -------------------------------------------------

def test_command_uses_stream_json_not_single_action():
    cmd = _cmd()
    assert "--output-format" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in cmd
    # The capability-killing flags from the legacy adapter must NOT be present.
    assert "--json-schema" not in cmd
    assert "--tools" not in cmd


def test_command_attaches_mcp_strictly():
    cmd = _cmd()
    assert "--mcp-config" in cmd
    assert cmd[cmd.index("--mcp-config") + 1] == "/repo/.mcp.json"
    # Strict: only our per-run config is used, so the user's global workbench
    # server (no run-scoped approval env) cannot shadow it and bypass approval.
    assert "--strict-mcp-config" in cmd


def test_command_session_vs_resume():
    new = _cmd(resume=False)
    assert "--session-id" in new and "--resume" not in new
    cont = _cmd(resume=True)
    assert "--resume" in cont and "--session-id" not in cont


def test_command_never_skips_permissions():
    # Approval is enforced server-side in the MCP tool handler; the command must
    # never disable Claude's permission checks nor rely on a prompt tool.
    cmd = _cmd()
    assert "--dangerously-skip-permissions" not in cmd
    assert "--permission-prompt-tool" not in cmd


def test_permission_prompt_tool_name():
    assert permission_prompt_tool_name() == "mcp__aieng-workbench__request_approval"


# --- stream-json translation ----------------------------------------------

def _tr(raw):
    return translate_stream_event(raw, run_id="r1", project_id="p1", session_id="s1")


def test_translate_init_event():
    events = _tr({
        "type": "system", "subtype": "init", "model": "claude-opus-4-8",
        "tools": ["Read", "Bash", "Skill"], "mcp_servers": [{"name": "aieng-workbench"}],
    })
    assert len(events) == 1
    assert events[0]["type"] == "agent_phase_changed"
    assert events[0]["payload"]["tool_count"] == 3
    assert events[0]["payload"]["model"] == "claude-opus-4-8"


def test_translate_assistant_text_and_tool_use():
    events = _tr({
        "type": "assistant",
        "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Building the flange now."},
            {"type": "tool_use", "id": "tu_1", "name": "cad.execute_build123d", "input": {"code": "..."}},
        ]},
    })
    kinds = [(e["type"], e.get("payload", {}).get("kind")) for e in events]
    assert ("agent_message", "assistant_text") in kinds
    tool_started = [e for e in events if e["type"] == "tool_started"]
    assert tool_started and tool_started[0]["payload"]["tool_name"] == "cad.execute_build123d"
    assert tool_started[0]["payload"]["tool_use_id"] == "tu_1"


def test_translate_thinking_is_diagnostic_kind():
    events = _tr({
        "type": "assistant",
        "message": {"content": [{"type": "thinking", "thinking": "consider proportions"}]},
    })
    assert events[0]["payload"]["kind"] == "thought_summary"


def test_translate_tool_result_success_and_error():
    ok = _tr({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tu_1", "content": "done"},
        ]},
    })
    assert ok[0]["type"] == "tool_completed" and ok[0]["status"] == "success"

    err = _tr({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tu_2", "content": "boom", "is_error": True},
        ]},
    })
    assert err[0]["type"] == "tool_failed" and err[0]["status"] == "error"


def test_translate_result_terminal_success():
    events = _tr({
        "type": "result", "subtype": "success", "is_error": False,
        "result": "The 40mm flange is ready.", "num_turns": 5,
        "usage": {"input_tokens": 100}, "total_cost_usd": 0.01,
    })
    assert len(events) == 1
    assert events[0]["type"] == "run_status_changed"
    assert events[0]["status"] == "completed"
    assert "40mm flange" in events[0]["content"]


def test_translate_result_terminal_failure():
    events = _tr({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": ""})
    assert events[0]["status"] == "failed"


def test_unknown_event_is_ignored():
    assert _tr({"type": "stream_event", "event": {"type": "ping"}}) == []


# --- per-run MCP config injection -----------------------------------------

def test_build_run_mcp_config_injects_run_scoped_env():
    base = {"mcpServers": {"aieng-workbench": {"command": "conda", "env": {"AIENG_BACKEND_URL": "x"}}}}
    cfg = build_run_mcp_config(
        base, run_id="run123", project_id="proj1", session_id="sess1",
        backend_url="http://127.0.0.1:8000",
    )
    env = cfg["mcpServers"]["aieng-workbench"]["env"]
    assert env["AIENG_AUTOPILOT_RUN_ID"] == "run123"
    assert env["AIENG_AUTOPILOT_PROJECT_ID"] == "proj1"
    assert env["AIENG_AUTOPILOT_SESSION_ID"] == "sess1"
    assert env["AIENG_AGENTIC_PERMISSION_TOOL"] == "1"
    assert env["AIENG_BACKEND_URL"] == "http://127.0.0.1:8000"


def test_build_run_mcp_config_does_not_mutate_base():
    base = {"mcpServers": {"aieng-workbench": {"env": {}}}}
    build_run_mcp_config(base, run_id="r", project_id=None, session_id=None, backend_url=None)
    # original base untouched (deep-copied)
    assert base["mcpServers"]["aieng-workbench"]["env"] == {}


def test_build_run_mcp_config_creates_server_entry_when_missing():
    cfg = build_run_mcp_config({}, run_id="r", project_id=None, session_id=None, backend_url=None)
    assert "aieng-workbench" in cfg["mcpServers"]
    assert cfg["mcpServers"]["aieng-workbench"]["env"]["AIENG_AGENTIC_PERMISSION_TOOL"] == "1"
