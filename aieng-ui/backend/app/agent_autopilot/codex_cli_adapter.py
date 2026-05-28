from __future__ import annotations

import os
import subprocess
import json
import tempfile
import time
from pathlib import Path
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


class CodexCliAdapter:
    adapter_id = "codex-cli"
    label = "Codex CLI"

    def __init__(self, command: str | None = None) -> None:
        self.command = command or os.environ.get("AIENG_CODEX_CLI_COMMAND", "codex")

    def probe(self, timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS) -> LocalAgentCapability:
        start = time.perf_counter()
        if os.environ.get("AIENG_DISABLE_CODEX_CLI_ADAPTER") == "1":
            return LocalAgentCapability(
                adapter_id=self.adapter_id,
                label=self.label,
                status="blocked",
                command=self.command,
                diagnostic="Codex CLI adapter disabled by AIENG_DISABLE_CODEX_CLI_ADAPTER=1.",
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
                diagnostic="codex --help timed out; refusing to automate an interactive session.",
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
        root_text = f"{help_result.stdout}\n{help_result.stderr}"
        lower = root_text.lower()
        has_exec = "exec" in lower or "run" in lower
        exec_text = ""
        if has_exec:
            try:
                exec_result = run_probe_command(command_path, ["exec", "--help"], timeout_seconds)
                exec_text = f"{exec_result.stdout}\n{exec_result.stderr}"
            except Exception:
                exec_text = ""
        combined = f"{root_text}\n{exec_text}"
        combined_lower = combined.lower()
        supports_json = "--json" in combined_lower or "jsonl" in combined_lower
        supports_schema = "--output-schema" in combined_lower
        supports_tool_disable = (
            "--sandbox" in combined_lower
            and "read-only" in combined_lower
            and "--ask-for-approval" in combined_lower
        )
        status = "available" if has_exec and supports_schema and supports_tool_disable else "blocked"
        diagnostic = (
            "Safe non-interactive JSON-capable mode appears available."
            if status == "available"
            else "Codex CLI found, but no safe non-interactive JSON mode was detected."
        )
        return LocalAgentCapability(
            adapter_id=self.adapter_id,
            label=self.label,
            status=status,
            command=self.command,
            command_path=command_path,
            version=_first_line(combined),
            supports_non_interactive=has_exec,
            supports_json=supports_json,
            supports_json_schema=supports_schema,
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
        capability = self.probe()
        if capability.status != "available":
            return AdapterInvocationResult(
                status="error",
                diagnostic=capability.diagnostic,
                duration_ms=_elapsed_ms(start),
            )
        command_path = capability.command_path
        if not command_path:
            return AdapterInvocationResult(
                status="error",
                diagnostic=f"Command not found on PATH: {self.command}",
                duration_ms=_elapsed_ms(start),
            )
        with tempfile.TemporaryDirectory(prefix="aieng-codex-autopilot-") as tmp:
            schema_path = Path(tmp) / "agent_action_schema.json"
            output_path = Path(tmp) / "last_message.json"
            schema_path.write_text(json.dumps(action_schema), encoding="utf-8")
            cmd = [
                command_path,
                "--ask-for-approval",
                "never",
                "exec",
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--ignore-rules",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                prompt,
            ]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=timeout_seconds,
                    check=False,
                )
                output_text = output_path.read_text(encoding="utf-8") if output_path.exists() else result.stdout
            except subprocess.TimeoutExpired as exc:
                return AdapterInvocationResult(
                    status="timeout",
                    raw_output=exc.stdout or "",
                    stderr=exc.stderr or "",
                    diagnostic=f"Codex CLI step timed out after {timeout_seconds}s.",
                    duration_ms=_elapsed_ms(start),
                )
            except OSError as exc:
                return AdapterInvocationResult(status="error", diagnostic=str(exc), duration_ms=_elapsed_ms(start))
            if result.returncode != 0:
                return AdapterInvocationResult(
                    status="error",
                    raw_output=result.stdout,
                    stderr=result.stderr,
                    diagnostic=f"Codex CLI exited with code {result.returncode}.",
                    duration_ms=_elapsed_ms(start),
                )
            try:
                action = parse_action_json(output_text)
            except Exception as exc:
                return AdapterInvocationResult(
                    status="error",
                    raw_output=output_text,
                    stderr=result.stderr,
                    diagnostic=f"Codex CLI returned invalid action JSON: {exc}",
                    duration_ms=_elapsed_ms(start),
                )
            return AdapterInvocationResult(
                status="success",
                action=action,
                raw_output=output_text,
                stderr=result.stderr,
                duration_ms=_elapsed_ms(start),
            )
