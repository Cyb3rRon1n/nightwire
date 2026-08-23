import json

from fastapi.testclient import TestClient

from engine.persistence import JSONFileSessionStore
from narrator.client import NarratorClient
from server.app import create_app


async def _unused_chat_fn(*, model, messages, format):
    raise AssertionError("narrator should not be called by this test")


def _client(tmp_path, narrator_client=None):
    store = JSONFileSessionStore(tmp_path)
    client = narrator_client or NarratorClient(chat_fn=_unused_chat_fn)
    return TestClient(create_app(store, client))


def test_join_broadcasts_a_filtered_view_back_to_the_sender(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        view = ws.receive_json()

    assert view["characters"]["p1"]["name"] == "Rook"
    assert view["session_id"] == "s1"


def test_second_player_join_broadcasts_a_redacted_view_to_the_first(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws1:
        ws1.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws1.receive_json()  # p1's own join broadcast

        with client.websocket_connect("/ws/s1/p2") as ws2:
            ws2.send_json({
                "type": "join",
                "character": {"player_id": "p2", "name": "Ghost", "role": "netrunner", "lifepath": "corpo"},
            })
            ws2.receive_json()  # p2's own join broadcast

            view = ws1.receive_json()  # p1 re-broadcast after p2 joins

    assert "inventory" not in view["characters"]["p2"]
    assert view["characters"]["p2"]["name"] == "Ghost"


def test_invalid_message_sends_an_error_without_closing_the_connection(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({"type": "nonsense"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "unknown message type" in error["message"]

        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        view = ws.receive_json()
        assert view["characters"]["p1"]["name"] == "Rook"


def test_join_with_a_character_id_not_matching_the_url_is_rejected(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "someone-else", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "does not match" in error["message"]


def test_two_connections_to_the_same_session_share_state(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws1, client.websocket_connect("/ws/s1/p2") as ws2:
        ws1.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws1.receive_json()  # p1's own join broadcast

        ws2.send_json({
            "type": "join",
            "character": {"player_id": "p2", "name": "Ghost", "role": "netrunner", "lifepath": "corpo"},
        })
        ws2.receive_json()  # p2's own join broadcast
        ws1.receive_json()  # p1 re-broadcast after p2 joins

        # p1 (the first connection) mutates the session.
        ws1.send_json({"type": "advance_turn"})
        view1 = ws1.receive_json()
        view2 = ws2.receive_json()

    # Both connections' views must still contain both characters — a private
    # per-connection Session would drop p2 from p1's broadcast and vice versa.
    assert "p1" in view1["characters"]
    assert "p2" in view1["characters"]
    assert "p1" in view2["characters"]
    assert "p2" in view2["characters"]


def test_state_persists_across_a_reconnect(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({"type": "advance_turn"})
        view = ws.receive_json()

    assert "p1" in view["characters"]


def test_action_message_triggers_the_narrator_and_broadcasts_narration(tmp_path):
    async def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps({
            "narration": "The alley is quiet.", "tool_call": {"tool": None},
        })}}
    narrator_client = NarratorClient(chat_fn=chat_fn)
    client = _client(tmp_path, narrator_client)

    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

        ws.send_json({"type": "action", "text": "I look around."})
        view = ws.receive_json()

    assert "The alley is quiet." in view["log"]


def test_action_message_missing_text_sends_an_error(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

        ws.send_json({"type": "action"})
        error = ws.receive_json()

    assert error["type"] == "error"
    assert "text" in error["message"]
