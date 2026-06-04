from app.agent_autopilot.llm_api_adapter import LlmApiAdapter
from app.agent_autopilot.schema import AutopilotAgentAction


class _FakeProvider:
    def __init__(self) -> None:
        self.calls = []

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = True,
        cache_control=None,
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "json_mode": json_mode,
                "cache_control": cache_control,
            }
        )
        assert "Autopilot" in system_prompt
        assert "RESPONSE_SCHEMA_JSON" in system_prompt
        assert "AUTOPILOT_CONTEXT_JSON:\n" not in system_prompt
        assert '"autopilot_context"' in user_prompt
        return AutopilotAgentAction.model_validate(
            {
                "thought_summary": "The user asked for an explanation.",
                "action": {"type": "final", "message": "This is a simple bracket."},
                "done": True,
                "user_message": "This is a simple bracket.",
            }
        ).model_dump_json()


def test_llm_api_adapter_returns_autopilot_action() -> None:
    provider = _FakeProvider()
    adapter = LlmApiAdapter(
        settings=object(),
        llm_config={"provider": "openai-compatible", "model": "demo"},
        provider_factory=lambda _settings, _config: provider,
    )

    result = adapter.invoke(
        prompt="explain the model",
        action_schema=AutopilotAgentAction.json_schema_for_adapter(),
        system_context={"tools": [{"name": "aieng.agent_context"}]},
    )

    assert result.status == "success"
    assert result.action is not None
    assert result.action.action.type == "final"
    assert provider.calls[0]["json_mode"] is True
    assert provider.calls[0]["cache_control"] == {"type": "ephemeral"}


def test_llm_api_adapter_emits_common_progress_phases() -> None:
    provider = _FakeProvider()
    adapter = LlmApiAdapter(
        settings=object(),
        llm_config={"provider": "openai-compatible", "model": "demo"},
        provider_factory=lambda _settings, _config: provider,
    )
    events = []

    result = adapter.invoke(
        prompt="explain the model",
        action_schema=AutopilotAgentAction.json_schema_for_adapter(),
        on_progress=events.append,
        system_context={"tools": [{"name": "aieng.agent_context"}]},
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
    prepared = next(event for event in events if event["phase"] == "prompt_prepared")
    assert prepared["cache_control_enabled"] is True
    assert isinstance(prepared["system_prompt_fingerprint"], str)
    assert prepared["system_prompt_chars"] > 0
    assert prepared["user_prompt_chars"] > 0


class _RetryingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = True,
        cache_control=None,
    ) -> str:
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
        system_context={"tools": [{"name": "aieng.agent_context"}]},
    )

    assert result.status == "success"
    assert result.action is not None
    assert result.action.action.type == "final"
    assert result.action.action.message == "Recovered with valid final message."
    assert provider.calls == 2


def test_llm_api_adapter_keeps_system_prompt_stable_when_dynamic_context_changes() -> None:
    provider = _FakeProvider()
    adapter = LlmApiAdapter(
        settings=object(),
        llm_config={"provider": "openai-compatible", "model": "demo"},
        provider_factory=lambda _settings, _config: provider,
    )

    adapter.invoke(
        prompt='{"objective":"first","working_memory":[{"kind":"user_message","summary":"one"}]}',
        action_schema=AutopilotAgentAction.json_schema_for_adapter(),
        system_context={"tools": [{"name": "aieng.agent_context"}]},
    )
    adapter.invoke(
        prompt='{"objective":"second","working_memory":[{"kind":"user_message","summary":"two"}]}',
        action_schema=AutopilotAgentAction.json_schema_for_adapter(),
        system_context={"tools": [{"name": "aieng.agent_context"}]},
    )

    assert len(provider.calls) == 2
    assert provider.calls[0]["system_prompt"] == provider.calls[1]["system_prompt"]
    assert provider.calls[0]["user_prompt"] != provider.calls[1]["user_prompt"]
