from app.agent_autopilot.llm_api_adapter import LlmApiAdapter
from app.agent_autopilot.schema import AutopilotAgentAction


class _FakeProvider:
    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        assert "Autopilot" in system_prompt
        assert "response_schema" in user_prompt
        return AutopilotAgentAction.model_validate(
            {
                "thought_summary": "The user asked for an explanation.",
                "action": {"type": "final", "message": "This is a simple bracket."},
                "done": True,
                "user_message": "This is a simple bracket.",
            }
        ).model_dump_json()


def test_llm_api_adapter_returns_autopilot_action() -> None:
    adapter = LlmApiAdapter(
        settings=object(),
        llm_config={"provider": "openai-compatible", "model": "demo"},
        provider_factory=lambda _settings, _config: _FakeProvider(),
    )

    result = adapter.invoke(
        prompt="explain the model",
        action_schema=AutopilotAgentAction.json_schema_for_adapter(),
    )

    assert result.status == "success"
    assert result.action is not None
    assert result.action.action.type == "final"
