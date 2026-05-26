from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Optional, Protocol


class LLMProvider(Protocol):
    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        ...


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    input_price_per_million_tokens: Optional[float] = None
    output_price_per_million_tokens: Optional[float] = None
    max_output_tokens: int = 8192
    temperature: float = 0.0
    top_p: float = 1.0
    seed: Optional[int] = None

    def resolved_api_key(self) -> Optional[str]:
        if self.api_key:
            return self.api_key
        env_name = self.api_key_env or _default_api_key_env(self.provider)
        return os.getenv(env_name) if env_name else None


def _default_api_key_env(provider: str) -> Optional[str]:
    normalized = provider.strip().lower()
    if normalized == "anthropic":
        return "ANTHROPIC_API_KEY"
    if normalized == "openai-compatible":
        return "OPENAI_API_KEY"
    return None


def _extract_text_from_anthropic_response(response: object) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, list):
        parts = []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "\n".join(parts)
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    raise ValueError("Anthropic response did not contain text content")


def _extract_text_from_openai_response(response: object) -> str:
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
    raise ValueError("OpenAI-compatible response did not contain message content")


def _openai_request_kwargs(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
    temperature: float,
    top_p: float,
    seed: Optional[int],
) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_output_tokens,
        "temperature": temperature,
        "top_p": top_p,
    }
    if seed is not None:
        kwargs["seed"] = seed
    return kwargs


def _supports_json_mode_retry(exc: Exception) -> bool:
    message = str(exc).lower()
    return "response_format" in message or "json_object" in message or "json schema" in message


@dataclass
class AnthropicProvider:
    client: object
    model: str
    max_output_tokens: int = 8192
    temperature: float = 0.0

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_output_tokens,
            temperature=self.temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return _extract_text_from_anthropic_response(response)


@dataclass
class OpenAICompatibleProvider:
    client: object
    model: str
    max_output_tokens: int = 8192
    temperature: float = 0.0
    top_p: float = 1.0
    seed: Optional[int] = None

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        request_kwargs = _openai_request_kwargs(
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            seed=self.seed,
        )
        try:
            response = self.client.chat.completions.create(
                **request_kwargs,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            if not _supports_json_mode_retry(exc):
                raise
            response = self.client.chat.completions.create(**request_kwargs)
        return _extract_text_from_openai_response(response)


def build_provider(config: ProviderConfig) -> LLMProvider:
    provider_name = config.provider.strip().lower()
    api_key = config.resolved_api_key()
    if not api_key:
        raise ValueError(f"API key is required for provider {config.provider!r}")

    if provider_name == "anthropic":
        anthropic = importlib.import_module("anthropic")
        client = anthropic.Anthropic(api_key=api_key)
        return AnthropicProvider(
            client=client,
            model=config.model,
            max_output_tokens=config.max_output_tokens,
            temperature=config.temperature,
        )

    if provider_name == "openai-compatible":
        if not config.base_url:
            raise ValueError("openai-compatible provider requires base_url")
        openai = importlib.import_module("openai")
        client = openai.OpenAI(api_key=api_key, base_url=config.base_url)
        return OpenAICompatibleProvider(
            client=client,
            model=config.model,
            max_output_tokens=config.max_output_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            seed=config.seed,
        )

    raise ValueError(f"Unsupported provider: {config.provider}")
