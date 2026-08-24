import json

from fastapi.testclient import TestClient

from engine.persistence import JSONFileSessionStore
from narrator.client import NarratorClient
from narrator.tts_backend import VoiceOption
from server.app import create_app


async def _unused_chat_fn(*, model, messages, format):
    raise AssertionError("narrator should not be called by this test")


async def _unused_generate_fn(**kwargs):
    raise AssertionError("unload should not be called by this test")


class _UnusedImageBackend:
    async def generate_portrait(self, description):
        raise AssertionError("image backend should not be called by this test")

    async def generate_scene(self, prompt, reference_paths):
        raise AssertionError("image backend should not be called by this test")


class _UnusedTTSBackend:
    # A single dummy voice, not an empty list - assign_voice() (Task 5)
    # indexes into whatever voice bank it's given, so an empty list would
    # crash with IndexError before synthesize()'s AssertionError ever
    # fires. This backend is only safe to use with tests that never send
    # an "action" message at all.
    voices = [VoiceOption(id="unused", gender=None)]

    async def synthesize(self, text, voice):
        raise AssertionError("tts backend should not be called by this test")


class FakeTTSBackend:
    voices = [VoiceOption(id="af_heart", gender="female")]

    async def synthesize(self, text, voice):
        return b"fake-wav-bytes"


def _client(tmp_path, narrator_client=None, image_backend=None, tts_backend=None):
    store = JSONFileSessionStore(tmp_path)
    client = narrator_client or NarratorClient(chat_fn=_unused_chat_fn, generate_fn=_unused_generate_fn)
    backend = image_backend or _UnusedImageBackend()
    tts = tts_backend or _UnusedTTSBackend()
    return TestClient(create_app(store, client, backend, tts))


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
            "narration": [{"speaker": "narrator", "text": "The alley is quiet."}], "tool_call": {"tool": None},
        })}}
    narrator_client = NarratorClient(chat_fn=chat_fn)
    client = _client(tmp_path, narrator_client, tts_backend=FakeTTSBackend())

    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

        ws.send_json({"type": "action", "text": "I look around."})
        view = ws.receive_json()

    assert "The alley is quiet." in view["log"]


def test_action_message_with_a_narration_segment_synthesizes_audio(tmp_path):
    async def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps({
            "narration": [{"speaker": "narrator", "text": "The alley is quiet."}],
            "tool_call": {"tool": None},
        })}}
    narrator_client = NarratorClient(chat_fn=chat_fn)

    client = _client(tmp_path, narrator_client, tts_backend=FakeTTSBackend())

    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

        ws.send_json({"type": "action", "text": "I look around."})
        view = ws.receive_json()

    assert any(line.startswith("[audio: ") for line in view["log"])


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


def test_approve_character_generates_and_broadcasts_a_portrait(tmp_path):
    generate_calls = []

    async def generate_fn(**kwargs):
        generate_calls.append(kwargs)

    narrator_client = NarratorClient(chat_fn=_unused_chat_fn, generate_fn=generate_fn)

    class FakeImageBackend:
        async def generate_portrait(self, description):
            assert "Rook" in description
            return b"fake-portrait-bytes"

        async def generate_scene(self, prompt, reference_paths):
            raise AssertionError("not exercised by this test")

    client = _client(tmp_path, narrator_client, FakeImageBackend())

    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

        ws.send_json({"type": "approve_character"})
        view = ws.receive_json()

    assert generate_calls == [{"model": narrator_client.model, "keep_alive": 0}]
    portrait_path = view["characters"]["p1"]["portrait_path"]
    assert portrait_path is not None
    assert (tmp_path / portrait_path).read_bytes() == b"fake-portrait-bytes"


def test_approve_character_without_a_joined_character_sends_an_error(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({"type": "approve_character"})
        error = ws.receive_json()

    assert error["type"] == "error"
