"""Tests for the headless elicitation-approval decision logic (#228)."""

from app.mcp_approval import (
    ApprovalConfirmation,
    decision_from_elicitation,
    elicit_approval_message,
    no_surface_deny,
)


def test_accept_with_approve_true_allows() -> None:
    decision = decision_from_elicitation("accept", ApprovalConfirmation(approve=True))
    assert decision["behavior"] == "allow"


def test_accept_with_approve_false_denies() -> None:
    decision = decision_from_elicitation("accept", ApprovalConfirmation(approve=False))
    assert decision["behavior"] == "deny"
    assert decision["recoverable"] is True


def test_decline_denies() -> None:
    decision = decision_from_elicitation("decline", None)
    assert decision["behavior"] == "deny"
    assert "NOT executed" in decision["message"]
    assert decision["recoverable"] is True


def test_cancel_denies() -> None:
    decision = decision_from_elicitation("cancel", None)
    assert decision["behavior"] == "deny"


def test_accept_without_data_defaults_to_allow() -> None:
    # If a client returns accept with no structured data, treat the explicit
    # accept action as approval.
    decision = decision_from_elicitation("accept", None)
    assert decision["behavior"] == "allow"


def test_no_surface_is_fail_safe_deny() -> None:
    decision = no_surface_deny("cae.run_solver")
    assert decision["behavior"] == "deny"
    assert decision["code"] == "approval_surface_unavailable"
    assert "cae.run_solver" in decision["message"]
    assert decision["recoverable"] is True


def test_message_names_tool_and_project() -> None:
    msg = elicit_approval_message("cad.execute_build123d", {"project_id": "bracket_01"})
    assert "cad.execute_build123d" in msg
    assert "bracket_01" in msg
    # no project_id is tolerated
    assert "cae.run_solver" in elicit_approval_message("cae.run_solver", {})
