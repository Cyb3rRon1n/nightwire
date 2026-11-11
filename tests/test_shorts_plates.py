from pathlib import Path

from narrator.designs import load_designs
from tools.shorts.plates import load_plates, plate_id, plate_path

TOML = '''
[[plate]]
name = "toward-shelves"
view = "from the stools toward the shelves"
source = "play.png"
[[plate]]
name = "toward-door"
view = "from behind the counter toward the noren door"
'''


def test_load_and_paths(tmp_path):
    (tmp_path / "izakaya.toml").write_text(TOML)
    p = load_plates("izakaya", tmp_path)
    assert list(p) == ["toward-shelves", "toward-door"] and p["toward-door"].source == ""
    dd = tmp_path / "dd"
    assert plate_path(dd, "izakaya", p["toward-shelves"]) == dd / "izakaya" / "play.png"
    assert plate_path(dd, "izakaya", p["toward-door"]) == dd / "izakaya" / "plates" / "toward-door.png"
    assert plate_id("izakaya", "toward-door") == "plate--izakaya--toward-door"
    assert load_plates("nowhere", tmp_path) == {}


def test_plate_catalogues_stay_out_of_the_designs_folder():
    root = Path(__file__).resolve().parents[1]
    assert load_designs(root / "narrator/worlds/designs")  # the real folder still loads
    assert not list((root / "narrator/worlds/designs").glob("*plates*"))
    assert load_plates("mama-satos-izakaya", root / "narrator/worlds/plates")


# ---- Task 12: plate renders ----
import asyncio

import pytest
from PIL import Image

from narrator.designs import Design
from tests.test_shorts_model import SHORT, SHOT, write
from tools.shorts import plates as pl
from tools.shorts.model import load_short

PLACE = Design(name="Izakaya", kind="location", source="t", tags="izakaya, lanterns", alt_tags="izakaya, night", status="approved")


def test_plate_workflow_adds_controlnet_and_rewires_sampler():
    plate = pl.Plate("toward-door", "from the counter toward the door")
    wf = pl.plate_workflow(PLACE, "Time: late.", ["windows"], plate, "guide.png", 5)
    assert wf["61"]["inputs"]["image"] == "guide.png" and wf["60"]["class_type"] == "ControlNetLoader"
    assert wf["3"]["inputs"]["positive"] == ["62", 0] and wf["3"]["inputs"]["negative"] == ["62", 1]
    assert wf["5"]["inputs"]["width"] == 1216 and wf["5"]["inputs"]["height"] == 832
    text = wf["6"]["inputs"]["text"]
    assert text.split(", empty room")[0].endswith(f"({plate.view}:1.3)") and plate.view in text and "no humans" in text and "izakaya, night" in text and "Time: late." in text
    assert text.index("1.3") < text.index("izakaya, night")  # room tags are the tail
    assert (wf["62"]["inputs"]["strength"], wf["62"]["inputs"]["end_percent"]) == (0.8, 0.85)
    assert wf["9"]["inputs"]["filename_prefix"] == "nightwire_plates/toward-door"
    assert wf["34"]["inputs"]["positive"] == ["62", 0] and wf["34"]["inputs"]["denoise"] == 0.35  # refine pass keeps the guide
    assert wf["9"]["inputs"]["images"] == ["35", 0] and "40" not in wf
    assert wf["3"]["inputs"]["cfg"] == 3.5 and "photorealistic" in wf["7"]["inputs"]["text"]


def test_plate_workflow_without_lineart_is_plain():
    wf = pl.plate_workflow(PLACE, "s", [], pl.Plate("a", "v"), None, 1)
    assert "60" not in wf and "62" not in wf and wf["3"]["inputs"]["positive"] != ["62", 0]


def make_short(tmp_path):
    shot = SHOT.replace("lens = 35.0", 'lens = 35.0\nplate = "toward-door"')
    return load_short(write(tmp_path / "pilot", SHORT, shot))


def catalogue(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "mama-satos-izakaya.toml").write_text(TOML)
    return tmp_path


def test_plan_jobs_uses_first_shot_lineart_and_skips_present(tmp_path):
    s, root, dd, work = make_short(tmp_path), catalogue(tmp_path / "cat"), tmp_path / "dd", tmp_path / "work"
    art = work / "shots" / "S01" / "guide" / "start-room-lineart.png"
    art.parent.mkdir(parents=True)
    art.write_bytes(b"x")
    jobs = pl.plan_jobs(s, work, dd, root, seeds=2)
    assert [(j[0].name, j[1].name, j[2], j[3]) for j in jobs] == [("toward-door-c01.png", "toward-door", art, 1), ("toward-door-c02.png", "toward-door", art, 2)]
    (dd / "mama-satos-izakaya" / "plates").mkdir(parents=True)
    (dd / "mama-satos-izakaya" / "plates" / "toward-door-c01.png").write_bytes(b"x")
    assert [j[0].name for j in pl.plan_jobs(s, work, dd, root, seeds=2)] == ["toward-door-c02.png"]
    assert [j[0].name for j in pl.plan_jobs(s, work, dd, root, seeds=2, redo=True)] == ["toward-door-c01.png", "toward-door-c02.png"]
    (dd / "mama-satos-izakaya" / "plates" / "toward-door.png").write_bytes(b"x")
    assert pl.plan_jobs(s, work, dd, root, seeds=2) == [] and pl.plan_jobs(s, work, dd, root, seeds=2, redo=True) == []


def test_choose_copies_refuses_missing_and_source(tmp_path):
    dd = tmp_path
    plate = pl.Plate("toward-door", "v")
    (dd / "p" / "plates").mkdir(parents=True)
    with pytest.raises(ValueError, match="no candidate"):
        pl.choose(dd, "p", plate, 2)
    (dd / "p" / "plates" / "toward-door-c02.png").write_bytes(b"two")
    assert pl.choose(dd, "p", plate, 2).read_bytes() == b"two"
    with pytest.raises(ValueError, match="adopted"):
        pl.choose(dd, "p", pl.Plate("s", "v", source="play.png"), 1)


def test_render_uploads_lineart_and_keeps_going_after_a_failure(tmp_path):
    class Fake:
        def __init__(self): self.uploads, self.runs = [], []
        async def upload_image(self, name, png): self.uploads.append(name); return "in-" + name
        async def run_workflow(self, wf):
            self.runs.append(wf)
            if len(self.runs) == 1:
                raise RuntimeError("boom")
            return b"png"
    art = tmp_path / "a.png"
    art.write_bytes(b"x")
    plate = pl.Plate("toward-door", "v")
    f = Fake()
    errs = asyncio.run(pl.render([(tmp_path / "o1.png", plate, art, 1), (tmp_path / "o2.png", plate, art, 3)], f, PLACE, "s", [], 10))
    assert len(errs) == 1 and "boom" in errs[0] and (tmp_path / "o2.png").read_bytes() == b"png"
    assert f.runs[0]["61"]["inputs"]["image"] == "in-plate-guide-toward-door.png"
    assert f.runs[0]["3"]["inputs"]["seed"] == 10 and f.runs[1]["3"]["inputs"]["seed"] == 12


def test_negative_comes_from_not_visible_and_positive_leaves_it_out():
    from tools.shorts.model import scene_look
    from tools.shorts.model import Scene
    import types
    sc = Scene(time="late night", weather="indoors", set="a bar", light=["lanterns"], not_visible=["windows"])
    look = scene_look(types.SimpleNamespace(scene=sc))
    assert "Not visible" not in look and "windows" not in look and "Light: lanterns." in look
    wf = pl.plate_workflow(PLACE, look, sc.not_visible, pl.Plate("a", "v"), None, 1)
    assert "windows" in wf["7"]["inputs"]["text"] and "windows" not in wf["6"]["inputs"]["text"]
    assert "street" not in wf["7"]["inputs"]["text"] and "rain" not in wf["7"]["inputs"]["text"]
    assert scene_look(types.SimpleNamespace(scene=None)) == ""


def test_plate_tags_replace_place_tags_and_set_and_avoid_goes_negative():
    from tools.shorts.model import Scene, scene_look, scene_mood
    import types
    sc = Scene(time="late night", weather="indoors", set="a bar with a counter", light=["lanterns"], not_visible=["windows"])
    short = types.SimpleNamespace(scene=sc)
    plate = pl.Plate("d", "v", tags="coat hooks, noren", avoid=["bottle shelves"])
    wf = pl.plate_workflow(PLACE, scene_look(short), sc.not_visible, plate, None, 1, scene_mood(short))
    pos, neg = wf["6"]["inputs"]["text"], wf["7"]["inputs"]["text"]
    assert "coat hooks, noren" in pos and "izakaya, night" not in pos and "Set:" not in pos and "Time: late night." in pos and "Light: lanterns." in pos
    assert "bottle shelves" in neg and "windows" in neg and pl.NO_TEXT in neg
    plain = pl.plate_workflow(PLACE, scene_look(short), sc.not_visible, pl.Plate("d", "v"), None, 1, scene_mood(short))
    assert "izakaya, night" in plain["6"]["inputs"]["text"] and "Set: a bar" in plain["6"]["inputs"]["text"]
    assert pl.NO_TEXT in plain["7"]["inputs"]["text"]


def test_real_toward_door_plate_has_tags_and_avoid():
    p = load_plates("mama-satos-izakaya")["toward-door"]
    assert "noren curtain" in p.tags and "bottle shelves" in p.avoid


def test_outdoor_plate_is_not_an_empty_room():
    out = pl.plate_workflow(PLACE, "s", [], pl.Plate("facade", "a building", tags="outdoors, building facade"), None, 1)
    assert "empty room" not in out["6"]["inputs"]["text"] and "no humans" in out["6"]["inputs"]["text"]


def test_plate_mood_replaces_the_scene_mood():
    p = pl.Plate("facade", "a building", tags="outdoors", mood="Light: corridor lights.")
    text = pl.plate_workflow(PLACE, "s", [], p, None, 1, mood="Light: ceiling bulb, indoors.")["6"]["inputs"]["text"]
    assert "corridor lights" in text and "ceiling bulb" not in text
