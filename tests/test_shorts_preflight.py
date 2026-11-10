from pathlib import Path

from test_shorts_model import PLANNED, SHORT, write
from tools.shorts import preflight
from tools.shorts.backends import fal
from tools.shorts.model import load_short


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
    images = {f"plate--{s.place}--door": keep}
    ap = {"images": images, "SCENE": {scene_fp(s): keep}}
    p = preflight.package(s, s.shots[0], None, plates, sd, ap, dd)
    assert "start keyframe not approved" in p and "end keyframe not approved" in p
    images[f"key--{s.slug}--s01--start"] = keep
    images[f"key--{s.slug}--s01--end"] = keep
    p = preflight.package(s, s.shots[0], None, plates, sd, ap, dd)
    assert not any("keyframe" in x or "plate" in x or "scene" in x for x in p), p


def test_bible_words(tmp_path):
    shot = PLANNED.replace('action = "C2 asks who paid her tab."', 'action = "C2 shakes rain off her hood."')
    shot = shot.replace('text = "Who paid it?"', 'text = "Still raining?"')
    s = load_short(write(tmp_path, short=SCENE_SHORT, shot=shot))
    problems, warnings = preflight.bible_words(s, s.shots[0])
    assert any("'rain' in action" in x for x in problems) and any("'raining'" in w for w in warnings)
