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
    assert len(world.npcs) == 11
    assert "utsusemi" in world.system_block()
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
    with pytest.raises(ValueError, match="1900"):
        parse_world(_raw(primer="x" * 1900))


from engine.session import Session
from narrator.world import select_cards


def _card(world, name):
    return next(e.card for e in world.districts + world.factions + world.npcs if e.name == name)


def test_location_district_comes_first_even_if_others_mentioned_more_recently():
    world = kuroshio()
    session = Session(session_id="s", location="Ikebe Low - Mama Sato's izakaya", log=["The Kuze-gumi enforcer smiles."])

    cards = select_cards(world, session, "I ride out toward the Loop.", budget_chars=10_000)

    assert cards[0] == _card(world, "Ikebe Low")
    assert _card(world, "The Loop") in cards
    assert _card(world, "Kuze-gumi") in cards


def test_matching_is_diacritic_insensitive():
    world = kuroshio()
    session = Session(session_id="s", location="Tenjo Heights - lobby")

    cards = select_cards(world, session, "I wait.", budget_chars=10_000)

    assert cards[0] == _card(world, "Tenjō Heights")


def test_matching_is_whole_word():
    world = kuroshio()
    session = Session(session_id="s")

    assert select_cards(world, session, "I look for a loophole in the contract.", budget_chars=10_000) == []


def test_aliases_match():
    world = kuroshio()
    session = Session(session_id="s")

    cards = select_cards(world, session, "I call my contact in the Kuze about Ogane drones.", budget_chars=10_000)

    assert cards == [_card(world, "Ōgane Heavy"), _card(world, "Kuze-gumi")]


def test_action_text_mentions_rank_before_older_log_mentions():
    world = kuroshio()
    session = Session(session_id="s", log=["We left Hanabira-chō behind.", "Rain on the Docks."])

    cards = select_cards(world, session, "I head for the Loop.", budget_chars=10_000)

    assert cards == [_card(world, "The Loop"), _card(world, "Kuroshio Docks"), _card(world, "Hanabira-chō")]


def test_bracket_lines_and_lines_older_than_scan_depth_are_ignored():
    world = kuroshio()
    old = ["Hanabira-chō was loud."] + [f"filler {i}" for i in range(6)]
    session = Session(session_id="s", log=old + ["[image: the Loop at night]"])

    assert select_cards(world, session, "I wait.", budget_chars=10_000) == []


def test_at_most_four_cards():
    world = kuroshio()
    session = Session(session_id="s")

    cards = select_cards(world, session, "Ikebe, the Loop, the Docks, Hanabira and Tenjo.", budget_chars=10_000)

    assert len(cards) == 4


def test_budget_limits_cards():
    world = kuroshio()
    session = Session(session_id="s")
    first = _card(world, "Ikebe Low")

    cards = select_cards(world, session, "Ikebe and the Loop.", budget_chars=len(first) + 1)

    assert cards == [first]


def test_no_match_returns_empty():
    session = Session(session_id="s", location="somewhere unnamed")

    assert select_cards(kuroshio(), session, "I wait.", budget_chars=10_000) == []


def test_bare_string_aliases_rejected():
    bad = [{"name": "Ikebe Low", "aliases": "Ikebe", "card": "Old alleys."}]

    with pytest.raises(ValueError, match="aliases"):
        parse_world(_raw(district=bad))


def test_empty_alias_rejected():
    bad = [{"name": "Ikebe Low", "aliases": [""], "card": "Old alleys."}]

    with pytest.raises(ValueError, match="aliases"):
        parse_world(_raw(district=bad))


def test_parse_world_builds_npcs_with_home():
    raw = _raw(npc=[{"name": "Mama Sato", "aliases": ["Sato"], "home": "Ikebe Low", "card": "Mama Sato runs an izakaya."}])

    world = parse_world(raw)

    assert world.npcs == (WorldEntry("Mama Sato", ("Sato",), "Mama Sato runs an izakaya.", "Ikebe Low"),)


def test_npc_without_home_is_allowed():
    world = parse_world(_raw(npc=[{"name": "Saeko Kirigaya", "aliases": [], "card": "A torite boss."}]))

    assert world.npcs[0].home is None


def test_npc_home_must_be_an_existing_district():
    raw = _raw(npc=[{"name": "Mama Sato", "aliases": [], "home": "Nowhere", "card": "An izakaya owner."}])

    with pytest.raises(ValueError, match="home"):
        parse_world(raw)


def test_npc_alias_colliding_with_a_faction_alias_fails():
    raw = _raw(npc=[{"name": "Kuze Taro", "aliases": ["Kuze"], "card": "A clan soldier."}])

    with pytest.raises(ValueError, match="duplicates"):
        parse_world(raw)


def test_overlong_npc_card_fails():
    with pytest.raises(ValueError, match="400"):
        parse_world(_raw(npc=[{"name": "Mama Sato", "aliases": [], "card": "x" * 401}]))


def test_npc_matched_by_mention_and_alias():
    world = kuroshio()
    session = Session(session_id="s")

    assert select_cards(world, session, "I ask Arakawa for work.", budget_chars=10_000) == [_card(world, "Jun Arakawa")]


def test_resident_npc_joins_location_when_nobody_is_named():
    world = kuroshio()
    session = Session(session_id="s", location="Ikebe Low - the izakaya")

    cards = select_cards(world, session, "I sit down.", budget_chars=10_000)

    assert cards == [_card(world, "Ikebe Low"), _card(world, "Mama Sato")]


def test_mentioned_resident_is_not_added_twice_and_next_resident_is_not_forced():
    world = kuroshio()
    session = Session(session_id="s", location="Ikebe Low - the izakaya")

    cards = select_cards(world, session, "I ask Mama Sato about the chrome-ya.", budget_chars=10_000)

    assert cards == [_card(world, "Ikebe Low"), _card(world, "Mama Sato")]


def test_resident_outranks_other_mentions_when_cap_is_full():
    world = kuroshio()
    session = Session(session_id="s", location="Ikebe Low")

    cards = select_cards(world, session, "The Loop, the Docks and Hanabira.", budget_chars=10_000)

    assert cards == [_card(world, n) for n in ("Ikebe Low", "Mama Sato", "Hanabira-chō", "Kuroshio Docks")]


def test_resident_comes_before_stale_faction_mentions():
    world = kuroshio()
    session = Session(
        session_id="s",
        location="Hanabira-chō - a karaoke box",
        log=["The Kuze-gumi and Kaminari Run are at war.", "Hoshikawa repo men watch the door."],
    )

    cards = select_cards(world, session, "I look for work.", budget_chars=10_000)

    assert cards[:2] == [_card(world, "Hanabira-chō"), _card(world, "Jun Arakawa")]
    assert len(cards) == 4


def test_resident_skipped_when_budget_is_full():
    world = kuroshio()
    session = Session(session_id="s", location="Ikebe Low")
    ikebe = _card(world, "Ikebe Low")

    assert select_cards(world, session, "I wait.", budget_chars=len(ikebe) + 1) == [ikebe]


def test_no_resident_without_a_location_match():
    world = kuroshio()
    session = Session(session_id="s", location="somewhere unnamed")

    assert select_cards(world, session, "I wait.", budget_chars=10_000) == []


def test_npc_without_home_is_never_a_resident():
    world = kuroshio()
    homeless = [n.name for n in world.npcs if n.home is None]
    session = Session(session_id="s", location="Ikebe Low")

    cards = select_cards(world, session, "I wait.", budget_chars=10_000)

    assert homeless == ["Saeko Kirigaya"]
    assert _card(world, "Saeko Kirigaya") not in cards
