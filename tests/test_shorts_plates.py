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
    wf = pl.plate_workflow(PLACE, "Time: late.", plate, "guide.png", 5)
    assert wf["61"]["inputs"]["image"] == "guide.png" and wf["60"]["class_type"] == "ControlNetLoader"
    assert wf["3"]["inputs"]["positive"] == ["62", 0] and wf["3"]["inputs"]["negative"] == ["62", 1]
    assert wf["5"]["inputs"]["width"] == 1216 and wf["5"]["inputs"]["height"] == 832
    text = wf["6"]["inputs"]["text"]
    assert plate.view in text and "no humans" in text and "izakaya, night" in text and "Time: late." in text
    assert wf["9"]["inputs"]["filename_prefix"] == "nightwire_plates/toward-door"
    assert "34" not in wf  # base size has no second pass


def test_plate_workflow_without_lineart_is_plain():
    wf = pl.plate_workflow(PLACE, "s", pl.Plate("a", "v"), None, 1)
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
    assert [(j[0].name, j[1].name, j[2]) for j in jobs] == [("toward-door-c01.png", "toward-door", art), ("toward-door-c02.png", "toward-door", art)]
    (dd / "mama-satos-izakaya" / "plates").mkdir(parents=True)
    (dd / "mama-satos-izakaya" / "plates" / "toward-door-c01.png").write_bytes(b"x")
    assert [j[0].name for j in pl.plan_jobs(s, work, dd, root, seeds=2)] == ["toward-door-c02.png"]
    (dd / "mama-satos-izakaya" / "plates" / "toward-door.png").write_bytes(b"x")
    assert pl.plan_jobs(s, work, dd, root, seeds=2) == []


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
    errs = asyncio.run(pl.render([(tmp_path / "o1.png", plate, art), (tmp_path / "o2.png", plate, art)], f, PLACE, "s", 10))
    assert len(errs) == 1 and "boom" in errs[0] and (tmp_path / "o2.png").read_bytes() == b"png"
    assert f.runs[0]["61"]["inputs"]["image"] == "in-plate-guide-toward-door.png"
    assert f.runs[0]["3"]["inputs"]["seed"] == 10 and f.runs[1]["3"]["inputs"]["seed"] == 11
