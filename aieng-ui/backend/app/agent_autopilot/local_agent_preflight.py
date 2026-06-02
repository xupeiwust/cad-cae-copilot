from __future__ import annotations

import os
import platform
import time
from typing import Any

from .adapters import LocalAgentAdapter, adapter_registry, resolve_command
from .schema import LocalAgentCapability


def _env_name_summary(prefixes: tuple[str, ...]) -> dict[str, list[str]]:
    return {
        f"{prefix.rstrip('_')}_env_names": sorted(
            name for name in os.environ if name.startswith(prefix)
        )
        for prefix in prefixes
    }


def _diagnostic_env(command_path: str | None) -> dict[str, Any]:
    path_entries = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
    command_dir = os.path.dirname(os.path.abspath(command_path)) if command_path else ""
    return {
        "USERPROFILE_present": bool(os.environ.get("USERPROFILE")),
        "APPDATA_present": bool(os.environ.get("APPDATA")),
        "LOCALAPPDATA_present": bool(os.environ.get("LOCALAPPDATA")),
        "HOME_present": bool(os.environ.get("HOME")),
        "PATH_entry_count": len(path_entries),
        "command_dir_in_PATH": bool(command_dir) and any(
            os.path.normcase(os.path.abspath(entry)) == os.path.normcase(command_dir)
            for entry in path_entries
        ),
        **_env_name_summary(("ANTHROPIC_", "CLAUDE_", "OPENAI_", "CODEX_")),
    }


def classify_local_agent_status(capability: LocalAgentCapability, *, preflight: dict[str, Any] | None = None) -> str:
    text = " ".join(
        str(part or "")
        for part in (
            capability.status,
            capability.diagnostic,
            preflight.get("error") if preflight else "",
            preflight.get("stderr") if preflight else "",
            preflight.get("stdout") if preflight else "",
            preflight.get("stdout_parsed_result") if preflight else "",
        )
    ).lower()
    if capability.status == "missing" or "command not found" in text:
        return "missing_binary"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "not logged in" in text or "/login" in text or "auth" in text:
        return "auth_error"
    if "no conversation found with session id" in text or "session not found" in text:
        return "session_not_found"
    if "required non-interactive json flags" in text or "unsupported" in text or "unknown option" in text:
        return "unsupported_flag"
    if capability.status == "available" and (preflight is None or preflight.get("ok", True)):
        return "ready"
    if capability.status == "blocked":
        return "unsupported_flag"
    return "unknown_error"


def actionable_fix(status: str, adapter_id: str) -> str | None:
    if status == "ready":
        return None
    if status == "missing_binary":
        command = "Claude Code" if adapter_id == "claude-code" else "Codex CLI"
        executable = "claude" if adapter_id == "claude-code" else "codex"
        return f"Install {command} and ensure {executable} is on PATH."
    if status == "auth_error":
        return "Authenticate the local CLI in the same shell/user environment used to start the backend."
    if status == "timeout":
        return "Increase the preflight timeout or verify the CLI is not waiting for interactive input."
    if status == "session_not_found":
        return "Start a new run or resume with the same backend/adapter session id; the CLI conversation was not found."
    if status == "unsupported_flag":
        return "Upgrade the local CLI or disable incompatible adapter flags."
    return "Inspect adapter diagnostics and rerun the preflight from the backend environment."


def _features(capability: LocalAgentCapability) -> dict[str, bool]:
    return {
        "json_output": bool(capability.supports_json),
        "schema_output": bool(capability.supports_json_schema),
        "session_resume": bool(capability.supports_session_continuation),
        "tool_disable": bool(capability.supports_tool_disable),
        "non_interactive": bool(capability.supports_non_interactive),
    }


def _claude_plain_preflight(adapter: LocalAgentAdapter) -> dict[str, Any] | None:
    if getattr(adapter, "adapter_id", "") != "claude-code":
        return None
    try:
        from .claude_code_adapter import run_claude_preflight

        return run_claude_preflight(command=getattr(adapter, "command", None))
    except Exception as exc:  # pragma: no cover - defensive diagnostics only
        return {"ok": False, "error": str(exc)}


def _safe_preflight_payload(preflight: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remove environment values from the embedded plain-CLI preflight result.

    ``run_claude_preflight`` is also used in failure diagnostics where detailed
    USERPROFILE/PATH values were intentionally requested.  The public
    /api/local-agents/preflight contract is stricter: expose env variable names
    and presence/count metadata, not env values.
    """
    if preflight is None:
        return None
    safe = dict(preflight)
    env = safe.get("env_summary")
    if isinstance(env, dict):
        path_entries = env.get("PATH_first_entries")
        safe["env_summary"] = {
            "USERPROFILE_present": bool(env.get("USERPROFILE")),
            "APPDATA_present": bool(env.get("APPDATA")),
            "LOCALAPPDATA_present": bool(env.get("LOCALAPPDATA")),
            "HOME_present": bool(env.get("HOME")),
            "PATH_entry_count": len(path_entries) if isinstance(path_entries, list) else None,
            "claude_dir_in_PATH": bool(env.get("claude_dir_in_PATH")),
            "ANTHROPIC_env_names": list(env.get("ANTHROPIC_env_names") or []),
            "CLAUDE_env_names": list(env.get("CLAUDE_env_names") or []),
        }
    return safe


def local_agent_preflight(
    *,
    adapter: str | None = None,
    adapters: dict[str, LocalAgentAdapter] | None = None,
) -> dict[str, Any]:
    registry = adapters or adapter_registry()
    selected = {
        adapter_id: instance
        for adapter_id, instance in registry.items()
        if adapter is None or adapter_id == adapter
    }
    items: list[dict[str, Any]] = []
    started = time.perf_counter()
    for adapter_id, instance in selected.items():
        item_start = time.perf_counter()
        capability = instance.probe()
        plain_preflight = _claude_plain_preflight(instance)
        safe_plain_preflight = _safe_preflight_payload(plain_preflight)
        status = classify_local_agent_status(capability, preflight=plain_preflight)
        command_path = capability.command_path or resolve_command(capability.command)
        items.append({
            "adapter_id": capability.adapter_id,
            "label": capability.label,
            "available": status == "ready",
            "status": status,
            "version": capability.version,
            "features": _features(capability),
            "diagnostic": {
                "resolved_path": command_path,
                "cwd": os.getcwd(),
                "platform": platform.platform(),
                "env_summary": _diagnostic_env(command_path),
                "capability": capability.model_dump(),
                **({"plain_cli_preflight": safe_plain_preflight} if safe_plain_preflight is not None else {}),
            },
            "actionable_fix": actionable_fix(status, capability.adapter_id),
            "duration_ms": int((time.perf_counter() - item_start) * 1000),
        })
    return {
        "adapters": items,
        "available": [item for item in items if item["available"]],
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
