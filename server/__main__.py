import uvicorn

from engine.persistence import JSONFileSessionStore
from narrator.client import NarratorClient
from server.app import create_app


def build_app():
    store = JSONFileSessionStore("./sessions")
    narrator_client = NarratorClient(model="qwen3:8b", system_prompt="You are a cyberpunk tabletop game master.")
    return create_app(store, narrator_client)


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
