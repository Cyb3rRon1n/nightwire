from ruleset.lifepaths import LIFEPATHS, Lifepath


def test_three_lifepaths_exist():
    assert set(LIFEPATHS.keys()) == {"corpo", "streetkid", "nomad"}


def test_every_lifepath_has_a_nonempty_description():
    for lifepath in LIFEPATHS.values():
        assert isinstance(lifepath, Lifepath)
        assert lifepath.description.strip() != ""


def test_lifepath_has_no_mechanical_fields():
    # Zero mechanical weight per spec - a Lifepath is name + description
    # only, nothing a rules engine would read as a stat bonus.
    fields = {f.name for f in Lifepath.__dataclass_fields__.values()}
    assert fields == {"name", "description"}
