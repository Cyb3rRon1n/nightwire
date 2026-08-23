import json

import pytest

from narrator.client import NarratorClient, NarratorResponse


def _fake_chat_returning(payload: dict):
    def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps(payload)}}
    return chat_fn


def test_respond_returns_narration_only_when_no_tool_call():
    client = NarratorClient(
        model="qwen3:8b",
        system_prompt="You are a cyberpunk GM.",
        chat_fn=_fake_chat_returning({"narration": "The alley is quiet.", "tool": None, "tool_args": {}}),
    )
    response = client.respond([{"role": "user", "content": "I look around."}])
    assert isinstance(response, NarratorResponse)
    assert response.narration == "The alley is quiet."
    assert response.tool is None
    assert response.tool_args == {}


def test_respond_returns_a_tool_call():
    client = NarratorClient(
        chat_fn=_fake_chat_returning({
            "narration": "You lunge for the ledge.",
            "tool": "request_roll",
            "tool_args": {"attribute_mod": 2, "skill_mod": 1, "difficulty": "hard", "reason": "leap across a gap"},
        }),
    )
    response = client.respond([{"role": "user", "content": "I try to jump the gap."}])
    assert response.tool == "request_roll"
    assert response.tool_args["difficulty"] == "hard"


def test_respond_passes_the_structured_output_schema_to_chat_fn():
    seen = {}

    def chat_fn(*, model, messages, format):
        seen["format"] = format
        seen["model"] = model
        return {"message": {"content": json.dumps({"narration": "ok", "tool": None, "tool_args": {}})}}

    client = NarratorClient(model="qwen3:8b", chat_fn=chat_fn)
    client.respond([{"role": "user", "content": "hi"}])

    assert seen["model"] == "qwen3:8b"
    assert seen["format"] == NarratorResponse.model_json_schema()


def test_respond_prepends_the_system_prompt():
    seen = {}

    def chat_fn(*, model, messages, format):
        seen["messages"] = messages
        return {"message": {"content": json.dumps({"narration": "ok", "tool": None, "tool_args": {}})}}

    client = NarratorClient(system_prompt="You are a cyberpunk GM.", chat_fn=chat_fn)
    client.respond([{"role": "user", "content": "hi"}])

    assert seen["messages"][0] == {"role": "system", "content": "You are a cyberpunk GM."}
    assert seen["messages"][1] == {"role": "user", "content": "hi"}


def test_respond_raises_on_malformed_model_output():
    client = NarratorClient(chat_fn=lambda **kwargs: {"message": {"content": "not json"}})
    with pytest.raises(ValueError):
        client.respond([{"role": "user", "content": "hi"}])
