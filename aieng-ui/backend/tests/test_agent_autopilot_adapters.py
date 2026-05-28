import subprocess

from app.agent_autopilot.adapters import parse_action_json
from app.agent_autopilot.claude_code_adapter import ClaudeCodeAdapter
from app.agent_autopilot.codex_cli_adapter import CodexCliAdapter


def test_parse_action_json_extracts_schema_valid_action() -> None:
    action = parse_action_json(
        '{"thought_summary":"x","action":{"type":"final","message":"Done"},"done":true}'
    )
    assert action.action.type == "final"


def test_parse_action_json_normalizes_flat_cli_action_shape() -> None:
    action = parse_action_json(
        '{"thought_summary":"","done":true,"user_message":null,'
        '"action":{"type":"final","tool_name":null,"input_json":"{}","question":null,'
        '"message":"Done","reason":null}}'
    )
    assert action.action.type == "final"
    assert action.action.message == "Done"


def test_parse_action_json_decodes_cli_tool_input_json() -> None:
    action = parse_action_json(
        '{"thought_summary":"","done":false,"user_message":null,'
        '"action":{"type":"tool_call","tool_name":"aieng.agent_context",'
        '"input_json":"{\\"project_id\\":\\"p1\\"}","question":null,'
        '"message":null,"reason":null}}'
    )
    assert action.action.type == "tool_call"
    assert action.action.input == {"project_id": "p1"}


def test_parse_action_json_reads_claude_structured_output_wrapper() -> None:
    action = parse_action_json(
        '{"type":"result","structured_output":{"thought_summary":"","done":true,'
        '"user_message":"ok","action":{"type":"final","tool_name":null,'
        '"input_json":"{}","question":null,"message":"ok","reason":null}}}'
    )
    assert action.action.type == "final"
    assert action.action.message == "ok"


def test_claude_probe_reports_available_when_required_flags_exist(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter.run_probe_command",
        lambda *_args: subprocess.CompletedProcess(
            ["claude", "--help"],
            0,
            stdout="Usage: claude -p --output-format json --json-schema --permission-mode --tools",
            stderr="",
        ),
    )
    cap = ClaudeCodeAdapter().probe()
    assert cap.status == "available"
    assert cap.supports_non_interactive
    assert cap.supports_json_schema
    assert cap.supports_tool_disable


def test_codex_probe_reports_blocked_without_noninteractive_json(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.codex_cli_adapter.resolve_command", lambda _cmd: "codex")
    monkeypatch.setattr(
        "app.agent_autopilot.codex_cli_adapter.run_probe_command",
        lambda *_args: subprocess.CompletedProcess(
            ["codex", "--help"],
            0,
            stdout="Usage: codex",
            stderr="",
        ),
    )
    cap = CodexCliAdapter().probe()
    assert cap.status == "blocked"
    assert "no safe non-interactive JSON mode" in cap.diagnostic


def test_codex_probe_checks_exec_help_for_safe_structured_mode(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.codex_cli_adapter.resolve_command", lambda _cmd: "codex")

    def _probe(_cmd, args, _timeout):
        if args == ["--help"]:
            return subprocess.CompletedProcess(["codex"], 0, stdout="Commands:\n  exec", stderr="")
        return subprocess.CompletedProcess(
            ["codex", "exec", "--help"],
            0,
            stdout="--sandbox [read-only] --ask-for-approval --output-schema <FILE> --json",
            stderr="",
        )

    monkeypatch.setattr("app.agent_autopilot.codex_cli_adapter.run_probe_command", _probe)
    cap = CodexCliAdapter().probe()
    assert cap.status == "available"
    assert cap.supports_json_schema
    assert cap.supports_tool_disable


def test_missing_command_is_safe_diagnostic(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: None)
    cap = ClaudeCodeAdapter(command="missing-claude").probe()
    assert cap.status == "missing"
    assert "missing-claude" in cap.diagnostic


def test_claude_adapter_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AIENG_DISABLE_CLAUDE_CODE_ADAPTER", "1")
    cap = ClaudeCodeAdapter().probe()
    assert cap.status == "blocked"
    assert "disabled" in cap.diagnostic


def test_claude_invoke_parses_successful_json(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._run_claude_step",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["claude"],
            0,
            stdout='{"action":{"type":"final","message":"Done"},"done":true}',
            stderr="",
        ),
    )
    result = ClaudeCodeAdapter().invoke(prompt="p", action_schema={})
    assert result.status == "success"
    assert result.action is not None
    assert result.action.action.type == "final"


def test_claude_invoke_reports_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._run_claude_step",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["claude"], 0, stdout="not json", stderr=""),
    )
    result = ClaudeCodeAdapter().invoke(prompt="p", action_schema={})
    assert result.status == "error"
    assert "invalid action JSON" in result.diagnostic


def test_claude_invoke_reports_nonzero_exit(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._run_claude_step",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["claude"], 2, stdout="", stderr="bad"),
    )
    result = ClaudeCodeAdapter().invoke(prompt="p", action_schema={})
    assert result.status == "error"
    assert "exited with code 2" in result.diagnostic


def test_claude_invoke_reports_timeout(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")

    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["claude"], timeout=1, output="", stderr="")

    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter._run_claude_step", _raise_timeout)
    result = ClaudeCodeAdapter().invoke(prompt="p", action_schema={}, timeout_seconds=1)
    assert result.status == "timeout"
    assert "timed out" in result.diagnostic
