"""Headless MCP approval via client elicitation (#228).

The workbench's *managed* approval mode routes gated mutations through the
backend broker, which assumes a running web viewer to answer the prompt. A
headless CLI / IDE agent (no viewer) would otherwise stall in a poll loop with
nothing able to respond.

This module provides the **elicitation** approval path: the MCP server asks the
*connecting client* to prompt the human (MCP `elicitation/create`). When the
client supports elicitation, the user approves/declines in their own agent UI;
when it does not, there is no surface and the gated tool is **denied** (documented
fail-safe — the mutation never runs silently).

The decision logic here is pure and side-effect-free so it is fully unit-testable
without a live MCP client; ``mcp_server`` supplies the real ``ctx.elicit`` call.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Opt-in per connection. Set by the CLI ``--approval-mode elicit`` or directly.
ELICIT_APPROVAL_MODE_ENV = "AIENG_MCP_APPROVAL_MODE"
ELICIT_APPROVAL_MODE_VALUE = "elicit"


class ApprovalConfirmation(BaseModel):
    """Schema the connecting client renders for an approval prompt.

    MCP elicitation requires a flat schema of primitive fields. ``approve`` is the
    explicit decision; ``note`` is an optional free-text reason the user may add.
    """

    approve: bool = Field(
        default=False,
        description="Approve this gated workbench mutation? Decline to cancel — the tool will not run.",
    )
    note: str = Field(default="", description="Optional reason or note for the audit trail.")


def elicit_approval_message(tool_name: str, tool_input: Any) -> str:
    """Human-facing prompt text for a gated tool's approval request."""
    project_id = tool_input.get("project_id") if isinstance(tool_input, dict) else None
    target = f" on project '{project_id}'" if project_id else ""
    return (
        f"Approve gated workbench tool '{tool_name}'{target}?\n\n"
        "This performs a side-effecting action (CAD/CAE mutation or solver run). "
        "Decline to cancel — the tool will not be executed."
    )


def decision_from_elicitation(action: str, data: Any) -> dict[str, Any]:
    """Map an MCP ``ElicitationResult`` (action + validated data) to the permission contract.

    Returns the Claude permission-contract dict the handler expects:
        {"behavior": "allow"} | {"behavior": "deny", "message": ..., "recoverable": True}

    Honesty: only an explicit ``accept`` with ``approve=true`` allows the tool.
    ``decline`` / ``cancel`` — and an ``accept`` whose form value is ``approve=false`` —
    all deny. The denial is ``recoverable`` (the agent may re-request).
    """
    if action == "accept":
        approved = True
        if data is not None:
            approved = bool(getattr(data, "approve", True))
        if approved:
            return {"behavior": "allow"}
        return {
            "behavior": "deny",
            "message": "User declined the approval prompt (approve=false). The tool was NOT executed.",
            "recoverable": True,
        }
    return {
        "behavior": "deny",
        "message": (
            f"Approval not granted (the user {action}ed the prompt). The tool was NOT executed. "
            "Re-run the tool to request approval again."
        ),
        "recoverable": True,
    }


def no_surface_deny(tool_name: str) -> dict[str, Any]:
    """Fail-safe denial when the connected client cannot show an approval prompt.

    Returned when the client does not advertise the MCP *elicitation* capability,
    so there is no surface to answer the request. The gate is never bypassed.
    """
    return {
        "behavior": "deny",
        "code": "approval_surface_unavailable",
        "message": (
            f"'{tool_name}' requires approval, but the connected MCP client does not support "
            "elicitation — there is no surface to prompt for approval, so the request cannot be "
            "answered. The tool was NOT executed. Use a client that supports MCP elicitation, or "
            "run the server with --approval-mode managed (workbench viewer) or --approval-mode block."
        ),
        "recoverable": True,
    }
