"""One bounded local-model request; FERMiON owns tool and evidence authority."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fermion.adapters.llama_cpp import strip_model_reasoning


class PydanticAgentBridge:
    def __init__(self, endpoint: str, model_identifier: str | None, model_path: str | None,
                 system_prompt: str, *, api_key: str | None = None):
        from openai import AsyncOpenAI
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        name = model_identifier or (Path(model_path).stem if model_path else "local-qwen")
        parsed = urlsplit(endpoint)
        base = urlunsplit((parsed.scheme, parsed.netloc, "/v1", "", ""))
        # Disable SDK retries as well as agent retries: one user turn must not
        # silently incur several slow local generations.
        client = AsyncOpenAI(base_url=base, api_key=api_key or "local", max_retries=0)
        self.agent = Agent(OpenAIChatModel(name, provider=OpenAIProvider(openai_client=client)),
                           system_prompt=system_prompt, retries=0)
        self.agent.instrument = False
        self.last_metadata: dict[str, object] = {}

    def synthesize(self, prompt: str, max_tokens: int = 1024, *, timeout_seconds: float = 60,
                   temperature: float = 0.4) -> str:
        from pydantic_ai.usage import UsageLimits
        self.last_metadata = {}
        result = self.agent.run_sync(prompt, model_settings={"max_tokens": max_tokens,
                                      "timeout": timeout_seconds, "temperature": temperature},
                                     usage_limits=UsageLimits(request_limit=1), retries=0)
        usage = result.usage
        if callable(usage):  # Older supported SDK releases exposed a method.
            usage = usage()
        # SDK defaults for absent usage are not measured zero-token generations.
        def reported(value):
            return value if type(value) is int and value > 0 else None
        messages = result.all_messages()
        self.last_metadata = {"prompt_tokens": reported(usage.input_tokens),
                              "completion_tokens": reported(usage.output_tokens),
                              "total_tokens": reported(usage.total_tokens),
                              "finish_reason": getattr(messages[-1], "finish_reason", None) if messages else None}
        return strip_model_reasoning(str(result.output))
