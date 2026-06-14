"""Backend wiring tests for headless elicitation approval (#228).

Exercise the decision function with a fake MCP context (no live client needed):
a client that supports elicitation can receive + resolve the request; a client
that cannot is denied (documented fail-safe).
"""

import asyncio

import app.mcp_server as mcp_server
from app import mcp_approval


class _FakeSession:
    def __init__(self, supports: bool) -> None:
        self._supports = supports

    def check_client_capability(self, _cap) -> bool:
        return self._supports


class _FakeRequestContext:
    def __init__(self, session) -> None:
        self.session = session


class _FakeResult:
    def __init__(self, action, data=None) -> None:
        self.action = action
        self.data = data


class _FakeContext:
    """Minimal stand-in for mcp Context: capability check + async elicit."""

    def __init__(self, *, supports: bool, action: str = "accept", approve: bool = True) -> None:
        self.request_context = _FakeRequestContext(_FakeSession(supports))
        self._action = action
        self._approve = approve
        self.elicited = False

    async def elicit(self, *, message: str, schema):  # noqa: ARG002
        self.elicited = True
        return _FakeResult(self._action, mcp_approval.ApprovalConfirmation(approve=self._approve))


def _run(coro):
    return asyncio.run(coro)


def test_headless_client_can_resolve_approval_allow() -> None:
    ctx = _FakeContext(supports=True, action="accept", approve=True)
    decision = _run(mcp_server._elicit_permission_decision("cae.run_solver", {"project_id": "p"}, ctx=ctx))
    assert ctx.elicited is True
    assert decision["behavior"] == "allow"


def test_headless_client_can_resolve_approval_decline() -> None:
    ctx = _FakeContext(supports=True, action="decline")
    decision = _run(mcp_server._elicit_permission_decision("cae.run_solver", {"project_id": "p"}, ctx=ctx))
    assert decision["behavior"] == "deny"
    assert decision["recoverable"] is True


def test_no_elicitation_surface_fails_safe_deny() -> None:
    ctx = _FakeContext(supports=False)
    decision = _run(mcp_server._elicit_permission_decision("cae.run_solver", {"project_id": "p"}, ctx=ctx))
    assert ctx.elicited is False  # never even prompted
    assert decision["behavior"] == "deny"
    assert decision["code"] == "approval_surface_unavailable"


def test_no_context_fails_safe_deny() -> None:
    decision = _run(mcp_server._elicit_permission_decision("cae.run_solver", {}, ctx=None))
    assert decision["behavior"] == "deny"
    assert decision["code"] == "approval_surface_unavailable"


def test_elicit_prompt_exception_denies(monkeypatch) -> None:
    class _BoomContext(_FakeContext):
        async def elicit(self, *, message: str, schema):  # noqa: ARG002
            raise RuntimeError("transport closed")

    ctx = _BoomContext(supports=True)
    decision = _run(mcp_server._elicit_permission_decision("cae.run_solver", {}, ctx=ctx))
    assert decision["behavior"] == "deny"


def test_elicit_mode_helper_respects_env_and_broker_precedence(monkeypatch) -> None:
    monkeypatch.setenv(mcp_approval.ELICIT_APPROVAL_MODE_ENV, mcp_approval.ELICIT_APPROVAL_MODE_VALUE)
    monkeypatch.delenv("AIENG_MCP_MANAGED_APPROVAL", raising=False)
    monkeypatch.delenv("AIENG_AGENTIC_PERMISSION_TOOL", raising=False)
    assert mcp_server._elicit_approval_mode() is True
    # broker modes take precedence — elicit yields to managed
    monkeypatch.setenv("AIENG_MCP_MANAGED_APPROVAL", "1")
    assert mcp_server._elicit_approval_mode() is False


def test_cli_elicit_mode_sets_env() -> None:
    try:
        mcp_server._apply_cli_runtime_options(approval_mode="elicit")
        import os

        assert os.environ.get(mcp_approval.ELICIT_APPROVAL_MODE_ENV) == mcp_approval.ELICIT_APPROVAL_MODE_VALUE
    finally:
        mcp_server._apply_cli_runtime_options(approval_mode="client")  # reset
