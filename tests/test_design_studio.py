import io
import json
import zipfile

import pytest
from PIL import Image

from narrator.designs import Design, load_design, save_design
from tools import design_studio as ds


def _png(color=(200, 50, 50), size=(64, 48)):
    buf = io.BytesIO(); Image.new("RGB", size, color).save(buf, "PNG"); return buf.getvalue()


class FakeBackend:
    def __init__(self):
        self.workflows = []

    async def run_workflow(self, workflow):
        self.workflows.append(workflow)
        return _png()


@pytest.fixture
def studio(tmp_path):
    designs = tmp_path / "designs"; data = tmp_path / "data"
    designs.mkdir(); data.mkdir()
    save_design(Design(name="Mama Sato", kind="character", source="npc:Mama Sato", presentation="feminine",
                       tags="grey hair, hair bun, apron"), designs / "mama-sato.toml")
    save_design(Design(name="Izakaya", kind="location", source="place:Izakaya", tags="izakaya, lanterns",
                       alt_tags="indoors, counter", props=["lantern", "ramen bowl"]), designs / "izakaya.toml")
    return designs, data


def _args(studio, *rest):
    designs, data = studio
    return ["--designs-dir", str(designs), "--design-dir", str(data), "--no-gpu-etiquette", *rest]


async def test_candidates_writes_four_and_updates_status(studio):
    designs, data = studio
    backend = FakeBackend()
    assert await ds.main(_args(studio, "candidates", "mama-sato"), backend=backend) == 0
    files = sorted((data / "mama-sato" / "candidates").glob("r1-c*-*.png"))
    assert [f.name.split("-")[1] for f in files] == ["c1", "c2", "c3", "c4"]
    d = load_design(designs / "mama-sato.toml")
    assert d.status == "candidates" and d.notes[-1].endswith("round 1: 4 candidates")
    assert len(backend.workflows) == 4
    await ds.main(_args(studio, "candidates", "mama-sato"), backend=backend)
    assert len(list((data / "mama-sato" / "candidates").glob("r2-c*-*.png"))) == 4


async def test_all_drafts_and_rerolls_selection(studio):
    designs, _ = studio
    backend = FakeBackend()
    await ds.main(_args(studio, "candidates", "--all-drafts"), backend=backend)
    assert len(backend.workflows) == 8
    await ds.main(_args(studio, "reroll", "izakaya", "warmer light"))
    backend.workflows.clear()
    await ds.main(_args(studio, "candidates", "--rerolls"), backend=backend)
    assert len(backend.workflows) == 4
    assert "reroll: warmer light" in load_design(designs / "izakaya.toml").notes[-2]


async def test_approve_sets_seed_from_candidate(studio):
    designs, data = studio
    await ds.main(_args(studio, "candidates", "mama-sato"), backend=FakeBackend())
    c3 = next((data / "mama-sato" / "candidates").glob("r1-c3-*.png"))
    seed = int(c3.stem.split("-")[2])
    assert await ds.main(_args(studio, "approve", "mama-sato", "3")) == 0
    d = load_design(designs / "mama-sato.toml")
    assert d.status == "approved" and d.seed == seed and "approved r1 #3" in d.notes[-1]


async def test_approve_unknown_candidate_fails(studio):
    assert await ds.main(_args(studio, "approve", "mama-sato", "2")) == 1


async def test_sheets_for_character_and_location(studio):
    designs, data = studio
    backend = FakeBackend()
    for slug in ("mama-sato", "izakaya"):
        await ds.main(_args(studio, "candidates", slug), backend=backend)
        await ds.main(_args(studio, "approve", slug, "1"))
    backend.workflows.clear()
    assert await ds.main(_args(studio, "sheets", "--approved-missing"), backend=backend) == 0
    assert sorted(p.name for p in (data / "mama-sato").glob("*.png")) == ["colorguide.png", "expressions.png", "turnaround.png"]
    assert sorted(p.name for p in (data / "izakaya").glob("*.png")) == ["alternate.png", "establishing.png", "moodkeys.png", "props.png"]
    # 3 character sheets + establishing + alternate + props + 3 mood renders
    assert len(backend.workflows) == 9
    assert load_design(designs / "mama-sato.toml").palette
    backend.workflows.clear()
    await ds.main(_args(studio, "sheets", "--approved-missing"), backend=backend)
    assert backend.workflows == []


async def test_gallery_and_export(studio):
    designs, data = studio
    await ds.main(_args(studio, "candidates", "mama-sato"), backend=FakeBackend())
    await ds.main(_args(studio, "approve", "mama-sato", "1"))
    await ds.main(_args(studio, "sheets", "mama-sato"), backend=FakeBackend())
    await ds.main(_args(studio, "candidates", "izakaya"), backend=FakeBackend())
    assert await ds.main(_args(studio, "gallery")) == 0
    html = (data / "gallery" / "index.html").read_text()
    assert "Mama Sato" in html and "Izakaya" in html and "#4" in html
    assert (data / "gallery" / "img").is_dir()
    assert await ds.main(_args(studio, "export")) == 0
    zips = list((data / "exports").glob("nightwire-designs-*.zip"))
    names = zipfile.ZipFile(zips[0]).namelist()
    assert "mama-sato/design.toml" in names and "mama-sato/turnaround.png" in names
    assert not any(n.startswith("izakaya/") for n in names) and "index.html" in names


async def test_reapprove_clears_sheets_and_rerenders(studio):
    designs, data = studio
    backend = FakeBackend()
    await ds.main(_args(studio, "candidates", "mama-sato"), backend=backend)
    await ds.main(_args(studio, "approve", "mama-sato", "1"))
    await ds.main(_args(studio, "sheets", "mama-sato"), backend=backend)
    assert load_design(designs / "mama-sato.toml").palette
    await ds.main(_args(studio, "reroll", "mama-sato", "older"))
    assert load_design(designs / "mama-sato.toml").status == "candidates"
    await ds.main(_args(studio, "candidates", "mama-sato"), backend=backend)
    await ds.main(_args(studio, "approve", "mama-sato", "2"))
    d = load_design(designs / "mama-sato.toml")
    assert d.palette == [] and not list((data / "mama-sato").glob("*.png"))
    backend.workflows.clear()
    await ds.main(_args(studio, "sheets", "--approved-missing"), backend=backend)
    assert len(backend.workflows) == 3
    assert load_design(designs / "mama-sato.toml").palette


async def test_gpu_etiquette_scheme_and_all_models(monkeypatch):
    calls = []

    class Resp:
        def read(self):
            return b'{"models": [{"name": "a:1"}, {"name": "b:2"}]}'

    def fake(req, timeout=None):
        calls.append((req.full_url, req.data))
        return Resp()

    monkeypatch.setenv("OLLAMA_HOST", "10.0.0.5:11434")
    monkeypatch.setattr(ds.urllib.request, "urlopen", fake)
    ds._gpu_etiquette("http://c:8188", before=True)
    assert all(u.startswith("http://10.0.0.5:11434/") for u, _ in calls)
    unloads = [json.loads(b) for u, b in calls if u.endswith("/api/generate")]
    assert [x["model"] for x in unloads] == ["a:1", "b:2"] and all(x["keep_alive"] == 0 for x in unloads)


class FailingBackend(FakeBackend):
    def __init__(self, fail_marker):
        super().__init__(); self.fail_marker = fail_marker; self.current = None

    async def run_workflow(self, workflow):
        if self.fail_marker in json.dumps(workflow):
            raise RuntimeError("boom")
        return await super().run_workflow(workflow)


async def test_candidates_continue_after_failure(studio):
    designs, data = studio
    rc = await ds.main(_args(studio, "candidates", "mama-sato", "izakaya"), backend=FailingBackend("lantern"))
    assert rc == 1
    assert len(list((data / "mama-sato" / "candidates").glob("*.png"))) == 4
    assert load_design(designs / "mama-sato.toml").status == "candidates"


async def test_sheets_continue_after_failure(studio):
    designs, data = studio
    for slug in ("mama-sato", "izakaya"):
        await ds.main(_args(studio, "candidates", slug), backend=FakeBackend())
        await ds.main(_args(studio, "approve", slug, "1"))
    rc = await ds.main(_args(studio, "sheets", "izakaya", "mama-sato"), backend=FailingBackend("lantern"))
    assert rc == 1
    assert load_design(designs / "mama-sato.toml").palette


async def test_batch_reloads_design_from_disk(studio):
    designs, _ = studio

    class EditingBackend(FakeBackend):
        async def run_workflow(self, workflow):
            if not self.workflows:  # first render of the batch: hand-edit the second design
                d = load_design(designs / "izakaya.toml"); d.tags = "izakaya, edited-tag"
                save_design(d, designs / "izakaya.toml")
            return await super().run_workflow(workflow)

    await ds.main(_args(studio, "candidates", "mama-sato", "izakaya"), backend=EditingBackend())
    d = load_design(designs / "izakaya.toml")
    assert d.tags == "izakaya, edited-tag" and d.status == "candidates"
