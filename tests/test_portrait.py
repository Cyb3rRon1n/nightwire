from engine.character import CharacterSheet
from server.portrait import _build_portrait_prompt


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

    assert prompt == "Zeta, a Spacer Diplomat — moody neon lighting, rain-slicked cyberpunk city backdrop, highly detailed digital painting"
