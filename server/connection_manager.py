from typing import Protocol

from engine.session import Session
from server.views import build_view


class SendsJSON(Protocol):
    async def send_json(self, data: dict) -> None: ...


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, dict[str, SendsJSON]] = {}

    def connect(self, session_id: str, player_id: str, connection: SendsJSON) -> None:
        self._connections.setdefault(session_id, {})[player_id] = connection

    def disconnect(self, session_id: str, player_id: str) -> None:
        self._connections.get(session_id, {}).pop(player_id, None)

    async def broadcast(self, session_id: str, session: Session) -> None:
        for player_id, connection in self._connections.get(session_id, {}).items():
            await connection.send_json(build_view(session, player_id))
