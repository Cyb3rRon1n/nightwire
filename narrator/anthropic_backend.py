"""AnthropicNarratorBackend - forces the model to call a schema-shaped tool,
then validates the result the same way NarratorClient.respond() already
validates Ollama's output - not true constrained decoding (Anthropic's
forced tool-use guarantees the tool gets called, not that its input matches
the schema; model_validate is what actually catches non-conformance and
raises ValueError). Raw httpx, no anthropic SDK dependency - matches every
other backend in this project (ComfyUIBackend, FluxWorkerBackend,
KokoroBackend).

Note: forced tool_choice of type "tool" returns a 400 error on the
claude-fable-5-1 / claude-mythos-5-1 model family. NARRATOR_ANTHROPIC_MODEL
is user-settable, so pointing it at a Fable-family model fails hard here
with no hint why."""

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
        num_ctx: int = 8192,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.system_prompt = ""
        self.num_ctx = num_ctx
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
        text_block = next(
            (block for block in data["content"] if block.get("type") == "text"), None,
        )
        if text_block is None:
            raise ValueError("Anthropic response had no text block")
        return text_block["text"].strip()

    async def judge(self, messages: list[dict], schema: dict) -> dict:
        # The Messages API rejects a system role inside messages - it goes in the top-level field.
        system = [m["content"] for m in messages if m["role"] == "system"]
        body = {
            "model": self.model,
            "max_tokens": 200,
            "temperature": 0,
            "messages": [m for m in messages if m["role"] != "system"],
            "tools": [{"name": "referee", "description": "Answer every referee question.", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": "referee"},
        }
        if system:
            body["system"] = "\n\n".join(system)
        result = await self._client.post(_API_URL, json=body, headers=self._headers())
        result.raise_for_status()
        tool_use = next((b for b in result.json().get("content", []) if b.get("type") == "tool_use"), None)
        if tool_use is None:
            raise ValueError("Anthropic referee response had no tool_use block")
        return tool_use["input"]

    async def unload(self) -> None:
        # No local resources to free - a hosted API has nothing resident here.
        pass
