"""Phase 1 of the VSCode-parity agentic web-chat path (Approach A).

This module spawns a *real* agentic Claude Code session (stream-json mode) scoped
to the repository root, with the workbench MCP server attached, so the model is
the orchestrator — exactly like the VSCode Claude Code chat. It is deliberately
ADDITIVE: the existing single-action engine path (``llm-api`` / ``claude-code`` /
``codex-cli``) is untouched. Selection happens upstream via
``adapter_id == "claude-agent"`` (Phase 3).

Design doc: ``aieng-ui/docs/web-chat-agentic-parity-plan.md``.

The two core pieces are pure and unit-testable without a live nested agent:
- :func:`build_agent_command` constructs the ``claude`` argv.
- :func:`translate_stream_event` maps one Claude stream-json event to zero or more
  events in our existing ``_publish_agent_event`` contract
  (see ``event_contract.py``).

:class:`ClaudeAgentSession` is the thin subprocess driver around them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .claude_code_adapter import (
    _build_claude_env,
    _resolve_claude_exe,
    _windows_subprocess_kwargs,
)

# A full agentic session may legitimately run for minutes (multi-step modeling
# with thinking). Keep a generous but bounded ceiling; configurable via env.
DEFAULT_AGENT_SESSION_TIMEOUT_SECONDS = 900

# The MCP server name as registered in the repo .mcp.json. The permission-prompt
# tool (Phase 2) is addressed as mcp__<server>__<tool>.
WORKBENCH_MCP_SERVER = "aieng-workbench"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def repo_root() -> Path:
    """Absolute path to the repository root (where AGENTS.md / CLAUDE.md / .mcp.json live).

    Running the session with this as cwd is what makes the agent auto-load the
    root docs and the workspace ``.claude`` skills — the capability the UI chat
    currently lacks. Overridable via ``AIENG_AGENT_REPO_ROOT`` for non-standard
    layouts / tests.
    """
    override = os.environ.get("AIENG_AGENT_REPO_ROOT")
    if override:
        return Path(override).resolve()
    # claude_agent_session.py -> agent_autopilot -> app -> backend -> aieng-ui -> <repo root>
    return Path(__file__).resolve().parents[4]


def _mcp_config_path(root: Path) -> str | None:
    candidate = root / ".mcp.json"
    return str(candidate) if candidate.exists() else None


def build_run_mcp_config(
    base_config: dict[str, Any],
    *,
    run_id: str,
    project_id: str | None,
    session_id: str | None,
    backend_url: str | None,
    server_name: str = WORKBENCH_MCP_SERVER,
) -> dict[str, Any]:
    """Augment the repo ``.mcp.json`` with per-run env so the workbench MCP server
    spawned by this session knows which run it serves and exposes the approval
    bridge tool.

    Pure: deep-copies ``base_config`` and merges env on the workbench server entry.
    The injected env is what lets the ``request_approval`` permission tool attach
    approvals to the correct run (``AIENG_AUTOPILOT_RUN_ID``) and be registered
    at all (``AIENG_AGENTIC_PERMISSION_TOOL=1``).
    """
    config = json.loads(json.dumps(base_config or {}))  # cheap deep copy
    servers = config.setdefault("mcpServers", {})
    server = servers.get(server_name)
    if not isinstance(server, dict):
        server = {}
        servers[server_name] = server
    env = server.setdefault("env", {})
    if backend_url:
        env["AIENG_BACKEND_URL"] = backend_url
    env["AIENG_AGENTIC_PERMISSION_TOOL"] = "1"
    env["AIENG_AUTOPILOT_RUN_ID"] = run_id
    if project_id:
        env["AIENG_AUTOPILOT_PROJECT_ID"] = project_id
    if session_id:
        env["AIENG_AUTOPILOT_SESSION_ID"] = session_id
    return config


def _load_base_mcp_config(root: Path) -> dict[str, Any]:
    path = root / ".mcp.json"
    if not path.exists():
        return {"mcpServers": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"mcpServers": {}}


def build_agent_command(
    *,
    command_path: str,
    prompt: str,
    session_id: str,
    resume: bool,
    root: Path,
    mcp_config: str | None,
    permission_prompt_tool: str | None,
    model: str | None = None,
    extra_dirs: list[str] | None = None,
) -> list[str]:
    """Build the argv for a stream-json agentic ``claude`` session.

    Key differences from the legacy single-action adapter
    (``claude_code_adapter.ClaudeCodeAdapter``):
    - ``--output-format stream-json`` (+ ``--verbose``) instead of
      ``--json-schema`` — Claude runs its own multi-step loop with thinking.
    - ``--mcp-config`` attaches the workbench tools so ``cad.*/cae.*/aieng.*`` are
      callable directly by the model.
    - **No** crippling ``--tools`` allowlist — ``Skill`` / ``Task`` / MCP tools are
      available (cwd = repo root supplies docs + skills).
    - ``--permission-prompt-tool`` routes gated mutations through the backend
      approval bridge (Phase 2) instead of auto-running them.

    The ``prompt`` is passed on argv via ``-p``; callers that need very large
    prompts should prefer stdin in the session driver.
    """
    cmd: list[str] = [
        command_path,
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    # Session continuity across approval / follow-up turns.
    if resume:
        cmd += ["--resume", session_id]
    else:
        cmd += ["--session-id", session_id]
    if mcp_config:
        # Use ONLY our per-run MCP config (which carries the run-scoped approval
        # env). --strict-mcp-config prevents Claude from also loading the user's
        # global `aieng-workbench` server, which would NOT have the run-scoped
        # approval env and could let gated mutations bypass our approval gate.
        cmd += ["--mcp-config", mcp_config, "--strict-mcp-config"]
    # NOTE: approval is enforced server-side in the workbench MCP tool handler
    # (settings-independent), not via --permission-prompt-tool — a user's Claude
    # allow-list would otherwise skip the prompt for already-allowed tools.
    # `permission_prompt_tool` is accepted for API compatibility but unused.
    _ = permission_prompt_tool
    if model:
        cmd += ["--model", model]
    # Repo root is cwd (set by the driver); add any extra reachable dirs.
    for extra in extra_dirs or []:
        cmd += ["--add-dir", extra]
    return cmd


def permission_prompt_tool_name(server: str = WORKBENCH_MCP_SERVER, tool: str = "request_approval") -> str:
    return f"mcp__{server}__{tool}"


def _content_blocks(message: Any) -> list[dict[str, Any]]:
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def _stringify_tool_result(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif block.get("type") == "image":
                    parts.append("[image]")
                else:
                    parts.append(json.dumps(block, ensure_ascii=False))
            else:
                parts.append(str(block))
        return "\n".join(p for p in parts if p)
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False)


def translate_stream_event(
    raw: dict[str, Any],
    *,
    run_id: str,
    project_id: str | None,
    session_id: str | None,
) -> list[dict[str, Any]]:
    """Map one Claude stream-json event to event-contract events.

    Returns a (possibly empty) list of dicts shaped for ``_publish_agent_event``.
    Pure: no side effects, safe to unit-test against captured fixtures.
    """
    base = {
        "run_id": run_id,
        "project_id": project_id,
        "session_id": session_id,
    }
    etype = str(raw.get("type") or "")
    out: list[dict[str, Any]] = []

    def _eid(suffix: str) -> str:
        return f"{run_id}-{suffix}-{uuid.uuid4().hex[:8]}"

    if etype == "system" and raw.get("subtype") == "init":
        tools = raw.get("tools") if isinstance(raw.get("tools"), list) else []
        mcp_servers = raw.get("mcp_servers") if isinstance(raw.get("mcp_servers"), list) else []
        out.append({
            **base,
            "event_id": _eid("agent-init"),
            "type": "agent_phase_changed",
            "content": "Agentic session initialized.",
            "payload": {
                "phase": "session_initialized",
                "adapter_id": "claude-agent",
                "model": raw.get("model"),
                "tool_count": len(tools),
                "mcp_servers": mcp_servers,
            },
        })
        return out

    if etype == "assistant":
        for block in _content_blocks(raw.get("message")):
            btype = block.get("type")
            if btype == "text":
                text = str(block.get("text") or "").strip()
                if text:
                    out.append({
                        **base,
                        "event_id": _eid("assistant-text"),
                        "type": "agent_message",
                        "content": text,
                        "payload": {"kind": "assistant_text", "adapter_id": "claude-agent"},
                    })
            elif btype == "thinking":
                thinking = str(block.get("thinking") or "").strip()
                if thinking:
                    out.append({
                        **base,
                        "event_id": _eid("assistant-thinking"),
                        "type": "agent_message",
                        "content": thinking,
                        "payload": {"kind": "thought_summary", "adapter_id": "claude-agent"},
                    })
            elif btype == "tool_use":
                out.append({
                    **base,
                    "event_id": _eid("tool-started"),
                    "type": "tool_started",
                    "content": f"Calling {block.get('name')}",
                    "payload": {
                        "tool_name": block.get("name"),
                        "tool_use_id": block.get("id"),
                        "input": block.get("input") if isinstance(block.get("input"), dict) else {},
                        "adapter_id": "claude-agent",
                    },
                })
        return out

    if etype == "user":
        for block in _content_blocks(raw.get("message")):
            if block.get("type") != "tool_result":
                continue
            is_error = bool(block.get("is_error"))
            result_text = _stringify_tool_result(block.get("content"))
            out.append({
                **base,
                "event_id": _eid("tool-result"),
                "type": "tool_failed" if is_error else "tool_completed",
                "status": "error" if is_error else "success",
                "content": result_text[:2000],
                "payload": {
                    "tool_use_id": block.get("tool_use_id"),
                    "is_error": is_error,
                    "adapter_id": "claude-agent",
                },
            })
        return out

    if etype == "result":
        is_error = bool(raw.get("is_error"))
        subtype = str(raw.get("subtype") or "")
        final_text = str(raw.get("result") or "").strip()
        status = "failed" if is_error else "completed"
        out.append({
            **base,
            "event_id": _eid("result"),
            "type": "run_status_changed",
            "status": status,
            "content": final_text or (f"Session ended ({subtype})." if subtype else "Session ended."),
            "payload": {
                "adapter_id": "claude-agent",
                "subtype": subtype,
                "num_turns": raw.get("num_turns"),
                "usage": raw.get("usage"),
                "total_cost_usd": raw.get("total_cost_usd"),
                "duration_ms": raw.get("duration_ms"),
            },
        })
        return out

    return out


@dataclass
class ClaudeAgentSession:
    """Thin subprocess driver for a stream-json agentic claude session.

    ``on_event`` receives event-contract dicts (already translated). The driver
    enforces a wall-clock timeout and Windows-safe process termination, mirroring
    the legacy adapter's hardening.
    """

    command: str | None = None
    model: str | None = None
    backend_url: str | None = None
    timeout_seconds: int = field(default_factory=lambda: _env_int(
        "AIENG_CLAUDE_AGENT_TIMEOUT_SECONDS", DEFAULT_AGENT_SESSION_TIMEOUT_SECONDS
    ))

    def __post_init__(self) -> None:
        self.command = self.command or os.environ.get("AIENG_CLAUDE_CODE_COMMAND", "claude")
        self.backend_url = self.backend_url or os.environ.get("AIENG_BACKEND_URL") or None

    def run(
        self,
        *,
        prompt: str,
        run_id: str,
        project_id: str | None,
        session_id: str | None,
        claude_session_id: str,
        resume: bool = False,
        on_event: Callable[[dict[str, Any]], None],
        on_spawn: Callable[[subprocess.Popen[str]], None] | None = None,
    ) -> dict[str, Any]:
        """Spawn the session, stream events, and return a small summary dict.

        ``session_id`` is the **chat** session (used to tag emitted events so the
        UI associates them with the visible transcript, and injected into the MCP
        server env so approvals attach to the right session). ``claude_session_id``
        is a distinct **UUID** for the Claude CLI ``--session-id`` / ``--resume``
        (the chat session id is not a valid UUID). Conflating the two tags every
        event with the wrong session and the UI drops them.

        Writes a per-run MCP config (so the workbench MCP server enforces the
        run-scoped approval gate for gated mutations) and streams events. Emits a
        terminal ``run_status_changed`` even on spawn/timeout failure so the
        transcript never hangs in an active state.
        """
        root = repo_root()
        command_path = _resolve_claude_exe(self.command or "claude")
        if not command_path:
            on_event({
                "run_id": run_id, "project_id": project_id, "session_id": session_id,
                "event_id": f"{run_id}-agent-missing",
                "type": "run_status_changed", "status": "failed",
                "content": f"Claude command not found on PATH: {self.command}",
                "payload": {"adapter_id": "claude-agent"},
            })
            return {"status": "failed", "reason": "command_not_found"}

        # Per-run MCP config: workbench tools + the run-scoped approval bridge.
        run_config = build_run_mcp_config(
            _load_base_mcp_config(root),
            run_id=run_id,
            project_id=project_id,
            session_id=session_id,
            backend_url=self.backend_url,
        )
        config_dir = Path(tempfile.mkdtemp(prefix=f"aieng-agent-{run_id}-"))
        config_path = config_dir / "mcp.json"
        config_path.write_text(json.dumps(run_config), encoding="utf-8")

        cmd = build_agent_command(
            command_path=command_path,
            prompt=prompt,
            session_id=claude_session_id,  # CLI requires a UUID, distinct from chat session
            resume=resume,
            root=root,
            mcp_config=str(config_path),
            permission_prompt_tool=None,
            model=self.model,
        )
        env = _build_claude_env()
        start = time.perf_counter()
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(root),
            **_windows_subprocess_kwargs(),
        )
        if on_spawn is not None:
            try:
                on_spawn(proc)
            except Exception:  # pragma: no cover - registration must not break the run
                pass
        terminal_seen = False
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                if (time.perf_counter() - start) > self.timeout_seconds:
                    self._kill(proc)
                    break
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(raw, dict):
                    continue
                for event in translate_stream_event(
                    raw, run_id=run_id, project_id=project_id, session_id=session_id
                ):
                    if event.get("type") == "run_status_changed":
                        terminal_seen = True
                    on_event(event)
            proc.wait(timeout=10)
        except Exception as exc:  # pragma: no cover - defensive
            self._kill(proc)
            on_event({
                "run_id": run_id, "project_id": project_id, "session_id": session_id,
                "event_id": f"{run_id}-agent-error",
                "type": "run_status_changed", "status": "failed",
                "content": f"Agentic session error: {exc}",
                "payload": {"adapter_id": "claude-agent"},
            })
            return {"status": "failed", "reason": str(exc)}
        finally:
            shutil.rmtree(config_dir, ignore_errors=True)

        if not terminal_seen:
            stderr = (proc.stderr.read() if proc.stderr else "") or ""
            on_event({
                "run_id": run_id, "project_id": project_id, "session_id": session_id,
                "event_id": f"{run_id}-agent-noterminal",
                "type": "run_status_changed", "status": "failed",
                "content": "Agentic session ended without a final result.",
                "payload": {"adapter_id": "claude-agent", "stderr": stderr[:800], "rc": proc.returncode},
            })
            return {"status": "failed", "reason": "no_terminal_event"}
        return {"status": "completed"}

    @staticmethod
    def _kill(proc: subprocess.Popen[str]) -> None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True, text=True, check=False,
                )
            else:
                proc.kill()
        except Exception:  # pragma: no cover - best effort
            pass


__all__ = [
    "DEFAULT_AGENT_SESSION_TIMEOUT_SECONDS",
    "WORKBENCH_MCP_SERVER",
    "ClaudeAgentSession",
    "build_agent_command",
    "translate_stream_event",
    "permission_prompt_tool_name",
    "repo_root",
]
