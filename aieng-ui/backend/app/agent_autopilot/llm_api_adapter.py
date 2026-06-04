from __future__ import annotations

import hashlib
import inspect
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
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
    _cached_system_prompt_key: str | None = field(default=None, init=False, repr=False)
    _cached_system_prompt: str | None = field(default=None, init=False, repr=False)

    def _request_action(
        self,
        provider: Any,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: int,
        json_mode: bool = True,
        cache_control: dict[str, Any] | None = None,
    ) -> str:
        def _call_provider() -> str:
            generate = provider.generate
            kwargs: dict[str, Any] = {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "json_mode": json_mode,
                "cache_control": cache_control,
            }
            try:
                signature = inspect.signature(generate)
            except (TypeError, ValueError):
                signature = None
            if signature is not None:
                params = signature.parameters
                accepts_kwargs = any(
                    param.kind == inspect.Parameter.VAR_KEYWORD
                    for param in params.values()
                )
                if not accepts_kwargs:
                    kwargs = {
                        key: value
                        for key, value in kwargs.items()
                        if key in params
                    }
            return generate(**kwargs)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_call_provider)
            return future.result(timeout=timeout_seconds)

    def _prompt_cache_control(self) -> dict[str, Any] | None:
        enabled = self.llm_config.get("enable_prompt_caching", True)
        if enabled is False:
            return None
        return {"type": "ephemeral"}

    @staticmethod
    def _stable_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)

    @staticmethod
    def _fingerprint(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _build_system_prompt(
        self,
        *,
        action_schema: dict[str, Any],
        system_context: dict[str, Any] | None = None,
    ) -> str:
        context_json = self._stable_json(system_context or {})
        schema_json = self._stable_json(action_schema)
        cache_key = self._fingerprint(context_json + "\n" + schema_json)
        if self._cached_system_prompt_key == cache_key and self._cached_system_prompt is not None:
            return self._cached_system_prompt

        sections = [
            (
                "You are the AIENG Workbench Autopilot decision adapter. "
                "Return only one JSON object for the next action. Do not include Markdown fences."
            ),
            (
                "Choose only from the tools and rules provided in the prompt context. "
                "If the best response is conversational, return a chat, ask_user, pause, or final action instead of inventing a tool."
            ),
        ]
        if system_context:
            sections.append("WORKBENCH_SYSTEM_CONTEXT_JSON:\n" + context_json)
        sections.append(
            "RESPONSE_SCHEMA_JSON:\n"
            + schema_json
        )
        sections.append(
            "OUTPUT_CONTRACT:\n"
            "Return JSON matching RESPONSE_SCHEMA_JSON. "
            "For tool_call actions, put the tool input as a JSON string in action.input_json."
        )
        sections.append(
            "PROMPT_SPLIT:\n"
            "Treat WORKBENCH_SYSTEM_CONTEXT_JSON and RESPONSE_SCHEMA_JSON as the static cacheable layer. "
            "Treat the user message as the dynamic per-step AUTOPILOT_CONTEXT_JSON payload."
        )
        system_prompt = "\n\n".join(sections)
        self._cached_system_prompt_key = cache_key
        self._cached_system_prompt = system_prompt
        return system_prompt

    def _build_dynamic_user_prompt(self, prompt: str) -> str:
        try:
            prompt_payload = json.loads(prompt)
        except json.JSONDecodeError:
            prompt_payload = {"raw_prompt": prompt}
        return self._stable_json(
            {
                "autopilot_context": prompt_payload,
                "task": (
                    "Return exactly one next-action JSON object that matches RESPONSE_SCHEMA_JSON. "
                    "Base it on autopilot_context and do not add any extra prose."
                ),
            }
        )

    def _build_repair_user_prompt(
        self,
        *,
        prompt: str,
        validation_error: str,
        previous_output: str,
    ) -> str:
        try:
            prompt_payload = json.loads(prompt)
        except json.JSONDecodeError:
            prompt_payload = {"raw_prompt": prompt}
        return self._stable_json(
            {
                "autopilot_context": prompt_payload,
                "repair_contract": (
                    "Your previous output failed schema validation. "
                    "Return exactly one corrected JSON object that matches RESPONSE_SCHEMA_JSON. "
                    "Preserve the original intent, but do not leave final/chat/pause/ask_user text fields empty."
                ),
                "validation_error": validation_error,
                "previous_output": previous_output,
            }
        )

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
        system_context: dict[str, Any] | None = None,
    ) -> AdapterInvocationResult:
        start = time.perf_counter()
        if on_progress is not None:
            on_progress(progress_event(self.adapter_id, "started", "Starting LLM API adapter."))
        try:
            provider = self.provider_factory(self.settings, self.llm_config)
            system_prompt = self._build_system_prompt(
                action_schema=action_schema,
                system_context=system_context,
            )
            user_prompt = self._build_dynamic_user_prompt(prompt)
            cache_control = self._prompt_cache_control()
            system_prompt_fingerprint = self._fingerprint(system_prompt)
            if on_progress is not None:
                on_progress(progress_event(
                    self.adapter_id,
                    "prompt_prepared",
                    "LLM API prompt prepared.",
                    system_prompt_fingerprint=system_prompt_fingerprint,
                    system_prompt_chars=len(system_prompt),
                    user_prompt_chars=len(user_prompt),
                    cache_control_enabled=bool(cache_control),
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
                json_mode=True,
                cache_control=cache_control,
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
                repair_prompt = self._build_repair_user_prompt(
                    prompt=prompt,
                    validation_error=f"{type(exc).__name__}: {exc}",
                    previous_output=raw,
                )
                repaired_raw = self._request_action(
                    provider,
                    system_prompt=system_prompt,
                    user_prompt=repair_prompt,
                    timeout_seconds=timeout_seconds,
                    json_mode=True,
                    cache_control=cache_control,
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
