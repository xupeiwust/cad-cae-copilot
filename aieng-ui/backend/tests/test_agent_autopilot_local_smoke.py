import os

import pytest

from app.agent_autopilot.claude_code_adapter import ClaudeCodeAdapter
from app.agent_autopilot.codex_cli_adapter import CodexCliAdapter
from app.agent_autopilot.schema import AutopilotAgentAction


@pytest.mark.skipif(
    os.environ.get("AIENG_RUN_LOCAL_AGENT_SMOKE") != "1",
    reason="Set AIENG_RUN_LOCAL_AGENT_SMOKE=1 to call the local Claude Code CLI.",
)
def test_claude_code_local_smoke() -> None:
    result = ClaudeCodeAdapter().invoke(
        prompt="Return a final Local Agent Autopilot action JSON with message 'smoke ok'.",
        action_schema=AutopilotAgentAction.json_schema_for_adapter(),
        timeout_seconds=60,
    )
    assert result.status == "success", result.diagnostic
    assert result.action is not None
    assert result.action.action.type == "final"


@pytest.mark.skipif(
    os.environ.get("AIENG_RUN_CODEX_LOCAL_AGENT_SMOKE") != "1",
    reason="Set AIENG_RUN_CODEX_LOCAL_AGENT_SMOKE=1 to call the local Codex CLI.",
)
def test_codex_cli_local_smoke() -> None:
    result = CodexCliAdapter().invoke(
        prompt="Return a final Local Agent Autopilot action JSON with message 'smoke ok'.",
        action_schema=AutopilotAgentAction.json_schema_for_adapter(),
        timeout_seconds=120,
    )
    assert result.status == "success", result.diagnostic
    assert result.action is not None
    assert result.action.action.type == "final"
