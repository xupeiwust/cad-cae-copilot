from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import uuid
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


def _resolve_claude_exe(command: str) -> str | None:
    """On Windows, npm global CLI tools are often installed as .cmd wrappers.
    Those wrappers can trigger interactive 'Terminate batch job (Y/N)?'
    prompts when the underlying Node process exits.  Prefer the .exe if it
    exists alongside the .cmd."""
    path = resolve_command(command)
    if not path or os.name != "nt":
        return path
    lower = path.lower()
    if lower.endswith((".cmd", ".bat")):
        # Try replacing .cmd/.bat with .exe in the same directory
        base = path[:-4] if lower.endswith(".cmd") else path[:-4]
        exe_candidate = base + ".exe"
        if os.path.isfile(exe_candidate):
            return exe_candidate
    return path


# Track which deterministic sessions have already been created by this adapter.
# Key = effective_session_id (UUID string).  Value = True.
# Used to decide between --session-id (first call) and --resume (subsequent calls).
# A module-level dict survives across per-request engine/adapter rebuilds.
_session_created_flags: dict[str, bool] = {}


def _run_claude_step(cmd: list[str], prompt: str, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "NO_COLOR": "1",
    })
    # On Windows use CREATE_NO_WINDOW to prevent the child process from
    # creating a console window (and possibly interactive prompts like the
    # infamous "Terminate batch job (Y/N)?").
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[call-arg]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        **kwargs,
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
    logger.info(
        "claude step finished: rc=%s stdout=%d chars stderr=%d chars cmd=%s",
        proc.returncode,
        len(stdout),
        len(stderr),
        cmd[:6],
    )
    if proc.returncode != 0:
        logger.warning(
            "claude step nonzero exit: rc=%s stderr=%r stdout_preview=%r",
            proc.returncode,
            stderr[:500],
            stdout[:500],
        )
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout=stdout, stderr=stderr)


class ClaudeCodeAdapter:
    adapter_id = "claude-code"
    label = "Claude Code CLI"

    def __init__(self, command: str | None = None, workspace: str | None = None) -> None:
        self.command = command or os.environ.get("AIENG_CLAUDE_CODE_COMMAND", "claude")
        self.workspace = workspace or os.environ.get("AIENG_LOCAL_AGENT_WORKSPACE", "")
        # Allowlist for Claude's built-in tools. Empty string disables all built-in
        # tools; a comma-separated list (e.g. "Read,Edit,Grep") enables only those.
        # Default allows most common tools except Bash to avoid arbitrary shell execution.
        self.tools = os.environ.get("AIENG_CLAUDE_CODE_TOOLS", "Read,Edit,Grep,Glob,LS,Search")

    @staticmethod
    def _claude_session_id(session_id: str | None) -> str:
        """Return a valid UUID for --session-id / --resume.

        The frontend chat session ID is an arbitrary string (e.g. 12-char hex).
        Claude CLI --session-id and --resume require a strict UUID format, so we
        map non-UUID values deterministically via uuid5.  This is stateless and
        survives adapter instance rebuilds (e.g. per-request engine creation).
        """
        if session_id is None:
            return str(uuid.uuid4())
        try:
            uuid.UUID(session_id)
            return session_id
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_OID, session_id))

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
            supports_session_continuation=True,
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
            on_progress(progress_event(self.adapter_id, "started", "Starting Claude Code CLI in non-interactive JSON mode."))
        command_path = _resolve_claude_exe(self.command)
        if not command_path:
            return AdapterInvocationResult(
                status="error",
                diagnostic=f"Command not found on PATH: {self.command}",
                duration_ms=_elapsed_ms(start),
            )
        # Session-aware invocation:
        #   First call for a session uses --session-id to create it.
        #   Subsequent calls use --resume <session_id> to reconnect to the
        #   same session instead of --continue (which resumes the *most recent*
        #   session and could leak into a user's interactive CLI session).
        #   A module-level dict tracks which sessions have already been created
        #   so the adapter survives per-request rebuilds.
        effective_session_id = self._claude_session_id(session_id)
        has_existing_session = _session_created_flags.get(effective_session_id, False)
        use_resume = has_existing_session or step_index > 0
        if on_progress is not None:
            on_progress(progress_event(
                self.adapter_id,
                "prompt_prepared",
                f"Claude Code command resolved; session={effective_session_id} mode={'--resume' if use_resume else '--session-id'}.",
                command_path=command_path,
                session_id=effective_session_id,
                step_index=step_index,
            ))

        def _build_cmd(session_flag: str) -> list[str]:
            cmd = [
                command_path,
                "-p",
                "--bare",
                session_flag,
                effective_session_id,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(action_schema),
                "--permission-mode",
                "auto",
                "--tools",
                self.tools,
            ]
            if self.workspace:
                cmd.extend(["--add-dir", self.workspace])
            return cmd

        cmd = _build_cmd("--resume" if use_resume else "--session-id")
        try:
            if on_progress is not None:
                on_progress(progress_event(
                    self.adapter_id,
                    "request_sent",
                    "Claude Code request prepared; starting subprocess.",
                    session_id=effective_session_id,
                    step_index=step_index,
                ))
                on_progress(progress_event(
                    self.adapter_id,
                    "waiting_for_model",
                    "Claude Code process is running; waiting for structured action JSON.",
                    session_id=effective_session_id,
                    step_index=step_index,
                ))
            result = _run_claude_step(cmd, prompt, timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            if on_progress is not None:
                on_progress(progress_event(self.adapter_id, "timeout", f"Claude Code step timed out after {timeout_seconds}s.", step_index=step_index))
            return AdapterInvocationResult(
                status="timeout",
                raw_output=exc.stdout or "",
                stderr=exc.stderr or "",
                diagnostic=f"Claude Code step timed out after {timeout_seconds}s.",
                duration_ms=_elapsed_ms(start),
            )
        except OSError as exc:
            if on_progress is not None:
                on_progress(progress_event(self.adapter_id, "error", str(exc), step_index=step_index))
            return AdapterInvocationResult(
                status="error",
                diagnostic=str(exc),
                duration_ms=_elapsed_ms(start),
            )
        # If the CLI reports the session is already locked, mark it as created
        # and retry with --resume (handles backend restarts where the module
        # dict was cleared but the session still exists on disk).
        if result.returncode != 0 and "already in use" in (result.stderr or ""):
            logger.warning(
                "claude session '%s' already in use; retrying with --resume.",
                effective_session_id,
            )
            _session_created_flags[effective_session_id] = True
            cmd = _build_cmd("--resume")
            try:
                result = _run_claude_step(cmd, prompt, timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                if on_progress is not None:
                    on_progress(progress_event(self.adapter_id, "timeout", f"Claude Code step timed out after {timeout_seconds}s.", step_index=step_index))
                return AdapterInvocationResult(
                    status="timeout",
                    raw_output=exc.stdout or "",
                    stderr=exc.stderr or "",
                    diagnostic=f"Claude Code step timed out after {timeout_seconds}s.",
                    duration_ms=_elapsed_ms(start),
                )
            except OSError as exc:
                if on_progress is not None:
                    on_progress(progress_event(self.adapter_id, "error", str(exc), step_index=step_index))
                return AdapterInvocationResult(
                    status="error",
                    diagnostic=str(exc),
                    duration_ms=_elapsed_ms(start),
                )
        # Mark the session as created on success so future calls use --resume.
        if result.returncode == 0:
            _session_created_flags[effective_session_id] = True
        if result.returncode != 0:
            diag = (
                f"Claude Code exited with code {result.returncode}.\n"
                f"session_id={effective_session_id} step={step_index}\n"
                f"stderr: {result.stderr[:800]!r}\n"
                f"stdout_preview: {result.stdout[:800]!r}"
            )
            logger.error("claude invoke failed: %s", diag)
            if on_progress is not None:
                on_progress(progress_event(self.adapter_id, "error", "Claude Code exited with an error.", step_index=step_index))
            return AdapterInvocationResult(
                status="error",
                raw_output=result.stdout,
                stderr=result.stderr,
                diagnostic=diag,
                duration_ms=_elapsed_ms(start),
            )
        try:
            if on_progress is not None:
                on_progress(progress_event(
                    self.adapter_id,
                    "parsing_output",
                    (
                        "Claude Code returned output; validating the structured action "
                        f"({len(result.stdout)} stdout chars, {len(result.stderr)} stderr chars)."
                    ),
                    stdout_chars=len(result.stdout),
                    stderr_chars=len(result.stderr),
                    step_index=step_index,
                ))
            action = parse_action_json(result.stdout)
        except Exception as exc:
            diag = (
                f"Claude Code returned invalid action JSON: {exc}\n"
                f"session_id={effective_session_id} step={step_index}\n"
                f"stderr: {result.stderr[:800]!r}\n"
                f"stdout_preview: {result.stdout[:800]!r}"
            )
            logger.error("claude parse failed: %s", diag)
            if on_progress is not None:
                on_progress(progress_event(self.adapter_id, "error", "Claude Code returned invalid action JSON.", step_index=step_index))
            return AdapterInvocationResult(
                status="error",
                raw_output=result.stdout,
                stderr=result.stderr,
                diagnostic=diag,
                duration_ms=_elapsed_ms(start),
            )
        if on_progress is not None:
            on_progress(progress_event(
                self.adapter_id,
                "completed",
                f"Claude Code selected action {action.action.type}.",
                action_type=action.action.type,
                duration_ms=_elapsed_ms(start),
                step_index=step_index,
            ))
        return AdapterInvocationResult(
            status="success",
            action=action,
            raw_output=result.stdout,
            stderr=result.stderr,
            duration_ms=_elapsed_ms(start),
        )
