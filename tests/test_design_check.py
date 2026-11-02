from narrator.designs import Design
from tools import design_check as dc


def test_missing_forbidden_and_unchecked():
    panels = [{"red hair": 0.9, "cigarette": 0.7, "purple eyes": 0.1, "holding": 0.0}, {"red hair": 0.1, "cigarette": 0.0, "purple eyes": 0.1, "holding": 0.0}]
    got = dc.judge_tags(["red hair", "purple eyes", "chrome jaw"], ["cigarette", "holding", "made up"], panels)
    assert got == {"missing": {"red hair": 1, "purple eyes": 2}, "forbidden": {"cigarette": 1}, "unchecked": ["chrome jaw"]}


def test_canon_details_are_not_forbidden_but_carried_items_are():
    d = Design(name="K", kind="character", source="x", tags="fang, cigarette, visor", required=["visor"], held=["cigarette"], negative="child")
    terms = dc.forbidden_terms(d)
    assert "fangs" not in terms and "visor" not in terms and "cigarette" in terms and "child" in terms


def test_flags_use_thresholds():
    entry = {"forbidden": {"cigarette": 2}, "missing": {"red hair": 3, "scar": 1},
             "worst_panel_pair": {"a": "Smile", "b": "Sad", "difference": 0.5}, "nearest": {"slug": "rin", "difference": 0.05}}
    flags = dc.flags_for(entry)
    assert len(flags) == 4 and "looks like rin" in flags[3]
    assert len(dc.flags_for({"forbidden": {}, "missing": {}, "worst_panel_pair": {"a": "a", "b": "b", "difference": 0.1}, "nearest": {"slug": "r", "difference": 0.9}})) == 0


def test_scene_people_and_rank():
    assert dc.scene_people("ayame-tsuda--the-loop.png") == ["ayame-tsuda"]
    assert dc.scene_people("pair--a--b--the-loop.png") == ["a", "b"]
    assert dc.rank_of("a", {"a": 0.1, "b": 0.2}) == 1 and dc.rank_of("b", {"a": 0.1, "b": 0.2}) == 2



def test_colour_drift_flags_a_changing_colour_but_not_canon_two_tone_hair():
    assert dc.colour_drift([{"pink eyes": 0.9}, {"pink eyes": 0.8}, {"orange eyes": 0.4}], {"blank eyes"}) == {"eyes": {"pink": 2, "orange": 1}}
    assert dc.colour_drift([{"blue eyes": 0.9}, {"blue eyes": 0.8}, {"grey eyes": 0.1}], set()) == {}  # too unsure to count
    assert dc.colour_drift([{"black hair": 0.9}, {"pink hair": 0.8}], {"black hair", "pink hair"}) == {}


def test_body_sheet_flags_background_character_and_hair():
    entry = {"forbidden": {}, "missing": {}, "sheets": {"portrait": 0.1, "colorguide": 0.4}, "background": {"turnaround": 12, "colorguide": 128},
             "body_hair_missing": ["red hair"]}
    flags = dc.flags_for(entry)
    assert len(flags) == 3 and "colorguide may not read" in flags[0] and "red hair" in flags[1] and "brightness 12" in flags[2]


def test_border_brightness_reads_the_background_not_the_subject():
    from PIL import Image
    im = Image.new("L", (100, 100), 128)
    im.paste(0, (10, 10, 90, 90))
    assert dc.border_brightness(im) == 128
