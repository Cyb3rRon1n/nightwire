import json
from types import SimpleNamespace

from PIL import Image

from tools.review import producers as P


def png(path, size=(64, 64)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "blue").save(path)
    return path


def ctx(tmp_path, designs=None, world=None):
    return {"design_dir": tmp_path / "dd", "site": tmp_path / "site", "world_ids": world,
            "shorts_site": tmp_path / "dd" / "shorts" / "_site", "designs": designs or {}}


def char(slug, status="approved"):
    return SimpleNamespace(slug=slug, name=slug.title(), kind="character", status=status)


def test_sheets_one_item_per_character_with_old_versions_as_compare(tmp_path):
    c = ctx(tmp_path, {"saeko": char("saeko"), "draft": char("draft", "draft")})
    png(c["design_dir"] / "saeko" / "turnaround.png")
    png(c["design_dir"] / "saeko" / "turnaround-old.png")
    png(c["design_dir"] / "saeko" / "portrait.png")
    png(c["design_dir"] / "draft" / "turnaround.png")
    (item,) = P.sheets(c)
    assert item.kind == "sheet" and item.stage == "designs" and item.project == "saeko"
    assert item.id.startswith("sheet--saeko--") and len(item.files) == 2
    assert [x["label"] for x in item.compare] == ["Turnaround: before"]


def test_candidates_from_gallery_rounds(tmp_path):
    c = ctx(tmp_path)
    g = c["design_dir"] / "gallery"
    png(g / "img" / "rin" / "r2-c1.jpg"); png(g / "img" / "rin" / "r2-c2.jpg")
    (g / "rounds.json").write_text(json.dumps({"rin": 2}))
    (item,) = P.candidates(c)
    assert item.kind == "pick" and item.choices == ("pick", "reroll", "skip")
    assert item.extra == {"slug": "rin", "round": 2, "n": [1, 2]}
    assert item.files == ["/designs/img/rin/r2-c1.jpg", "/designs/img/rin/r2-c2.jpg"]


def test_world_takes_wallpapers(tmp_path):
    ids = tmp_path / "ids.json"
    ids.write_text(json.dumps(["cast-rin"]))
    c = ctx(tmp_path, world=ids)
    (w,) = P.world(c)
    assert w.id == "cast-rin" and w.files == ["/world/cast-rin.jpg"] and w.stage == "production"
    site = c["shorts_site"]
    site.mkdir(parents=True)
    (site / "shorts.json").write_text(json.dumps([{"slug": "pilot", "title": "Resting", "shots": [
        {"id": "S01", "takes": [{"id": "t001", "image_id": "short--pilot--s01--t001", "src": "pilot/S01/takes/t001.mp4"}]}]}]))
    (t,) = P.takes(c)
    assert t.id == "short--pilot--s01--t001" and t.files == ["/shorts/pilot/S01/takes/t001.mp4"] and t.project == "pilot"
    (site / "loops").mkdir()
    (site / "loops" / "loops.json").write_text(json.dumps({"wallpapers": [
        {"id": "loop--x", "file": "x.mp4", "title": "X", "note": "n"}], "experiments": []}))
    (wp,) = P.wallpapers(c)
    assert wp.id == "loop--x" and wp.files == ["/shorts/loops/x.mp4"] and wp.stage == "finished"
