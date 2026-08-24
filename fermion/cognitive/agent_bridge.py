"""Primary conversational agent bridge; FERMiON remains the only tool/evidence authority."""
from __future__ import annotations
from pathlib import Path
class PydanticAgentBridge:
    def __init__(self, endpoint:str, model_path:str|None):
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        model_name=Path(model_path).stem if model_path else "local-qwen"
        base=endpoint.replace("/completion","/v1")
        self.agent=Agent(OpenAIChatModel(model_name,provider=OpenAIProvider(base_url=base,api_key="local")),system_prompt="You are FERMiON's language interface. Explain only supplied FERMiON evidence; never invent tool results or receipts.")
    def synthesize(self,prompt:str, max_tokens:int=1024)->str:
        # Keep local Thinking models from spending their whole context on orchestration data.
        return str(self.agent.run_sync(prompt, model_settings={"max_tokens":max_tokens}).output)
