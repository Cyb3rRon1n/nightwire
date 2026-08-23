import pytest

from engine.character import CharacterSheet
from engine.session import Session
from server.connection_manager import ConnectionManager


class FakeConnection:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


def _session_with_two_players():
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    session.characters["p2"] = CharacterSheet(player_id="p2", name="Ghost", role="netrunner", lifepath="corpo")
    return session


@pytest.mark.asyncio
async def test_broadcast_sends_each_connection_its_own_filtered_view():
    manager = ConnectionManager()
    conn1, conn2 = FakeConnection(), FakeConnection()
    manager.connect("s1", "p1", conn1)
    manager.connect("s1", "p2", conn2)
    session = _session_with_two_players()

    await manager.broadcast("s1", session)

    assert conn1.sent[0]["characters"]["p1"]["name"] == "Rook"
    assert "inventory" in conn1.sent[0]["characters"]["p1"]
    assert "inventory" not in conn1.sent[0]["characters"]["p2"]
    assert conn2.sent[0]["characters"]["p2"]["name"] == "Ghost"


@pytest.mark.asyncio
async def test_broadcast_only_reaches_connections_in_that_session():
    manager = ConnectionManager()
    conn1 = FakeConnection()
    manager.connect("s1", "p1", conn1)
    other_session = Session(session_id="s2")

    await manager.broadcast("s2", other_session)

    assert conn1.sent == []


@pytest.mark.asyncio
async def test_disconnect_removes_the_connection_from_future_broadcasts():
    manager = ConnectionManager()
    conn1 = FakeConnection()
    manager.connect("s1", "p1", conn1)
    manager.disconnect("s1", "p1")
    session = _session_with_two_players()

    await manager.broadcast("s1", session)

    assert conn1.sent == []


def test_disconnect_of_an_unknown_connection_is_a_no_op():
    manager = ConnectionManager()
    manager.disconnect("never-connected", "p1")  # must not raise
