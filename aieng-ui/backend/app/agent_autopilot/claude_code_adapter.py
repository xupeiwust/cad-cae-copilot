from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

from .adapters import (
    DEFAULT_PROBE_TIMEOUT_SECONDS,
    DEFAULT_STEP_TIMEOUT_SECONDS,
    _elapsed_ms,
    _first_line,
    capability_from_missing,
    parse_action_json,
    resolve_command,
    run_probe_command,
)
from .schema import AdapterInvocationResult, LocalAgentCapability


def _run_claude_step(cmd: list[str], prompt: str, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "NO_COLOR": "1",
    })
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    try:
        stdout, stderr = proc.communicate(input=prompt, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            proc.kill()
        stdout, stderr = proc.communicate(timeout=5)
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=timeout_seconds,
            output=stdout or exc.output,
            stderr=stderr or exc.stderr,
        ) from exc
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout=stdout, stderr=stderr)


class ClaudeCodeAdapter:
    adapter_id = "claude-code"
    label = "Claude Code CLI"

    def __init__(self, command: str | None = None, workspace: str | None = None) -> None:
        self.command = command or os.environ.get("AIENG_CLAUDE_CODE_COMMAND", "claude")
        self.workspace = workspace or os.environ.get("AIENG_LOCAL_AGENT_WORKSPACE", "")

    def probe(self, timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS) -> LocalAgentCapability:
        start = time.perf_counter()
        if os.environ.get("AIENG_DISABLE_CLAUDE_CODE_ADAPTER") == "1":
            return LocalAgentCapability(
                adapter_id=self.adapter_id,
                label=self.label,
                status="blocked",
                command=self.command,
                diagnostic="Claude Code adapter disabled by AIENG_DISABLE_CLAUDE_CODE_ADAPTER=1.",
                probe_duration_ms=_elapsed_ms(start),
            )
        command_path = resolve_command(self.command)
        if not command_path:
            return capability_from_missing(self.adapter_id, self.label, self.command, _elapsed_ms(start))
        try:
            help_result = run_probe_command(command_path, ["--help"], timeout_seconds)
        except subprocess.TimeoutExpired:
            return LocalAgentCapability(
                adapter_id=self.adapter_id,
                label=self.label,
                status="blocked",
                command=self.command,
                command_path=command_path,
                diagnostic="claude --help timed out; refusing to start an interactive session.",
                probe_duration_ms=_elapsed_ms(start),
            )
        except OSError as exc:
            return LocalAgentCapability(
                adapter_id=self.adapter_id,
                label=self.label,
                status="error",
                command=self.command,
                command_path=command_path,
                diagnostic=str(exc),
                probe_duration_ms=_elapsed_ms(start),
            )
        text = f"{help_result.stdout}\n{help_result.stderr}"
        supports_non_interactive = "-p" in text or "--print" in text
        supports_json = "--output-format" in text and "json" in text.lower()
        supports_json_schema = "--json-schema" in text
        supports_tool_disable = "--tools" in text
        status = "available" if supports_non_interactive and supports_json else "blocked"
        diagnostic = "Safe non-interactive JSON mode detected." if status == "available" else (
            "Claude Code CLI found, but required non-interactive JSON flags were not detected."
        )
        return LocalAgentCapability(
            adapter_id=self.adapter_id,
            label=self.label,
            status=status,
            command=self.command,
            command_path=command_path,
            version=_first_line(text),
            supports_non_interactive=supports_non_interactive,
            supports_json=supports_json,
            supports_json_schema=supports_json_schema,
            supports_tool_disable=supports_tool_disable,
            diagnostic=diagnostic,
            probe_duration_ms=_elapsed_ms(start),
        )

    def invoke(
        self,
        *,
        prompt: str,
        action_schema: dict[str, Any],
        timeout_seconds: int = DEFAULT_STEP_TIMEOUT_SECONDS,
    ) -> AdapterInvocationResult:
        start = time.perf_counter()
        command_path = resolve_command(self.command)
        if not command_path:
            return AdapterInvocationResult(
                status="error",
                diagnostic=f"Command not found on PATH: {self.command}",
                duration_ms=_elapsed_ms(start),
            )
        cmd = [
            command_path,
            "-p",
            "--bare",
            "--no-session-persistence",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(action_schema),
            "--permission-mode",
            "plan",
            "--tools",
            "",
        ]
        if self.workspace:
            cmd.extend(["--add-dir", self.workspace])
        try:
            result = _run_claude_step(cmd, prompt, timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            return AdapterInvocationResult(
                status="timeout",
                raw_output=exc.stdout or "",
                stderr=exc.stderr or "",
                diagnostic=f"Claude Code step timed out after {timeout_seconds}s.",
                duration_ms=_elapsed_ms(start),
            )
        except OSError as exc:
            return AdapterInvocationResult(
                status="error",
                diagnostic=str(exc),
                duration_ms=_elapsed_ms(start),
            )
        if result.returncode != 0:
            return AdapterInvocationResult(
                status="error",
                raw_output=result.stdout,
                stderr=result.stderr,
                diagnostic=f"Claude Code exited with code {result.returncode}.",
                duration_ms=_elapsed_ms(start),
            )
        try:
            action = parse_action_json(result.stdout)
        except Exception as exc:
            return AdapterInvocationResult(
                status="error",
                raw_output=result.stdout,
                stderr=result.stderr,
                diagnostic=f"Claude Code returned invalid action JSON: {exc}",
                duration_ms=_elapsed_ms(start),
            )
        return AdapterInvocationResult(
            status="success",
            action=action,
            raw_output=result.stdout,
            stderr=result.stderr,
            duration_ms=_elapsed_ms(start),
        )
