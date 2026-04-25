from __future__ import annotations

import json
import os
import pathlib
import re
from dataclasses import dataclass
from typing import Any

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimaxi.com/v1"
SUPPORTED_PROVIDERS = {"gpt", "minimax"}


def load_env_file(path: pathlib.Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def get_env_value(name: str, env_values: dict[str, str], default: str = "") -> str:
    return os.environ.get(name) or env_values.get(name, default)


def extract_json_object(text: str) -> dict[str, Any]:
    body = text.strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*", "", body)
        body = re.sub(r"\s*```$", "", body)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", body, flags=re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))

    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object, got: {type(payload).__name__}")
    return payload


def build_json_system_prompt(instruction_text: str, expected_fields: list[str]) -> str:
    return (
        instruction_text.strip()
        + "\n\n"
        + "Return one JSON object only. It must contain exactly these fields: "
        + ", ".join(expected_fields)
        + ". Use empty strings for missing fields. Do not return markdown."
    )


@dataclass(slots=True)
class LLMConfig:
    provider: str
    api_key: str
    model: str
    timeout: int = 60
    base_url: str = ""
    max_retries: int = 3
    system_prompt_role: str = "system"

    @classmethod
    def from_env(cls, env_values: dict[str, str]) -> "LLMConfig":
        provider = get_env_value("LLM_PROVIDER", env_values, "gpt").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported LLM_PROVIDER: {provider}. Expected one of {sorted(SUPPORTED_PROVIDERS)}")

        if provider == "gpt":
            api_key = get_env_value("OPENAI_API_KEY", env_values) or get_env_value("GPT_TOKEN", env_values)
            model = get_env_value("OPENAI_MODEL", env_values, "gpt-4.1-mini")
            base_url = get_env_value("OPENAI_BASE_URL", env_values, DEFAULT_OPENAI_BASE_URL)
        else:
            api_key = get_env_value("MINIMAX_API_KEY", env_values)
            model = get_env_value("MINIMAX_MODEL", env_values, "MiniMax-M2.7")
            base_url = get_env_value("MINIMAX_BASE_URL", env_values, DEFAULT_MINIMAX_BASE_URL)

        timeout = int(get_env_value("LLM_TIMEOUT", env_values, "60"))
        max_retries = int(get_env_value("LLM_MAX_RETRIES", env_values, "3"))
        return cls(
            provider=provider,
            api_key=api_key,
            model=model,
            timeout=timeout,
            base_url=base_url,
            max_retries=max_retries,
        )

    def resolved_base_url(self) -> str:
        if self.base_url:
            return self.base_url
        if self.provider == "gpt":
            return DEFAULT_OPENAI_BASE_URL
        if self.provider == "minimax":
            return DEFAULT_MINIMAX_BASE_URL
        raise ValueError(f"Unsupported provider: {self.provider}")

    def validate(self) -> None:
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider: {self.provider}")
        if not self.api_key:
            if self.provider == "gpt":
                raise RuntimeError("Missing OPENAI_API_KEY or GPT_TOKEN in .env.")
            raise RuntimeError("Missing MINIMAX_API_KEY in .env.")
        if not self.model:
            raise RuntimeError("Missing model name in LLM config.")


@dataclass(slots=True)
class PydanticAIChatClient:
    config: LLMConfig

    def _build_agent(self, output_type: type[Any], system_prompt: str):
        try:
            from openai import AsyncOpenAI
            from pydantic_ai import Agent
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider
        except ImportError as error:
            raise RuntimeError(
                'Missing dependencies. Install with: pip install "pydantic-ai-slim[openai]"'
            ) from error

        client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.resolved_base_url(),
            max_retries=self.config.max_retries,
            timeout=self.config.timeout,
        )
        provider = OpenAIProvider(openai_client=client)
        model = OpenAIChatModel(self.config.model, provider=provider)
        return Agent(model, output_type=output_type, system_prompt=system_prompt)

    def chat_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_type: type[Any],
    ) -> Any:
        self.config.validate()
        agent = self._build_agent(output_type, system_prompt)
        result = agent.run_sync(user_prompt)
        output = result.output

        if hasattr(output, "model_dump"):
            return output.model_dump()
        return output

    def chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_type: type[Any],
    ) -> dict[str, Any]:
        payload = self.chat_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_type=output_type,
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"Expected JSON object, got: {type(payload).__name__}")
        return payload
