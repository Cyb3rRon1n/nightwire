from PIL import Image, ImageDraw

from tools.shorts.__main__ import main
from tools.shorts.guides import lineart, regions

from tests.test_shorts_cli import setup


def test_lineart_draws_edges_white_on_black(tmp_path):
    src = tmp_path / "g.png"
    im = Image.new("RGB", (100, 100), "black")
    ImageDraw.Draw(im).rectangle([30, 30, 70, 70], fill="white")
    im.save(src)
    out = Image.open(lineart(src, tmp_path / "l.png")).convert("L")
    assert out.getpixel((50, 50)) == 0 and out.getpixel((5, 5)) == 0
    assert max(out.getpixel((30, y)) for y in range(30, 71)) == 255


def test_regions_missing_is_empty_and_loads_json(tmp_path):
    assert regions(tmp_path) == {}
    (tmp_path / "guide").mkdir()
    (tmp_path / "guide" / "regions.json").write_text('{"start": {"C1": [0, 0, 0.5, 1]}}')
    assert regions(tmp_path)["start"]["C1"] == [0, 0, 0.5, 1]


def test_guides_command_writes_lineart_per_guide_png(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    sd = tmp_path / "design-data" / "shorts" / "pilot" / "shots" / "S01"

    def fake_run(work, slug):  # stands in for the Blender run: drops guide pngs
        (sd / "guide").mkdir(parents=True)
        for n in ("start", "end", "start-room", "end-room"):
            im = Image.new("RGB", (64, 64), "black")
            ImageDraw.Draw(im).rectangle([20, 20, 40, 40], fill="white")
            im.save(sd / "guide" / f"{n}.png")

    monkeypatch.setattr("tools.shorts.remote.run", fake_run)
    monkeypatch.setattr("tools.shorts.__main__.subprocess.run", lambda *a, **k: None)
    monkeypatch.setattr("tools.shorts.remote.encode", lambda *a: ["x"])
    assert main(["guides", "pilot"]) == 0
    for n in ("start", "end", "start-room", "end-room"):
        assert (sd / "guide" / f"{n}-lineart.png").exists()
