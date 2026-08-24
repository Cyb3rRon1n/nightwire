import uvicorn

from engine.persistence import JSONFileSessionStore
from narrator.client import NarratorClient
from narrator.image_backend import FluxWorkerBackend
from server.app import create_app


def build_app():
    store = JSONFileSessionStore("./sessions")
    system_prompt = (
        "You are a cyberpunk tabletop game master. "
        "You may optionally set image_request to generate a picture of the current scene. "
        "Use it rarely - only when the player enters a visually distinct new location, "
        "or a genuinely striking, memorable moment occurs (not routine combat or dialogue). "
        "Never two turns in a row. When you do, image_request.prompt should be a short, "
        "concrete visual description (setting, lighting, mood) - not a summary of the plot."
    )
    narrator_client = NarratorClient(model="qwen3:8b", system_prompt=system_prompt)
    # output_dir default (frontend/public/generated) matches
    # image_server/optimized_image_server.py's own OUT_DIR default,
    # assuming both processes run from the repo root.
    image_backend = FluxWorkerBackend()
    return create_app(store, narrator_client, image_backend)


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
