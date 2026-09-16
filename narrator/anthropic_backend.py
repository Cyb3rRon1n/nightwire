"""AnthropicNarratorBackend - forced tool-use for schema-constrained
output, the real Anthropic-API equivalent of Ollama's format= JSON-schema
param NarratorClient.respond() already relies on. Raw httpx, no anthropic
SDK dependency - matches every other backend in this project
(ComfyUIBackend, FluxWorkerBackend, KokoroBackend)."""

import httpx
from pydantic import ValidationError

from narrator.client import NarratorResponse

_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_TOOL_NAME = "narrator_response"


class AnthropicNarratorBackend:
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-5",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.system_prompt = ""
        self._client = client or httpx.AsyncClient(timeout=60.0)
        self._tool_schema = NarratorResponse.model_json_schema()

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    async def respond(self, messages: list[dict]) -> NarratorResponse:
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": messages,
            "tools": [
                {
                    "name": _TOOL_NAME,
                    "description": "Respond with the narrator's structured turn output.",
                    "input_schema": self._tool_schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": _TOOL_NAME},
        }
        if self.system_prompt:
            body["system"] = self.system_prompt
        result = await self._client.post(_API_URL, json=body, headers=self._headers())
        result.raise_for_status()
        data = result.json()
        tool_use = next(
            (block for block in data.get("content", []) if block.get("type") == "tool_use"),
            None,
        )
        if tool_use is None:
            raise ValueError("Anthropic response had no tool_use block")
        try:
            return NarratorResponse.model_validate(tool_use["input"])
        except ValidationError as e:
            raise ValueError(f"model returned invalid structured output: {e}") from e

    async def summarize(self, text: str) -> str:
        body = {
            "model": self.model,
            "max_tokens": 512,
            "messages": [{"role": "user", "content": text}],
            "system": (
                "Summarize the following tabletop RPG session events in 2-3 sentences. "
                "Preserve named characters, promises, and key decisions made. Prose only, no lists."
            ),
        }
        result = await self._client.post(_API_URL, json=body, headers=self._headers())
        result.raise_for_status()
        data = result.json()
        text_block = next(block for block in data["content"] if block.get("type") == "text")
        return text_block["text"].strip()

    async def unload(self) -> None:
        # No local resources to free - a hosted API has nothing resident here.
        pass
