from PIL import Image, ImageDraw

from tools import reference_library as lib


def _turnaround(n):
    im = Image.new("RGB", (900, 400), (128, 128, 128))
    d = ImageDraw.Draw(im)
    for i in range(n):
        d.rectangle((50 + i * 300, 20, 150 + i * 300, 380), fill=(20, 20, 20))
    d.rectangle((870, 100, 875, 110), fill=(250, 0, 0))  # stray mark, not a person
    return im


def test_split_figures_finds_people_and_ignores_stray_marks():
    figures = lib.split_figures(_turnaround(3))
    assert [f.size for f in figures] == [(101, 361)] * 3


def test_views_are_only_labelled_from_a_clean_three_view_split(tmp_path):
    for slug, n, want in (("three", 3, ["front", "side", "back"]), ("two", 2, ["figure-0", "figure-1"])):
        (tmp_path / "d" / slug).mkdir(parents=True)
        _turnaround(n).save(tmp_path / "d" / slug / "turnaround.png")
        assert [e["view"] for e in lib.build_character(slug, tmp_path / "d", tmp_path / "lib")] == want


def test_scene_images_need_owner_approval_and_survive_a_rebuild(tmp_path):
    (tmp_path / "d" / "a").mkdir(parents=True)
    _turnaround(3).save(tmp_path / "d" / "a" / "turnaround.png")
    lib.build_character("a", tmp_path / "d", tmp_path / "lib")
    src = tmp_path / "x.png"
    _turnaround(1).save(src)
    assert lib.add_scene("a", src, tmp_path / "lib", lighting="neon", place="bar", note="")["owner_ok"] is False
    lib.build_character("a", tmp_path / "d", tmp_path / "lib")
    assert [e["kind"] for e in lib._load(tmp_path / "lib" / "a" / "manifest.json")] == ["view", "view", "view", "scene"]


def test_every_pose_has_all_body_points(tmp_path):
    for name in lib.POSES:
        assert set(lib.pose_points(name)) == set(lib._ORDER), name
