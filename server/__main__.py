import uvicorn

from engine.persistence import JSONFileSessionStore
from narrator.client import NarratorClient
from narrator.image_backend import FluxWorkerBackend
from server.app import create_app


def build_app():
    store = JSONFileSessionStore("./sessions")
    system_prompt = (
        "You are a cyberpunk tabletop game master. "
        "Most turns should set tool_call.tool to null - plain narration, dialogue, and "
        "exploration need no tool at all. Only call start_combat when violence actually "
        "breaks out this turn (weapons fire, a blade drawn in anger, a hostile attack "
        "landing) - never for tension, a threat, a dangerous location, or an NPC being "
        "hostile in words only. Example: an NPC pulls a gun and fires -> start_combat. "
        "Example: an NPC sneers and refuses to talk, or the player enters a gang-controlled "
        "block -> tool_call stays null, that's just narration. Once combat has started, "
        "don't call start_combat again on later turns - use end_combat only when the fight "
        "genuinely ends (surrender, death, flight), and leave tool_call null for ordinary "
        "combat narration in between. "
        "You may optionally set image_request to generate a picture of the current scene. "
        "Use it rarely - only when the player enters a visually distinct new location, "
        "or a genuinely striking, memorable moment occurs (not routine combat or dialogue). "
        "Never two turns in a row. Example: player steps into a neon-lit rooftop bar for "
        "the first time -> set image_request.prompt to 'a rain-slicked rooftop bar, neon "
        "signs reflecting off wet concrete, city skyline behind'. Player orders a drink or "
        "asks a question -> leave image_request unset. When you do set it, the prompt "
        "should be a short, concrete visual description (setting, lighting, mood) - not a "
        "summary of the plot."
    )
    narrator_client = NarratorClient(model="qwen3:8b", system_prompt=system_prompt)
    # output_dir default (frontend/public/generated) matches
    # image_server/optimized_image_server.py's own OUT_DIR default,
    # assuming both processes run from the repo root.
    image_backend = FluxWorkerBackend()
    return create_app(store, narrator_client, image_backend)


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
