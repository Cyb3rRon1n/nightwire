from engine.character import CharacterSheet


def test_character_sheet_requires_only_identity_and_build_fields():
    sheet = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    assert sheet.player_id == "p1"
    assert sheet.name == "Rook"
    assert sheet.role == "solo"
    assert sheet.lifepath == "streetkid"


def test_character_sheet_has_sensible_defaults():
    sheet = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    assert sheet.attributes == {}
    assert sheet.health == 100
    assert sheet.max_health == 100
    assert sheet.armor == 0
    assert sheet.conditions == []
    assert sheet.inventory == []
    assert sheet.portrait_path is None
    assert sheet.unspent_attribute_points == 0


def test_character_sheet_fields_are_mutable():
    # Health/conditions/inventory change during play - not a frozen dataclass.
    sheet = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    sheet.health -= 3
    sheet.conditions.append("bleeding")
    sheet.inventory.append("stim pack")
    assert sheet.health == 97
    assert sheet.conditions == ["bleeding"]
    assert sheet.inventory == ["stim pack"]


def test_two_characters_do_not_share_mutable_default_state():
    # A real dataclass footgun: mutable defaults must use default_factory,
    # not a bare [] literal, or every instance shares the same list.
    a = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    b = CharacterSheet(player_id="p2", name="Ash", role="fixer", lifepath="corpo")
    a.conditions.append("bleeding")
    assert b.conditions == []
