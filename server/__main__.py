import os

import uvicorn

from engine.persistence import JSONFileSessionStore
from narrator.client import NarratorClient
from narrator.image_backend import FluxWorkerBackend, ImageBackend
from narrator.tts_backend import KokoroBackend, OpenAITTSBackend, TTSBackend, VoiceOption
from server.app import create_app


class NullImageBackend:
    """No-op image backend for NIGHTWIRE_IMAGE_BACKEND=none. Attempts fail
    soft into an `[image error: ...]` log line via the existing
    `except (ValueError, TypeError, OSError)` handling in
    server/narration.py - same mechanism any other image-gen failure uses.
    """

    async def generate_portrait(self, description: str, reference_photos: list[str] | None = None) -> bytes:
        raise ValueError("image generation disabled (NIGHTWIRE_IMAGE_BACKEND=none)")

    async def generate_scene(self, prompt: str, reference_paths: list[str]) -> bytes:
        raise ValueError("image generation disabled (NIGHTWIRE_IMAGE_BACKEND=none)")


class NullTTSBackend:
    """No-op TTS backend for NIGHTWIRE_TTS_BACKEND=none - same fail-soft shape as NullImageBackend."""

    voices: list[VoiceOption] = []

    async def synthesize(self, text: str, voice: str) -> bytes:
        raise ValueError("tts disabled (NIGHTWIRE_TTS_BACKEND=none)")

    async def unload(self) -> None:
        pass


def build_app():
    store = JSONFileSessionStore("./sessions")
    system_prompt = (
        "You are a cyberpunk tabletop game master. "
        "Most turns should set tool_call.tool to null - plain narration, dialogue, and "
        "exploration need no tool at all. Combat start/end is entirely player-controlled "
        "outside your tools - never mention or imply that you're starting or ending combat "
        "as a mechanical event, just narrate what's happening. "
        "You may optionally set image_request to generate a picture of the current scene. "
        "Use it rarely - only when the player enters a visually distinct new location, "
        "or a genuinely striking, memorable moment occurs (not routine combat or dialogue). "
        "Never two turns in a row. Example: player steps into a neon-lit rooftop bar for "
        "the first time -> set image_request.prompt to 'a rain-slicked rooftop bar, neon "
        "signs reflecting off wet concrete, city skyline behind'. Player orders a drink, "
        "asks a question, checks their own gear or inventory, or takes a routine combat "
        "action in a location already described this scene -> leave image_request unset, "
        "even if the action itself sounds visually interesting. When you do set it, the "
        "prompt should be a short, concrete visual description (setting, lighting, mood) - "
        "not a summary of the plot. "
        "Narration is a list of segments, each with a speaker. Use speaker 'narrator' for "
        "your own descriptive prose; use the exact same name every time a given character "
        "speaks (don't vary casing or spelling turn to turn). Set gender only the first "
        "time a new speaker appears - male or female, whichever fits the character. "
        "Characters have 100 max Health. Scale apply_character_update's health_delta to "
        "that pool: a grazing or minor hit is roughly -5 to -15, a solid hit -20 to -35, "
        "a devastating or critical hit -40 to -60. Don't default to small single-digit "
        "deltas from a d20-style game - a fight should plausibly end in a handful of hits."
    )
    model = os.environ.get("NIGHTWIRE_MODEL", "qwen3:8b")
    narrator_client = NarratorClient(model=model, system_prompt=system_prompt)

    image_choice = os.environ.get("NIGHTWIRE_IMAGE_BACKEND", "flux")
    image_backend: ImageBackend = FluxWorkerBackend() if image_choice == "flux" else NullImageBackend()

    tts_choice = os.environ.get("NIGHTWIRE_TTS_BACKEND", "kokoro")
    tts_backend: TTSBackend
    if tts_choice == "openai":
        tts_backend = OpenAITTSBackend(api_key=os.environ["NIGHTWIRE_TTS_API_KEY"])
    elif tts_choice == "none":
        tts_backend = NullTTSBackend()
    else:
        tts_backend = KokoroBackend()

    return create_app(store, narrator_client, image_backend, tts_backend)


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
