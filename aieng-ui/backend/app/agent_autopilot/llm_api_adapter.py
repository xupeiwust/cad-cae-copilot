from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Callable

from .. import agent_engine
from .adapters import DEFAULT_PROBE_TIMEOUT_SECONDS, DEFAULT_STEP_TIMEOUT_SECONDS, _elapsed_ms, parse_action_json
from .schema import AdapterInvocationResult, LocalAgentCapability


ProviderFactory = Callable[[Any, dict[str, Any]], Any]


@dataclass
class LlmApiAdapter:
    settings: Any
    llm_config: dict[str, Any]
    provider_factory: ProviderFactory = agent_engine._build_provider

    adapter_id: str = "llm-api"
    label: str = "LLM API"

    def probe(self, timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS) -> LocalAgentCapability:
        model = str(self.llm_config.get("model") or "configured-model")
        provider = str(self.llm_config.get("provider") or "openai-compatible")
        api_key_env = str(self.llm_config.get("api_key_env") or "")
        diagnostic = f"Uses configured {provider} provider and model {model}."
        if not api_key_env:
            diagnostic = "No API key environment variable is configured."
        return LocalAgentCapability(
            adapter_id=self.adapter_id,
            label=self.label,
            status="available" if api_key_env or self.llm_config.get("base_url") else "blocked",
            command="provider-api",
            command_path=None,
            version=model,
            supports_non_interactive=True,
            supports_json=True,
            supports_json_schema=False,
            supports_tool_disable=True,
            supports_session_continuation=False,
            diagnostic=diagnostic,
        )

    def invoke(
        self,
        *,
        prompt: str,
        action_schema: dict[str, Any],
        timeout_seconds: int = DEFAULT_STEP_TIMEOUT_SECONDS,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        session_id: str | None = None,
        step_index: int = 0,
    ) -> AdapterInvocationResult:
        start = time.perf_counter()
        if on_progress is not None:
            on_progress({"phase": "started", "adapter_id": self.adapter_id})
        try:
            provider = self.provider_factory(self.settings, self.llm_config)
            system_prompt = (
                "You are the AIENG Workbench Autopilot decision adapter. "
                "Return only one JSON object for the next action. Do not include Markdown fences. "
                "Use only tools listed in the user prompt. If the best answer is conversational, "
                "return a chat or final action instead of inventing a tool."
            )
            user_prompt = json.dumps(
                {
                    "autopilot_prompt": prompt,
                    "response_schema": action_schema,
                    "output_contract": (
                        "Return JSON matching response_schema. For tool_call actions, put the tool input "
                        "as a JSON string in action.input_json."
                    ),
                },
                ensure_ascii=False,
            )
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    provider.generate,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                raw = future.result(timeout=timeout_seconds)
            if on_progress is not None:
                on_progress({"phase": "completed", "adapter_id": self.adapter_id})
            return AdapterInvocationResult(
                status="success",
                action=parse_action_json(raw),
                raw_output=raw,
                duration_ms=_elapsed_ms(start),
            )
        except FutureTimeoutError:
            if on_progress is not None:
                on_progress({"phase": "timeout", "adapter_id": self.adapter_id})
            return AdapterInvocationResult(
                status="timeout",
                diagnostic=f"LLM API call timed out after {timeout_seconds}s.",
                duration_ms=_elapsed_ms(start),
            )
        except TimeoutError as exc:
            return AdapterInvocationResult(
                status="timeout",
                diagnostic=str(exc),
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            return AdapterInvocationResult(
                status="error",
                diagnostic=f"{type(exc).__name__}: {exc}",
                duration_ms=_elapsed_ms(start),
            )
