import pytest

from narrator.designs import Design, load_design, load_designs, save_design, slugify, validate


def _char(**kw):
    base = dict(name="Mama Sato", kind="character", source="npc:Mama Sato", presentation="feminine",
                tags="1girl, mature female, grey hair, hair bun, warm smile, apron")
    base.update(kw)
    return Design(**base)


def _loc(**kw):
    base = dict(name="Mama Sato's izakaya", kind="location", source="place:Mama Sato's izakaya",
                tags="scenery, no humans, izakaya, paper lanterns", alt_tags="indoors, counter, bar stools",
                props=["paper lanterns", "ramen bowl"])
    base.update(kw)
    return Design(**base)


@pytest.mark.parametrize("name,slug", [("Mama Sato", "mama-sato"), ("Brother Tōru", "brother-toru"),
                                       ("Tenjō Heights", "tenjo-heights"), ("Mama Sato's izakaya", "mama-satos-izakaya"),
                                       ("Hanabira-chō", "hanabira-cho"), ("Yomi  Line", "yomi-line")])
def test_slugify(name, slug):
    assert slugify(name) == slug
    assert _char(name=name).slug == slug


def test_valid_designs_pass():
    validate(_char())
    validate(_loc())
    validate(_char(status="approved", seed=42))


@pytest.mark.parametrize("bad,message", [
    (dict(kind="vehicle"), "kind"),
    (dict(status="done"), "status"),
    (dict(name=""), "name"),
    (dict(tags=""), "tags"),
    (dict(presentation="robot"), "presentation"),
    (dict(alt_tags="indoors"), "alt_tags"),
    (dict(props=["cup"]), "props"),
    (dict(status="approved", seed=0), "seed"),
])
def test_invalid_characters_raise(bad, message):
    with pytest.raises(ValueError, match=message):
        validate(_char(**bad))


def test_location_cannot_have_presentation():
    with pytest.raises(ValueError, match="presentation"):
        validate(_loc(presentation="feminine"))


def test_round_trip_and_stable_order(tmp_path):
    d = _loc(status="approved", seed=7, palette=["#111111", "#ffcc00"], notes=["2026-10-28 draft from world card"])
    path = tmp_path / f"{d.slug}.toml"
    save_design(d, path)
    text = path.read_text()
    keys = [line.split(" = ")[0] for line in text.splitlines() if " = " in line]
    assert keys == ["name", "kind", "source", "tags", "negative", "alt_tags", "props", "status", "seed", "palette", "notes"]
    assert load_design(path) == d
    save_design(load_design(path), path)
    assert path.read_text() == text


def test_character_toml_includes_presentation_and_omits_location_fields(tmp_path):
    d = _char(negative='two mechanical arms, "quoted"')
    path = tmp_path / "x.toml"
    save_design(d, path)
    text = path.read_text()
    assert 'presentation = "feminine"' in text and "alt_tags" not in text and "props" not in text
    assert load_design(path) == d


def test_load_designs_keys_by_slug(tmp_path):
    save_design(_char(), tmp_path / "mama-sato.toml")
    save_design(_loc(), tmp_path / "mama-satos-izakaya.toml")
    assert list(load_designs(tmp_path)) == ["mama-sato", "mama-satos-izakaya"]


def test_load_design_rejects_invalid_file(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('name = "X"\nkind = "vehicle"\nsource = "npc:X"\ntags = "a"\n')
    with pytest.raises(ValueError, match="kind"):
        load_design(path)


def test_control_chars_round_trip(tmp_path):
    d = _char(notes=["line1\nline2\ttab\r\x01end"])
    save_design(d, tmp_path / "m.toml")
    assert load_design(tmp_path / "m.toml").notes == d.notes
