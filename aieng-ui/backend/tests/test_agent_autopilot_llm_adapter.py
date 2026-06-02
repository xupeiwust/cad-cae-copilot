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


def test_llm_api_adapter_emits_common_progress_phases() -> None:
    adapter = LlmApiAdapter(
        settings=object(),
        llm_config={"provider": "openai-compatible", "model": "demo"},
        provider_factory=lambda _settings, _config: _FakeProvider(),
    )
    events = []

    result = adapter.invoke(
        prompt="explain the model",
        action_schema=AutopilotAgentAction.json_schema_for_adapter(),
        on_progress=events.append,
    )

    assert result.status == "success"
    phases = [event["phase"] for event in events]
    assert phases == [
        "started",
        "prompt_prepared",
        "request_sent",
        "waiting_for_model",
        "parsing_output",
        "completed",
    ]


class _RetryingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        assert "Autopilot" in system_prompt
        if self.calls == 1:
            return '{"thought_summary":"x","action":{"type":"final","message":""},"done":true}'
        return AutopilotAgentAction.model_validate(
            {
                "thought_summary": "Recovered malformed terminal output.",
                "action": {"type": "final", "message": "Recovered with valid final message."},
                "done": True,
                "user_message": "Recovered with valid final message.",
            }
        ).model_dump_json()


def test_llm_api_adapter_retries_once_on_empty_terminal_message() -> None:
    provider = _RetryingProvider()
    adapter = LlmApiAdapter(
        settings=object(),
        llm_config={"provider": "openai-compatible", "model": "demo"},
        provider_factory=lambda _settings, _config: provider,
    )

    result = adapter.invoke(
        prompt="explain the model",
        action_schema=AutopilotAgentAction.json_schema_for_adapter(),
    )

    assert result.status == "success"
    assert result.action is not None
    assert result.action.action.type == "final"
    assert result.action.action.message == "Recovered with valid final message."
    assert provider.calls == 2
