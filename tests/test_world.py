import pytest

from narrator.world import World, WorldEntry, kuroshio, parse_world


def _raw(**overrides):
    raw = {
        "primer": "Setting: a test city.",
        "glossary": {"chrome": "cyberware"},
        "district": [{"name": "Ikebe Low", "aliases": ["Ikebe"], "card": "Ikebe Low is old alleys."}],
        "faction": [{"name": "Kuze-gumi", "aliases": ["Kuze"], "card": "The Kuze-gumi is a clan."}],
    }
    raw.update(overrides)
    return raw


def test_shipped_kuroshio_world_loads():
    world = kuroshio()

    assert len(world.districts) == 6
    assert len(world.factions) == 6
    assert "Kuroshio" in world.primer


def test_system_block_contains_primer_and_every_glossary_term():
    world = kuroshio()

    block = world.system_block()

    assert world.primer in block
    for term, definition in world.glossary.items():
        assert f"{term}: {definition}" in block


def test_parse_world_builds_entries():
    world = parse_world(_raw())

    assert world.districts == (WorldEntry("Ikebe Low", ("Ikebe",), "Ikebe Low is old alleys."),)
    assert world.factions[0].name == "Kuze-gumi"


def test_missing_primer_fails():
    with pytest.raises(ValueError, match="primer"):
        parse_world(_raw(primer=""))


def test_missing_card_fails():
    with pytest.raises(ValueError, match="card"):
        parse_world(_raw(district=[{"name": "Ikebe Low", "aliases": []}]))


def test_overlong_card_fails():
    with pytest.raises(ValueError, match="400"):
        parse_world(_raw(district=[{"name": "Ikebe Low", "aliases": [], "card": "x" * 401}]))


def test_duplicate_alias_across_entries_fails():
    raw = _raw(faction=[{"name": "Ikebe Gang", "aliases": ["ikebe"], "card": "A gang."}])

    with pytest.raises(ValueError, match="duplicates"):
        parse_world(raw)


def test_alias_that_only_differs_by_diacritics_counts_as_duplicate():
    raw = _raw(faction=[{"name": "Ōgane Heavy", "aliases": ["Ogane Heavy"], "card": "Arms."}])

    with pytest.raises(ValueError, match="duplicates"):
        parse_world(raw)


def test_overlong_primer_plus_glossary_fails():
    with pytest.raises(ValueError, match="1600"):
        parse_world(_raw(primer="x" * 1600))
