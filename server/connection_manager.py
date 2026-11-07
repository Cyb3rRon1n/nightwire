from typing import Protocol

from engine.session import Session
from server.views import build_view


class SendsJSON(Protocol):
    async def send_json(self, data: dict) -> None: ...


class ConnectionManager:
    """Every open connection per player, so a second tab (or a phone beside a laptop) doesn't silence the first."""

    def __init__(self) -> None:
        self._connections: dict[str, dict[str, list[SendsJSON]]] = {}

    def connect(self, session_id: str, player_id: str, connection: SendsJSON) -> None:
        self._connections.setdefault(session_id, {}).setdefault(player_id, []).append(connection)

    def disconnect(self, session_id: str, player_id: str, connection: SendsJSON | None = None) -> None:
        conns = self._connections.get(session_id, {})
        if connection is None:
            conns.pop(player_id, None)
            return
        tabs = conns.get(player_id, [])
        if connection in tabs:
            tabs.remove(connection)
        if not tabs:
            conns.pop(player_id, None)

    async def broadcast(self, session_id: str, session: Session) -> None:
        for player_id, tabs in list(self._connections.get(session_id, {}).items()):
            view = build_view(session, player_id)
            for connection in list(tabs):
                try:
                    await connection.send_json(view)
                except Exception:
                    self.disconnect(session_id, player_id, connection)
