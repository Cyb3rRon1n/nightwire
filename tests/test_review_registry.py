import json

import pytest
from PIL import Image

from tools.review.registry import Item, build_items, valid_id, web_copy, write_items


def test_valid_id():
    assert valid_id("plate--mama-satos-izakaya--toward-door")
    assert not valid_id("Plate--x") and not valid_id("") and not valid_id("a" * 101) and not valid_id("a_b")


def test_item_rejects_bad_id_and_stage():
    with pytest.raises(ValueError):
        Item("Bad Id", "plate", "pre-production", "p", "t", ["/x.jpg"])
    with pytest.raises(ValueError):
        Item("ok-id", "plate", "later", "p", "t", ["/x.jpg"])


def test_build_items_collects_and_keeps_going_on_error():
    def good(ctx):
        return [Item("a", "plate", "pre-production", "p", "A", ["/a.jpg"])]

    def broken(ctx):
        raise RuntimeError("boom")

    items, errors = build_items([good, broken], {})
    assert [i.id for i in items] == ["a"] and errors == ["broken: boom"]


def test_duplicate_ids_are_an_error():
    def twice(ctx):
        return [Item("a", "plate", "designs", "p", "A", ["/a.jpg"])] * 2

    items, errors = build_items([twice], {})
    assert len(items) == 1 and any("duplicate id a" in e for e in errors)


def test_web_copy_and_write(tmp_path):
    src = tmp_path / "big.png"
    Image.new("RGB", (4000, 1000), "red").save(src)
    url = web_copy(src, tmp_path / "site", "plates/x.jpg")
    assert url == "/review/media/plates/x.jpg"
    assert max(Image.open(tmp_path / "site" / "media" / "plates" / "x.jpg").size) == 2048
    path = write_items([Item("a", "plate", "designs", "p", "A", [url])], tmp_path / "site")
    data = json.loads(path.read_text())
    assert data["items"][0]["id"] == "a" and data["items"][0]["choices"] == ["keep", "fix", "reject"]
