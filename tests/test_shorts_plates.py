from tools.shorts.plates import load_plates, plate_id, plate_path

TOML = '''
[[plate]]
name = "toward-shelves"
view = "from the stools toward the shelves"
source = "play.png"
[[plate]]
name = "toward-door"
view = "from behind the counter toward the noren door"
'''


def test_load_and_paths(tmp_path):
    (tmp_path / "izakaya.plates.toml").write_text(TOML)
    p = load_plates("izakaya", tmp_path)
    assert list(p) == ["toward-shelves", "toward-door"] and p["toward-door"].source == ""
    dd = tmp_path / "dd"
    assert plate_path(dd, "izakaya", p["toward-shelves"]) == dd / "izakaya" / "play.png"
    assert plate_path(dd, "izakaya", p["toward-door"]) == dd / "izakaya" / "plates" / "toward-door.png"
    assert plate_id("izakaya", "toward-door") == "plate--izakaya--toward-door"
    assert load_plates("nowhere", tmp_path) == {}
