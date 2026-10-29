import base64

import pytest

from engine.character import CharacterSheet
from server.portrait import _build_portrait_prompt, _validate_reference_photos


def _data_url(raw_bytes: bytes, media_type: str = "image/png") -> str:
    encoded = base64.b64encode(raw_bytes).decode()
    return f"data:{media_type};base64,{encoded}"


def test_known_role_and_lifepath_get_visual_tags():
    character = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")

    prompt = _build_portrait_prompt(character)

    assert "Rook" in prompt
    assert "tactical armor plating" in prompt
    assert "hand-me-down cyberware" in prompt
    assert "neon lighting" in prompt


def test_unknown_role_and_lifepath_fall_back_to_plain_description():
    character = CharacterSheet(player_id="p1", name="Zeta", role="Diplomat", lifepath="Spacer")

    prompt = _build_portrait_prompt(character)

    assert prompt == "Zeta, a Spacer Diplomat — moody neon lighting, rain-slicked cyberpunk city backdrop"


def test_no_reference_photos_returns_empty_list():
    assert _validate_reference_photos(None) == []


def test_valid_reference_photos_pass_through_unchanged():
    url = _data_url(b"fake-png-bytes")
    assert _validate_reference_photos([url]) == [url]


def test_more_than_two_reference_photos_is_rejected():
    urls = [_data_url(b"a"), _data_url(b"b"), _data_url(b"c")]
    with pytest.raises(ValueError, match="at most 2"):
        _validate_reference_photos(urls)


def test_non_list_reference_photos_is_rejected():
    with pytest.raises(ValueError, match="must be a list"):
        _validate_reference_photos("not-a-list")


def test_non_string_entry_is_rejected():
    with pytest.raises(ValueError, match="must be a string"):
        _validate_reference_photos([123])


def test_malformed_data_url_is_rejected():
    with pytest.raises(ValueError, match="base64 data URL"):
        _validate_reference_photos(["not-a-data-url"])


def test_disallowed_image_type_is_rejected():
    url = _data_url(b"fake-gif-bytes", media_type="image/gif")
    with pytest.raises(ValueError, match="unsupported image type"):
        _validate_reference_photos([url])


def test_invalid_base64_payload_is_rejected():
    with pytest.raises(ValueError, match="invalid base64"):
        _validate_reference_photos(["data:image/png;base64,not-valid-base64!!"])


def test_oversized_reference_photo_is_rejected():
    oversized = b"x" * (4 * 1024 * 1024 + 1)
    url = _data_url(oversized)
    with pytest.raises(ValueError, match="exceeds"):
        _validate_reference_photos([url])


def test_portrait_prompt_has_no_digital_painting_phrase():
    from engine.character import CharacterSheet
    from server.portrait import _build_portrait_prompt
    assert "digital painting" not in _build_portrait_prompt(CharacterSheet(player_id="p", name="Rook", role="solo", lifepath="streetkid"))


async def test_tag_backend_portrait_uses_presentation_subject(tmp_path):
    from engine.character import CharacterSheet
    from engine.persistence import JSONFileSessionStore
    from engine.session import Session
    from server.portrait import handle_approve_character
    seen = {}
    class _Img:
        wants_tags = True
        async def generate_portrait(self, description, reference_photos=None, negative=None):
            seen["prompt"], seen["negative"] = description, negative
            return b"png"
        async def generate_scene(self, prompt, reference_paths, negative=None):
            raise AssertionError
    class _Client:
        async def judge(self, messages, schema):
            seen["tagged"] = True
            return {"tags": ["bomber jacket", "short hair", "cyberarm", "neon", "rain", "smirk"]}
        async def unload(self):
            assert seen.get("tagged")
            seen["unloaded_after_prompt"] = "prompt" not in seen
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", presentation="masculine")
    await handle_approve_character(session, JSONFileSessionStore(tmp_path), _Client(), _Img(), "p1", {})
    assert seen["prompt"].startswith("masterpiece") and ", 1boy, solo" in seen["prompt"] and "cyberarm" in seen["prompt"]
    assert seen["negative"] and seen["unloaded_after_prompt"] is True


async def _portrait_with_tts(tmp_path, tts):
    from engine.character import CharacterSheet
    from engine.persistence import JSONFileSessionStore
    from engine.session import Session
    from server.portrait import handle_approve_character
    order = []
    class _Img:
        wants_tags = True
        async def generate_portrait(self, description, reference_photos=None, negative=None):
            order.append("generate")
            return b"png"
    class _Client:
        async def judge(self, messages, schema):
            order.append("tag")
            return {"tags": ["a", "b", "c", "d", "e", "f"]}
        async def unload(self):
            order.append("narrator_unload")
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", presentation="masculine")
    await handle_approve_character(session, JSONFileSessionStore(tmp_path), _Client(), _Img(), "p1", {},
                                   tts_backend=tts(order))
    return order


async def test_portrait_unloads_tts_after_tagging_before_generate(tmp_path):
    class _Tts:
        def __init__(self, order): self.order = order
        async def unload(self): self.order.append("tts_unload")
    order = await _portrait_with_tts(tmp_path, _Tts)
    assert order == ["tag", "narrator_unload", "tts_unload", "generate"]


async def test_portrait_survives_failing_tts_unload(tmp_path):
    class _Tts:
        def __init__(self, order): pass
        async def unload(self): raise RuntimeError("boom")
    order = await _portrait_with_tts(tmp_path, _Tts)
    assert order[-1] == "generate"
