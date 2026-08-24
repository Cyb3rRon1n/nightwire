from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel


class VoiceOption(BaseModel):
    id: str
    gender: Literal["male", "female"] | None = None


class TTSBackend(Protocol):
    voices: list[VoiceOption]

    async def synthesize(self, text: str, voice: str) -> bytes: ...


class KokoroBackend:
    """Talks to a local Kokoro server exposing an OpenAI-compatible
    /v1/audio/speech endpoint (the shape remsky/Kokoro-FastAPI and similar
    self-hosted wrappers use). base_url is a config default, not a protocol
    constant - point it at whatever the real deployment ends up running on.

    Voice IDs verified against hexgrad/Kokoro-82M's own VOICES.md
    (Apache 2.0), American English subset only, 2026-08-23.
    """

    voices = [
        VoiceOption(id="af_heart", gender="female"),
        VoiceOption(id="af_bella", gender="female"),
        VoiceOption(id="af_nova", gender="female"),
        VoiceOption(id="af_sarah", gender="female"),
        VoiceOption(id="am_adam", gender="male"),
        VoiceOption(id="am_michael", gender="male"),
        VoiceOption(id="am_onyx", gender="male"),
        VoiceOption(id="am_echo", gender="male"),
    ]

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8880",
        model: str = "kokoro",
        speech_fn: Callable[[str, str], Awaitable[bytes]] | None = None,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self._speech_fn = speech_fn or self._default_speech

    async def _default_speech(self, text: str, voice: str) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.base_url}/v1/audio/speech",
                    json={"model": self.model, "voice": voice, "input": text, "response_format": "wav"},
                )
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as e:
            raise ValueError(f"tts request failed: {e}") from e

    async def synthesize(self, text: str, voice: str) -> bytes:
        return await self._speech_fn(text, voice)


class OpenAITTSBackend:
    """Hosted fallback: OpenAI's /v1/audio/speech endpoint. Voice IDs and
    the request shape verified against OpenAI's own API docs, 2026-08-23 -
    OpenAI publishes no gender label for these voices (tonal descriptors
    only), so VoiceOption.gender is deliberately left unset for all of them.
    """

    voices = [
        VoiceOption(id="alloy"),
        VoiceOption(id="echo"),
        VoiceOption(id="fable"),
        VoiceOption(id="onyx"),
        VoiceOption(id="nova"),
        VoiceOption(id="shimmer"),
    ]

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com",
        model: str = "tts-1",
        speech_fn: Callable[[str, str], Awaitable[bytes]] | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._speech_fn = speech_fn or self._default_speech

    async def _default_speech(self, text: str, voice: str) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.base_url}/v1/audio/speech",
                    json={"model": self.model, "voice": voice, "input": text, "response_format": "wav"},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as e:
            raise ValueError(f"tts request failed: {e}") from e

    async def synthesize(self, text: str, voice: str) -> bytes:
        return await self._speech_fn(text, voice)
