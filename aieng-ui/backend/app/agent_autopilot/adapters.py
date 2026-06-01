from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .schema import AdapterInvocationResult, AutopilotAgentAction, LocalAgentCapability


DEFAULT_PROBE_TIMEOUT_SECONDS = 3
DEFAULT_STEP_TIMEOUT_SECONDS = 1800


class LocalAgentAdapter(Protocol):
    adapter_id: str
    label: str

    def probe(self, timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS) -> LocalAgentCapability:
        ...

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
        ...


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def resolve_command(command: str) -> str | None:
    return shutil.which(command)


def run_probe_command(command_path: str, args: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [command_path, *args],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def _first_line(text: str) -> str:
    for line in text.splitlines():
        clean = line.strip()
        if clean:
            return clean[:300]
    return ""


def capability_from_missing(adapter_id: str, label: str, command: str, duration_ms: int) -> LocalAgentCapability:
    return LocalAgentCapability(
        adapter_id=adapter_id,
        label=label,
        status="missing",
        command=command,
        diagnostic=f"Command not found on PATH: {command}",
        probe_duration_ms=duration_ms,
    )


def parse_action_json(text: str) -> AutopilotAgentAction:
    stripped = text.strip()
    if not stripped:
        raise ValueError("adapter returned empty output")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if isinstance(payload, dict) and "result" in payload and isinstance(payload["result"], dict):
        payload = payload["result"]
    if isinstance(payload, dict) and isinstance(payload.get("structured_output"), dict):
        payload = payload["structured_output"]
    if isinstance(payload, dict) and isinstance(payload.get("action"), dict):
        action = dict(payload["action"])
        action_type = action.get("type")
        if action_type == "tool_call":
            action_input = action.get("input") if isinstance(action.get("input"), dict) else {}
            if not action_input and isinstance(action.get("input_json"), str):
                try:
                    parsed_input = json.loads(action["input_json"] or "{}")
                    action_input = parsed_input if isinstance(parsed_input, dict) else {}
                except json.JSONDecodeError:
                    action_input = {}
            payload["action"] = {
                "type": "tool_call",
                "tool_name": action.get("tool_name") or "",
                "input": action_input,
            }
        elif action_type == "ask_user":
            payload["action"] = {"type": "ask_user", "question": action.get("question") or ""}
        elif action_type == "final":
            payload["action"] = {"type": "final", "message": action.get("message") or ""}
        elif action_type == "pause":
            payload["action"] = {"type": "pause", "reason": action.get("reason") or ""}
        elif action_type == "chat":
            payload["action"] = {"type": "chat", "message": action.get("message") or ""}
    return AutopilotAgentAction.model_validate(payload)


@dataclass
class FakeLocalAgentAdapter:
    actions: list[AutopilotAgentAction] = field(default_factory=list)

    adapter_id: str = "fake"
    label: str = "Fake local agent"

    def probe(self, timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS) -> LocalAgentCapability:
        return LocalAgentCapability(
            adapter_id=self.adapter_id,
            label=self.label,
            status="available",
            command="fake",
            supports_non_interactive=True,
            supports_json=True,
            supports_json_schema=True,
            supports_tool_disable=True,
            supports_session_continuation=False,
            diagnostic="Deterministic in-process adapter for dry-run tests.",
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
            on_progress({"phase": "started", "adapter_id": self.adapter_id})
        if self.actions:
            action = self.actions.pop(0)
        else:
            action = AutopilotAgentAction.model_validate(
                {
                    "thought_summary": "No more fake actions; finish the dry run.",
                    "action": {
                        "type": "final",
                        "message": "Autopilot dry run completed.",
                    },
                    "done": True,
                    "user_message": "Autopilot dry run completed.",
                }
            )
        if on_progress is not None:
            on_progress({"phase": "completed", "adapter_id": self.adapter_id})
        return AdapterInvocationResult(
            status="success",
            action=action,
            raw_output=action.model_dump_json(),
            duration_ms=_elapsed_ms(start),
        )


def adapter_registry(fake_actions: list[dict[str, Any]] | None = None) -> dict[str, LocalAgentAdapter]:
    from .claude_code_adapter import ClaudeCodeAdapter
    from .codex_cli_adapter import CodexCliAdapter

    parsed_fake_actions = [
        AutopilotAgentAction.model_validate(item)
        for item in (fake_actions or [])
    ]
    return {
        "fake": FakeLocalAgentAdapter(parsed_fake_actions),
        "claude-code": ClaudeCodeAdapter(),
        "codex-cli": CodexCliAdapter(),
    }


def probe_local_agent_capabilities() -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    for adapter_id, adapter in adapter_registry().items():
        if adapter_id == "fake":
            continue
        try:
            probes.append(adapter.probe().model_dump())
        except Exception as exc:
            probes.append(
                LocalAgentCapability(
                    adapter_id=adapter_id,
                    label=getattr(adapter, "label", adapter_id),
                    status="error",
                    command=os.environ.get("AIENG_LOCAL_AGENT_COMMAND", adapter_id),
                    diagnostic=f"Capability probe failed: {exc}",
                ).model_dump()
            )
    return probes


__all__ = [
    "DEFAULT_PROBE_TIMEOUT_SECONDS",
    "DEFAULT_STEP_TIMEOUT_SECONDS",
    "FakeLocalAgentAdapter",
    "LocalAgentAdapter",
    "adapter_registry",
    "capability_from_missing",
    "parse_action_json",
    "probe_local_agent_capabilities",
    "resolve_command",
    "run_probe_command",
    "_elapsed_ms",
    "_first_line",
]
