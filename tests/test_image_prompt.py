import pytest

from engine.character import CharacterSheet
from narrator.image_prompt import (
    NEGATIVE, PORTRAIT_NEGATIVE, QUALITY, STYLE, build_prompt, character_design, clean_tags, resolve,
    subject_tags,
)


def _pc(**kw):
    return CharacterSheet(**{"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid", **kw})


def test_scene_subject():
    assert subject_tags("scene") == ["scenery", "no humans"]


@pytest.mark.parametrize("presentation,first", [("feminine", "1girl"), ("masculine", "1boy"),
                                                ("androgynous", "1other"), (None, "1other")])
def test_portrait_subject_follows_presentation(presentation, first):
    assert subject_tags("portrait", _pc(presentation=presentation)) == [first, "solo", "upper body", "portrait", "looking at viewer"]


def test_tsukumogami_portrait_overrides_presentation():
    c = _pc(lifepath="tsukumogami", presentation="feminine")
    assert subject_tags("portrait", c) == ["1other", "solo", "upper body", "portrait", "android", "robot joints"]


def test_clean_tags_drops_round_four_junk_and_owned_tags():
    raw = ["1structure", "1Bridge", "1girl", "Neon_Signs", "neon signs", "masterpiece", "highly detailed",
           "anime", "rain", "  wet street ", "", "2girls", "best quality"]
    assert clean_tags(raw) == ["neon signs", "rain", "wet street"]


def test_clean_tags_caps_at_25():
    assert len(clean_tags([f"tag {i}" for i in range(40)])) == 25


def test_build_prompt_order():
    assert build_prompt(["scenery", "no humans"], ["rain", "alley"]) == ", ".join(
        [QUALITY, "scenery", "no humans", STYLE, "rain", "alley"])
    assert build_prompt(["scenery", "no humans"], "a rainy alley").endswith(", a rainy alley")


class _Client:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    async def judge(self, messages, schema):
        self.calls.append((messages, schema))
        if self.error:
            raise self.error
        return self.answer


async def test_resolve_uses_cleaned_tags():
    client = _Client({"tags": ["1girl", "izakaya", "paper lanterns", "steam", "ramen", "counter", "rain"]})
    pos, neg, source = await resolve(client, "scene", "a lantern-lit izakaya")
    assert source == "tags" and neg == NEGATIVE
    assert pos == build_prompt(["scenery", "no humans"], ["izakaya", "paper lanterns", "steam", "ramen", "counter", "rain"])
    assert client.calls[0][1]["required"] == ["tags"]


@pytest.mark.parametrize("client", [_Client(error=ValueError("bad json")), _Client({"tags": ["rain", "alley"]})])
async def test_resolve_falls_back_to_the_sentence(client):
    pos, neg, source = await resolve(client, "scene", "a rainy alley")
    assert source == "sentence"
    assert pos == build_prompt(["scenery", "no humans"], "a rainy alley")


async def test_resolve_portrait_uses_character_subject():
    client = _Client({"tags": ["bomber jacket", "short hair", "cyberarm", "neon", "rain"]})
    pos, _, _ = await resolve(client, "portrait", "Rook, a streetkid solo", _pc(presentation="masculine"))
    assert pos.startswith(QUALITY + ", 1boy, solo")


async def test_resolve_portrait_drops_lower_body_tags():
    client = _Client({"tags": ["scuffed boots", "layered street fashion", "cyberware", "neon", "rain",
                               "smirk", "full body"]})
    pos, neg, _ = await resolve(client, "portrait", "Rook, a streetkid solo", _pc(presentation="masculine"))
    assert "boots" not in pos and "full body" not in pos
    assert "layered street fashion" in pos and "cyberware" in pos and "smirk" in pos
    assert neg == PORTRAIT_NEGATIVE


async def test_resolve_scene_keeps_lower_body_tags():
    client = _Client({"tags": ["scuffed boots", "full body", "neon", "rain", "alley"]})
    pos, neg, _ = await resolve(client, "scene", "a rainy alley")
    assert "scuffed boots" in pos and "full body" in pos and neg == NEGATIVE


def test_portrait_negative_bans_lower_body():
    assert PORTRAIT_NEGATIVE.startswith(NEGATIVE)
    assert "full body" in PORTRAIT_NEGATIVE and "boots" in PORTRAIT_NEGATIVE


def test_character_design_finds_the_approved_sheet():
    tags, negative = character_design(_pc(name="Hachi"))
    assert "android" in tags and "wide hips" in negative


@pytest.mark.parametrize("name", ["Nobody At All", ""])
def test_character_design_is_empty_without_an_approved_sheet(name):
    assert character_design(_pc(name=name)) == ([], "")


async def test_resolve_portrait_takes_the_design_sheet():
    client = _Client({"tags": ["bomber jacket", "short hair", "neon", "rain", "smirk"]})
    pos, neg, _ = await resolve(client, "portrait", "she looks tired", _pc(name="Hachi"))
    assert "android" in pos and "robot joints" in pos
    assert "wide hips" in neg


async def test_resolve_scene_never_takes_the_design_sheet():
    client = _Client({"tags": ["rain", "alley", "neon", "puddle", "steam"]})
    pos, neg, _ = await resolve(client, "scene", "an empty alley", _pc(name="Hachi"))
    assert "android" not in pos and "no humans" in pos and "wide hips" not in neg


async def test_resolve_portrait_drops_the_sheets_lower_body_tags():
    client = _Client({"tags": ["bomber jacket", "short hair", "neon", "rain", "smirk"]})
    pos, _, _ = await resolve(client, "portrait", "she looks tired", _pc(name="Saeko Kirigaya"))
    assert "long legs" not in pos
