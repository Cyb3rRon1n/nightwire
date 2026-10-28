import json

import httpx
import pytest

from engine.character import CharacterSheet
from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.anthropic_backend import AnthropicNarratorBackend
from narrator.client import NarratorClient
from narrator.openai_compat_backend import OpenAICompatNarratorBackend
from narrator.tts_backend import VoiceOption
from server.narration import handle_action


def _fake_client(narration: str, tool: str | None = None, tool_args: dict | None = None, image_prompt: str | None = None, num_ctx: int = 8192, summarize_fn=None) -> NarratorClient:
    async def chat_fn(*, model, messages, format):
        tool_call = {"tool": tool} if tool is None else {"tool": tool, "tool_args": tool_args or {}}
        payload = {"narration": [{"speaker": "narrator", "text": narration}], "tool_call": tool_call}
        if image_prompt is not None:
            payload["image_request"] = {"prompt": image_prompt}
        return {"message": {"content": json.dumps(payload)}}

    async def generate_fn(**kwargs):
        pass

    return NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn, num_ctx=num_ctx, summarize_fn=summarize_fn)


def _fake_client_with_segments(segments: list[dict], tool: str | None = None, tool_args: dict | None = None) -> NarratorClient:
    async def chat_fn(*, model, messages, format):
        tool_call = {"tool": tool} if tool is None else {"tool": tool, "tool_args": tool_args or {}}
        return {"message": {"content": json.dumps({"narration": segments, "tool_call": tool_call})}}

    async def generate_fn(**kwargs):
        pass

    return NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn)


def _fake_client_with_summary(narration: str, summary_text: str) -> NarratorClient:
    async def chat_fn(*, model, messages, format):
        payload = {"narration": [{"speaker": "narrator", "text": narration}], "tool_call": {"tool": None}}
        return {"message": {"content": json.dumps(payload)}}

    async def generate_fn(**kwargs):
        pass

    async def summarize_fn(*, model, messages):
        return {"message": {"content": summary_text}}

    return NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn, summarize_fn=summarize_fn, num_ctx=100)


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
async def test_request_roll_becomes_a_pending_roll_not_a_roll(tmp_path):
    session = _session_with_character()
    client = _fake_client(
        "You eye the ledge.", tool="request_roll",
        tool_args={
            "player_id": "someone-else", "attribute": "reflexes", "skill": "athletics",
            "difficulty": "hard", "reason": "leap the gap",
        },
    )

    await _call(session, client, "p1", {"text": "I leap the gap."}, tmp_path, tts_backend=FakeTTSBackend())

    pending = session.pending_rolls["p1"]
    assert pending["player_id"] == "p1"
    assert pending["skill"] == "athletics" and pending["difficulty"] == "hard"
    assert pending["dc"] == 12 and pending["name"] == "Rook"
    assert "You eye the ledge." in session.log
    pending_line = next(line for line in session.log if line.startswith("[roll pending: "))
    assert json.loads(pending_line[len("[roll pending: "):-1])["skill"] == "athletics"
    assert not any(line.startswith("[request_roll") for line in session.log)


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
async def test_pending_roll_is_keyed_to_the_actor_not_the_models_player_id(tmp_path):
    # Server-authoritative: the acting player always owns the roll they
    # triggered, whatever player_id the model put in tool_args.
    session = _session_with_two_characters()
    client = _fake_client(
        "You eye the ledge.", tool="request_roll",
        tool_args={
            "player_id": "someone-else", "attribute": "reflexes", "skill": "athletics",
            "difficulty": "easy", "reason": "leap",
        },
    )

    await _call(session, client, "p1", {"text": "I leap the gap."}, tmp_path, tts_backend=FakeTTSBackend())

    assert list(session.pending_rolls) == ["p1"]
    assert session.pending_rolls["p1"]["player_id"] == "p1"


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
async def test_handle_action_still_generates_image_when_tts_unload_fails(tmp_path):
    # Real bug found live: a dead/unreachable TTS backend's unload() raising
    # was caught by the same try/except wrapping generate_scene, silently
    # aborting image generation for a failure that had nothing to do with it.
    session = _session_with_character()
    client = _fake_client("The alley opens onto a neon plaza.", image_prompt="a neon cyberpunk plaza")

    class DeadTTSBackend:
        voices = [VoiceOption(id="unused", gender=None)]

        async def synthesize(self, text, voice):
            return b"fake-wav-bytes"

        async def unload(self) -> None:
            raise httpx.HTTPError("tts backend unreachable")

    class FakeImageBackend:
        async def generate_portrait(self, description):
            raise AssertionError("not exercised by this test")

        async def generate_scene(self, prompt, reference_paths):
            return b"fake-scene-bytes"

    store = await _call(
        session, client, "p1", {"text": "I step into the plaza."}, tmp_path,
        FakeImageBackend(), tts_backend=DeadTTSBackend(),
    )

    image_line = next(line for line in session.log if line.startswith("[image: "))
    image_path = image_line.removeprefix("[image: ").removesuffix("]")
    assert (store.directory / image_path).read_bytes() == b"fake-scene-bytes"


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
async def test_handle_action_logs_an_image_error_from_httpx_without_raising(tmp_path):
    # ComfyUIBackend's realistic failures (dead/unreachable instance, bad
    # checkpoint name) surface as httpx exceptions, not ValueError/TypeError/
    # OSError - those must be caught here too, or the whole turn (narration,
    # audio, tool call already applied) is lost when this propagates up to
    # server/app.py's outer handler.
    session = _session_with_character()
    client = _fake_client("The scene shifts.", image_prompt="a scene")

    class UnreachableImageBackend:
        async def generate_portrait(self, description):
            raise AssertionError("not exercised by this test")

        async def generate_scene(self, prompt, reference_paths):
            raise httpx.ConnectError("connection refused")

    store = await _call(
        session, client, "p1", {"text": "I look up."}, tmp_path,
        UnreachableImageBackend(), tts_backend=FakeTTSBackend(),
    )

    assert any("image error" in line for line in session.log)
    # The rest of the turn survived - narration is still there, not just the
    # error - matching what the caller (server/app.py) will store.save().
    assert any("The scene shifts." in line for line in session.log)
    assert store is not None


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


def test_select_verbatim_narrative_keeps_everything_under_budget():
    from server.narration import _select_verbatim_narrative

    narrative = ["short line one", "short line two"]
    # num_ctx=100 -> budget = int(100 * 0.55 * 4) = 220 chars, both lines fit
    result = _select_verbatim_narrative(narrative, num_ctx=100)

    assert result == narrative


def test_select_verbatim_narrative_drops_oldest_lines_past_budget():
    from server.narration import _select_verbatim_narrative

    # num_ctx=10 -> budget = int(10 * 0.55 * 4) = 22 chars
    narrative = ["a" * 20, "b" * 20, "c" * 20]
    result = _select_verbatim_narrative(narrative, num_ctx=10)

    # Only the most recent line(s) that fit within 22 chars survive, in order
    assert result == ["c" * 20]


def test_build_messages_includes_narrative_summary_when_present():
    from server.narration import _build_messages

    session = _session_with_character()
    session.narrative_summary = "Earlier, the party met a fixer named Jax."
    session.log = ["p1: I nod at Jax."]

    messages = _build_messages(session, "I ask Jax about the job.", num_ctx=8192)

    content = messages[0]["content"]
    assert "Summary of earlier events: Earlier, the party met a fixer named Jax." in content
    assert "Recent events:\np1: I nod at Jax." in content


def test_build_messages_omits_summary_section_when_empty():
    from server.narration import _build_messages

    session = _session_with_character()
    session.log = ["p1: I look around."]

    messages = _build_messages(session, "I move forward.", num_ctx=8192)

    assert "Summary of earlier events" not in messages[0]["content"]


@pytest.mark.asyncio
async def test_maybe_compact_does_nothing_when_nothing_excluded():
    from server.narration import _maybe_compact

    session = _session_with_character()
    session.log = ["p1: I look around.", "The alley is quiet."]
    client = _fake_client_with_summary("ok", "should not be called")

    await _maybe_compact(session, client)

    assert session.narrative_summary == ""
    assert session.narrative_summary_line_count == 0


@pytest.mark.asyncio
async def test_maybe_compact_summarizes_excluded_lines_once_budget_exceeded():
    from server.narration import _maybe_compact

    session = _session_with_character()
    # num_ctx=100 on the fake client -> budget = 260 chars; make the log
    # clearly exceed that so some lines are excluded from the verbatim window.
    session.log = [f"line {i}: " + ("x" * 30) for i in range(20)]
    client = _fake_client_with_summary("ok", "The party wandered the district for a while.")

    await _maybe_compact(session, client)

    assert session.narrative_summary == "The party wandered the district for a while."
    assert session.narrative_summary_line_count > 0


@pytest.mark.asyncio
async def test_maybe_compact_does_not_re_summarize_when_excluded_count_unchanged():
    from server.narration import _maybe_compact

    session = _session_with_character()
    session.log = [f"line {i}: " + ("x" * 30) for i in range(20)]
    client = _fake_client_with_summary("ok", "first summary")

    await _maybe_compact(session, client)
    first_summary = session.narrative_summary
    assert first_summary == "first summary"

    # Same client would return "first summary" again if called - but nothing
    # new was added to session.log, so a second call must be a no-op.
    await _maybe_compact(session, client)

    assert session.narrative_summary == first_summary


@pytest.mark.asyncio
async def test_maybe_compact_logs_summary_error_and_keeps_prior_summary_on_failure():
    from server.narration import _maybe_compact

    session = _session_with_character()
    session.log = [f"line {i}: " + ("x" * 30) for i in range(20)]
    session.narrative_summary = "an existing summary"
    session.narrative_summary_line_count = 0  # force the trigger to fire again

    async def failing_summarize_fn(*, model, messages):
        raise ValueError("model unavailable")

    async def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps({"narration": [], "tool_call": {"tool": None}})}}

    client = NarratorClient(chat_fn=chat_fn, summarize_fn=failing_summarize_fn, num_ctx=100)

    await _maybe_compact(session, client)

    assert session.narrative_summary == "an existing summary"
    assert any("[summary error:" in line for line in session.log)


@pytest.mark.asyncio
async def test_maybe_compact_catches_ollama_response_error():
    from server.narration import _maybe_compact
    import ollama

    session = _session_with_character()
    session.log = [f"line {i}: " + ("x" * 30) for i in range(20)]

    async def failing_summarize_fn(*, model, messages):
        raise ollama.ResponseError("model unavailable", status_code=500)

    client = NarratorClient(summarize_fn=failing_summarize_fn, num_ctx=100)

    await _maybe_compact(session, client)

    assert any("[summary error:" in line for line in session.log)


@pytest.mark.asyncio
async def test_maybe_compact_requires_threshold_growth_before_refiring():
    from server.narration import _maybe_compact

    session = _session_with_character()
    session.log = [f"line {i}: " + ("x" * 30) for i in range(20)]
    calls = []

    async def counting_summarize_fn(*, model, messages):
        calls.append(messages)
        return {"message": {"content": f"summary call {len(calls)}"}}

    client = NarratorClient(summarize_fn=counting_summarize_fn, num_ctx=100)

    await _maybe_compact(session, client)
    assert len(calls) == 1

    # Add one line - fewer than the hysteresis threshold - must NOT re-fire.
    session.log.append("a small addition")
    await _maybe_compact(session, client)
    assert len(calls) == 1

    # Add enough lines to cross the threshold - must re-fire.
    for i in range(20, 30):
        session.log.append(f"line {i}: " + ("x" * 30))
    await _maybe_compact(session, client)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_maybe_compact_caps_the_summarization_input_size():
    from server.narration import _maybe_compact, _MAX_SUMMARIZE_INPUT_CHARS

    session = _session_with_character()
    session.log = [f"line {i}: " + ("x" * 500) for i in range(200)]
    seen = {}

    async def summarize_fn(*, model, messages):
        seen["text_len"] = len(messages[1]["content"])
        return {"message": {"content": "a capped summary"}}

    client = NarratorClient(summarize_fn=summarize_fn, num_ctx=100)

    await _maybe_compact(session, client)

    assert seen["text_len"] <= _MAX_SUMMARIZE_INPUT_CHARS


@pytest.mark.asyncio
async def test_handle_action_skips_compaction_on_a_turn_that_generated_an_image(tmp_path):
    session = _session_with_character()
    session.log = [f"line {i}: " + ("x" * 30) for i in range(20)]
    calls = []

    async def counting_summarize_fn(*, model, messages):
        calls.append(messages)
        return {"message": {"content": "should not be called"}}

    client = _fake_client(
        "The alley opens onto a neon plaza.", image_prompt="a neon cyberpunk plaza",
        num_ctx=100, summarize_fn=counting_summarize_fn,
    )

    class FakeImageBackend:
        async def generate_portrait(self, description):
            raise AssertionError("not exercised by this test")

        async def generate_scene(self, prompt, reference_paths):
            return b"fake-scene-bytes"

    await _call(
        session, client, "p1", {"text": "I step into the plaza."}, tmp_path,
        FakeImageBackend(), tts_backend=FakeTTSBackend(),
    )

    assert calls == []
    assert session.narrative_summary_line_count == 0


class _FakeHTTPResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass


class _FakeHTTPClient:
    """Stands in for httpx.AsyncClient - only the method the hosted
    backends actually call (post)."""

    def __init__(self, response_json):
        self.response_json = response_json

    async def post(self, url, json=None, headers=None):
        return _FakeHTTPResponse(self.response_json)


# Finding 1 regression: server/narration.py reads narrator_client.num_ctx on
# every real player action (_build_messages, _maybe_compact). Neither new
# backend defined it, so this crashed with AttributeError on the very first
# turn after switching NARRATOR_BACKEND. A bare hasattr() check wouldn't
# have caught this shape of bug convincingly - runtime_checkable Protocol
# isinstance() checks don't verify plain attributes either - so these drive
# the real handle_action code path instead, against each new backend, with a
# fake HTTP client standing in for the network.
@pytest.mark.asyncio
async def test_handle_action_works_with_the_anthropic_backend(tmp_path):
    session = _session_with_character()
    fake_http = _FakeHTTPClient({
        "content": [{
            "type": "tool_use",
            "name": "narrator_response",
            "input": {
                "narration": [{"speaker": "narrator", "text": "The alley is quiet."}],
                "tool_call": {"tool": None},
            },
        }],
    })
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_http)

    store = await _call(session, backend, "p1", {"text": "I look around."}, tmp_path, tts_backend=FakeTTSBackend())

    assert session.log[0] == "p1: I look around."
    assert session.log[1] == "The alley is quiet."
    assert store is not None


@pytest.mark.asyncio
async def test_handle_action_works_with_the_openai_compat_backend(tmp_path):
    session = _session_with_character()
    payload = json.dumps({
        "narration": [{"speaker": "narrator", "text": "The alley is quiet."}],
        "tool_call": {"tool": None},
    })
    fake_http = _FakeHTTPClient({"choices": [{"message": {"content": payload}}]})
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_http)

    await _call(session, backend, "p1", {"text": "I look around."}, tmp_path, tts_backend=FakeTTSBackend())

    assert session.log[0] == "p1: I look around."
    assert session.log[1] == "The alley is quiet."


def test_select_npc_memory_for_context_keeps_everything_under_budget():
    from server.narration import _select_npc_memory_for_context

    session = Session(session_id="s1")
    session.npc_memory = {"Jax": ["offered a job"], "Mora": ["bypassed a lock"]}

    result = _select_npc_memory_for_context(session, num_ctx=8192)

    assert result == session.npc_memory


def test_select_npc_memory_for_context_drops_everything_past_a_tiny_budget():
    from server.narration import _select_npc_memory_for_context

    # num_ctx=10 -> budget = int(10 * 0.05 * 4) = 2 chars - nothing fits.
    session = Session(session_id="s1")
    session.npc_memory = {"Jax": ["a fact"], "Mora": ["another fact"]}

    result = _select_npc_memory_for_context(session, num_ctx=10)

    assert result == {}


def test_select_npc_memory_keeps_the_most_recently_touched_when_over_budget():
    from narrator.tools import execute_tool
    from server.narration import _select_npc_memory_for_context

    session = Session(session_id="s1")
    for i in range(14):
        execute_tool(session, "remember_npc", {"name": f"npc{i:02d}", "fact": "x" * 150})

    result = _select_npc_memory_for_context(session, num_ctx=8192)

    assert list(result) == [f"npc{i:02d}" for i in range(4, 14)]


def test_build_messages_includes_known_npcs_when_present():
    from server.narration import _build_messages

    session = _session_with_character()
    session.npc_memory = {"Jax": ["offered the party a job"]}
    session.log = ["p1: I look around."]

    messages = _build_messages(session, "I ask about Jax.", num_ctx=8192)

    assert "Known NPCs:\nJax: offered the party a job" in messages[0]["content"]


def test_build_messages_omits_known_npcs_when_empty():
    from server.narration import _build_messages

    session = _session_with_character()
    session.log = ["p1: I look around."]

    messages = _build_messages(session, "I move forward.", num_ctx=8192)

    assert "Known NPCs" not in messages[0]["content"]


def test_build_messages_puts_scene_and_world_notes_right_before_the_action():
    from narrator.world import kuroshio
    from server.narration import _build_messages

    session = _session_with_character()
    session.location = "Ikebe Low - Mama Sato's izakaya"
    session.scene_mood = "tense"
    session.active_objectives = ["find the chrome-ya", "pay off the torite"]
    session.log = ["p1: I look around."]
    ikebe = next(d.card for d in kuroshio().districts if d.name == "Ikebe Low")
    sato = next(n.card for n in kuroshio().npcs if n.name == "Mama Sato")

    content = _build_messages(session, "I order a drink.", num_ctx=8192)[0]["content"]

    assert content.endswith(
        "Recent events:\np1: I look around.\n\n"
        "Scene: Ikebe Low - Mama Sato's izakaya · mood: tense · objectives: find the chrome-ya; pay off the torite\n\n"
        f"World notes:\n{ikebe}\n{sato}\n\n"
        "Player action: I order a drink."
    )


def test_scene_line_drops_empty_parts():
    from server.narration import _scene_line

    session = _session_with_character()
    session.scene_mood = "quiet"

    assert _scene_line(session) == "Scene: mood: quiet"


def test_scene_line_keeps_only_last_five_objectives():
    from server.narration import _scene_line

    session = _session_with_character()
    session.active_objectives = [f"obj{i:02d}" for i in range(20)]

    line = _scene_line(session)

    assert "obj14; obj15; obj16; obj17; obj18; obj19" not in line
    assert line == "Scene: objectives: obj15; obj16; obj17; obj18; obj19"


def test_scene_line_truncates_long_fields():
    from server.narration import _scene_line

    session = _session_with_character()
    session.location = "L" * 500
    session.scene_mood = "M" * 500
    session.active_objectives = ["O" * 500]

    line = _scene_line(session)

    assert line == f"Scene: {'L' * 120} · mood: {'M' * 120} · objectives: {'O' * 120}"


def test_build_messages_omits_scene_and_world_notes_when_nothing_applies():
    from server.narration import _build_messages

    session = _session_with_character()
    session.log = ["p1: I look around."]

    content = _build_messages(session, "I move forward.", num_ctx=8192)[0]["content"]

    assert "Scene:" not in content
    assert "World notes:" not in content


def test_build_messages_world_notes_from_mentions_without_location():
    from narrator.world import kuroshio
    from server.narration import _build_messages

    session = _session_with_character()
    loop = next(d.card for d in kuroshio().districts if d.name == "The Loop")

    content = _build_messages(session, "I ride out onto the Loop.", num_ctx=8192)[0]["content"]

    assert f"World notes:\n{loop}\n\nPlayer action: I ride out onto the Loop." in content
    assert "Scene:" not in content


@pytest.mark.asyncio
async def test_action_is_refused_while_that_players_roll_is_pending(tmp_path):
    session = _session_with_character()
    session.pending_rolls["p1"] = {"player_id": "p1"}
    client = _fake_client("unused")

    with pytest.raises(ValueError, match="roll first"):
        await _call(session, client, "p1", {"text": "I run."}, tmp_path)


@pytest.mark.asyncio
async def test_other_players_can_act_while_one_roll_is_pending(tmp_path):
    session = _session_with_two_characters()
    session.pending_rolls["p1"] = {"player_id": "p1"}
    client = _fake_client("Ghost waits.")

    await _call(session, client, "someone-else", {"text": "I wait."}, tmp_path, tts_backend=FakeTTSBackend())

    assert "Ghost waits." in session.log


async def _roll(session, client, player_id, tmp_path, tts_backend=None):
    from server.narration import handle_roll

    store = JSONFileSessionStore(tmp_path)
    await handle_roll(session, client, store, _UnusedImageBackend(), tts_backend or FakeTTSBackend(), player_id)
    return store


def _pending(session, difficulty="hard", dc=16):
    session.pending_rolls["p1"] = {
        "player_id": "p1", "attribute": "reflexes", "skill": "stealth",
        "difficulty": difficulty, "reason": "slip past the guard", "dc": dc, "name": "Rook",
    }


@pytest.mark.asyncio
async def test_roll_with_nothing_pending_is_refused(tmp_path):
    session = _session_with_character()

    with pytest.raises(ValueError, match="no roll pending"):
        await _roll(session, _fake_client("unused"), "p1", tmp_path)


@pytest.mark.asyncio
async def test_roll_resolves_logs_visible_line_and_clears_pending(tmp_path, monkeypatch):
    session = _session_with_character()  # reflexes 14 -> modifier +2, stealth rank 0
    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 7)

    await _roll(session, _fake_client("The guard never turns."), "p1", tmp_path)

    assert "p1" not in session.pending_rolls
    assert "Rook rolls Stealth (Reflexes) vs Hard: a failure (7 +2 +0 = 9 vs 12)." in session.log
    roll_line = next(line for line in session.log if line.startswith("[roll: "))
    data = json.loads(roll_line[len("[roll: "):-1])
    assert data["die_result"] == 7 and data["outcome"] == "failure" and data["skill"] == "stealth"
    assert "The guard never turns." in session.log


@pytest.mark.asyncio
async def test_natural_ten_and_one_are_called_out(tmp_path, monkeypatch):
    session = _session_with_character()
    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 10)
    await _roll(session, _fake_client("ok"), "p1", tmp_path)
    assert any(line.endswith("vs 12) — a natural 10.") and "a clean success" in line for line in session.log)

    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 1)
    await _roll(session, _fake_client("ok"), "p1", tmp_path)
    assert any(line.endswith("vs 12) — a natural 1.") and "a failure" in line for line in session.log)


@pytest.mark.asyncio
async def test_resolution_prompt_contains_the_result(tmp_path, monkeypatch):
    session = _session_with_character()
    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 7)
    sent = []

    async def chat_fn(*, model, messages, format):
        sent.append(messages)
        payload = {"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None}}
        return {"message": {"content": json.dumps(payload)}}

    async def generate_fn(**kwargs):
        pass

    await _roll(session, NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn), "p1", tmp_path)

    content = sent[0][-1]["content"]
    assert "Roll result for Rook: a failure on slip past the guard." in content
    assert "Rook rolls Stealth (Reflexes) vs Hard: a failure" in content


@pytest.mark.asyncio
async def test_no_new_roll_during_a_resolution(tmp_path, monkeypatch):
    session = _session_with_character()
    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 7)
    client = _fake_client(
        "The guard spins.", tool="request_roll",
        tool_args={"player_id": "p1", "attribute": "reflexes", "skill": "athletics", "difficulty": "easy", "reason": "dodge"},
    )

    await _roll(session, client, "p1", tmp_path)

    assert session.pending_rolls == {}
    assert "[tool error: no new rolls during a roll resolution]" in session.log


@pytest.mark.asyncio
async def test_resolution_can_apply_consequences(tmp_path, monkeypatch):
    session = _session_with_character()
    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 2)
    client = _fake_client(
        "The guard's baton cracks your ribs.", tool="apply_character_update",
        tool_args={"player_id": "p1", "health_delta": -20},
    )

    await _roll(session, client, "p1", tmp_path)

    assert session.characters["p1"].health == 80


def test_resolve_roll_returns_merged_result_and_logs_lines(monkeypatch):
    from server.narration import resolve_roll

    session = _session_with_character()
    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 7)

    rolled = resolve_roll(session, "p1")

    assert "p1" not in session.pending_rolls
    assert rolled["die_result"] == 7 and rolled["outcome"] == "failure" and rolled["skill"] == "stealth"
    assert "Rook rolls Stealth (Reflexes) vs Hard: a failure (7 +2 +0 = 9 vs 12)." in session.log
    assert any(line.startswith("[roll: ") for line in session.log)


def test_resolve_roll_keeps_pending_roll_if_execute_tool_fails():
    import pytest
    from server.narration import resolve_roll

    session = _session_with_character()
    _pending(session)
    del session.characters["p1"]

    with pytest.raises(ValueError):
        resolve_roll(session, "p1")

    assert "p1" in session.pending_rolls


@pytest.mark.asyncio
async def test_overclocked_roll_charges_humanity_and_names_it(tmp_path, monkeypatch):
    from server.narration import resolve_roll

    session = _session_with_character()
    session.characters["p1"].chrome = ["kagerou"]
    _pending(session)
    rolls = iter([4, 9, 3])  # d10, second d10, 1d6 humanity
    monkeypatch.setattr("random.randint", lambda a, b: next(rolls))  # both modules use the random module

    rolled = resolve_roll(session, "p1", overclock="kagerou")

    assert rolled["overclock"] == "kagerou" and rolled["humanity_loss"] == 3
    assert session.characters["p1"].humanity == 97
    assert any(line.startswith("Rook overclocks Kagerou (−3 humanity) and rolls Stealth (Reflexes) vs Hard:")
               and "(9 +2 +0 +2 = 13 vs 12)" in line for line in session.log)


def test_overclock_not_usable_on_this_roll_is_refused_and_roll_stays_pending():
    from server.narration import resolve_roll

    session = _session_with_character()
    session.characters["p1"].chrome = ["yomi_jack"]
    _pending(session)  # stealth, not hacking
    with pytest.raises(ValueError, match="overclock"):
        resolve_roll(session, "p1", overclock="yomi_jack")
    assert "p1" in session.pending_rolls


def test_crew_line_and_world_event_sit_before_the_action():
    from server.narration import _build_messages

    session = _session_with_character()
    session.characters["p1"].humanity = 62
    session.characters["p1"].chrome = ["kagerou", "hawkeye_optics"]
    session.pending_world_events.append("Rook is slipping.")

    content = _build_messages(session, "I wait.", num_ctx=8192)[0]["content"]

    assert "Crew: Rook: humanity 62 (Frayed), chrome: Kagerou, Hawkeye optics" in content
    assert "World event: Rook is slipping." in content
    assert content.index("World event:") < content.index("Player action: I wait.")
    assert session.pending_world_events == ["Rook is slipping."]  # cleared by the turn, not the prompt build


@pytest.mark.asyncio
async def test_world_events_clear_after_a_successful_turn_but_keep_ones_queued_mid_turn(tmp_path):
    session = _session_with_character()
    session.pending_world_events.append("old event")
    client = _fake_client("ok")
    orig = client.respond

    async def respond(messages):
        session.pending_world_events.append("mid-turn event")
        return await orig(messages)

    client.respond = respond
    await _call(session, client, "p1", {"text": "I wait."}, tmp_path, tts_backend=FakeTTSBackend())
    assert session.pending_world_events == ["mid-turn event"]


@pytest.mark.asyncio
async def test_world_events_survive_a_failed_narrator_call(tmp_path):
    session = _session_with_character()
    session.pending_world_events.append("old event")
    client = _fake_client("ok")

    async def boom(messages):
        raise ValueError("narrator down")

    client.respond = boom
    with pytest.raises(ValueError):
        await _call(session, client, "p1", {"text": "I wait."}, tmp_path)
    assert session.pending_world_events == ["old event"]


def test_overclock_humanity_loss_is_the_actual_change_not_the_raw_die(monkeypatch):
    from server.narration import resolve_roll

    session = _session_with_character()
    session.characters["p1"].chrome = ["kagerou"]
    session.characters["p1"].humanity = 3
    _pending(session)
    rolls = iter([4, 9, 5])  # d10, second d10, 1d6
    monkeypatch.setattr("random.randint", lambda a, b: next(rolls))

    rolled = resolve_roll(session, "p1", overclock="kagerou")

    assert rolled["humanity_loss"] == 3
    assert session.characters["p1"].humanity == 0
    assert any("(−3 humanity)" in line for line in session.log)


def test_overclock_refused_while_gone_too_far_and_roll_stays_pending():
    from server.narration import resolve_roll

    session = _session_with_character()
    session.characters["p1"].chrome = ["kagerou"]
    session.characters["p1"].gone_too_far = True
    _pending(session)
    with pytest.raises(ValueError, match="overclock"):
        resolve_roll(session, "p1", overclock="kagerou")
    assert "p1" in session.pending_rolls


def test_no_crew_line_for_unchromed_full_humanity():
    from server.narration import _build_messages

    session = _session_with_character()
    assert "Crew:" not in _build_messages(session, "I wait.", num_ctx=8192)[0]["content"]


def test_crew_entry_is_capped():
    from server.narration import _crew_line

    session = _session_with_character()
    session.characters["p1"].name = "R" * 300
    session.characters["p1"].humanity = 50
    assert len(_crew_line(session)) <= len("Crew: ") + 200


@pytest.mark.asyncio
async def test_handle_action_ticks_debt_and_surfaces_the_notice(tmp_path):
    session = _session_with_character()
    c = session.characters["p1"]
    c.chrome, c.installments_owed, c.repo_actions, c.repo_clock = ["kagerou"], 3, 9, 5
    sent_messages = []

    async def chat_fn(*, model, messages, format):
        sent_messages.append(messages)
        payload = {"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None}}
        return {"message": {"content": json.dumps(payload)}}

    async def generate_fn(**kwargs):
        pass

    client = NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn)
    await _call(session, client, "p1", {"text": "I wait."}, tmp_path, tts_backend=FakeTTSBackend())

    assert c.repo_strikes == 1
    assert any("[torite: Hoshikawa sends Rook a polite final notice" in line for line in session.log)
    assert "World event: Hoshikawa sends Rook" in sent_messages[0][-1]["content"]


def test_crew_line_shows_debt_state():
    from server.narration import _crew_line

    session = _session_with_character()
    c = session.characters["p1"]
    c.chrome = ["kagerou"]
    c.installments_owed = 3
    c.repo_clock = 4
    c.throttled = "kagerou"
    c.pending_repo = "kagerou"
    assert "owes 3, repo clock 4/6, throttled: Kagerou, repo crew coming for: Kagerou" in _crew_line(session)


def test_crew_line_includes_debtor_without_chrome_or_humanity_loss():
    from server.narration import _crew_line

    session = _session_with_character()
    session.characters["p1"].installments_owed = 2
    assert "owes 2" in _crew_line(session)


def test_saeko_card_selected_from_pending_world_event():
    from server.narration import _build_messages

    session = _session_with_character()
    session.pending_world_events = ["Saeko Kirigaya's torite crew comes for Rook's Kagerou."]
    content = _build_messages(session, "I wait.", num_ctx=8192)[0]["content"]
    assert "World notes:" in content.split("World event:")[1]
    assert content.count("Saeko Kirigaya") >= 2


async def test_bodiless_physical_roll_is_refused(tmp_path):
    session = _session_with_character()
    session.characters["p1"].lifepath = "tsukumogami"
    session.characters["p1"].bodiless = True
    client = _fake_client("You strain toward the ledge.", tool="request_roll", tool_args={
        "player_id": "p1", "attribute": "body", "skill": "athletics", "difficulty": "moderate", "reason": "climb"})
    await _call(session, client, "p1", {"text": "I climb."}, tmp_path, tts_backend=FakeTTSBackend())
    assert "p1" not in session.pending_rolls
    assert f"[tool error: {session.characters['p1'].name} has no body]" in session.log


async def test_bodiless_hacking_roll_still_pends(tmp_path):
    session = _session_with_character()
    session.characters["p1"].bodiless = True
    client = _fake_client("The vending machine's screen flickers.", tool="request_roll", tool_args={
        "player_id": "p1", "attribute": "tech", "skill": "hacking", "difficulty": "moderate", "reason": "jack the door"})
    await _call(session, client, "p1", {"text": "I hack the door."}, tmp_path, tts_backend=FakeTTSBackend())
    assert session.pending_rolls["p1"]["skill"] == "hacking"


def test_crew_line_for_tsukumogami_shows_selfhood_and_bodiless():
    from engine.character import CharacterSheet
    from engine.session import Session
    from server.narration import _crew_line
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Hachi", role="fixer", lifepath="tsukumogami",
                                              humanity=35, installments_owed=4, bodiless=True)
    line = _crew_line(session)
    assert "Hachi: selfhood 35 (Flickering)" in line
    assert "bodiless: living in a nearby machine" in line
    assert "humanity" not in line


def test_crew_line_names_the_shell_as_repo_target():
    from engine.character import CharacterSheet
    from engine.debt import SHELL
    from engine.session import Session
    from server.narration import _crew_line
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Hachi", role="fixer", lifepath="tsukumogami",
                                              humanity=35, installments_owed=4, pending_repo=SHELL)
    assert "repo crew coming for: utsusemi shell" in _crew_line(session)


def test_tsukumogami_overclock_roll_line_says_selfhood(monkeypatch):
    from engine.character import CharacterSheet
    from engine.session import Session
    from server.narration import resolve_roll
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Hachi", role="fixer", lifepath="tsukumogami",
                                              humanity=50, chrome=["kagerou"], attributes={"reflexes": 14})
    session.pending_rolls["p1"] = {"player_id": "p1", "name": "Hachi", "attribute": "reflexes", "skill": "stealth",
                                   "difficulty": "hard", "dc": 12, "reason": "x"}
    rolls = iter([4, 9, 3])
    monkeypatch.setattr("random.randint", lambda a, b: next(rolls))
    resolve_roll(session, "p1", overclock="kagerou")
    assert any("(−3 selfhood)" in line and "humanity" not in line for line in session.log)


def test_crew_line_for_tsukumogami_at_zero_is_gone_dark():
    from engine.character import CharacterSheet
    from engine.chrome import change_humanity
    from engine.session import Session
    from server.narration import _crew_line
    session = Session(session_id="s1")
    c = CharacterSheet(player_id="p1", name="Hachi", role="fixer", lifepath="tsukumogami", humanity=3)
    change_humanity(c, -5)
    session.characters["p1"] = c
    assert "Hachi: selfhood 0 (Appliance, gone dark)" in _crew_line(session)
