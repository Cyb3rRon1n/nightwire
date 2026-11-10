import subprocess

import numpy as np
import pytest
from PIL import Image
from test_shorts_film import BOARD, FILM, SCENE, with_plate_key, world
from test_shorts_model import SHOT
from tools.lights import Lights
from tools.shorts import animatic, boards, film, wall
from tools.shorts.model import load_short


def _setup(tmp, shot):
    shorts, films, lib, plates, dd = world(tmp, shot=shot)
    _setup.plates = plates
    s = load_short(shorts / "pilot")
    boards.build(s, dd, dd / "shorts" / "pilot", lib, plates)
    return film.load_film("night", films, shorts), shorts, dd


def test_zoom_math():
    assert animatic.zoom_pan("slow push-in", 0) == (1.0, 0.0)
    assert animatic.zoom_pan("slow push-in", 1)[0] == pytest.approx(1.06)
    z, p0 = animatic.zoom_pan("slow pan", 0)
    assert z > 1 and p0 < 0 < animatic.zoom_pan("slow pan", 1)[1]
    assert animatic.zoom_pan("", 0.5) == (1.0, 0.0) == animatic.zoom_pan("static", 1)


def test_frame_count_gap_and_caption(tmp_path, monkeypatch):
    f, shorts, dd = _setup(tmp_path, SHOT + BOARD)  # 5 s, board start+end
    f.scenes = ["pilot", "pilot"]
    fr = list(animatic.frames(f, shorts, dd, fps=4, size=(160, 112), plates_root=_setup.plates))
    assert len(fr) == 2 * 5 * 4 + round(animatic.GAP_S * 4)
    assert fr[20 + 1].getbbox() is None  # the black gap
    cap = fr[0].crop((0, 112 - 20, 160, 112))
    assert cap.getbbox() is not None and cap.convert("L").getextrema()[1] > 150  # caption text drawn
    assert fr[0].crop((0, 0, 160, 80)).convert("L").getextrema()[1] > 0


def test_lights_only_for_short_shots_and_breathe(tmp_path):
    f, shorts, dd = _setup(tmp_path, with_plate_key(SHOT) + BOARD)
    plate = dd / "mama-satos-izakaya" / "plates" / "door.png"
    im = Image.new("RGB", (320, 200), (10, 10, 10))
    im.paste((255, 40, 200), (100, 60, 220, 140))
    im.save(plate)
    a = list(animatic.frames(f, shorts, dd, fps=4, size=(160, 112), plates_root=_setup.plates))
    b = list(animatic.frames(f, shorts, dd, fps=4, size=(160, 112), lights=False, plates_root=_setup.plates))
    assert len(a) == len(b) and any(x.tobytes() != y.tobytes() for x, y in zip(a, b))


def test_lights_gain_breathes_only_on_lights():
    img = np.full((120, 200, 3), 15, np.uint8)
    img[40:80, 60:140] = (60, 20, 255)
    lt = Lights(img, "200x120", seconds=4, fps=8)
    g0, g1 = lt.gain(0)[..., 0], lt.gain(5)[..., 0]
    assert g0.shape == (120, 200) and abs(g0 - g1).max() > 0.01
    assert g0[0, 0] == 1.0 and lt.gain(lt.N)[..., 0].tolist() == g0.tolist()  # dark stays, loop seamless


def test_build_encodes_and_wall_links(tmp_path):
    f, shorts, dd = _setup(tmp_path, SHOT.replace("end = 5.0", "end = 1.0") + BOARD)
    site = tmp_path / "site"
    out = animatic.build(f, "night", shorts, dd, site, fps=4, size=(160, 112), plates_root=_setup.plates)
    assert out == site / "films" / "night" / "animatic.mp4"
    n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v", "-show_entries", "stream=nb_read_frames",
                        "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    assert n == "4"
    wall.build(f, "night", shorts, dd, site)
    assert "animatic.mp4" in (site / "films" / "night" / "index.html").read_text()


def test_vertical_frames_and_build(tmp_path):
    f, shorts, dd = _setup(tmp_path, SHOT.replace("end = 5.0", "end = 1.0").replace("lens = 35.0", "lens = 35.0\nvertical = [0.2]") + BOARD)
    fr = list(animatic.frames(f, shorts, dd, fps=4, size=(160, 112), plates_root=_setup.plates, vertical=(54, 96)))
    assert len(fr) == 4 and fr[0].size == (54, 96)
    out = animatic.build(f, "night", shorts, dd, tmp_path / "site", fps=4, size=(160, 112), plates_root=_setup.plates, vertical=True)
    assert out.name == "animatic-9x16.mp4"
    wh = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
                        capture_output=True, text=True).stdout.strip()
    assert wh == "1080,1920"
