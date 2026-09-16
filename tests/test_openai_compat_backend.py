import pytest

from narrator.openai_compat_backend import OpenAICompatNarratorBackend


class _FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass


class _FakeOpenAIClient:
    """Stands in for httpx.AsyncClient - only the method
    OpenAICompatNarratorBackend actually calls (post)."""

    def __init__(self, response_json):
        self.response_json = response_json
        self.calls = []

    async def post(self, url, json=None, headers=None):
        self.calls.append((url, json, headers))
        return _FakeResponse(self.response_json)


def _chat_response(content_str: str):
    return {"choices": [{"message": {"content": content_str}}]}


@pytest.mark.asyncio
async def test_respond_requests_strict_json_schema_and_parses_it():
    import json
    payload = json.dumps({
        "narration": [{"speaker": "narrator", "text": "The alley is quiet."}],
        "tool_call": {"tool": None},
    })
    fake_client = _FakeOpenAIClient(_chat_response(payload))
    backend = OpenAICompatNarratorBackend(
        base_url="http://localhost:8080/v1", model="test-model", api_key="test-key", client=fake_client,
    )

    response = await backend.respond([{"role": "user", "content": "I look around."}])

    assert response.narration[0].text == "The alley is quiet."
    url, body, headers = fake_client.calls[0]
    assert url == "http://localhost:8080/v1/chat/completions"
    assert body["response_format"]["type"] == "json_schema"
    assert headers["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_respond_works_even_if_the_server_ignores_response_format():
    # A server that doesn't honor response_format at all - the schema
    # request was sent (asserted above), but this proves the fallback
    # validate-after-the-fact path is real, not just theoretical, for a
    # server that returns valid JSON without ever enforcing the schema.
    import json
    payload = json.dumps({
        "narration": [{"speaker": "narrator", "text": "Free-form but valid."}],
        "tool_call": {"tool": None},
    })
    fake_client = _FakeOpenAIClient(_chat_response(payload))
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_client)

    response = await backend.respond([{"role": "user", "content": "hi"}])

    assert response.narration[0].text == "Free-form but valid."


@pytest.mark.asyncio
async def test_respond_raises_value_error_on_malformed_json():
    fake_client = _FakeOpenAIClient(_chat_response("not json at all"))
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_client)

    with pytest.raises(ValueError):
        await backend.respond([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_respond_works_without_an_api_key():
    # A local vLLM/llama.cpp-server deployment needs no key at all.
    import json
    payload = json.dumps({"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None}})
    fake_client = _FakeOpenAIClient(_chat_response(payload))
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_client)

    await backend.respond([{"role": "user", "content": "hi"}])

    _, _, headers = fake_client.calls[0]
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_summarize_sends_a_plain_chat_completion():
    fake_client = _FakeOpenAIClient(_chat_response("  A short summary.  "))
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_client)

    result = await backend.summarize("Some session events.")

    assert result == "A short summary."
    _, body, _ = fake_client.calls[0]
    assert "response_format" not in body


@pytest.mark.asyncio
async def test_unload_is_a_noop():
    fake_client = _FakeOpenAIClient({})
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_client)
    await backend.unload()
    assert len(fake_client.calls) == 0
