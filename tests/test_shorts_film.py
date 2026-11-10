import hashlib
import json

import pytest
from PIL import Image
from test_greybox_library import _cell
from test_shorts_model import SHORT, SHOT, write
from tools.review import producers as P
from tools.shorts import boards, film, wall
from tools.shorts.model import load_short, validate_short

BOARD = '''
[[board]]
which = "start"
figure = "C1"
pose = "stand"
camera = "ws-front"
feet = [0.4, 0.9]
height = 0.5

[[board]]
which = "end"
figure = "C2"
pose = "stand"
camera = "ws-front"
feet = [0.7, 0.9]
height = 0.4
'''
SCENE = '''
[scene]
time = "late night"
weather = "rain"
set = "an izakaya"
light = ["paper lantern"]

[wardrobe]
C1 = "navy jacket zipped"
'''
FILM = 'title = "One night"\ncharacter = "saeko-kirigaya"\nlogline = "A night."\nmood = "wet neon"\nscenes = ["pilot"]\n'



def world(tmp, shot=SHOT + BOARD, with_plate=True, short=SHORT + SCENE):
    shorts, films, lib = tmp / "shorts", tmp / "films", tmp / "lib"
    write(shorts / "pilot", short=short, shot=shot)
    films.mkdir()
    (films / "night.toml").write_text(FILM)
    lib.mkdir()
    for pose in ("stand",):
        (lib / pose).mkdir()
        _cell_at(lib / pose / "ws-front")
    plates = tmp / "plates"
    plates.mkdir()
    (plates / "mama-satos-izakaya.toml").write_text('[[plate]]\nname = "door"\nview = "toward the door"\n')
    dd = tmp / "dd"
    if with_plate:
        (dd / "mama-satos-izakaya" / "plates").mkdir(parents=True)
        Image.new("RGB", (1000, 600), (200, 180, 160)).save(dd / "mama-satos-izakaya" / "plates" / "door.png")
    return shorts, films, lib, plates, dd


def _cell_at(path):
    src = _cell(path.parent, "tmp-" + path.name)
    src.rename(path)


def with_plate_key(shot):
    return shot.replace("lens = 35.0", 'lens = 35.0\nplate = "door"')


def test_board_fields_load_and_validate(tmp_path):
    s = load_short(write(tmp_path / "s", shot=SHOT + BOARD))
    b = s.shots[0].boards
    assert [(x.which, x.figure, x.pose, x.camera, x.feet, x.height) for x in b][0] == ("start", "C1", "stand", "ws-front", (0.4, 0.9), 0.5)
    assert not [p for p in validate_short(s, {}) if "board" in p]


@pytest.mark.parametrize("old,new,msg", [
    ('pose = "stand"\ncamera = "ws-front"\nfeet = [0.4', 'pose = "nope"\ncamera = "ws-front"\nfeet = [0.4', "pose"),
    ('camera = "ws-front"\nfeet = [0.4', 'camera = "nope"\nfeet = [0.4', "camera"),
    ('which = "start"', 'which = "middle"', "which"),
    ('figure = "C1"', 'figure = "C9"', "figure"),
    ("height = 0.5", "height = 1.5", "height"),
    ("feet = [0.4, 0.9]", "feet = [4, 0.9]", "feet"),
])
def test_board_validation(tmp_path, old, new, msg):
    assert old in BOARD
    s = load_short(write(tmp_path / "s", shot=SHOT + BOARD.replace(old, new, 1)))
    assert any("board" in p and msg in p for p in validate_short(s, {}))


def test_load_film_and_validation(tmp_path):
    shorts, films, *_ = world(tmp_path)
    f = film.load_film("night", films, shorts)
    assert (f.title, f.character, f.mood, f.scenes) == ("One night", "saeko-kirigaya", "wet neon", ["pilot"])
    (films / "bad.toml").write_text(FILM.replace('["pilot"]', '["pilot", "ghost"]'))
    with pytest.raises(ValueError, match="ghost"):
        film.load_film("bad", films, shorts)
    (films / "empty.toml").write_text(FILM.replace('["pilot"]', "[]"))
    with pytest.raises(ValueError, match="scenes"):
        film.load_film("empty", films, shorts)
    with pytest.raises(ValueError, match="no film"):
        film.load_film("none", films, shorts)


def test_boards_build_on_plate_with_real_library_format(tmp_path):
    shorts, films, lib, plates, dd = world(tmp_path, shot=with_plate_key(SHOT) + BOARD)
    s = load_short(shorts / "pilot")
    out = boards.build(s, dd, dd / "shorts" / "pilot", lib, plates)
    assert [p.name for p in out] == ["board-start.png", "board-end.png"]
    im = Image.open(out[0])
    assert im.size == (1000, 600)  # the plate's size
    assert out[0].with_name("board-start.pose.json").exists()
    assert out[0].parent == dd / "shorts" / "pilot" / "shots" / "S01"


def test_missing_plate_gets_dark_placeholder_with_name(tmp_path):
    shorts, films, lib, plates, dd = world(tmp_path, shot=with_plate_key(SHOT) + BOARD, with_plate=False)
    s = load_short(shorts / "pilot")
    out = boards.build(s, dd, dd / "shorts" / "pilot", lib, plates)
    im = Image.open(out[0]).convert("RGB")
    assert im.size == boards.CARD and sum(im.getpixel((5, 5))) < 150  # dark
    # the plate name is drawn on the card: some pixels are bright outside the figures
    assert max(sum(im.getpixel((x, y))) for x in range(24, 300) for y in range(24, 64)) > 250  # dimmed by the board darkening


def test_missing_library_cell_is_a_clear_error(tmp_path):
    shorts, films, lib, plates, dd = world(tmp_path)
    s = load_short(shorts / "pilot")
    import shutil
    shutil.rmtree(lib / "stand")
    with pytest.raises(ValueError, match="stand/ws-front"):
        boards.build(s, dd, dd / "shorts" / "pilot", lib, plates)


def test_shot_filter(tmp_path):
    shorts, films, lib, plates, dd = world(tmp_path)
    s = load_short(shorts / "pilot")
    assert boards.build(s, dd, dd / "w", lib, plates, shot="S99") == []


def _built(tmp_path, **kw):
    shorts, films, lib, plates, dd = world(tmp_path, **kw)
    s = load_short(shorts / "pilot")
    boards.build(s, dd, dd / "shorts" / "pilot", lib, plates)
    return shorts, films, dd, plates


def test_wall_page_contents(tmp_path):
    shorts, films, dd, plates = _built(tmp_path, shot=with_plate_key(SHOT.replace('summary = "', 'summary = "<b>', 1)) + BOARD)
    f = film.load_film("night", films, shorts)
    page = wall.build(f, "night", shorts, dd, tmp_path / "site")
    assert page == tmp_path / "site" / "films" / "night" / "index.html"
    html = page.read_text()
    for needle in ("One night", "wet neon", "late night", "mama-satos-izakaya", "navy jacket zipped", "C1",
                   "S01", "5 s", "/review/?project=night", "boards/pilot-S01.jpg"):
        assert needle in html, needle
    assert "&lt;b&gt;slow push" in html  # escaped
    assert (page.parent / "boards" / "pilot-S01.jpg").exists()
    assert "<script" not in html


def test_wall_without_boards_still_builds(tmp_path):
    shorts, films, lib, plates, dd = world(tmp_path)
    f = film.load_film("night", films, shorts)
    html = wall.build(f, "night", shorts, dd, tmp_path / "site").read_text()
    assert "no board yet" in html and "S01" in html


def ctx(tmp_path, shorts, films, plates=None):
    return {"design_dir": tmp_path / "dd", "site": tmp_path / "rsite", "shorts_dir": shorts, "films_dir": films,
            "plates_root": plates, "shorts_site": tmp_path / "dd" / "shorts" / "_site", "designs": {}}


def test_films_producer_item_and_id_changes(tmp_path):
    shorts, films, dd, plates = _built(tmp_path)
    c = ctx(tmp_path, shorts, films, plates)
    (item,) = P.films(c)
    assert item.kind == "wall" and item.stage == "pre-production" and item.project == "night"
    assert item.id.startswith("film--night--") and len(item.id.split("--")[2]) == 10
    assert len(item.files) == 2 and "S01" in item.context and "pilot" in item.context
    again = P.films(c)[0].id
    assert again == item.id
    # film TOML change
    (films / "night.toml").write_text(FILM.replace("wet neon", "dry"))
    assert P.films(c)[0].id != item.id
    (films / "night.toml").write_text(FILM)
    assert P.films(c)[0].id == item.id
    # shot TOML change
    sh = shorts / "pilot" / "shots" / "S01.toml"
    sh.write_text(sh.read_text().replace("slow push in", "slow push out"))
    changed = P.films(c)[0].id
    assert changed != item.id
    # board png change
    png = dd / "shorts" / "pilot" / "shots" / "S01" / "board-start.png"
    Image.new("RGB", (10, 10)).save(png)
    assert P.films(c)[0].id != changed


def test_films_producer_in_registry_and_no_films_dir(tmp_path):
    assert P.films in P.ALL
    assert P.films(ctx(tmp_path, tmp_path / "none", tmp_path / "nofilms")) == []


def test_cli_boards_and_wall(tmp_path, monkeypatch, capsys):
    from tools.shorts.__main__ import main
    shorts, films, lib, plates, dd = world(tmp_path, shot=with_plate_key(SHOT) + BOARD)
    monkeypatch.setattr("tools.shorts.__main__.SHORTS_DIR", shorts)
    monkeypatch.setattr("tools.shorts.film.FILMS_DIR", films)
    monkeypatch.setattr("tools.shorts.plates.PLATES_ROOT", plates)
    monkeypatch.setenv("NIGHTWIRE_DESIGN_DIR", str(dd))
    monkeypatch.setattr("tools.greybox_library.build.default_out", lambda: lib)
    assert main(["boards", "pilot"]) == 0
    assert (dd / "shorts" / "pilot" / "shots" / "S01" / "board-start.png").exists()
    assert main(["boards", "pilot", "S01"]) == 0
    assert main(["wall", "night"]) == 0
    assert (dd / "shorts" / "_site" / "films" / "night" / "index.html").exists()
    assert main(["wall", "ghost"]) == 1
    assert main(["boards", "ghost"]) == 1


def test_films_producer_skips_bad_film_and_bad_slug(tmp_path, capsys):
    shorts, films, lib, plates, dd = world(tmp_path)
    (films / "ghosty.toml").write_text(FILM.replace('["pilot"]', '["ghost"]'))
    (films / "Bad_Slug.toml").write_text(FILM)
    (films / "broken.toml").write_text('title = "x"\nscenes = ["pilot"')
    c = {"shorts_dir": shorts, "films_dir": films, "design_dir": dd, "site": tmp_path / "site"}
    items = P.films(c)
    assert [i.id.split("--")[1] for i in items] == ["night"]
    err = capsys.readouterr().err
    assert "ghosty" in err and "Bad_Slug" in err and "broken" in err
