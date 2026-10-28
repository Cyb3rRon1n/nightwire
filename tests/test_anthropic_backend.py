import pytest

from narrator.anthropic_backend import AnthropicNarratorBackend


class _FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass


class _FakeAnthropicClient:
    """Stands in for httpx.AsyncClient - only the method
    AnthropicNarratorBackend actually calls (post), duck-typed to httpx's
    own response shape."""

    def __init__(self, response_json):
        self.response_json = response_json
        self.calls = []

    async def post(self, url, json=None, headers=None):
        self.calls.append((url, json, headers))
        return _FakeResponse(self.response_json)


def _tool_use_response(tool_input: dict):
    return {
        "content": [
            {"type": "tool_use", "name": "narrator_response", "input": tool_input},
        ],
    }


@pytest.mark.asyncio
async def test_respond_forces_tool_use_and_parses_the_tool_input():
    payload = {
        "narration": [{"speaker": "narrator", "text": "The alley is quiet."}],
        "tool_call": {"tool": None},
    }
    fake_client = _FakeAnthropicClient(_tool_use_response(payload))
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_client)

    response = await backend.respond([{"role": "user", "content": "I look around."}])

    assert response.narration[0].text == "The alley is quiet."
    assert response.tool is None
    # Forced tool-use is the whole point - assert the actual request shape,
    # not just that a request happened.
    _, body, headers = fake_client.calls[0]
    assert body["tool_choice"] == {"type": "tool", "name": "narrator_response"}
    assert body["tools"][0]["name"] == "narrator_response"
    assert headers["x-api-key"] == "test-key"


@pytest.mark.asyncio
async def test_respond_raises_value_error_on_missing_tool_use_block():
    fake_client = _FakeAnthropicClient({"content": [{"type": "text", "text": "oops, no tool call"}]})
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_client)

    with pytest.raises(ValueError, match="no tool_use block"):
        await backend.respond([{"role": "user", "content": "I look around."}])


@pytest.mark.asyncio
async def test_respond_raises_value_error_on_schema_mismatch():
    # tool_input is missing the required "narration" field entirely.
    fake_client = _FakeAnthropicClient(_tool_use_response({"tool_call": {"tool": None}}))
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_client)

    with pytest.raises(ValueError):
        await backend.respond([{"role": "user", "content": "I look around."}])


@pytest.mark.asyncio
async def test_summarize_sends_a_plain_unconstrained_request():
    fake_client = _FakeAnthropicClient({"content": [{"type": "text", "text": "  A short summary.  "}]})
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_client)

    result = await backend.summarize("Some session events.")

    assert result == "A short summary."
    _, body, _ = fake_client.calls[0]
    assert "tools" not in body
    assert "tool_choice" not in body


@pytest.mark.asyncio
async def test_summarize_raises_value_error_when_response_has_no_text_block():
    # A thinking-only or refusal response with no text content block used to
    # crash with StopIteration (surfaced as RuntimeError by asyncio), which
    # escapes server/narration.py's fail-soft exception tuple entirely.
    fake_client = _FakeAnthropicClient({"content": [{"type": "thinking", "thinking": "..."}]})
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_client)

    with pytest.raises(ValueError, match="no text block"):
        await backend.summarize("Some session events.")


@pytest.mark.asyncio
async def test_unload_is_a_noop():
    backend = AnthropicNarratorBackend(api_key="test-key", client=_FakeAnthropicClient({}))
    await backend.unload()  # must not raise, must not call the fake client
    assert len(backend._client.calls) == 0


@pytest.mark.asyncio
async def test_respond_sends_system_prompt_as_top_level_system_field():
    payload = {"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None}}
    fake_client = _FakeAnthropicClient(_tool_use_response(payload))
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_client)
    backend.system_prompt = "You are a cyberpunk GM."

    await backend.respond([{"role": "user", "content": "hi"}])

    _, body, _ = fake_client.calls[0]
    assert body["system"] == "You are a cyberpunk GM."
    assert all(m["role"] != "system" for m in body["messages"])


@pytest.mark.asyncio
async def test_judge_forces_a_tool_with_the_given_schema():
    schema = {"type": "object", "properties": {"gig_paid_out": {"type": "boolean"}}, "required": ["gig_paid_out"]}
    client = _FakeAnthropicClient(_tool_use_response({"gig_paid_out": True}))
    backend = AnthropicNarratorBackend(api_key="k", model="m", client=client)
    assert await backend.judge([{"role": "user", "content": "x"}], schema) == {"gig_paid_out": True}
    body = client.calls[0][1]
    assert body["tools"][0]["input_schema"] == schema
    assert body["temperature"] == 0


@pytest.mark.asyncio
async def test_judge_moves_the_referee_system_message_into_the_system_field():
    from engine.character import CharacterSheet
    from engine.session import Session
    from narrator.referee import _SYSTEM, _messages, build_questions
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    questions = build_questions(session, "p1")
    messages = _messages(session, "p1", "I eat.", "You eat.", questions)
    client = _FakeAnthropicClient(_tool_use_response({"human_moment": "none"}))
    backend = AnthropicNarratorBackend(api_key="k", model="m", client=client)
    await backend.judge(messages, {"type": "object"})
    body = client.calls[0][1]
    assert body["system"] == _SYSTEM
    assert all(m["role"] != "system" for m in body["messages"])
    assert [m["role"] for m in body["messages"]] == ["user"]
