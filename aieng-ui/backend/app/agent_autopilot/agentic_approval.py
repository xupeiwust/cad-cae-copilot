"""Phase 2 of the VSCode-parity agentic web-chat path (Approach A).

The agentic session (``claude_agent_session.py``) lets Claude drive the workbench
MCP tools directly. Gated mutations (``cad.execute_build123d``, ``cae.run_solver``,
…) must still pause for UI approval — the agentic path must NEVER bypass approval.

Mechanism: Claude Code is launched with ``--permission-prompt-tool
mcp__aieng-workbench__request_approval``. When Claude wants to run a gated tool it
calls that MCP tool instead of running it; the MCP tool bridges to the backend,
which classifies the tool, emits an ``approval_requested`` event into the run
transcript (so the existing approval card renders), and blocks until the user
approves/denies via the UI. The decision is returned to Claude in the
permission-prompt-tool result contract::

    {"behavior": "allow", "updatedInput": {...}}
    {"behavior": "deny",  "message": "..."}

This module is pure + process-local and unit-testable without a live agent:
- name normalization (``mcp__server__cad_execute_build123d`` → ``cad.execute_build123d``)
- gated classification against the runtime registry's ``requires_approval`` flag
- the permission-prompt-tool result formatter
- :class:`PermissionBroker`, the thread-safe rendezvous the endpoints poll/resolve.

Design doc: ``aieng-ui/docs/web-chat-agentic-parity-plan.md``.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

WORKBENCH_MCP_PREFIX = "mcp__aieng-workbench__"
GENERIC_MCP_PREFIX = "mcp__"


def strip_mcp_prefix(name: str) -> str:
    """Reduce a permission-prompt tool_name to the bare workbench tool name.

    Claude may pass ``mcp__aieng-workbench__cad_execute_build123d`` (fully
    qualified) or a bare ``cad_execute_build123d``. We normalize to the bare,
    server-local name (still underscore form).
    """
    n = name.strip()
    if n.startswith(WORKBENCH_MCP_PREFIX):
        return n[len(WORKBENCH_MCP_PREFIX):]
    if n.startswith(GENERIC_MCP_PREFIX):
        # mcp__<server>__<tool>
        rest = n[len(GENERIC_MCP_PREFIX):]
        parts = rest.split("__", 1)
        return parts[1] if len(parts) == 2 else rest
    return n


def build_approval_name_set(tool_defs: Iterable[dict[str, Any]]) -> set[str]:
    """Set of gated tool names in BOTH dotted and underscore forms.

    Single source of truth = the registry's ``requires_approval`` flag
    (``runtime.list_tools_for_mcp()``), so a newly-gated tool is covered
    automatically. We index both ``cad.execute_build123d`` and
    ``cad_execute_build123d`` since callers may present either.
    """
    gated: set[str] = set()
    for td in tool_defs:
        if not td.get("requires_approval"):
            continue
        name = str(td.get("name") or "")
        if not name:
            continue
        gated.add(name)
        gated.add(name.replace(".", "_"))
    return gated


def requires_approval(tool_name: str, approval_names: set[str]) -> bool:
    """True if the (possibly mcp-qualified) tool requires UI approval.

    ``approval_names`` already contains both dotted and underscore forms
    (see :func:`build_approval_name_set`), so a single membership test covers
    whichever form Claude presented — avoiding an ambiguous underscore→dot
    reversal for multi-underscore tool names.
    """
    return strip_mcp_prefix(tool_name) in approval_names


def resolve_registry_name(tool_name: str, tool_defs: Iterable[dict[str, Any]]) -> str:
    """Map a (possibly mcp-qualified / underscore) tool name to its dotted
    registry name for display/audit. Falls back to the bare name."""
    bare = strip_mcp_prefix(tool_name)
    for td in tool_defs:
        name = str(td.get("name") or "")
        if name == bare or name.replace(".", "_") == bare:
            return name
    return bare


def format_decision(*, allowed: bool, tool_input: dict[str, Any] | None = None, message: str | None = None) -> dict[str, Any]:
    """Permission-prompt-tool result contract consumed by Claude Code."""
    if allowed:
        return {"behavior": "allow", "updatedInput": dict(tool_input or {})}
    return {"behavior": "deny", "message": message or "Denied by the user in the workbench UI."}


@dataclass
class _PendingPermission:
    permission_id: str
    run_id: str | None
    tool_name: str
    tool_input: dict[str, Any]
    created_at: float
    status: str = "pending"  # pending | allowed | denied
    message: str | None = None
    updated_input: dict[str, Any] | None = None
    # Set when resolved, so a long-poll GET can return immediately instead of the
    # caller hammering the endpoint every ~1.5s.
    resolved_event: threading.Event = field(default_factory=threading.Event)


class PermissionBroker:
    """Process-local rendezvous between the MCP permission tool and the UI.

    Lives in the backend process (the MCP server polls it over HTTP). Thread-safe.
    Intentionally simple: a workbench is effectively single-user; entries are
    short-lived and dropped once resolved+observed (or on TTL sweep).
    """

    def __init__(self, ttl_seconds: float = 1800.0) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, _PendingPermission] = {}
        self._ttl = ttl_seconds

    def create(self, *, run_id: str | None, tool_name: str, tool_input: dict[str, Any]) -> _PendingPermission:
        self._sweep()
        pid = uuid.uuid4().hex[:16]
        entry = _PendingPermission(
            permission_id=pid,
            run_id=run_id,
            tool_name=tool_name,
            tool_input=dict(tool_input or {}),
            created_at=time.time(),
        )
        with self._lock:
            self._pending[pid] = entry
        return entry

    def get(self, permission_id: str) -> _PendingPermission | None:
        with self._lock:
            return self._pending.get(permission_id)

    def wait(self, permission_id: str, timeout: float) -> _PendingPermission | None:
        """Block until the entry is resolved or ``timeout`` elapses (long-poll).

        Returns the entry regardless of whether it resolved in time (caller reads
        ``.status``). Returns None for an unknown id.
        """
        entry = self.get(permission_id)
        if entry is None:
            return None
        if entry.status == "pending" and timeout > 0:
            entry.resolved_event.wait(timeout=timeout)
        return self.get(permission_id)

    def resolve(
        self,
        permission_id: str,
        *,
        approved: bool,
        message: str | None = None,
        updated_input: dict[str, Any] | None = None,
    ) -> _PendingPermission | None:
        with self._lock:
            entry = self._pending.get(permission_id)
            if entry is None:
                return None
            entry.status = "allowed" if approved else "denied"
            entry.message = message
            entry.updated_input = updated_input
        entry.resolved_event.set()
        return entry

    def decision_for(self, entry: _PendingPermission) -> dict[str, Any]:
        if entry.status == "allowed":
            return format_decision(allowed=True, tool_input=entry.updated_input or entry.tool_input)
        return format_decision(allowed=False, message=entry.message)

    def _sweep(self) -> None:
        cutoff = time.time() - self._ttl
        with self._lock:
            stale = [pid for pid, e in self._pending.items() if e.created_at < cutoff]
            for pid in stale:
                self._pending.pop(pid, None)


__all__ = [
    "WORKBENCH_MCP_PREFIX",
    "PermissionBroker",
    "build_approval_name_set",
    "requires_approval",
    "resolve_registry_name",
    "strip_mcp_prefix",
    "format_decision",
]
