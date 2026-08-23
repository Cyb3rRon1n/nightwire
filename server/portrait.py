from pathlib import Path

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarratorClient
from narrator.image_backend import ImageBackend


async def handle_approve_character(
    session: Session,
    store: JSONFileSessionStore,
    narrator_client: NarratorClient,
    image_backend: ImageBackend,
    player_id: str,
) -> None:
    if player_id not in session.characters:
        raise ValueError(f"no joined character for player_id {player_id!r}")
    character = session.characters[player_id]

    description = f"{character.name}, a {character.lifepath} {character.role}"
    await narrator_client.unload()
    image_bytes = await image_backend.generate_portrait(description)

    relative_path = f"portraits/{session.session_id}/{player_id}.png"
    output_path = store.directory / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)

    character.portrait_path = relative_path
