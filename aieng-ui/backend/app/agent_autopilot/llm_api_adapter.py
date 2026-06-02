from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Callable

from .. import agent_engine
from .adapters import DEFAULT_PROBE_TIMEOUT_SECONDS, DEFAULT_STEP_TIMEOUT_SECONDS, _elapsed_ms, parse_action_json, progress_event
from .schema import AdapterInvocationResult, LocalAgentCapability


ProviderFactory = Callable[[Any, dict[str, Any]], Any]


@dataclass
class LlmApiAdapter:
    settings: Any
    llm_config: dict[str, Any]
    provider_factory: ProviderFactory = agent_engine._build_provider

    adapter_id: str = "llm-api"
    label: str = "LLM API"

    def _request_action(
        self,
        provider: Any,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: int,
    ) -> str:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                provider.generate,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            return future.result(timeout=timeout_seconds)

    def probe(self, timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS) -> LocalAgentCapability:
        model = str(self.llm_config.get("model") or "configured-model")
        provider = str(self.llm_config.get("provider") or "openai-compatible")
        api_key_env = str(self.llm_config.get("api_key_env") or "")
        api_key_present = bool(self.llm_config.get("api_key") or api_key_env)
        diagnostic = f"Uses configured {provider} provider and model {model}."
        if not api_key_present:
            diagnostic = "No API key is configured for this request or via environment variable."
        return LocalAgentCapability(
            adapter_id=self.adapter_id,
            label=self.label,
            status="available" if api_key_present else "blocked",
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
            on_progress(progress_event(self.adapter_id, "started", "Starting LLM API adapter."))
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
            if on_progress is not None:
                on_progress(progress_event(
                    self.adapter_id,
                    "prompt_prepared",
                    "LLM API prompt prepared.",
                    step_index=step_index,
                ))
            if on_progress is not None:
                on_progress(progress_event(
                    self.adapter_id,
                    "request_sent",
                    "LLM API request sent.",
                    step_index=step_index,
                ))
                on_progress(progress_event(
                    self.adapter_id,
                    "waiting_for_model",
                    "Waiting for LLM API response.",
                    step_index=step_index,
                ))
            raw = self._request_action(
                provider,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout_seconds=timeout_seconds,
            )
            if on_progress is not None:
                on_progress(progress_event(
                    self.adapter_id,
                    "parsing_output",
                    "LLM API returned output; validating structured action.",
                    step_index=step_index,
                ))
            try:
                action = parse_action_json(raw)
            except Exception as exc:
                if on_progress is not None:
                    on_progress(progress_event(
                        self.adapter_id,
                        "request_sent",
                        "LLM API returned malformed structured output; requesting one corrected JSON retry.",
                        step_index=step_index,
                    ))
                    on_progress(progress_event(
                        self.adapter_id,
                        "waiting_for_model",
                        "Waiting for corrected LLM API response.",
                        step_index=step_index,
                    ))
                repair_prompt = json.dumps(
                    {
                        "autopilot_prompt": prompt,
                        "response_schema": action_schema,
                        "repair_contract": (
                            "Your previous output failed schema validation. "
                            "Return exactly one corrected JSON object that matches response_schema. "
                            "Preserve the original intent, but do not leave final/chat/pause/ask_user text fields empty."
                        ),
                        "validation_error": f"{type(exc).__name__}: {exc}",
                        "previous_output": raw,
                    },
                    ensure_ascii=False,
                )
                repaired_raw = self._request_action(
                    provider,
                    system_prompt=system_prompt,
                    user_prompt=repair_prompt,
                    timeout_seconds=timeout_seconds,
                )
                if on_progress is not None:
                    on_progress(progress_event(
                        self.adapter_id,
                        "parsing_output",
                        "LLM API returned corrected output; validating structured action.",
                        step_index=step_index,
                    ))
                try:
                    action = parse_action_json(repaired_raw)
                    raw = repaired_raw
                except Exception as repair_exc:
                    raise ValueError(
                        f"invalid structured action after one correction attempt: {repair_exc}"
                    ) from repair_exc
            if on_progress is not None:
                on_progress(progress_event(
                    self.adapter_id,
                    "completed",
                    f"LLM API selected action {action.action.type}.",
                    action_type=action.action.type,
                    duration_ms=_elapsed_ms(start),
                    step_index=step_index,
                ))
            return AdapterInvocationResult(
                status="success",
                action=action,
                raw_output=raw,
                duration_ms=_elapsed_ms(start),
            )
        except FutureTimeoutError:
            if on_progress is not None:
                on_progress(progress_event(self.adapter_id, "timeout", f"LLM API call timed out after {timeout_seconds}s.", step_index=step_index))
            return AdapterInvocationResult(
                status="timeout",
                diagnostic=f"LLM API call timed out after {timeout_seconds}s.",
                duration_ms=_elapsed_ms(start),
            )
        except TimeoutError as exc:
            if on_progress is not None:
                on_progress(progress_event(self.adapter_id, "timeout", str(exc), step_index=step_index))
            return AdapterInvocationResult(
                status="timeout",
                diagnostic=str(exc),
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            if on_progress is not None:
                on_progress(progress_event(self.adapter_id, "error", f"{type(exc).__name__}: {exc}", step_index=step_index))
            return AdapterInvocationResult(
                status="error",
                diagnostic=f"{type(exc).__name__}: {exc}",
                duration_ms=_elapsed_ms(start),
            )
