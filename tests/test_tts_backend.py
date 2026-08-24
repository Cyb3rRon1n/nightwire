import httpx
import pytest

from narrator.tts_backend import KokoroBackend, OpenAITTSBackend


def _fake_speech_fn(response: bytes, seen: dict):
    async def speech_fn(text: str, voice: str) -> bytes:
        seen["text"] = text
        seen["voice"] = voice
        return response

    return speech_fn


@pytest.mark.asyncio
async def test_kokoro_backend_synthesize_calls_speech_fn_with_text_and_voice():
    seen = {}
    backend = KokoroBackend(speech_fn=_fake_speech_fn(b"fake-wav-bytes", seen))

    result = await backend.synthesize("You're late, choom.", "am_adam")

    assert result == b"fake-wav-bytes"
    assert seen["text"] == "You're late, choom."
    assert seen["voice"] == "am_adam"


def test_kokoro_backend_voices_are_gender_tagged():
    backend = KokoroBackend()
    genders = {v.gender for v in backend.voices}
    assert genders == {"male", "female"}
    assert all(v.id.startswith(("af_", "am_")) for v in backend.voices)


@pytest.mark.asyncio
async def test_openai_tts_backend_synthesize_calls_speech_fn_with_text_and_voice():
    seen = {}
    backend = OpenAITTSBackend(api_key="sk-test", speech_fn=_fake_speech_fn(b"fake-mp3-bytes", seen))

    result = await backend.synthesize("The alley is quiet.", "onyx")

    assert result == b"fake-mp3-bytes"
    assert seen["text"] == "The alley is quiet."
    assert seen["voice"] == "onyx"


@pytest.mark.asyncio
async def test_kokoro_backend_default_speech_wraps_httpx_errors_as_value_error(monkeypatch):
    async def raise_connect_error(self, *args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", raise_connect_error)
    backend = KokoroBackend()

    with pytest.raises(ValueError):
        await backend.synthesize("You're late, choom.", "am_adam")


@pytest.mark.asyncio
async def test_kokoro_backend_default_speech_requests_wav_format(monkeypatch):
    seen = {}

    async def fake_post(self, url, *, json=None, **kwargs):
        seen["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(200, content=b"fake-wav-bytes", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    backend = KokoroBackend()

    result = await backend.synthesize("You're late, choom.", "am_adam")

    assert result == b"fake-wav-bytes"
    assert seen["json"]["response_format"] == "wav"


@pytest.mark.asyncio
async def test_kokoro_backend_unload_posts_to_dev_unload(monkeypatch):
    seen = {}

    async def fake_post(self, url, **kwargs):
        seen["url"] = url
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    backend = KokoroBackend(base_url="http://127.0.0.1:8880")

    await backend.unload()

    assert seen["url"] == "http://127.0.0.1:8880/dev/unload"


@pytest.mark.asyncio
async def test_kokoro_backend_unload_wraps_httpx_errors_as_value_error(monkeypatch):
    async def raise_connect_error(self, *args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", raise_connect_error)
    backend = KokoroBackend()

    with pytest.raises(ValueError):
        await backend.unload()


@pytest.mark.asyncio
async def test_openai_tts_backend_unload_is_a_no_op():
    backend = OpenAITTSBackend(api_key="sk-test")
    await backend.unload()  # must not raise - no local VRAM to free


@pytest.mark.asyncio
async def test_openai_tts_backend_default_speech_wraps_httpx_errors_as_value_error(monkeypatch):
    async def raise_status_error(self, *args, **kwargs):
        request = httpx.Request("POST", "https://api.openai.com/v1/audio/speech")
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("server error", request=request, response=response)

    monkeypatch.setattr(httpx.AsyncClient, "post", raise_status_error)
    backend = OpenAITTSBackend(api_key="sk-test")

    with pytest.raises(ValueError):
        await backend.synthesize("The alley is quiet.", "onyx")


@pytest.mark.asyncio
async def test_openai_tts_backend_default_speech_requests_wav_format(monkeypatch):
    seen = {}

    async def fake_post(self, url, *, json=None, **kwargs):
        seen["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(200, content=b"fake-wav-bytes", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    backend = OpenAITTSBackend(api_key="sk-test")

    result = await backend.synthesize("The alley is quiet.", "onyx")

    assert result == b"fake-wav-bytes"
    assert seen["json"]["response_format"] == "wav"


def test_openai_tts_backend_voices_have_no_gender_label():
    # OpenAI does not publish gender labels for its TTS voices (verified
    # against its own API docs, 2026-08-23) - only tonal descriptors like
    # "deep" or "bright". Inventing male/female tags here would be an
    # unverified claim; leaving gender unset lets voice_assignment.py fall
    # back to its ungendered path for this backend instead.
    backend = OpenAITTSBackend(api_key="sk-test")
    assert all(v.gender is None for v in backend.voices)
