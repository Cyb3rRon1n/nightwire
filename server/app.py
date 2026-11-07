import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarratorClient
from narrator.image_backend import ImageBackend
from narrator.place_art import ART_DIR
from narrator.tts_backend import TTSBackend
from server.connection_manager import ConnectionManager
from server.dispatch import handle_message
from server.narration import handle_action, narrate_roll, resolve_roll
from server.phone_turns import deliver_due, handle_text
from server.portrait import handle_approve_character
from server.views import build_view


def create_app(
    store: JSONFileSessionStore,
    narrator_client: NarratorClient,
    image_backend: ImageBackend,
    tts_backend: TTSBackend,
) -> FastAPI:
    app = FastAPI()
    # Serves generated portraits/scene images (sessions/portraits/..., sessions/images/...)
    # - store.directory always exists (JSONFileSessionStore creates it), the
    # portrait/image subdirs are created lazily on first write.
    app.mount("/media", StaticFiles(directory=store.directory), name="media")
    if ART_DIR.is_dir():  # approved place art (tools/export_place_art.py), named by StateView.location_art
        app.mount("/place-art", StaticFiles(directory=ART_DIR), name="place-art")
    character_art = ART_DIR.parent / "character_art"
    if character_art.is_dir():  # approved NPC portraits (tools/export_character_art.py) for the conversation
        app.mount("/character-art", StaticFiles(directory=character_art), name="character-art")
    manager = ConnectionManager()
    sessions: dict[str, Session] = {}  # ponytail: single-process; needs a real store if ever multi-worker

    locks: dict[str, asyncio.Lock] = {}

    async def _handle(session: Session, player_id: str, message: dict) -> None:
        if message.get("type") == "action":
            await handle_action(session, narrator_client, store, image_backend, tts_backend, player_id, message)
            await deliver_due(session, narrator_client, player_id)
        elif message.get("type") == "text":
            await handle_text(session, narrator_client, player_id, message)
        elif message.get("type") == "roll":
            rolled = resolve_roll(session, player_id, overclock=message.get("overclock"))
            # Show the die landing now; the resolution narration (slow) follows.
            store.save(session)
            await manager.broadcast(session.session_id, session)
            await narrate_roll(session, narrator_client, store, image_backend, tts_backend, player_id, rolled)
            await deliver_due(session, narrator_client, player_id)
        elif message.get("type") == "approve_character":
            await handle_approve_character(session, store, narrator_client, image_backend, player_id, message,
                                           tts_backend=tts_backend)
        else:
            handle_message(session, message, player_id)

    @app.websocket("/ws/{session_id}/{player_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str, player_id: str) -> None:
        await websocket.accept()
        if session_id not in sessions:
            sessions[session_id] = store.load(session_id) or Session(session_id=session_id)
        session = sessions[session_id]
        manager.connect(session_id, player_id, websocket)
        if player_id in session.characters:
            # A returning player (refresh, server restart, second tab) gets the game straight away instead of a join form.
            await websocket.send_json(build_view(session, player_id))

        try:
            while True:
                try:
                    message = await websocket.receive_json()
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"invalid message: {e}"})
                    continue

                if message.get("type") == "join":
                    character_id = (message.get("character") or {}).get("player_id")
                    if character_id != player_id:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"character.player_id {character_id!r} does not match connection player_id {player_id!r}",
                        })
                        continue

                # One turn at a time per session (dry run 2026-11-06: two players acting at once ran two narrations
                # in parallel, each written without the other). Others' messages wait here.
                async with locks.setdefault(session_id, asyncio.Lock()):
                    try:
                        await _handle(session, player_id, message)
                    except Exception as e:
                        await websocket.send_json({"type": "error", "message": str(e)})
                        continue
                    store.save(session)
                    await manager.broadcast(session_id, session)
        except WebSocketDisconnect:
            manager.disconnect(session_id, player_id, websocket)

    return app
