from narrator import citymap
from server.views import build_view
from tests.test_referee import _session


def _d(view: dict, name: str) -> dict:
    return next(d for d in view["districts"] if d["name"] == name)


def test_seven_districts_in_order_and_here_has_no_go():
    s = _session()
    s.location = "Ikebe Low"
    v = citymap.view(s)
    assert [d["name"] for d in v["districts"]] == list(citymap.ORDER)
    assert [d["name"] for d in v["districts"] if d["here"]] == ["Ikebe Low"]
    assert _d(v, "Ikebe Low")["go"] is None
    assert _d(v, "Kuroshio Docks")["go"] == "I take the Ring Line to Kuroshio Docks."


def test_on_the_ring_line_it_is_here():
    s = _session()
    s.location = "Ring Line"
    ring = _d(citymap.view(s), "Ring Line")
    assert ring["here"] and ring["go"] is None


def test_special_lines_and_taxis_when_no_trains():
    s = _session()
    v = citymap.view(s)
    assert _d(v, "Tenjō Heights")["go"] == "I ride a maglev pod up to Tenjō Heights."
    assert _d(v, "Yomi Line")["go"] == "I head down into the sealed Yomi Line."
    assert _d(v, "The Loop")["go"] == "I ride up onto the Loop."
    s.stretch = 3  # small hours
    v = citymap.view(s)
    assert v["trains"] is False
    assert _d(v, "Hanabira-chō")["go"] == "I take a taxi to Hanabira-chō."


def test_no_location_nothing_is_here_and_every_district_has_a_go():
    v = citymap.view(_session())
    assert not any(d["here"] for d in v["districts"]) and all(d["go"] for d in v["districts"])
    assert v["caption"] == "Kuroshio."


def test_mood_is_the_worst_place_in_the_district_including_the_district_key():
    s = _session()
    s.places = {"Ikebe Low": {"heat": 3, "warmth": 0, "marks": []},
                "Mama Sato's izakaya": {"heat": 0, "warmth": 2, "marks": []},
                "Kuroshio Docks": {"heat": 7, "warmth": 0, "marks": []}}
    v = citymap.view(s)
    assert (_d(v, "Ikebe Low")["mood"], _d(v, "Kuroshio Docks")["mood"], _d(v, "Hanabira-chō")["mood"]) == \
        ("wary", "tense", "calm")


def test_only_shown_clocks_and_the_caption_counts_them():
    s = _session()
    s.location = "Kuroshio Docks"
    s.clocks = {"container": {"filled": 3, "night": 1, "rest_until": 0},
                "kuze-ikebe": {"filled": 2, "night": 1, "rest_until": 0}}
    v = citymap.view(s)
    assert _d(v, "Ikebe Low")["clock"] == {"filled": 2, "size": 6}
    assert _d(v, "Kuroshio Docks")["clock"] == {"filled": 0, "size": 6}  # the Ōgane clock; the container is hidden
    assert v["caption"] == "Kuroshio. You are in Kuroshio Docks. 1 district under pressure."


def test_people_by_district_and_places_known_by_visit_or_objective():
    s = _session()
    s.people = {"Tomoe": {"who": "man", "district": "Ikebe Low"}, "Rika": {"who": "driver", "district": "Hanabira-chō"}}
    s.places = {"Mama Sato's izakaya": {"heat": 0, "warmth": 0, "marks": []}}
    s.active_objectives = ["Ask at the Low-city shrine who cut Ikebe Low's power"]
    v = citymap.view(s)
    assert _d(v, "Ikebe Low")["people"] == ["Tomoe"]
    assert _d(v, "Ikebe Low")["places"] == ["Low-city shrine", "Mama Sato's izakaya"]
    assert _d(v, "Kuroshio Docks")["places"] == []


def test_the_view_carries_the_map():
    assert len(build_view(_session(), "p1")["map"]["districts"]) == 7


def test_every_go_line_is_a_move_to_its_district():
    from narrator.movement import destination
    s = _session()
    for stretch in (0, 3):  # trains, then taxis
        s.stretch = stretch
        for d in citymap.view(s)["districts"]:
            assert destination(d["go"]) == d["name"], d["go"]
