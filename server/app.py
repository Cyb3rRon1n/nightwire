from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarratorClient
from narrator.image_backend import ImageBackend
from narrator.tts_backend import TTSBackend
from server.connection_manager import ConnectionManager
from server.dispatch import handle_message
from server.narration import handle_action
from server.portrait import handle_approve_character


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
    manager = ConnectionManager()
    sessions: dict[str, Session] = {}  # ponytail: single-process; needs a real store if ever multi-worker

    @app.websocket("/ws/{session_id}/{player_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str, player_id: str) -> None:
        await websocket.accept()
        if session_id not in sessions:
            sessions[session_id] = store.load(session_id) or Session(session_id=session_id)
        session = sessions[session_id]
        manager.connect(session_id, player_id, websocket)

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

                try:
                    if message.get("type") == "action":
                        await handle_action(session, narrator_client, store, image_backend, tts_backend, player_id, message)
                    elif message.get("type") == "approve_character":
                        await handle_approve_character(session, store, narrator_client, image_backend, player_id)
                    else:
                        handle_message(session, message, player_id)
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
                    continue

                store.save(session)
                await manager.broadcast(session_id, session)
        except WebSocketDisconnect:
            manager.disconnect(session_id, player_id, websocket)

    return app
