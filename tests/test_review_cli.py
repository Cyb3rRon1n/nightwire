import json

from tools.review.__main__ import main


def test_build_writes_page_and_items(tmp_path, monkeypatch):
    dd = tmp_path / "dd"
    (dd / "shorts" / "_site").mkdir(parents=True)
    monkeypatch.setenv("NIGHTWIRE_DESIGN_DIR", str(dd))
    monkeypatch.setattr("tools.review.__main__.load_designs", lambda: {})
    assert main(["build"]) == 0
    site = dd / "review" / "_site"
    assert "items.json" in (site / "index.html").read_text()
    assert json.loads((site / "items.json").read_text())["items"] == []


def test_build_defaults_to_newest_lab_archive(tmp_path, monkeypatch):
    dd = tmp_path / "dd"
    (dd / "shorts" / "_site").mkdir(parents=True)
    for name, ids in (("2026-01-01", ["old-x"]), ("2026-11-01", ["new-y"])):
        (dd / "lab-archive" / name / "world-page").mkdir(parents=True)
        (dd / "lab-archive" / name / "world-page" / "ids.json").write_text(json.dumps(ids))
    monkeypatch.setenv("NIGHTWIRE_DESIGN_DIR", str(dd))
    monkeypatch.setattr("tools.review.__main__.load_designs", lambda: {})
    assert main(["build"]) == 0
    assert [i["id"] for i in json.loads((dd / "review" / "_site" / "items.json").read_text())["items"]] == ["new-y"]
