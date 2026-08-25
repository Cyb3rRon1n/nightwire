import json

import pytest

from engine.character import CharacterSheet
from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarratorClient
from narrator.tts_backend import VoiceOption
from server.narration import handle_action


def _fake_client(narration: str, tool: str | None = None, tool_args: dict | None = None, image_prompt: str | None = None) -> NarratorClient:
    async def chat_fn(*, model, messages, format):
        tool_call = {"tool": tool} if tool is None else {"tool": tool, "tool_args": tool_args or {}}
        payload = {"narration": [{"speaker": "narrator", "text": narration}], "tool_call": tool_call}
        if image_prompt is not None:
            payload["image_request"] = {"prompt": image_prompt}
        return {"message": {"content": json.dumps(payload)}}

    async def generate_fn(**kwargs):
        pass

    return NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn)


def _fake_client_with_segments(segments: list[dict], tool: str | None = None, tool_args: dict | None = None) -> NarratorClient:
    async def chat_fn(*, model, messages, format):
        tool_call = {"tool": tool} if tool is None else {"tool": tool, "tool_args": tool_args or {}}
        return {"message": {"content": json.dumps({"narration": segments, "tool_call": tool_call})}}

    async def generate_fn(**kwargs):
        pass

    return NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn)


def _session_with_character() -> Session:
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(
        player_id="p1", name="Rook", role="solo", lifepath="streetkid", attributes={"reflexes": 14},
    )
    return session


def _session_with_two_characters() -> Session:
    session = _session_with_character()
    session.characters["someone-else"] = CharacterSheet(
        player_id="someone-else", name="Ghost", role="netrunner", lifepath="corpo",
        attributes={"reflexes": 20},
    )
    return session


class _UnusedImageBackend:
    async def generate_portrait(self, description):
        raise AssertionError("not exercised by this test")

    async def generate_scene(self, prompt, reference_paths):
        raise AssertionError("not exercised by this test")


class FakeTTSBackend:
    # A 3-voice bank, deliberately ordered so a gender=None speaker
    # (narrator falls back to the full bank, picks index 0) and a
    # gender="male" speaker (candidates = [voice-a, voice-b]) land on
    # different voices rather than coincidentally colliding on a 2-voice
    # bank - see assign_voice's "unused, else first match" rule (Task 5).
    voices = [
        VoiceOption(id="voice-neutral", gender="female"),
        VoiceOption(id="voice-a", gender="male"),
        VoiceOption(id="voice-b", gender="male"),
    ]

    def __init__(self, audio_bytes: bytes = b"fake-wav-bytes"):
        self.audio_bytes = audio_bytes
        self.calls = []
        self.unload_calls = 0

    async def synthesize(self, text: str, voice: str) -> bytes:
        self.calls.append((text, voice))
        return self.audio_bytes

    async def unload(self) -> None:
        self.unload_calls += 1


class _UnusedTTSBackend:
    # A single dummy voice, not an empty list - assign_voice() indexes
    # into whatever bank it's given, so an empty list would crash with
    # IndexError before synthesize()'s AssertionError ever fires.
    voices = [VoiceOption(id="unused", gender=None)]

    async def synthesize(self, text, voice):
        raise AssertionError("not exercised by this test")

    async def unload(self) -> None:
        pass


async def _call(session, client, player_id, message, tmp_path, image_backend=None, tts_backend=None):
    store = JSONFileSessionStore(tmp_path)
    await handle_action(
        session, client, store, image_backend or _UnusedImageBackend(),
        tts_backend or _UnusedTTSBackend(), player_id, message,
    )
    return store


@pytest.mark.asyncio
async def test_handle_action_appends_the_players_action_and_the_narration_to_the_log(tmp_path):
    session = _session_with_character()
    client = _fake_client("The alley is quiet.")
    tts_backend = FakeTTSBackend()

    await _call(session, client, "p1", {"text": "I look around."}, tmp_path, tts_backend=tts_backend)

    assert session.log[0] == "p1: I look around."
    assert session.log[1] == "The alley is quiet."
    assert session.log[2].startswith("[audio: ")


@pytest.mark.asyncio
async def test_handle_action_raises_on_missing_text(tmp_path):
    session = _session_with_character()
    client = _fake_client("ok")
    with pytest.raises(ValueError, match="missing 'text'"):
        await _call(session, client, "p1", {}, tmp_path)


@pytest.mark.asyncio
async def test_handle_action_executes_a_tool_call_and_logs_the_result(tmp_path):
    session = _session_with_character()
    client = _fake_client(
        "You lunge for the ledge.", tool="request_roll",
        tool_args={
            "player_id": "someone-else", "attribute": "reflexes", "skill": "athletics",
            "difficulty": "easy", "reason": "leap",
        },
    )

    await _call(session, client, "p1", {"text": "I leap the gap."}, tmp_path, tts_backend=FakeTTSBackend())

    assert any("request_roll" in line for line in session.log)


@pytest.mark.asyncio
async def test_handle_action_grounds_the_narrator_in_real_player_ids(tmp_path):
    # apply_character_update trusts the model's player_id as-is (it may
    # legitimately target a teammate, not just the actor) - so the model
    # needs the real roster up front, not just whatever it can infer from
    # log lines a player has already spoken. Regression check for a live
    # probe where the model invented "player" instead of the real "p1" on
    # a session's very first turn, when the log had nothing to infer from.
    session = _session_with_two_characters()
    sent_messages = []

    async def chat_fn(*, model, messages, format):
        sent_messages.append(messages)
        payload = {"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None}}
        return {"message": {"content": json.dumps(payload)}}

    async def generate_fn(**kwargs):
        pass

    client = NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn)
    await _call(session, client, "p1", {"text": "I look around."}, tmp_path, tts_backend=FakeTTSBackend())

    content = sent_messages[0][-1]["content"]
    assert "p1 (Rook)" in content
    assert "someone-else (Ghost)" in content


@pytest.mark.asyncio
async def test_handle_action_overrides_the_models_player_id_for_request_roll(tmp_path):
    # Server-authoritative: the acting player_id always wins for request_roll,
    # regardless of what the model put in tool_args. p1 has reflexes 14
    # (modifier 2); someone-else has reflexes 20 (modifier 5). If the
    # override were ever removed, the roll would use someone-else's
    # attribute_mod of 5 instead of the actual actor's 2.
    session = _session_with_two_characters()
    client = _fake_client(
        "You lunge for the ledge.", tool="request_roll",
        tool_args={
            "player_id": "someone-else", "attribute": "reflexes", "skill": "athletics",
            "difficulty": "easy", "reason": "leap",
        },
    )

    await _call(session, client, "p1", {"text": "I leap the gap."}, tmp_path, tts_backend=FakeTTSBackend())

    result_line = next(line for line in session.log if "request_roll" in line)
    assert "'attribute_mod': 2" in result_line
    assert "'attribute_mod': 5" not in result_line


@pytest.mark.asyncio
async def test_handle_action_logs_a_tool_error_without_raising(tmp_path):
    session = _session_with_character()
    client = _fake_client(
        "You reach for your gear.", tool="apply_character_update",
        tool_args={"player_id": "ghost"},
    )

    await _call(session, client, "p1", {"text": "I check my gear."}, tmp_path, tts_backend=FakeTTSBackend())

    assert any("tool error" in line for line in session.log)


@pytest.mark.asyncio
async def test_handle_action_with_no_tool_call_only_logs_narration(tmp_path):
    session = _session_with_character()
    client = _fake_client("The street is empty.")
    tts_backend = FakeTTSBackend()

    await _call(session, client, "p1", {"text": "I look around."}, tmp_path, tts_backend=tts_backend)

    assert session.log[0] == "p1: I look around."
    assert session.log[1] == "The street is empty."
    assert session.log[2].startswith("[audio: ")


@pytest.mark.asyncio
async def test_handle_action_generates_a_scene_image_and_logs_its_path(tmp_path):
    session = _session_with_character()
    client = _fake_client("The alley opens onto a neon plaza.", image_prompt="a neon cyberpunk plaza")

    class FakeImageBackend:
        async def generate_portrait(self, description):
            raise AssertionError("not exercised by this test")

        async def generate_scene(self, prompt, reference_paths):
            assert prompt == "a neon cyberpunk plaza"
            return b"fake-scene-bytes"

    store = await _call(
        session, client, "p1", {"text": "I step into the plaza."}, tmp_path,
        FakeImageBackend(), tts_backend=FakeTTSBackend(),
    )

    image_line = next(line for line in session.log if line.startswith("[image: "))
    image_path = image_line.removeprefix("[image: ").removesuffix("]")
    assert (store.directory / image_path).read_bytes() == b"fake-scene-bytes"


@pytest.mark.asyncio
async def test_handle_action_unloads_the_tts_backend_before_generating_a_scene_image(tmp_path):
    # Real, live-verified need: on an 8GB card, a resident local TTS backend's
    # own VRAM footprint was enough by itself to push scene-image generation's
    # peak VAE-decode allocation into a CUDA OOM. Mirrors the existing
    # narrator_client.unload() swap-dance.
    session = _session_with_character()
    client = _fake_client("The alley opens onto a neon plaza.", image_prompt="a neon cyberpunk plaza")
    tts_backend = FakeTTSBackend()

    class FakeImageBackend:
        async def generate_portrait(self, description):
            raise AssertionError("not exercised by this test")

        async def generate_scene(self, prompt, reference_paths):
            assert tts_backend.unload_calls == 1, "tts backend must be unloaded before generating"
            return b"fake-scene-bytes"

    await _call(
        session, client, "p1", {"text": "I step into the plaza."}, tmp_path,
        FakeImageBackend(), tts_backend=tts_backend,
    )

    assert tts_backend.unload_calls == 1


@pytest.mark.asyncio
async def test_handle_action_suppresses_image_request_two_turns_in_a_row(tmp_path):
    # The model is told "never two turns in a row" but has no cross-call way
    # to enforce it - live probing found it violated on 3/3 consecutive
    # turns in one run. This is the server-side backstop.
    session = _session_with_character()
    client = _fake_client("A neon plaza unfolds.", image_prompt="a neon cyberpunk plaza")

    class CountingImageBackend:
        calls = 0

        async def generate_portrait(self, description):
            raise AssertionError("not exercised by this test")

        async def generate_scene(self, prompt, reference_paths):
            type(self).calls += 1
            return b"x"

    image_backend = CountingImageBackend()

    await _call(session, client, "p1", {"text": "I step into the plaza."}, tmp_path, image_backend, tts_backend=FakeTTSBackend())
    assert session.last_turn_had_image is True
    assert CountingImageBackend.calls == 1

    await _call(session, client, "p1", {"text": "I look around some more."}, tmp_path, image_backend, tts_backend=FakeTTSBackend())
    assert CountingImageBackend.calls == 1, "image_request fired two turns in a row despite the cooldown"
    assert not any(line.startswith("[image: ") for line in session.log[-3:])
    assert session.last_turn_had_image is False

    await _call(session, client, "p1", {"text": "I step into another plaza."}, tmp_path, image_backend, tts_backend=FakeTTSBackend())
    assert CountingImageBackend.calls == 2, "cooldown should only block the immediately-following turn"


@pytest.mark.asyncio
async def test_handle_action_uses_the_actors_own_portrait_as_a_reference(tmp_path):
    session = _session_with_character()
    session.characters["p1"].portrait_path = "portraits/s1/p1.png"
    (tmp_path / "portraits" / "s1").mkdir(parents=True)
    (tmp_path / "portraits" / "s1" / "p1.png").write_bytes(b"portrait-bytes")
    client = _fake_client("A figure steps forward.", image_prompt="a scene")

    seen = {}

    class FakeImageBackend:
        async def generate_portrait(self, description):
            raise AssertionError("not exercised by this test")

        async def generate_scene(self, prompt, reference_paths):
            seen["reference_paths"] = reference_paths
            return b"x"

    await _call(
        session, client, "p1", {"text": "I step forward."}, tmp_path,
        FakeImageBackend(), tts_backend=FakeTTSBackend(),
    )

    assert seen["reference_paths"] == [str(tmp_path / "portraits" / "s1" / "p1.png")]


@pytest.mark.asyncio
async def test_handle_action_logs_an_image_error_without_raising(tmp_path):
    session = _session_with_character()
    client = _fake_client("The scene shifts.", image_prompt="a scene")

    class FailingImageBackend:
        async def generate_portrait(self, description):
            raise AssertionError("not exercised by this test")

        async def generate_scene(self, prompt, reference_paths):
            raise ValueError("worker unreachable")

    await _call(
        session, client, "p1", {"text": "I look up."}, tmp_path,
        FailingImageBackend(), tts_backend=FakeTTSBackend(),
    )

    assert any("image error" in line for line in session.log)


@pytest.mark.asyncio
async def test_handle_action_logs_one_line_per_narration_segment(tmp_path):
    session = _session_with_character()
    client = _fake_client_with_segments([
        {"speaker": "narrator", "text": "The alley reeks of ozone."},
        {"speaker": "Jax", "gender": "male", "text": "You're late, choom."},
    ])

    await _call(session, client, "p1", {"text": "I check the alley."}, tmp_path, tts_backend=FakeTTSBackend())

    assert session.log[0] == "p1: I check the alley."
    assert session.log[1] == "The alley reeks of ozone."
    assert session.log[2].startswith("[audio: ")
    assert session.log[3] == "Jax: You're late, choom."
    assert session.log[4].startswith("[audio: ")


@pytest.mark.asyncio
async def test_handle_action_synthesizes_audio_for_each_segment_and_tags_the_log(tmp_path):
    session = _session_with_character()
    client = _fake_client_with_segments([
        {"speaker": "narrator", "text": "The alley reeks of ozone."},
        {"speaker": "Jax", "gender": "male", "text": "You're late, choom."},
    ])
    tts_backend = FakeTTSBackend()

    store = await _call(session, client, "p1", {"text": "I check the alley."}, tmp_path, tts_backend=tts_backend)

    audio_lines = [line for line in session.log if line.startswith("[audio: ")]
    assert len(audio_lines) == 2
    for line in audio_lines:
        relative_path = line.removeprefix("[audio: ").removesuffix("]")
        assert (store.directory / relative_path).read_bytes() == b"fake-wav-bytes"
    assert tts_backend.calls == [
        ("The alley reeks of ozone.", "voice-neutral"),
        ("You're late, choom.", "voice-a"),
    ]


@pytest.mark.asyncio
async def test_handle_action_reuses_the_same_voice_for_a_returning_speaker(tmp_path):
    session = _session_with_character()
    client = _fake_client_with_segments([{"speaker": "Jax", "gender": "male", "text": "First line."}])
    tts_backend = FakeTTSBackend()
    await _call(session, client, "p1", {"text": "..."}, tmp_path, tts_backend=tts_backend)
    first_voice = tts_backend.calls[0][1]

    client2 = _fake_client_with_segments([{"speaker": "Jax", "text": "Second line, no gender given this time."}])
    await _call(session, client2, "p1", {"text": "..."}, tmp_path, tts_backend=tts_backend)

    assert tts_backend.calls[1][1] == first_voice


@pytest.mark.asyncio
async def test_handle_action_logs_an_audio_error_without_raising(tmp_path):
    session = _session_with_character()
    client = _fake_client_with_segments([{"speaker": "narrator", "text": "The scene shifts."}])

    class FailingTTSBackend:
        voices = [VoiceOption(id="unused", gender=None)]

        async def synthesize(self, text, voice):
            raise ValueError("tts server unreachable")

    await _call(session, client, "p1", {"text": "..."}, tmp_path, tts_backend=FailingTTSBackend())

    assert any("audio error" in line for line in session.log)
