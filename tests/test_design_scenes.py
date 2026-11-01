from narrator.designs import Design
from tools import design_scenes as ds


def _c(slug, presentation="feminine", **k):
    return Design(name=slug, kind="character", source="x", presentation=presentation, status="approved", seed=7, tags=k.pop("tags", "red hair, cigarette"), **k)


LOC = Design(name="L", kind="location", source="x", status="approved", seed=9, tags="izakaya, lanterns")


def test_pair_keeps_each_character_on_their_own_side():
    a = _c("a", required=["purple eyes"], held=["cigarette"])
    b = _c("b", "masculine", tags="buzz cut")
    wf = ds.pair_workflow(a, b, LOC, 5)
    assert "1boy, 1girl" in wf["6"]["inputs"]["text"] and "izakaya" in wf["6"]["inputs"]["text"]
    left, right = wf["50"]["inputs"]["text"], wf["53"]["inputs"]["text"]
    assert "purple eyes" in left and "cigarette" not in left and "buzz cut" not in left and "buzz cut" in right
    la, ra = wf["51"]["inputs"], wf["54"]["inputs"]
    assert la["x"] == 0 and ra["x"] > 0 and la["x"] + la["width"] > ra["x"]
    assert ra["x"] + ra["width"] <= wf["5"]["inputs"]["width"]
    assert all(v % 8 == 0 for v in (la["width"], ra["width"], ra["x"]))
    assert wf["3"]["inputs"]["positive"] == ["55", 0] and wf["55"]["inputs"]["conditioning_1"] == ["52", 0]


def test_crowd_tags():
    assert ds._crowd(_c("a"), _c("b")) == "2girls"
    assert ds._crowd(_c("a", "masculine"), _c("b", "masculine")) == "2boys"
    assert ds._crowd(_c("a", "masculine"), _c("b")) == "1boy, 1girl"


def test_render_skips_existing_and_survives_a_failure(tmp_path):
    import asyncio

    class B:
        async def run_workflow(self, wf):
            if wf == "bad":
                raise RuntimeError("boom")
            return b"png"

    (tmp_path / "done.png").write_bytes(b"old")
    failed = asyncio.run(ds.render([("done.png", "x"), ("bad.png", "bad"), ("new.png", "x")], tmp_path, B()))
    assert failed == 1 and (tmp_path / "done.png").read_bytes() == b"old" and (tmp_path / "new.png").read_bytes() == b"png"
