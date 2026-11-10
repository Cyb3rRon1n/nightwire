from pathlib import Path

from test_shorts_model import PLANNED, SHORT, write
from tools.shorts import preflight
from tools.shorts.backends import fal
from tools.shorts.model import Line, load_short


def shot(tmp_path, text=PLANNED):
    return load_short(write(tmp_path, shot=text))


def test_complete_shot_passes(tmp_path):
    s = shot(tmp_path)
    r = preflight.run(s, s.shots[0], None, "a calm prompt", [], "seedance-2.0-fast", 0.0)
    assert r.problems == [] and r.ok


def test_missing_fields_are_listed(tmp_path):
    from test_shorts_model import SHOT
    s = shot(tmp_path, SHOT)
    r = preflight.run(s, s.shots[0], None, "p", [], "seedance-2.0-fast", 0.0)
    for f in ("size", "angle", "move", "action", "frame"):
        assert any(f"missing {f}" in p for p in r.problems), r.problems


def test_dialogue_pace(tmp_path):
    fast = PLANNED.replace('text = "Who paid it?"', 'text = "' + " ".join(["word"] * 12) + '"')
    s = shot(tmp_path, fast)  # 12 words in (5 s - 1 s air) = 3.0 words/s
    assert any("words/s" in p for p in preflight.run(s, s.shots[0], None, "p", [], "seedance-2.0-fast", 0).problems)


def test_one_action_and_one_move(tmp_path):
    two = PLANNED.replace('action = "C2 asks who paid her tab."', 'action = "C2 sits. C1 leaves."')
    two = two.replace('move = "slow push-in"', 'move = "push-in then pan left"')
    s = shot(tmp_path, two)
    p = preflight.run(s, s.shots[0], None, "p", [], "seedance-2.0-fast", 0).problems
    assert any("one sentence" in x for x in p) and any("one camera move" in x for x in p)


def test_continuity_props_and_screen_side(tmp_path):
    s = shot(tmp_path)
    prev = s.shots[0]
    nxt = load_short(write(tmp_path / "b", shot=PLANNED.replace('prop_change = ["C1"]', 'prop_change = []')
                           .replace('C1 = "sake cup in right hand"', 'C1 = "sake cup in left hand"')
                           .replace('C2 = "screen-left, facing camera"', 'C2 = "screen-right, facing camera"'))).shots[0]
    p = preflight.run(s, nxt, prev, "p", [], "seedance-2.0-fast", 0).problems
    assert any("C1 props change" in x for x in p) and any("C2 swaps screen side" in x for x in p)


def test_refs_missing_and_over_limit(tmp_path):
    s = shot(tmp_path)
    (tmp_path / "a.png").write_bytes(b"x")
    refs = [(f"C{i}_x.png", tmp_path / "a.png") for i in range(10)] + [("gone.png", tmp_path / "nope.png")]
    p = preflight.run(s, s.shots[0], None, "p", refs, "seedance-2.0-fast", 0).problems
    assert any("gone.png" in x and "missing" in x for x in p) and any("images" in x and "limit 9" in x for x in p)


def test_filter_words_warn_only(tmp_path):
    s = shot(tmp_path)
    r = preflight.run(s, s.shots[0], None, "she tries to plug it in", [], "seedance-2.0-fast", 0)
    assert r.ok and any("plug it in" in w for w in r.warnings)


def test_budget(tmp_path):
    s = shot(tmp_path)  # budget 25, 5 s on 2.0-fast ~ $1.21
    assert any("budget" in p for p in preflight.run(s, s.shots[0], None, "p", [], "seedance-2.0-fast", 24.5).problems)


def test_usable_refs_applies_skip_and_video(tmp_path):
    refs = [("C1_turnaround.png", Path("a")), ("floorplan.png", Path("b")), ("greybox.mp4", Path("c"))]
    kept, out = fal.usable_refs("seedance-2.0-fast", refs)
    assert [l for l, _ in kept] == ["C1_turnaround.png", "greybox.mp4"] and out == ["floorplan.png"]
    kept, out = fal.usable_refs("kling-3", refs)
    assert "greybox.mp4" in out


def test_missing_expected_ref_is_a_problem_but_floorplan_is_optional(tmp_path):
    from tools.shorts.prompt import expected_refs, ref_files
    s = shot(tmp_path)
    dd, sd = tmp_path / "dd", tmp_path / "dd" / "shorts" / s.slug / "shots" / "S01"
    sd.mkdir(parents=True)
    for label, p in expected_refs(s, dd, sd):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    (dd / "saeko-kirigaya" / "expressions.png").unlink()
    (dd / "shorts" / s.slug / "floorplan.png").unlink()
    expected = expected_refs(s, dd, sd)
    assert [l for l, _ in expected][-3:] == ["place.png", "floorplan.png", "greybox.mp4"]
    assert "C1_expressions.png" not in [l for l, _ in ref_files(s, dd, sd)]
    p = preflight.run(s, s.shots[0], None, "p", expected, "seedance-2.5", 0).problems
    assert any("C1_expressions.png: file missing" in x for x in p) and not any("floorplan" in x for x in p)


def test_shorts_copy_of_a_sheet_wins(tmp_path):
    from tools.shorts.prompt import expected_refs
    s = shot(tmp_path)
    dd, sd = tmp_path / "dd", tmp_path / "sd"
    alt = dd / "saeko-kirigaya" / "shorts" / "turnaround.png"
    alt.parent.mkdir(parents=True)
    alt.write_bytes(b"x")
    refs = dict(expected_refs(s, dd, sd))
    assert refs["C1_turnaround.png"] == alt
    assert refs["C1_portrait.png"] == dd / "saeko-kirigaya" / "portrait.png"


SCENE_SHORT = SHORT + '''
[scene]
time = "late night"
weather = "indoors; no windows"
set = "a narrow izakaya"
light = ["paper lanterns"]
not_visible = ["rain", "street"]

[wardrobe]
C1 = "navy jacket zipped"

[blocking]
seating = "side by side, C2 on C1's left"
'''


def _planned(extra):
    return PLANNED.replace("lens = 35.0", "lens = 35.0\n" + extra)


def test_package_problems(tmp_path):
    from tools.shorts.plates import Plate
    s = load_short(write(tmp_path, short=SCENE_SHORT, shot=_planned('plate = "door"\nend_frame = true')))
    sd = tmp_path / "sd"; sd.mkdir()
    p = preflight.package(s, s.shots[0], None, {"door": Plate("door", "v")}, sd,
                          {"images": {}, "SCENE": {}}, tmp_path / "dd")
    for want in ("plate door not rendered", "scene bible not approved", "no approved start keyframe",
                 "needs an end keyframe", "missing motion", "C2 has no [wardrobe] line"):
        assert any(want in x for x in p), (want, p)


def test_package_requires_approved_keyframes(tmp_path):
    from tools.shorts.approve import scene_fp
    from tools.shorts.plates import Plate
    s = load_short(write(tmp_path, short=SCENE_SHORT, shot=_planned('plate = "door"\nmotion = "C2 turns."\nend_frame = true')))
    dd, sd = tmp_path / "dd", tmp_path / "sd"
    sd.mkdir()
    plates = {"door": Plate("door", "v")}
    (dd / s.place / "plates").mkdir(parents=True)
    (dd / s.place / "plates" / "door.png").write_bytes(b"x")
    (sd / "keyframe-start.png").write_bytes(b"x")
    (sd / "keyframe-end.png").write_bytes(b"x")
    keep = {"verdict": "keep"}
    from tools.shorts.approve import keyframe_id
    from tools.shorts.plates import plate_id
    images = {plate_id(s.place, "door", dd / s.place / "plates" / "door.png"): keep}
    ap = {"images": images, "SCENE": {scene_fp(s): keep}}
    p = preflight.package(s, s.shots[0], None, plates, sd, ap, dd)
    assert "start keyframe not approved" in p and "end keyframe not approved" in p
    images[keyframe_id(s.slug, "S01", "start", sd / "keyframe-start.png")] = keep
    images[keyframe_id(s.slug, "S01", "end", sd / "keyframe-end.png")] = keep
    p = preflight.package(s, s.shots[0], None, plates, sd, ap, dd)
    assert not any("keyframe" in x or "plate" in x or "scene" in x for x in p), p


def test_bible_words(tmp_path):
    shot = PLANNED.replace('action = "C2 asks who paid her tab."', 'action = "C2 shakes rain off her hood."')
    shot = shot.replace('text = "Who paid it?"', 'text = "Still raining?"')
    s = load_short(write(tmp_path, short=SCENE_SHORT, shot=shot))
    problems, warnings = preflight.bible_words(s, s.shots[0])
    assert any("'rain' in action" in x for x in problems) and any("'rain'" in w for w in warnings)  # 'raining' now matches the 'rain' ban


def _bible(tmp_path, weather, action="C2 looks up.", not_visible='["street"]', motion=None):
    sc = SCENE_SHORT.replace('weather = "indoors; no windows"', f'weather = "{weather}"').replace('["rain", "street"]', not_visible)
    s = load_short(write(tmp_path, short=sc, shot=PLANNED.replace("C2 asks who paid her tab.", action)))
    return preflight.bible_words(s, s.shots[0])[0]


def test_bible_no_rain_or_snow_bans_snow(tmp_path):
    assert any("'snow'" in x for x in _bible(tmp_path, "indoors, no rain or snow", "snow falls on C2."))


def test_bible_rain_on_windows_allows_raining(tmp_path):
    p = _bible(tmp_path, "rain on the windows", "It is raining on C2.")
    assert not any("rain" in x for x in p)


def test_bible_inflections_and_no_false_hits(tmp_path):
    assert any("'window'" in x for x in _bible(tmp_path / "a", "indoors", "C2 looks through the windows."))
    assert not any("in action" in x for x in _bible(tmp_path / "b", "indoors", "C2 is training a drain."))


def test_package_end_keyframe_present_needs_approval_even_if_not_required(tmp_path):
    from tools.shorts.plates import Plate
    s = load_short(write(tmp_path, short=SCENE_SHORT, shot=_planned('plate = "door"\nmotion = "C2 turns."')))
    sh = s.shots[0]
    sh.at_end = dict(sh.at_start)  # same cast at both ends
    sd = tmp_path / "sd"; sd.mkdir()
    (sd / "keyframe-start.png").write_bytes(b"x"); (sd / "keyframe-end.png").write_bytes(b"x")
    from tools.shorts.approve import keyframe_id
    ap = {"images": {keyframe_id(s.slug, "S01", "start", sd / "keyframe-start.png"): {"verdict": "keep"}}, "SCENE": {}}
    p = preflight.package(s, sh, None, {"door": Plate("door", "v")}, sd, ap, tmp_path / "dd")
    assert "end keyframe not approved" in p and "start keyframe not approved" not in p


def test_package_no_plate_and_unknown_plate(tmp_path):
    from tools.shorts.plates import Plate
    s = load_short(write(tmp_path, short=SCENE_SHORT, shot=PLANNED))
    ap = {"images": {}, "SCENE": {}}
    assert "no plate" in preflight.package(s, s.shots[0], None, {}, tmp_path, ap, tmp_path)
    s.shots[0].plate = "nowhere"
    p = preflight.package(s, s.shots[0], None, {"door": Plate("door", "v")}, tmp_path, ap, tmp_path)
    assert any("plate nowhere is not in" in x for x in p)


def test_package_keep_on_an_old_chosen_keyframe_or_plate_does_not_count(tmp_path):
    from tools.shorts.approve import keyframe_id, scene_fp
    from tools.shorts.plates import Plate, plate_id
    s = load_short(write(tmp_path, short=SCENE_SHORT, shot=_planned('plate = "door"\nmotion = "C2 turns."')))
    dd, sd = tmp_path / "dd", tmp_path / "sd"
    sd.mkdir()
    (dd / s.place / "plates").mkdir(parents=True)
    plate, key = dd / s.place / "plates" / "door.png", sd / "keyframe-start.png"
    plate.write_bytes(b"plate-1")
    key.write_bytes(b"key-1")
    keep = {"verdict": "keep"}
    images = {plate_id(s.place, "door", plate): keep, keyframe_id(s.slug, "S01", "start", key): keep}
    ap = {"images": images, "SCENE": {scene_fp(s): keep}}
    plates = {"door": Plate("door", "v")}
    assert not [x for x in preflight.package(s, s.shots[0], None, plates, sd, ap, dd) if ("keyframe" in x and "needs an end" not in x) or "plate" in x]
    plate.write_bytes(b"plate-2")  # a different candidate was chosen: the old keeps no longer apply
    key.write_bytes(b"key-2")
    p = preflight.package(s, s.shots[0], None, plates, sd, ap, dd)
    assert "plate door not approved" in p and "start keyframe not approved" in p


def test_bible_words_scans_frame_and_line_rule(tmp_path):
    sc = SCENE_SHORT.replace('weather = "indoors; no windows"', 'weather = "indoors"').replace('["rain", "street"]', '["rain", "street"]')
    sc = sc.replace('line_rule = "', 'line_rule = "') 
    s = load_short(write(tmp_path, short=sc, shot=PLANNED))
    s.shots[0].frame["C1"] = "screen-right, rain on her hood"
    s.line_rule = "C1 stays left of the street"
    problems, _ = preflight.bible_words(s, s.shots[0])
    assert any("'rain' in frame C1" in x for x in problems) and any("'street' in line_rule" in x for x in problems)


def test_missing_why_warns_only(tmp_path):
    s = shot(tmp_path)
    r = preflight.run(s, s.shots[0], None, "p", [], "seedance-2.0-fast", 0)
    assert r.ok and any("missing why" in w for w in r.warnings)
    s = shot(tmp_path / "b", PLANNED.replace("lens = 35.0", 'lens = 35.0\nwhy = "x"'))
    assert not any("why" in w for w in preflight.run(s, s.shots[0], None, "p", [], "seedance-2.0-fast", 0).warnings)


def _lb(tmp_path, text=PLANNED):
    s = shot(tmp_path, text)
    return s, s.shots[0]


def test_lookbook_talking_close_face(tmp_path):
    from tools.shorts import lookbook
    s, sh = _lb(tmp_path)
    sh.size, sh.lines = "MCU", [object()]
    assert any("talking face" in w for w in lookbook.warnings(s, sh))
    sh.size = "WS"
    assert not any("talking face" in w for w in lookbook.warnings(s, sh))


def test_lookbook_lines_cast_move_and_dialogue_heavy(tmp_path):
    from tools.shorts import lookbook
    s, sh = _lb(tmp_path)
    sh.size, sh.lines, sh.frame, sh.move, sh.action = "WS", [object(), object()], {"C1": "a", "C2": "b", "C3": "c"}, "static", "C1 sits."
    w = lookbook.warnings(s, sh)
    assert any("2 lines" in x for x in w) and any("3 people" in x for x in w)
    assert not any("camera move" in x for x in w)
    assert any("dialogue-heavy" in x for x in w)
    sh.move = "slow pan"
    assert any("camera move" in x for x in lookbook.warnings(s, sh))
    sh.action = ""
    assert not any("camera move" in x for x in lookbook.warnings(s, sh))


def test_lookbook_quiet_shot_has_no_warnings_and_preflight_stays_ok(tmp_path):
    from tools.shorts import lookbook
    s, sh = _lb(tmp_path)
    sh.size, sh.lines, sh.frame, sh.move, sh.action = "EWS", [], {"C1": "from behind"}, "static", ""
    assert lookbook.warnings(s, sh) == []
    sh.lines, sh.size = [Line("C1", 0.0, "hi")], "CU"
    r = preflight.run(s, sh, None, "p", [], "seedance-2.0-fast", 0)
    assert any("talking face" in w for w in r.warnings) and not any("talking face" in p for p in r.problems)


def test_why_hint(tmp_path):
    from tools.shorts import lookbook
    s, sh = _lb(tmp_path)
    sh.size, sh.move, sh.frame = "EWS", "slow push-in", {"C1": "seen from behind"}
    h = lookbook.why_hint(sh)
    assert "enormous" in h and "drifting closer" in h and "behind" in h
    sh.size, sh.move, sh.frame = "", "", {}
    assert lookbook.why_hint(sh) == ""
    r = preflight.run(s, sh, None, "p", [], "seedance-2.0-fast", 0)
    assert any("missing why" in w for w in r.warnings)
