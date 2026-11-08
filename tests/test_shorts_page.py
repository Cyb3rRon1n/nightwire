import json

from tools.shorts.page import build, collect


def make_work(root):
    w = root / "pilot"
    (w / "shots" / "S01" / "preview").mkdir(parents=True)
    (w / "shots" / "S01" / "takes").mkdir()
    (w / "scene.json").write_text("{}")
    (w / "floorplan.png").write_bytes(b"p")
    (w / "shots" / "S01" / "greybox.mp4").write_bytes(b"g")
    (w / "shots" / "S01" / "preview" / "start.png").write_bytes(b"s")
    (w / "shots" / "S01" / "takes" / "t001.mp4").write_bytes(b"t")
    (w / "shots" / "S01" / "takes" / "t001.json").write_text(json.dumps({"model": "kling-3", "cost": 0.7}))
    (w / "costs.json").write_text(json.dumps([{"cost": 0.7}]))
    return w


def test_collect_lists_shots_and_takes(tmp_path):
    make_work(tmp_path)
    [entry] = collect(tmp_path, {"pilot": ("Last orders", 25.0)})
    assert entry["title"] == "Last orders" and entry["spent"] == 0.7 and entry["draft"] == ""
    take = entry["shots"][0]["takes"][0]
    assert take["image_id"] == "short--pilot--s01--t001" and take["src"] == "pilot/shots/S01/takes/t001.mp4"


def test_build_copies_media_and_writes_page(tmp_path):
    w = make_work(tmp_path / "work")
    (w / "draft.mp4").write_bytes(b"d")
    site = build(tmp_path / "work", tmp_path / "site", {"pilot": ("Last orders", 25.0)})
    assert (site / "pilot" / "shots" / "S01" / "takes" / "t001.mp4").read_bytes() == b"t"
    assert (site / "pilot" / "draft.mp4").read_bytes() == b"d"
    assert json.loads((site / "shorts.json").read_text())[0]["slug"] == "pilot"
    html = (site / "index.html").read_text()
    assert "/designs/api/images/" in html and "shorts.json" in html and "alert(" not in html


def test_page_lists_verdicts_from_exact_path_and_checks_ok(tmp_path):
    w = make_work(tmp_path / "work")
    html = (build(tmp_path / "work", tmp_path / "site", {"pilot": ("x", 25.0)}) / "index.html").read_text()
    assert 'fetch("/designs/api/images",' in html  # exact path: the picks API 404s on a trailing slash
    assert 'fetch(API + encodeURIComponent(id)' in html and 'API = "/designs/api/images/"' in html
    assert "vr.ok" in html
