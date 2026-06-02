import json
import os
import subprocess

import pytest

import app.agent_autopilot.claude_code_adapter as claude_module
from app.agent_autopilot.adapters import (
    COMMON_PROGRESS_PHASES,
    PROSE_RESULT_MESSAGE,
    AdapterResultError,
    ProseResultError,
    parse_action_json,
)
from app.agent_autopilot.claude_code_adapter import (
    DEFAULT_CLAUDE_PREFLIGHT_TIMEOUT_SECONDS,
    ClaudeCodeAdapter,
    _build_claude_env,
    _claude_preflight_timeout_default,
    _env_summary,
    run_claude_preflight,
)
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


def test_parse_action_json_rejects_empty_terminal_message_with_clear_error() -> None:
    with pytest.raises(ValueError, match="terminal action final requires a non-empty message"):
        parse_action_json(
            '{"thought_summary":"x","action":{"type":"final","message":""},"done":true}'
        )


# --- Claude CLI result-wrapper unwrapping (regression for "claude parse failed") ---


def _wrapper(result, *, is_error=False, subtype="success") -> str:
    return json.dumps(
        {
            "type": "result",
            "subtype": subtype,
            "is_error": is_error,
            "duration_ms": 339269,
            "result": result,
            "session_id": "abc",
        }
    )


def test_parse_wrapper_with_action_json_string_in_result() -> None:
    # Case B: wrapper whose `result` string is a valid AutopilotAgentAction JSON.
    inner = json.dumps(
        {
            "thought_summary": "done",
            "done": True,
            "action": {"type": "final", "message": "Bracket created."},
        }
    )
    action = parse_action_json(_wrapper(inner))
    assert action.action.type == "final"
    assert action.action.message == "Bracket created."


def test_parse_wrapper_with_fenced_action_json_in_result() -> None:
    inner = '```json\n{"action": {"type": "final", "message": "ok"}, "done": true}\n```'
    action = parse_action_json(_wrapper(inner))
    assert action.action.type == "final"
    assert action.action.message == "ok"


def test_parse_wrapper_with_prose_result_raises_prose_error() -> None:
    # Case C: the exact reported failure — wrapper `result` is prose.
    with pytest.raises(ProseResultError) as excinfo:
        parse_action_json(
            _wrapper("I've completed the parametric bracket CAD workflow. Done.")
        )
    assert str(excinfo.value) == PROSE_RESULT_MESSAGE


def test_parse_wrapper_with_is_error_raises_result_error() -> None:
    # Case E: wrapper reports failure.
    with pytest.raises(AdapterResultError):
        parse_action_json(_wrapper("anything", is_error=True))


def test_parse_wrapper_with_failure_subtype_raises_result_error() -> None:
    with pytest.raises(AdapterResultError):
        parse_action_json(_wrapper("anything", subtype="error_max_turns"))


def test_parse_malformed_json_raises() -> None:
    # Case D: malformed JSON with no recoverable object.
    with pytest.raises(ValueError):
        parse_action_json("not json at all")


def test_parse_empty_output_raises() -> None:
    with pytest.raises(ValueError):
        parse_action_json("   ")


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
    events = []
    result = ClaudeCodeAdapter().invoke(prompt="p", action_schema={}, on_progress=events.append)
    assert result.status == "success"
    assert result.action is not None
    assert result.action.action.type == "final"
    phases = [event["phase"] for event in events]
    assert phases == ["started", "prompt_prepared", "request_sent", "waiting_for_model", "parsing_output", "completed"]
    assert set(phases) <= set(COMMON_PROGRESS_PHASES)


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


def test_claude_failure_diagnostic_redacts_prompt_and_env_values(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "super-secret-token")
    monkeypatch.setenv("CLAUDE_CODE_TOKEN", "another-secret-token")
    monkeypatch.setenv("USERPROFILE", r"C:\Users\tester")
    monkeypatch.setenv("APPDATA", r"C:\Users\tester\AppData\Roaming")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\tester\AppData\Local")
    monkeypatch.setenv("HOME", r"C:\Users\tester")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._claude_version",
        lambda *_args, **_kwargs: {"ok": True, "output": "2.1.141 (Claude Code)"},
    )
    long_prompt = "inspect " + ("x" * 140) + " super-secret-token"
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._run_claude_step",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["claude"], 1, stdout="", stderr="bad"),
    )

    result = ClaudeCodeAdapter().invoke(prompt=long_prompt, action_schema={"secret": "schema-secret"})

    assert result.status == "error"
    assert "--json-schema" in result.diagnostic
    assert "<json_schema length=" in result.diagnostic
    assert '"prompt_length"' in result.diagnostic
    assert '"prompt_preview"' in result.diagnostic
    assert "super-secret-token" not in result.diagnostic
    assert "schema-secret" not in result.diagnostic
    assert "ANTHROPIC_API_KEY" in result.diagnostic
    assert "CLAUDE_CODE_TOKEN" in result.diagnostic
    assert "another-secret-token" not in result.diagnostic
    assert "USERPROFILE" in result.diagnostic
    assert '"passed_session_id": true' in result.diagnostic
    assert '"passed_json_schema": true' in result.diagnostic
    assert '"passed_permission_flags": true' in result.diagnostic
    assert '"adapter_id": "claude-code"' in result.diagnostic


def test_claude_preflight_success(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._claude_version",
        lambda *_args, **_kwargs: {"ok": True, "output": "2.1.141 (Claude Code)"},
    )

    def _fake_run(cmd, **kwargs):
        assert cmd == ["claude", "-p", "Say hello", "--output-format", "json"]
        assert kwargs["env"]["PYTHONUTF8"] == "1"
        assert kwargs["cwd"] == str(tmp_path)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"type": "result", "is_error": False, "result": "hello"}),
            stderr="",
        )

    monkeypatch.setattr(claude_module.subprocess, "run", _fake_run)
    result = run_claude_preflight(command="claude", cwd=str(tmp_path))
    assert result["ok"] is True
    assert result["resolved_path"] == "claude"
    assert result["version"]["output"].startswith("2.1.141")
    assert result["stdout_parsed_result"]["is_error"] is False
    assert result["rc"] == 0


def test_claude_preflight_default_timeout_is_20(monkeypatch) -> None:
    monkeypatch.delenv("AIENG_CLAUDE_PREFLIGHT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._claude_version",
        lambda *_args, **_kwargs: {"ok": True, "output": "2.1.141 (Claude Code)"},
    )
    captured: dict[str, int] = {}

    def _fake_run(cmd, **kwargs):
        captured["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"type": "result", "is_error": False, "result": "Hello!"}),
            stderr="",
        )

    monkeypatch.setattr(claude_module.subprocess, "run", _fake_run)
    result = run_claude_preflight(command="claude")
    assert DEFAULT_CLAUDE_PREFLIGHT_TIMEOUT_SECONDS == 20
    assert _claude_preflight_timeout_default() == 20
    assert captured["timeout"] == 20
    assert result["ok"] is True


def test_claude_preflight_timeout_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AIENG_CLAUDE_PREFLIGHT_TIMEOUT_SECONDS", "9")
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._claude_version",
        lambda *_args, **_kwargs: {"ok": True, "output": "2.1.141 (Claude Code)"},
    )
    captured: dict[str, int] = {}

    def _fake_run(cmd, **kwargs):
        captured["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"type": "result", "is_error": False, "result": "Hello!"}),
            stderr="",
        )

    monkeypatch.setattr(claude_module.subprocess, "run", _fake_run)
    result = run_claude_preflight(command="claude")
    assert _claude_preflight_timeout_default() == 9
    assert captured["timeout"] == 9
    assert result["ok"] is True


def test_claude_preflight_timeout_reports_timeout_only(monkeypatch) -> None:
    monkeypatch.setenv("AIENG_CLAUDE_PREFLIGHT_TIMEOUT_SECONDS", "8")
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._claude_version",
        lambda *_args, **_kwargs: {"ok": True, "output": "2.1.141 (Claude Code)"},
    )

    def _fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs["timeout"], output="", stderr="")

    monkeypatch.setattr(claude_module.subprocess, "run", _fake_run)
    result = run_claude_preflight(command="claude")
    assert result["ok"] is False
    assert result["error"] == "timeout after 8s"
    assert "Not logged in" not in json.dumps(result)
    assert "authenticated" not in json.dumps(result)
    assert "auth failure" not in json.dumps(result).lower()


def test_claude_preflight_not_logged_in(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._claude_version",
        lambda *_args, **_kwargs: {"ok": True, "output": "2.1.141 (Claude Code)"},
    )

    def _fake_run(cmd, **_kwargs):
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout=json.dumps({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"}),
            stderr="",
        )

    monkeypatch.setattr(claude_module.subprocess, "run", _fake_run)
    result = run_claude_preflight(command="claude")
    assert result["ok"] is False
    assert result["rc"] == 1
    assert result["stdout_parsed_result"]["is_error"] is True
    assert "Not logged in" in result["stdout_parsed_result"]["result"]


def test_claude_not_logged_in_with_successful_preflight_is_adapter_mismatch(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._claude_version",
        lambda *_args, **_kwargs: {"ok": True, "output": "2.1.141 (Claude Code)"},
    )
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter.run_claude_preflight",
        lambda **_kwargs: {"ok": True, "resolved_path": "claude", "rc": 0, "stdout_parsed_result": {"is_error": False}},
    )
    stdout = json.dumps({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._run_claude_step",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["claude"], 1, stdout=stdout, stderr=""),
    )

    result = ClaudeCodeAdapter().invoke(prompt="p", action_schema={})

    assert result.status == "error"
    assert "authenticated for plain CLI calls" in result.diagnostic
    assert "incompatible adapter flag or environment mismatch" in result.diagnostic
    assert "Please run /login" not in result.diagnostic.splitlines()[0]
    assert '"preflight"' in result.diagnostic


def test_claude_resume_session_not_found_has_normalized_diagnostic(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._claude_version",
        lambda *_args, **_kwargs: {"ok": True, "output": "2.1.141 (Claude Code)"},
    )
    stdout = "No conversation found with session ID: da0a3921-cc45-501e-ad5e-5629b0d95941"
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._run_claude_step",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["claude"], 1, stdout=stdout, stderr=""),
    )

    result = ClaudeCodeAdapter().invoke(
        prompt="p",
        action_schema={},
        session_id="da0a3921-cc45-501e-ad5e-5629b0d95941",
        step_index=1,
    )

    assert result.status == "error"
    assert result.diagnostic.splitlines()[0].startswith("Claude Code could not resume the requested session")
    assert "conversation/session mismatch" in result.diagnostic
    assert '"passed_resume": true' in result.diagnostic
    assert '"effective_claude_session_id": "da0a3921-cc45-501e-ad5e-5629b0d95941"' in result.diagnostic


def test_claude_invoke_reports_timeout(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")

    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["claude"], timeout=1, output="", stderr="")

    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter._run_claude_step", _raise_timeout)
    events = []
    result = ClaudeCodeAdapter().invoke(prompt="p", action_schema={}, timeout_seconds=1, on_progress=events.append)
    assert result.status == "timeout"
    assert "timed out before producing a structured action" in result.diagnostic
    assert result.diagnostic  # non-empty
    assert events[-1]["phase"] == "timeout"


def test_claude_invoke_blocks_on_prose_result(monkeypatch) -> None:
    # Case C end-to-end: prose wrapper → status=error with a non-empty, clear
    # message; raw stdout preserved; no fabricated success.
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    wrapper = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "I've completed the parametric bracket CAD workflow.",
        }
    )
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._run_claude_step",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["claude"], 0, stdout=wrapper, stderr=""),
    )
    result = ClaudeCodeAdapter().invoke(prompt="p", action_schema={})
    assert result.status == "error"
    assert result.action is None
    assert PROSE_RESULT_MESSAGE in result.diagnostic
    assert result.raw_output == wrapper


def test_claude_invoke_blocks_on_is_error_wrapper(monkeypatch) -> None:
    # Case E end-to-end: wrapper is_error=true → status=error, debug preserved.
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    wrapper = json.dumps(
        {"type": "result", "subtype": "error_during_execution", "is_error": True, "result": ""}
    )
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._run_claude_step",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["claude"], 0, stdout=wrapper, stderr="boom"),
    )
    result = ClaudeCodeAdapter().invoke(prompt="p", action_schema={})
    assert result.status == "error"
    assert result.action is None
    assert result.diagnostic  # non-empty
    assert "failed result" in result.diagnostic
    assert result.raw_output == wrapper


def test_claude_invoke_unwraps_wrapper_action_string(monkeypatch) -> None:
    # Case B end-to-end: wrapper result string carries a valid action.
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    inner = json.dumps({"action": {"type": "final", "message": "Done."}, "done": True})
    wrapper = json.dumps(
        {"type": "result", "subtype": "success", "is_error": False, "result": inner}
    )
    monkeypatch.setattr(
        "app.agent_autopilot.claude_code_adapter._run_claude_step",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["claude"], 0, stdout=wrapper, stderr=""),
    )
    result = ClaudeCodeAdapter().invoke(prompt="p", action_schema={})
    assert result.status == "success"
    assert result.action is not None
    assert result.action.action.type == "final"
    assert result.action.action.message == "Done."


def test_claude_argv_uses_expected_flags_and_no_bare_by_default(monkeypatch) -> None:
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude.exe")
    captured: dict[str, list[str]] = {}

    def _capture(cmd, _prompt, _timeout_seconds):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            cmd, 0, stdout='{"action":{"type":"final","message":"ok"},"done":true}', stderr=""
        )

    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter._run_claude_step", _capture)
    session_id = "da0a3921-cc45-501e-ad5e-5629b0d95941"
    ClaudeCodeAdapter().invoke(prompt="p", action_schema={}, session_id=session_id, step_index=0)

    cmd = captured["cmd"]
    assert cmd[0] == "claude.exe"
    assert "--bare" not in cmd
    assert "--session-id" in cmd
    assert session_id in cmd
    assert "--output-format" in cmd
    assert "--json-schema" in cmd
    assert "--permission-mode" in cmd
    assert "--tools" in cmd


def test_claude_argv_can_opt_into_bare_for_diagnostics(monkeypatch) -> None:
    monkeypatch.setenv("AIENG_CLAUDE_CODE_BARE", "1")
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude.exe")
    captured: dict[str, list[str]] = {}

    def _capture(cmd, _prompt, _timeout_seconds):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            cmd, 0, stdout='{"action":{"type":"final","message":"ok"},"done":true}', stderr=""
        )

    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter._run_claude_step", _capture)
    ClaudeCodeAdapter().invoke(prompt="p", action_schema={})
    assert captured["cmd"][:3] == ["claude.exe", "-p", "--bare"]


def test_claude_env_preserves_windows_profile_and_path(monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", r"C:\Users\RL_Carla")
    monkeypatch.setenv("APPDATA", r"C:\Users\RL_Carla\AppData\Roaming")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\RL_Carla\AppData\Local")
    monkeypatch.setenv("HOME", r"C:\Users\RL_Carla")
    claude_dir = r"C:\Users\RL_Carla\.local\bin"
    monkeypatch.setenv("PATH", os.pathsep.join([claude_dir, r"C:\Windows\System32"]))
    env = _build_claude_env()
    summary = _env_summary(env, os.path.join(claude_dir, "claude.exe"))

    assert env["USERPROFILE"] == r"C:\Users\RL_Carla"
    assert env["APPDATA"].endswith(r"AppData\Roaming")
    assert env["LOCALAPPDATA"].endswith(r"AppData\Local")
    assert env["HOME"] == r"C:\Users\RL_Carla"
    assert claude_dir in env["PATH"]
    assert summary["claude_dir_in_PATH"] is True
    assert summary["PATH_first_entries"][0] == claude_dir


def test_claude_invoke_clamps_large_timeout_to_adapter_ceiling(monkeypatch) -> None:
    # The engine passes a large global step timeout; the adapter must clamp it.
    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter.resolve_command", lambda _cmd: "claude")
    captured: dict[str, int] = {}

    def _capture(_cmd, _prompt, timeout_seconds):
        captured["timeout"] = timeout_seconds
        return subprocess.CompletedProcess(
            ["claude"], 0, stdout='{"action":{"type":"final","message":"ok"},"done":true}', stderr=""
        )

    monkeypatch.setattr("app.agent_autopilot.claude_code_adapter._run_claude_step", _capture)
    adapter = ClaudeCodeAdapter()
    assert adapter.timeout_seconds == 180
    adapter.invoke(prompt="p", action_schema={}, timeout_seconds=1800)
    assert captured["timeout"] == 180


def test_claude_timeout_default_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AIENG_CLAUDE_CODE_TIMEOUT_SECONDS", "90")
    assert ClaudeCodeAdapter().timeout_seconds == 90
    monkeypatch.setenv("AIENG_CLAUDE_CODE_TIMEOUT_SECONDS", "garbage")
    assert ClaudeCodeAdapter().timeout_seconds == 180
