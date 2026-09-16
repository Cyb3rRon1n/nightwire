"""OpenAICompatNarratorBackend - talks to any OpenAI-compatible chat
completions endpoint (OpenRouter, a local vLLM/llama.cpp-server, etc.).
Requests OpenAI's own Structured Outputs (response_format=json_schema),
but never assumes the server actually enforces it - "OpenAI-compatible"
spans providers with uneven strict-mode support, so every response is
validated the same way regardless of whether the server honored the
schema or just happened to return valid JSON. Raw httpx, no openai SDK
dependency - matches every other backend in this project."""

import httpx
from pydantic import ValidationError

from narrator.client import NarratorResponse

_SUMMARY_SYSTEM_PROMPT = (
    "Summarize the following tabletop RPG session events in 2-3 sentences. "
    "Preserve named characters, promises, and key decisions made. Prose only, no lists."
)


class OpenAICompatNarratorBackend:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        num_ctx: int = 8192,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.system_prompt = ""
        self.num_ctx = num_ctx
        self._client = client or httpx.AsyncClient(timeout=60.0)
        self._response_schema = NarratorResponse.model_json_schema()

    def _headers(self) -> dict:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def respond(self, messages: list[dict]) -> NarratorResponse:
        full_messages = messages
        if self.system_prompt:
            full_messages = [{"role": "system", "content": self.system_prompt}] + messages
        body = {
            "model": self.model,
            "messages": full_messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "narrator_response", "schema": self._response_schema},
            },
        }
        result = await self._client.post(
            f"{self.base_url}/chat/completions", json=body, headers=self._headers(),
        )
        result.raise_for_status()
        content = result.json()["choices"][0]["message"]["content"]
        try:
            return NarratorResponse.model_validate_json(content)
        except ValidationError as e:
            raise ValueError(f"model returned invalid structured output: {e}") from e

    async def summarize(self, text: str) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        result = await self._client.post(
            f"{self.base_url}/chat/completions", json=body, headers=self._headers(),
        )
        result.raise_for_status()
        content = result.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError(f"OpenAI-compat summarize response had non-string content: {content!r}")
        return content.strip()

    async def unload(self) -> None:
        # No local resources to free - a hosted API has nothing resident here.
        pass
