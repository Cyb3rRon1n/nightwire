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


def test_sheet_version_ignores_props_like_the_review_page(tmp_path):
    import os
    from narrator.design_sheets import CHARACTER_SHEETS
    c = ctx(tmp_path, {"saeko": char("saeko")})
    folder = c["design_dir"] / "saeko"
    for s in ("turnaround", "portrait", "props"):
        png(folder / f"{s}.png")
    os.utime(folder / "props.png", ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))  # props is newest
    (item,) = P.sheets(c)
    want = max((folder / f"{s}.png").stat().st_mtime_ns for s in CHARACTER_SHEETS if (folder / f"{s}.png").exists())
    assert item.id == f"sheet--saeko--{want}" and len(item.files) == 3


def _shorts_world(tmp_path, with_scene=True):
    from tests.test_shorts_model import SHORT, SHOT, write
    scene = '\n[scene]\ntime = "late night"\nweather = "indoors"\nset = "a bar"\n[wardrobe]\nC1 = "coat"\n' if with_scene else ""
    write(tmp_path / "shorts" / "pilot", SHORT + scene, SHOT.replace("lens = 35.0", 'lens = 35.0\nplate = "toward-door"'))
    (tmp_path / "plates").mkdir()
    (tmp_path / "plates" / "mama-satos-izakaya.toml").write_text(
        '[[plate]]\nname = "toward-door"\nview = "toward the door"\n[[plate]]\nname = "toward-shelves"\nview = "v"\nsource = "play.png"\n')
    c = ctx(tmp_path)
    c.update(shorts_dir=tmp_path / "shorts", plates_root=tmp_path / "plates")
    return c


def test_plates_item_per_plate_with_candidates_then_chosen(tmp_path):
    c = _shorts_world(tmp_path)
    base = c["design_dir"] / "mama-satos-izakaya"
    assert P.plates(c) == []  # nothing rendered yet
    png(base / "play.png")
    png(base / "plates" / "toward-door-c01.png")
    png(base / "plates" / "toward-door-c02.png")
    (item,) = P.plates(c)
    assert item.id == "plate--mama-satos-izakaya--toward-door" and item.kind == "plate" and item.stage == "pre-production"
    assert len(item.files) == 2 and item.context.endswith("toward the door")
    assert item.compare[0]["label"] == "Approved room"
    png(base / "plates" / "toward-door.png")
    (item,) = P.plates(c)
    assert len(item.files) == 1 and item.files[0].endswith("toward-door.jpg") and item.context == "toward the door"


def test_plates_adopted_source_still_gets_an_item(tmp_path):
    c = _shorts_world(tmp_path)
    c["plates_root"].joinpath("mama-satos-izakaya.toml").write_text(
        '[[plate]]\nname = "toward-door"\nview = "v"\nsource = "play.png"\n')
    png(c["design_dir"] / "mama-satos-izakaya" / "play.png")
    (item,) = P.plates(c)
    assert item.id.startswith("plate--mama-satos-izakaya--toward-door--") and len(item.files) == 1


def test_scenes_item_carries_bible_wardrobe_and_fingerprint_id(tmp_path):
    from tools.shorts.approve import scene_fp
    from tools.shorts.model import load_short
    c = _shorts_world(tmp_path)
    png(c["design_dir"] / "mama-satos-izakaya" / "play.png")
    (item,) = P.scenes(c)
    fp = scene_fp(load_short(tmp_path / "shorts" / "pilot"))
    assert item.id == f"plan--pilot--scene--{fp}" and item.kind == "scene" and len(item.files) == 1
    assert "late night" in item.context and "Wardrobe C1: coat" in item.context
    assert P.plates in P.ALL and P.scenes in P.ALL
    assert P.scenes(_shorts_world(tmp_path / "x", with_scene=False)) == []


def test_plans_item_when_only_approvals_pending_and_cut_item(tmp_path, monkeypatch):
    from test_shorts_cli import PACKAGED, setup
    from test_shorts_model import designs
    setup(tmp_path, monkeypatch, shot=PACKAGED, approved=False)
    toml = tmp_path / "script" / "pilot" / "short.toml"
    toml.write_text('model = "seedance-2.0-fast"\n' + toml.read_text())
    dd = tmp_path / "design-data"
    c = {"design_dir": dd, "site": tmp_path / "site", "shorts_dir": tmp_path / "script", "plates_root": tmp_path / "plates",
         "designs": designs(), "images": {}}
    png(dd / "shorts" / "pilot" / "shots" / "S01" / "preview" / "start.png")
    (item,) = P.plans(c)  # the plate is unapproved: an approval-pending problem only
    assert item.kind == "plan" and item.stage == "pre-production" and item.id.startswith("plan--pilot--s01--")
    assert len(item.files) == 1 and "Cost: about $" in item.context and "Waiting on: plate door not approved" in item.context
    shot = tmp_path / "script" / "pilot" / "shots" / "S01.toml"
    shot.write_text(shot.read_text().replace("C2 asks who paid her tab.", ""))
    assert P.plans(c) == []  # a real problem (empty action) hides it
    assert P.plans in P.ALL and P.cuts in P.ALL
    assert P.cuts(c) == []
    (dd / "shorts" / "pilot" / "draft.mp4").write_bytes(b"v")
    (cut,) = P.cuts(c)
    assert cut.id.startswith("cut--pilot--") and len(cut.id) == len("cut--pilot--") + 10 and cut.kind == "cut" and cut.stage == "finished"
    copy = c["site"] / "media" / "cuts" / "pilot" / "draft.mp4"
    before = copy.stat().st_mtime_ns
    import time
    time.sleep(0.01)
    P.cuts(c)
    assert copy.stat().st_mtime_ns == before  # not rewritten
    (dd / "shorts" / "pilot" / "draft.mp4").write_bytes(b"other cut")
    assert P.cuts(c)[0].id != cut.id


def test_plans_fp_follows_plate_pixels_and_equals_submit_fp(tmp_path, monkeypatch):
    from test_shorts_cli import PACKAGED, setup
    from test_shorts_model import designs
    from tools.shorts import __main__ as cli
    from tools.shorts import approve
    from tools.shorts.backends import fal
    from tools.shorts.model import load_short
    setup(tmp_path, monkeypatch, shot=PACKAGED, approved=False)
    toml = tmp_path / "script" / "pilot" / "short.toml"
    toml.write_text('model = "seedance-2.0-fast"\n' + toml.read_text())
    dd = tmp_path / "design-data"
    c = {"design_dir": dd, "site": tmp_path / "site", "shorts_dir": tmp_path / "script", "plates_root": tmp_path / "plates",
         "designs": designs(), "images": {}}
    (item,) = P.plans(c)
    s = load_short(tmp_path / "script" / "pilot")
    shot = s.shots[0]
    model = fal.shot_model(shot, s.model)
    _, prompt, refs = cli._preflight(s, shot, model, designs())  # submit's path: module defaults
    refs, _ = fal.usable_refs(model, refs)
    fp = approve.fingerprint(model, prompt, refs, int(round(shot.duration)), approve.fp_extra(s, shot, dd))
    assert item.id == approve.plan_image_id("pilot", shot.id, fp)
    png(dd / "mama-satos-izakaya" / "plates" / "door.png", size=(16, 16))  # plate re-rendered
    (changed,) = P.plans(c)
    assert changed.id != item.id
    # env var is the one override for every consumer
    monkeypatch.setenv("NIGHTWIRE_PLATES_DIR", str(tmp_path / "plates"))
    monkeypatch.setattr("tools.shorts.plates.PLATES_ROOT", tmp_path / "nowhere")
    del c["plates_root"]
    assert P.plans(c)[0].id == changed.id


def warded(slug="mama", text="shop", identity=("late 50s",)):
    from narrator.designs import WardrobeState
    d = char(slug)
    d.identity, d.appearance = list(identity), "grey hair"
    d.wardrobe = {"work": WardrobeState(text=text, tags="kimono", props=["ladle"])}
    return d


def test_bible_item_id_changes_with_text_and_includes_decisions(tmp_path):
    c = ctx(tmp_path, {"mama": warded()})
    png(c["design_dir"] / "mama" / "turnaround.png"); png(c["design_dir"] / "mama" / "portrait.png")
    (c["design_dir"] / "bibles").mkdir(); (c["design_dir"] / "bibles" / "mama-decisions.md").write_text("Q1: age?")
    (item,) = P.bibles(c)
    assert item.kind == "bible" and item.stage == "designs" and item.id.startswith("bible--mama--") and len(item.files) == 2
    assert "late 50s" in item.context and "ladle" in item.context and "Q1: age?" in item.context
    c["designs"]["mama"] = warded(text="shop apron")
    assert P.bibles(c)[0].id != item.id
    assert P.bibles(ctx(tmp_path, {"x": char("x")})) == []


def test_sheet_sets_need_all_four_and_id_follows_bytes_and_v1_sheets_skip_states(tmp_path):
    c = ctx(tmp_path, {"mama": warded()})
    w = c["design_dir"] / "mama" / "wardrobe" / "work"
    png(c["design_dir"] / "mama" / "turnaround.png"); png(c["design_dir"] / "mama" / "portrait.png")
    for s in ("turnaround", "portrait", "expressions"):
        png(w / f"{s}.png")
    assert P.sheet_sets(c) == []
    png(w / "props.png"); png(w / "colorguide.png")
    (item,) = P.sheet_sets(c)
    assert item.kind == "sheet-set" and item.id.startswith("sheet--mama--work--") and len(item.files) == 5 and len(item.compare) == 2
    png(w / "colorguide.png", (9, 9))
    assert P.sheet_sets(c)[0].id == item.id  # colour guide is shown, not hashed
    png(w / "props.png", (9, 9))
    assert P.sheet_sets(c)[0].id != item.id
    assert P.sheets(c) == []  # v1 item skipped for characters with states
    assert P.bibles in P.ALL and P.sheet_sets in P.ALL
