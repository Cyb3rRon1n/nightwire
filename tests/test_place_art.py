from narrator import place_art


def test_most_specific_place_wins(monkeypatch):
    monkeypatch.setattr(place_art, "_slugs", lambda: ["ikebe-low", "mama-satos-izakaya", "ogane-precinct", "danchi-block"])
    assert place_art.location_art("Mama Sato's izakaya, Ikebe Low") == "place-art/mama-satos-izakaya.jpg"
    assert place_art.location_art("a noodle stall in Ikebe") == "place-art/ikebe-low.jpg"


def test_world_bible_aliases_reach_the_design(monkeypatch):
    monkeypatch.setattr(place_art, "_slugs", lambda: ["ogane-precinct", "danchi-block"])
    assert place_art.location_art("the precinct") == "place-art/ogane-precinct.jpg"
    assert place_art.location_art("Harbor danchi") == "place-art/danchi-block.jpg"


def test_unknown_or_empty_location_has_no_art(monkeypatch):
    monkeypatch.setattr(place_art, "_slugs", lambda: ["ikebe-low"])
    assert place_art.location_art(None) is None
    assert place_art.location_art("a moon base") is None
    assert place_art.location_art("the low table") is None  # word match, like the world bible


def test_every_shipped_art_file_belongs_to_an_approved_place():
    for slug in place_art._slugs():
        assert place_art.design_name(slug)
