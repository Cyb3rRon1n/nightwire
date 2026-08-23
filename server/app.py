from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from server.connection_manager import ConnectionManager
from server.dispatch import handle_message


def create_app(store: JSONFileSessionStore) -> FastAPI:
    app = FastAPI()
    manager = ConnectionManager()

    @app.websocket("/ws/{session_id}/{player_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str, player_id: str) -> None:
        await websocket.accept()
        session = store.load(session_id) or Session(session_id=session_id)
        manager.connect(session_id, player_id, websocket)

        try:
            while True:
                message = await websocket.receive_json()

                if message.get("type") == "join":
                    character_id = (message.get("character") or {}).get("player_id")
                    if character_id != player_id:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"character.player_id {character_id!r} does not match connection player_id {player_id!r}",
                        })
                        continue

                try:
                    handle_message(session, message)
                except ValueError as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
                    continue

                store.save(session)
                await manager.broadcast(session_id, session)
        except WebSocketDisconnect:
            manager.disconnect(session_id, player_id)

    return app
