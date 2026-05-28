import pytest
from pydantic import ValidationError

from app.agent_autopilot.schema import AutopilotAgentAction


def test_agent_action_accepts_supported_action_types() -> None:
    for action in [
        {"type": "tool_call", "tool_name": "aieng.agent_context", "input": {"project_id": "p1"}},
        {"type": "ask_user", "question": "Which face should be fixed?"},
        {"type": "final", "message": "Done."},
        {"type": "pause", "reason": "Adapter unavailable."},
    ]:
        parsed = AutopilotAgentAction.model_validate({"action": action})
        assert parsed.action.type == action["type"]


def test_agent_action_rejects_unknown_type_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AutopilotAgentAction.model_validate({"action": {"type": "shell", "command": "dir"}})
    with pytest.raises(ValidationError):
        AutopilotAgentAction.model_validate(
            {
                "action": {"type": "tool_call", "tool_name": "aieng.agent_context", "input": {}},
                "direct_file_write": True,
            }
        )


def test_agent_action_json_schema_serializes() -> None:
    schema = AutopilotAgentAction.json_schema_for_adapter()
    assert schema["type"] == "object"
    assert "action" in schema["properties"]
