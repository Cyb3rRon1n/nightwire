import os

import uvicorn

from engine.persistence import JSONFileSessionStore
from narrator.client import NarratorClient
from narrator.image_backend import FluxWorkerBackend
from narrator.tts_backend import KokoroBackend
from server.app import create_app


def build_app():
    store = JSONFileSessionStore(os.environ.get("SESSION_STORE_DIR", "./sessions"))
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
        "deltas from a d20-style game - a fight should plausibly end in a handful of hits. "
        "Advancement is rare and milestone-scale - only when the party clears a major "
        "objective or survives a defining fight, never for routine success. When it's "
        "earned, set apply_character_update's skill_points_delta to 1-2, or "
        "attribute_points_delta to 1 (never more); a whole campaign hands out only a few."
    )
    narrator_client = NarratorClient(model=os.environ.get("NIGHTWIRE_MODEL", "qwen3:8b"), system_prompt=system_prompt)
    # output_dir default (frontend/public/generated) matches
    # image_server/optimized_image_server.py's own OUT_DIR default,
    # assuming both processes run from the repo root - still true when
    # FLUX_WORKER_URL points elsewhere (a container split needs a shared
    # volume mounted at this same path in both containers).
    image_backend = FluxWorkerBackend(
        base_url=os.environ.get("FLUX_WORKER_URL", "http://127.0.0.1:7869"),
        output_dir=os.environ.get("IMAGE_OUTPUT_DIR", "frontend/public/generated"),
    )
    # KokoroBackend is the local-first default (coexists with qwen3:8b, no
    # GPU-swap cost) - swap to OpenAITTSBackend(api_key=...) here for the
    # hosted fallback; selection is a startup-time config choice, not a
    # runtime toggle (see docs/superpowers/specs/2026-08-23-tts-narration-design.md).
    tts_backend = KokoroBackend(base_url=os.environ.get("KOKORO_URL", "http://127.0.0.1:8880"))
    return create_app(store, narrator_client, image_backend, tts_backend)


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.environ.get("SERVER_PORT", "8000")))
