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


def test_a_distinctive_last_word_alone_finds_the_place(monkeypatch):
    # Dry run 2026-11-06: the narrator shortened the location to "izakaya" and the art disappeared.
    monkeypatch.setattr(place_art, "_slugs", lambda: ["mama-satos-izakaya", "rins-room", "ring-line", "yomi-line"])
    assert place_art.location_art("the izakaya") == "place-art/mama-satos-izakaya.jpg"
    assert place_art.location_art("a back room") is None        # "room" is too generic
    assert place_art.location_art("the line") is None           # shared by two places
