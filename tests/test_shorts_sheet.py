import json

from test_shorts_model import SHORT, SHOT, designs, write
from tools.shorts import sheet
from tools.shorts.model import load_short
from tools.shorts.preflight import Report


def test_collect_and_build(tmp_path):
    s = load_short(write(tmp_path / "script", short=SHORT.replace('budget_usd = 25.0', 'budget_usd = 25.0\nline_rule = "C1 screen-right"')))
    dd = tmp_path / "design-data"
    for slug in ("saeko-kirigaya", "rin-kageyama"):
        (dd / slug).mkdir(parents=True)
        from PIL import Image
        Image.new("RGB", (64, 64)).save(dd / slug / "turnaround.png")
    (dd / "mama-satos-izakaya").mkdir()
    from PIL import Image
    Image.new("RGB", (64, 64)).save(dd / "mama-satos-izakaya" / "play.png")
    work = dd / "shorts" / s.slug
    (work / "shots" / "S01").mkdir(parents=True)
    (work / "shots" / "S01" / "greybox.mp4").write_bytes(b"g")
    (work / "costs.json").write_text(json.dumps([
        {"shot": "S01", "take": "req-1", "model": "m", "cost": 1.0, "note": "override: owner said go"},
        {"shot": "S01", "take": "req-2", "model": "m", "cost": 0.5}, {"shot": "S02", "take": "req-3", "model": "m", "cost": 0.5, "note": "x"}]))
    ref = dd / "saeko-kirigaya" / "turnaround.png"
    plans = {"S01": (Report(problems=["missing size"], warnings=["w"]), "PROMPT TEXT", [("C1_turnaround.png", ref)])}
    data = sheet.collect(s, designs(), dd, work, "seedance-2.0-fast", plans)
    row = data["shots"][0]
    assert row["id"] == "S01" and row["problems"] == ["missing size"] and row["prompt"] == "PROMPT TEXT"
    assert row["image_id"].startswith(f"plan--{s.slug}--s01--") and row["cost"] > 0
    assert row["overrides"] == ["override: owner said go"] and data["spent"] == 2.0
    assert data["line_rule"] == "C1 screen-right" and data["lines"][0]["who"] == "C2"
    site = sheet.build(data, dd, work, tmp_path / "site")
    assert (site / "index.html").exists() and json.loads((site / "sheet.json").read_text())["slug"] == s.slug
    assert (site / "cast" / "saeko-kirigaya-turnaround.jpg").exists()
    html = (site / "index.html").read_text()
    assert "/designs/api/images/" in html and "alert(" not in html and "Paid without approval: " in html
