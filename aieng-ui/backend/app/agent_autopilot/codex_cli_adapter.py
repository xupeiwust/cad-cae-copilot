from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

from .adapters import (
    DEFAULT_PROBE_TIMEOUT_SECONDS,
    DEFAULT_STEP_TIMEOUT_SECONDS,
    _elapsed_ms,
    _first_line,
    capability_from_missing,
    parse_action_json,
    progress_event,
    resolve_command,
    run_probe_command,
)
from .schema import AdapterInvocationResult, LocalAgentCapability


def _decode_output(data: bytes | None) -> str:
    """Decode subprocess output on Windows where Node.js tools may emit GBK."""
    if not data:
        return ""
    for encoding in ("utf-8", "gbk", "gb2312", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


class CodexCliAdapter:
    adapter_id = "codex-cli"
    label = "Codex CLI"

    def __init__(self, command: str | None = None) -> None:
        self.command = command or os.environ.get("AIENG_CODEX_CLI_COMMAND", "codex")
        self._capability_cache: LocalAgentCapability | None = None

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
            supports_session_continuation=False,
            diagnostic=diagnostic,
            probe_duration_ms=_elapsed_ms(start),
        )

    def invoke(
        self,
        *,
        prompt: str,
        action_schema: dict[str, Any],
        timeout_seconds: int = DEFAULT_STEP_TIMEOUT_SECONDS,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        session_id: str | None = None,
        step_index: int = 0,
    ) -> AdapterInvocationResult:
        start = time.perf_counter()
        if on_progress is not None:
            on_progress(progress_event(self.adapter_id, "started", "Starting Codex CLI capability check."))
        capability = (
            self._capability_cache
            if self._capability_cache and self._capability_cache.status == "available"
            else None
        )
        if capability is None:
            capability = self.probe()
            if capability.status == "available":
                self._capability_cache = capability
        if capability.status != "available":
            return AdapterInvocationResult(
                status="error",
                stderr="",
                diagnostic=capability.diagnostic,
                duration_ms=_elapsed_ms(start),
            )
        command_path = capability.command_path
        if not command_path:
            return AdapterInvocationResult(
                status="error",
                stderr="",
                diagnostic=f"Command not found on PATH: {self.command}",
                duration_ms=_elapsed_ms(start),
            )
        if on_progress is not None:
            on_progress(progress_event(
                self.adapter_id,
                "prompt_prepared",
                "Codex CLI is available; preparing structured output schema.",
                command_path=command_path,
                step_index=step_index,
            ))
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
            ]
            try:
                # Pipe the prompt via stdin to avoid Windows command-line length limit
                # (~8191 chars).  Codex exec reads the prompt from stdin when no
                # positional prompt arg is supplied.
                if on_progress is not None:
                    on_progress(progress_event(
                        self.adapter_id,
                        "request_sent",
                        "Codex exec request prepared; starting subprocess.",
                        schema_path=str(schema_path),
                        step_index=step_index,
                    ))
                    on_progress(progress_event(
                        self.adapter_id,
                        "waiting_for_model",
                        "Codex exec is running in read-only sandbox; waiting for final action JSON.",
                        schema_path=str(schema_path),
                        step_index=step_index,
                    ))
                result = subprocess.run(
                    cmd,
                    input=prompt.encode("utf-8"),
                    capture_output=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                stdout_decoded = _decode_output(result.stdout)
                stderr_decoded = _decode_output(result.stderr)
                output_text = (
                    _decode_output(output_path.read_bytes())
                    if output_path.exists()
                    else stdout_decoded
                )
            except subprocess.TimeoutExpired as exc:
                if on_progress is not None:
                    on_progress(progress_event(self.adapter_id, "timeout", f"Codex CLI step timed out after {timeout_seconds}s.", step_index=step_index))
                return AdapterInvocationResult(
                    status="timeout",
                    raw_output=_decode_output(exc.stdout),
                    stderr=_decode_output(exc.stderr),
                    diagnostic=f"Codex CLI step timed out after {timeout_seconds}s.",
                    duration_ms=_elapsed_ms(start),
                )
            except OSError as exc:
                if on_progress is not None:
                    on_progress(progress_event(self.adapter_id, "error", str(exc), step_index=step_index))
                return AdapterInvocationResult(
                    status="error",
                    stderr="",
                    diagnostic=str(exc),
                    duration_ms=_elapsed_ms(start),
                )
            if result.returncode != 0:
                diag = (
                    f"Codex CLI exited with code {result.returncode}.\n"
                    f"stderr: {stderr_decoded[:600]!r}\n"
                    f"stdout_preview: {stdout_decoded[:600]!r}"
                )
                logger.error("codex invoke failed: %s", diag)
                if on_progress is not None:
                    on_progress(progress_event(self.adapter_id, "error", "Codex CLI exited with an error.", step_index=step_index))
                return AdapterInvocationResult(
                    status="error",
                    raw_output=stdout_decoded,
                    stderr=stderr_decoded,
                    diagnostic=diag,
                    duration_ms=_elapsed_ms(start),
                )
            try:
                if on_progress is not None:
                    on_progress(progress_event(
                        self.adapter_id,
                        "parsing_output",
                        (
                            "Codex CLI returned output; validating the structured action "
                            f"({len(output_text)} output chars, {len(stderr_decoded)} stderr chars)."
                        ),
                        output_chars=len(output_text),
                        stderr_chars=len(stderr_decoded),
                        step_index=step_index,
                    ))
                action = parse_action_json(output_text)
            except Exception as exc:
                diag = (
                    f"Codex CLI returned invalid action JSON: {exc}\n"
                    f"stderr: {stderr_decoded[:600]!r}\n"
                    f"stdout_preview: {stdout_decoded[:600]!r}"
                )
                logger.error("codex parse failed: %s", diag)
                if on_progress is not None:
                    on_progress(progress_event(self.adapter_id, "error", "Codex CLI returned invalid action JSON.", step_index=step_index))
                return AdapterInvocationResult(
                    status="error",
                    raw_output=output_text,
                    stderr=stderr_decoded,
                    diagnostic=diag,
                    duration_ms=_elapsed_ms(start),
                )
            if on_progress is not None:
                on_progress(progress_event(
                    self.adapter_id,
                    "completed",
                    f"Codex CLI selected action {action.action.type}.",
                    action_type=action.action.type,
                    duration_ms=_elapsed_ms(start),
                    step_index=step_index,
                ))
            return AdapterInvocationResult(
                status="success",
                action=action,
                raw_output=output_text,
                stderr=stderr_decoded,
                duration_ms=_elapsed_ms(start),
            )
