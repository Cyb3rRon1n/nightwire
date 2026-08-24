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


def test_openai_tts_backend_voices_have_no_gender_label():
    # OpenAI does not publish gender labels for its TTS voices (verified
    # against its own API docs, 2026-08-23) - only tonal descriptors like
    # "deep" or "bright". Inventing male/female tags here would be an
    # unverified claim; leaving gender unset lets voice_assignment.py fall
    # back to its ungendered path for this backend instead.
    backend = OpenAITTSBackend(api_key="sk-test")
    assert all(v.gender is None for v in backend.voices)
