# tests/test_narrator_client.py
import json

import pytest

from narrator.client import NarratorClient, NarratorResponse


def _fake_chat_returning(payload: dict):
    async def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps(payload)}}
    return chat_fn


@pytest.mark.asyncio
async def test_respond_returns_narration_only_when_no_tool_call():
    client = NarratorClient(
        model="qwen3:8b",
        system_prompt="You are a cyberpunk GM.",
        chat_fn=_fake_chat_returning({"narration": "The alley is quiet.", "tool_call": {"tool": None}}),
    )
    response = await client.respond([{"role": "user", "content": "I look around."}])
    assert isinstance(response, NarratorResponse)
    assert response.narration == "The alley is quiet."
    assert response.tool is None
    assert response.tool_args == {}


@pytest.mark.asyncio
async def test_respond_returns_a_tool_call():
    client = NarratorClient(
        chat_fn=_fake_chat_returning({
            "narration": "You lunge for the ledge.",
            "tool_call": {
                "tool": "request_roll",
                "tool_args": {
                    "player_id": "p1", "attribute": "reflexes", "skill_mod": 1,
                    "difficulty": "hard", "reason": "leap across a gap",
                },
            },
        }),
    )
    response = await client.respond([{"role": "user", "content": "I try to jump the gap."}])
    assert response.tool == "request_roll"
    assert response.tool_args["difficulty"] == "hard"


@pytest.mark.asyncio
async def test_respond_rejects_a_tool_call_with_the_wrong_argument_shape():
    # The real bug this fix closes: a model calling start_combat (or any
    # tool) with a plausible-looking but wrong shape - e.g. a `scene`/
    # `enemies` object instead of start_combat's real `{"reason": str}` -
    # must fail validation, the same way a genuinely wrong tool_args dict
    # already did at execute_tool() time, but now caught at parse time.
    client = NarratorClient(
        chat_fn=_fake_chat_returning({
            "narration": "Combat breaks out!",
            "tool_call": {
                "tool": "start_combat",
                "tool_args": {"scene": "alley", "enemies": ["ganger"]},
            },
        }),
    )
    with pytest.raises(ValueError):
        await client.respond([{"role": "user", "content": "I draw my weapon."}])


@pytest.mark.asyncio
async def test_respond_passes_the_structured_output_schema_to_chat_fn():
    seen = {}

    async def chat_fn(*, model, messages, format):
        seen["format"] = format
        seen["model"] = model
        return {"message": {"content": json.dumps({"narration": "ok", "tool_call": {"tool": None}})}}

    client = NarratorClient(model="qwen3:8b", chat_fn=chat_fn)
    await client.respond([{"role": "user", "content": "hi"}])

    assert seen["model"] == "qwen3:8b"
    assert seen["format"] == NarratorResponse.model_json_schema()


@pytest.mark.asyncio
async def test_respond_prepends_the_system_prompt():
    seen = {}

    async def chat_fn(*, model, messages, format):
        seen["messages"] = messages
        return {"message": {"content": json.dumps({"narration": "ok", "tool_call": {"tool": None}})}}

    client = NarratorClient(system_prompt="You are a cyberpunk GM.", chat_fn=chat_fn)
    await client.respond([{"role": "user", "content": "hi"}])

    assert seen["messages"][0] == {"role": "system", "content": "You are a cyberpunk GM."}
    assert seen["messages"][1] == {"role": "user", "content": "hi"}


@pytest.mark.asyncio
async def test_respond_raises_on_malformed_model_output():
    async def chat_fn(**kwargs):
        return {"message": {"content": "not json"}}

    client = NarratorClient(chat_fn=chat_fn)
    with pytest.raises(ValueError):
        await client.respond([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_respond_raises_on_a_hallucinated_tool_name():
    client = NarratorClient(
        chat_fn=_fake_chat_returning({
            "narration": "You lunge for the ledge.",
            "tool_call": {"tool": "Agility Check (DC 15) to leap across the gap", "tool_args": {}},
        }),
    )
    with pytest.raises(ValueError):
        await client.respond([{"role": "user", "content": "I try to jump the gap."}])


@pytest.mark.asyncio
async def test_unload_calls_generate_with_keep_alive_zero_and_no_prompt():
    # Ollama's documented way to force-unload a model immediately: a
    # generate call with keep_alive=0 and no prompt - no inference runs.
    seen = {}

    async def generate_fn(**kwargs):
        seen.update(kwargs)

    client = NarratorClient(model="qwen3:8b", generate_fn=generate_fn)
    await client.unload()

    assert seen["model"] == "qwen3:8b"
    assert seen["keep_alive"] == 0
    assert "prompt" not in seen


@pytest.mark.asyncio
async def test_respond_parses_an_image_request():
    client = NarratorClient(
        chat_fn=_fake_chat_returning({
            "narration": "The alley opens onto a rain-slicked plaza, neon bleeding into puddles.",
            "tool_call": {"tool": None},
            "image_request": {"prompt": "a rain-slicked cyberpunk plaza, neon reflections"},
        }),
    )
    response = await client.respond([{"role": "user", "content": "I step into the plaza."}])
    assert response.image_request is not None
    assert response.image_request.prompt == "a rain-slicked cyberpunk plaza, neon reflections"


@pytest.mark.asyncio
async def test_respond_image_request_defaults_to_none():
    client = NarratorClient(
        chat_fn=_fake_chat_returning({
            "narration": "The alley is quiet.",
            "tool_call": {"tool": None},
        }),
    )
    response = await client.respond([{"role": "user", "content": "I look around."}])
    assert response.image_request is None
