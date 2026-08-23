from collections.abc import Awaitable, Callable
from typing import Literal

import ollama
from pydantic import BaseModel, ValidationError

from narrator.tools import TOOL_REGISTRY

ToolName = Literal[tuple(TOOL_REGISTRY)]


class NarratorResponse(BaseModel):
    narration: str
    tool: ToolName | None = None
    tool_args: dict = {}


class NarratorClient:
    def __init__(
        self,
        model: str = "qwen3:8b",
        system_prompt: str = "",
        chat_fn: Callable[..., Awaitable[dict]] | None = None,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self._client = ollama.AsyncClient(timeout=60)
        self._chat_fn = chat_fn or self._default_chat

    async def _default_chat(self, *, model: str, messages: list[dict], format: dict) -> dict:
        return await self._client.chat(model=model, messages=messages, format=format)

    async def respond(self, messages: list[dict]) -> NarratorResponse:
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages
        response = await self._chat_fn(
            model=self.model,
            messages=full_messages,
            format=NarratorResponse.model_json_schema(),
        )
        try:
            return NarratorResponse.model_validate_json(response["message"]["content"])
        except ValidationError as e:
            raise ValueError(f"model returned invalid structured output: {e}") from e
