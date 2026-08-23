from collections.abc import Callable

import ollama
from pydantic import BaseModel, ValidationError


class NarratorResponse(BaseModel):
    narration: str
    tool: str | None = None
    tool_args: dict = {}


class NarratorClient:
    def __init__(
        self,
        model: str = "qwen3:8b",
        system_prompt: str = "",
        chat_fn: Callable[..., dict] | None = None,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self._chat_fn = chat_fn or ollama.chat

    def respond(self, messages: list[dict]) -> NarratorResponse:
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages
        response = self._chat_fn(
            model=self.model,
            messages=full_messages,
            format=NarratorResponse.model_json_schema(),
        )
        try:
            return NarratorResponse.model_validate_json(response["message"]["content"])
        except ValidationError as e:
            raise ValueError(f"model returned invalid structured output: {e}") from e
