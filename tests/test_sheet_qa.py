"""Synthetic-image tests for tools/sheet_qa.py."""
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from tools import sheet_qa as q

GREY = (128, 128, 128)
SKIN = (240, 200, 170)
RED, DARK_RED = (240, 20, 40), (110, 10, 25)
design = SimpleNamespace(appearance="1girl, red hair, purple eyes")


def figure(d, x, hair, front=True, jacket=(30, 30, 35), open_chest=False):
    d.ellipse((x, 100, x + 80, 190), fill=hair)  # head, hair-covered
    if front:
        d.rectangle((x + 15, 125, x + 65, 185), fill=SKIN)  # face
    d.rectangle((x - 10, 190, x + 90, 330), fill=jacket)  # torso
    if open_chest:
        d.rectangle((x + 25, 200, x + 55, 260), fill=SKIN)
    d.rectangle((x, 330, x + 80, 700), fill=(30, 30, 35))  # legs


def make(tmp, hair=RED, portrait_hair=RED, front3=False, jacket3=(30, 30, 35), open_chest=False, n=3):
    im = Image.new("RGB", (900, 800), GREY)
    d = ImageDraw.Draw(im)
    for i in range(n):
        figure(d, 80 + i * 280, hair, True if i < 2 or front3 else False, jacket3 if i == 2 else (30, 30, 35), open_chest and i == 0)
    im.save(tmp / "turnaround.png")
    p = Image.new("RGB", (600, 600), GREY)
    ImageDraw.Draw(p).ellipse((100, 20, 500, 300), fill=portrait_hair)
    p.save(tmp / "portrait.png")


def flags(tmp):
    return [l for l in q.check_set(tmp, design, "work") if l.startswith("FLAG")]


def test_clean_set_passes(tmp_path):
    make(tmp_path)
    assert flags(tmp_path) == []


def test_hair_mismatch_flagged_and_fixed(tmp_path):
    make(tmp_path, portrait_hair=DARK_RED)
    assert any("hair portrait" in l for l in flags(tmp_path))
    out = tmp_path / "out"
    out.mkdir()
    assert [p.name for p in q.fix_hair(tmp_path, design, out)] == ["portrait-fixed.png"]
    fixed = np.asarray(Image.open(out / "portrait-fixed.png"))[150, 300]
    assert fixed[0] > 200  # back to bright red
    assert np.asarray(Image.open(tmp_path / "portrait.png"))[150, 300][0] < 150  # original untouched


def test_front_view_third_figure_flagged(tmp_path):
    make(tmp_path, front3=True)
    assert any("FRONT view" in l for l in flags(tmp_path))


def test_outfit_mismatch_flagged(tmp_path):
    make(tmp_path, jacket3=(230, 190, 20))
    assert any("outfit" in l for l in flags(tmp_path))


def test_wrong_figure_count_flagged(tmp_path):
    make(tmp_path, n=2)
    assert any("2 figures" in l for l in flags(tmp_path))


def test_open_chest_flagged(tmp_path):
    make(tmp_path, open_chest=True)
    assert any("cover" in l for l in flags(tmp_path))


def test_black_hair_hue_noise_not_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "_hair_tag", lambda d: "black")
    make(tmp_path, hair=(12, 10, 14), portrait_hair=(10, 12, 16))  # same black, different hue
    assert not any("hair" in l for l in flags(tmp_path))
